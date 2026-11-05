"""Chat-template inference. llama_cpp is optional until a model is requested."""


class LlamaCppBackend:
    def __init__(self):
        self.model = None
        self.model_path = None
        self.handler = None

    def load(self, model_path, n_gpu_layers=-1, n_ctx=4096, projector=None, reasoning_end_token=None,
             device_name='auto', min_free_gb=0, **kwargs):
        if self.model is not None:
            raise RuntimeError('Unload the previous model first')
        from llama_cpp import Llama, StoppingCriteriaList, llama_supports_gpu_offload
        if n_gpu_layers != 0 and not llama_supports_gpu_offload():
            raise RuntimeError("GPU offload unavailable; set NEURA_N_GPU_LAYERS=0 for explicit CPU inference")
        selected=None
        if n_gpu_layers!=0:
            from src.backends.devices import probe_devices,select_device
            selected=select_device(probe_devices(),device_name,min_free_gb)
        self.selected_device={k:v for k,v in selected.items() if k!='_pointer'} if selected else {'description':'CPU'}
        class CancellableLlama(Llama):
            neura_criteria = None
            neura_token_metrics = None
            def generate(self, tokens, *args, stopping_criteria=None, **kwargs):
                criteria = list(stopping_criteria or []) + list(self.neura_criteria or [])
                metrics=self.neura_token_metrics
                if metrics is not None:
                    metrics.update(prompt_tokens=len(tokens),context_size=self.n_ctx(),
                        effective_output_limit=min(metrics['requested_output_limit'],max(0,self.n_ctx()-len(tokens))),
                        completion_tokens=0,measurement='native prompt token IDs and yielded non-EOG token IDs')
                for token in super().generate(tokens,*args,stopping_criteria=StoppingCriteriaList(criteria),**kwargs):
                    if metrics is not None and not __import__('llama_cpp').llama_vocab_is_eog(self._model.vocab,token):metrics['completion_tokens']+=1
                    yield token
        handler = None
        try:
            if projector:
                from llama_cpp.llama_chat_format import MTMDChatHandler
                class SelectedMTMD(MTMDChatHandler):
                    def _init_mtmd_context(self, llama_model):
                        if self.mtmd_ctx is not None:return
                        params=self._mtmd_cpp.mtmd_context_params_default()
                        params.use_gpu=selected is not None
                        params.device=selected['_pointer'] if selected else None
                        params.print_timings=False
                        params.n_threads=llama_model.n_threads
                        params.flash_attn_type=llama_model.context_params.flash_attn_type
                        self.mtmd_ctx=self._mtmd_cpp.mtmd_init_from_file(self.clip_model_path.encode(),llama_model.model,params)
                        if not self.mtmd_ctx:raise ValueError('تعذر تحميل معالج الصورة على الجهاز المختار')
                        def cleanup():
                            if self.mtmd_ctx:
                                self._mtmd_cpp.mtmd_free(self.mtmd_ctx);self.mtmd_ctx=None
                        llama_model._stack.callback(cleanup)
                        if not self._mtmd_cpp.mtmd_support_vision(self.mtmd_ctx):raise ValueError('معالج الصورة لا يدعم الرؤية')
                handler = SelectedMTMD(clip_model_path=str(projector), verbose=False, use_gpu=n_gpu_layers != 0)
                kwargs['chat_handler'] = handler
            model = CancellableLlama(model_path=str(model_path), n_gpu_layers=n_gpu_layers,
                          n_ctx=n_ctx, verbose=False, split_mode=0, main_gpu=selected['gpu_index'] if selected else 0, **kwargs)
            if not projector and not model.metadata.get('tokenizer.chat_template'):
                model.close()
                raise ValueError('GGUF has no chat template; configure a verified handler first')
        except BaseException:
            if handler and hasattr(handler, 'close'):
                handler.close()
            raise
        self.reasoning_end_token = reasoning_end_token
        self.model, self.handler = model, handler
        self.model_path = str(model_path)

    def generate(self, prompt=None, *, messages=None, stream=False, **kwargs):
        if self.model is None:
            raise RuntimeError('Model not loaded')
        if messages is None:
            messages = [{'role': 'user', 'content': prompt}]
        self.model.neura_criteria = kwargs.pop('stopping_criteria', None)
        import time
        deadline=kwargs.pop('_neura_deadline',None)
        self.last_metrics={'requested_output_limit':kwargs.get('max_tokens') or self.model.n_ctx(),
            'deadline_monotonic':deadline,'deadline_remaining_s':max(0,deadline-time.monotonic()) if deadline else None}
        self.model.neura_token_metrics=self.last_metrics
        result = self.model.create_chat_completion(messages=messages, stream=stream, **kwargs)
        if not stream:result['neura_token_metrics']=dict(self.last_metrics)
        else:result=self._measured_stream(result)
        marker = getattr(self, 'reasoning_end_token', None)
        if not marker:
            return result
        if not stream:
            message = result['choices'][0]['message']
            raw = message.get('content') or ''
            if marker in raw:
                reasoning, _, answer = raw.partition(marker)
                message['content'] = answer.lstrip()
                message['reasoning_content'] = reasoning
            return result
        return self._answer_stream(result, marker)

    def _measured_stream(self,iterator):
        try:
            for chunk in iterator:
                if any(c.get('finish_reason') for c in chunk.get('choices',[])):chunk['neura_token_metrics']=dict(self.last_metrics)
                yield chunk
        finally:
            if hasattr(iterator,'close'):iterator.close()

    def measure_messages(self,messages,max_tokens=1024,**options):
        """Use the installed chat handler/tokenizer; abort before native generation.

        Supported GGUF handlers pass the final special-token-inclusive ID list to
        create_completion. Unsupported handler shapes fail, never estimate chars.
        Caller owns the coordinator lock while temporarily intercepting this call.
        """
        if self.model is None:raise RuntimeError('Model not loaded')
        class Measured(Exception):pass
        result={}
        had_override='create_completion' in vars(self.model)
        previous_override=vars(self.model).get('create_completion')
        def capture(*args,**kwargs):
            prompt=kwargs.get('prompt',args[0] if args else None)
            if not isinstance(prompt,list):raise ValueError('Handler does not expose final prompt token IDs')
            count=len(prompt);ctx=self.model.n_ctx()
            result.update(prompt_tokens=count,context_size=ctx,requested_output_limit=max_tokens,
                effective_output_limit=max(0,min(max_tokens,ctx-count)),measurement='installed formatter final token IDs')
            raise Measured()
        self.model.create_completion=capture
        try:
            try:self.model.create_chat_completion(messages=messages,stream=False,max_tokens=max_tokens,**options)
            except Measured:pass
            if not result:raise ValueError('Handler token measurement unavailable')
            return result
        finally:
            if had_override:self.model.create_completion=previous_override
            else:del self.model.create_completion

    @staticmethod
    def _answer_stream(iterator, marker):
        buffered = ''
        found = False
        try:
            for chunk in iterator:
                for choice in chunk.get('choices', []):
                    delta = choice.get('delta', {})
                    if found:
                        continue
                    buffered += delta.pop('content', '') or ''
                    if marker in buffered:
                        _, _, answer = buffered.partition(marker)
                        delta['content'] = answer.lstrip()
                        buffered = ''
                        found = True
                    elif choice.get('finish_reason') is not None:
                        delta['content'] = buffered
                        buffered = ''
                yield chunk
        finally:
            if hasattr(iterator, 'close'):
                iterator.close()

    def health_check(self):
        return {'status': 'loaded' if self.model else 'unloaded', 'model_path': self.model_path,
                'selected_device':getattr(self,'selected_device',None),
                'backend': 'llama-cpp-python',
                'chat_template': 'mtmd' if self.handler else 'gguf' if self.model else None}

    def unload(self):
        if self.model is not None:
            self.model.close()
            self.model = None
            self.model_path = None
        if self.handler is not None:
            if hasattr(self.handler, 'close'):
                self.handler.close()
            self.handler = None
