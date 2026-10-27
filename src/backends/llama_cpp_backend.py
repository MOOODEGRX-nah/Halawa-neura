"""Chat-template inference. llama_cpp is optional until a model is requested."""


class LlamaCppBackend:
    def __init__(self):
        self.model = None
        self.model_path = None
        self.handler = None

    def load(self, model_path, n_gpu_layers=-1, n_ctx=4096, projector=None, reasoning_end_token=None, **kwargs):
        if self.model is not None:
            raise RuntimeError('Unload the previous model first')
        from llama_cpp import Llama, StoppingCriteriaList, llama_supports_gpu_offload
        if n_gpu_layers != 0 and not llama_supports_gpu_offload():
            raise RuntimeError("GPU offload unavailable; set NEURA_N_GPU_LAYERS=0 for explicit CPU inference")
        class CancellableLlama(Llama):
            neura_criteria = None
            def generate(self, *args, stopping_criteria=None, **kwargs):
                criteria = list(stopping_criteria or []) + list(self.neura_criteria or [])
                return super().generate(*args, stopping_criteria=StoppingCriteriaList(criteria), **kwargs)
        handler = None
        try:
            if projector:
                from llama_cpp.llama_chat_format import MTMDChatHandler
                handler = MTMDChatHandler(clip_model_path=str(projector), verbose=False, use_gpu=n_gpu_layers != 0)
                kwargs['chat_handler'] = handler
            model = CancellableLlama(model_path=str(model_path), n_gpu_layers=n_gpu_layers,
                          n_ctx=n_ctx, verbose=False, split_mode=0, main_gpu=0, **kwargs)
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
        result = self.model.create_chat_completion(messages=messages, stream=stream, **kwargs)
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
