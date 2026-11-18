"""Single serialized model lifecycle, shared by chat, vision and projects."""
import threading
import os
from dataclasses import replace
from pathlib import Path
import time
from collections import deque
from contextlib import contextmanager
from src.runtime import Settings
from src.engine.router import Router
from src.backends.residency import ResidencyManager
from src.backends.llama_cpp_backend import LlamaCppBackend


class InferenceError(RuntimeError):
    def __init__(self, message, status=503, code='inference_unavailable'):
        super().__init__(message)
        self.status, self.code = status, code


class ResourceBlocked(InferenceError):
    def __init__(self,message):super().__init__(message,503,'resource_blocked')


def text_and_images(messages):
    text, has_image = '', False
    for message in messages:
        content = message['content']
        if isinstance(content, list):
            has_image |= any(p.get('type') == 'image_url' for p in content)
            content = '\n'.join(p.get('text', '') for p in content if p.get('type') == 'text')
        if message['role'] == 'user':
            text = content
    return text, has_image


class NeuraLoop:
    def __init__(self, config_dir=None, models_dir=None, enable_game_mode=False, *, settings=None, backend=None):
        self.settings = settings or Settings()
        self.models_dir = self.settings.models_dir if models_dir is None else Path(models_dir).resolve()
        self.residency = ResidencyManager(config_dir or self.settings.config_dir, models_dir=self.models_dir,settings=self.settings)
        self.router = Router(self.residency)
        self.backend = backend or LlamaCppBackend()
        self.current_model_id = None
        self.lock = threading.RLock()
        self.last_error = None
        self.phase = 'idle'
        self.last_metrics = {}
        self._metrics_lock = threading.Lock()
        self.recent = deque(maxlen=20)
        self.totals = {'requests': 0, 'prompt_tokens': 0, 'output_tokens': 0, 'errors': 0, 'unknown_usage_requests': 0}
        self._closed = False
        self._maintenance = False
        # Game monitoring is opt-in. It uses the same lock and never closes a busy model.
        self.game_monitor = None
        self._monitor_stop = threading.Event()
        self._monitor_thread = None
        from src.core.resource_policy import ResourcePolicy,ProtectionConfig,read_config
        try:resource_config=read_config(self.settings.data_dir,self.settings.resource_protection)
        except Exception as e:
            resource_config=ProtectionConfig(mode='protected');self.last_error='Resource settings invalid: '+str(e)
        if enable_game_mode and resource_config.mode=='normal':resource_config=resource_config.model_copy(update={'mode':'auto'})
        self._effective_settings=self.settings;self._active_residency=self.residency;self._applied_resource_key=None;self._resource_local=threading.local();self._cpu_fallback=False
        self.protection=ResourcePolicy(self,resource_config,start=resource_config.mode!='normal')

    def _record(self, tier, model_id, start, status, usage=None):
        usage = usage or {}
        duration = time.monotonic() - start
        record = {'t': time.time(), 'tier': tier, 'model_id': model_id, 'status': status,
                  'duration': duration, 'prompt': usage.get('prompt_tokens'), 'reused': None,
                  'output': usage.get('completion_tokens'), 'prefill_tps': None, 'decode_tps': None}
        with self._metrics_lock:
            self.recent.appendleft(record)
            self.totals['requests'] += 1
            self.totals['errors'] += status == 'error'
            self.totals['prompt_tokens'] += usage.get('prompt_tokens') or 0
            self.totals['output_tokens'] += usage.get('completion_tokens') or 0
            self.totals['unknown_usage_requests'] += not bool(usage)
            self.last_metrics = {'tier': tier, 'model_id': model_id, 'latency_ms': duration * 1000,
                                 'usage': usage, 'status': status}

    def metrics_snapshot(self):
        with self._metrics_lock:
            return {'last': dict(self.last_metrics), 'recent': list(self.recent), 'totals': dict(self.totals)}

    def _on_game(self, game):
        self.protection.observe({'time':time.monotonic(),'processes':[],'games':[{'name':str(game)}]})

    def _transition_resources(self,policy):
        from src.core.resource_policy import fingerprint
        if self._closed:return False
        cfg=policy.config;desired=policy.trigger.desired
        key=fingerprint({'protected':desired,'cpu_fallback':self._cpu_fallback,'profile':{k:cfg.model_dump()[k] for k in ('protected_gpu','protected_models_dir','tier_models','physical_cpu_core_limit','generation_threads','prompt_threads','protected_cpu_nice','protected_context','memory_reserve_gb')} if desired else {'gpu':self.settings.gpu_device,'context':self.settings.n_ctx,'threads':self.settings.n_threads,'gpu_layers':self.settings.n_gpu_layers}})
        if not desired and not policy.active and self._effective_settings is self.settings and self._applied_resource_key is None:
            self._applied_resource_key=key;return True
        if policy.active==desired and key==self._applied_resource_key:return policy.blocked_reason is None
        if not self.lock.acquire(blocking=False):return False
        try:
            if policy.active==desired and key==self._applied_resource_key:return policy.blocked_reason is None
            self._unload()
            if not desired:
                policy.limits.restore()
                if policy.limits.errors:policy.state='Resource Blocked';policy.blocked_reason='لم تتأكد استعادة حدود CPU: '+'; '.join(policy.limits.errors);return False
                self._effective_settings=self.settings;self._active_residency=self.residency;self._cpu_fallback=False;policy.device=None;policy.active=False;policy.state='Normal';policy.blocked_reason=None;policy.actual_confirmation='normal policy restored; no model loaded';self._applied_resource_key=key;return True
            try:
                cpus=policy.limits.activate(cfg.physical_cpu_core_limit,cfg.protected_cpu_nice)
                from src.backends.devices import probe_devices,select_device,physical_gpus
                if not policy.primary_pci:
                    physical=physical_gpus()
                    if physical:policy.primary_pci=max(physical,key=lambda d:d['total_bytes'])['pci_id']
                device=None
                if not self._cpu_fallback:
                    if not cfg.protected_gpu:raise ValueError('اختر GPU الثانوي من إعدادات الحماية؛ لا عودة تلقائية للرئيسي')
                    before={int(p.name) for p in Path('/proc/self/task').iterdir()}
                    with policy.limits.scope() as normal_mask:
                        device=select_device(probe_devices(),cfg.protected_gpu)
                        policy.limits.capture_threads(before,normal_mask)
                    if not device.get('stable_id') or device.get('pci_id')==policy.primary_pci:raise ValueError('الجهاز المحمي غير مميز عن الرئيسي أو هويته غير مؤكدة')
                if not cfg.protected_models_dir or not Path(cfg.protected_models_dir).is_dir():raise ValueError('اختر مجلد أوزان الملف المحمي')
                self._effective_settings=replace(self.settings,models_dir=Path(cfg.protected_models_dir),n_ctx=cfg.protected_context,n_gpu_layers=0 if self._cpu_fallback else -1,gpu_device=device['stable_id'] if device else 'auto',n_threads=cfg.generation_threads,n_threads_batch=cfg.prompt_threads,memory_reserve_gb=cfg.memory_reserve_gb)
                self._active_residency=ResidencyManager(self.settings.config_dir,models_dir=cfg.protected_models_dir,settings=self._effective_settings)
                if device:self._active_residency.bound_sysfs=device['sysfs_device']
                policy.device={k:v for k,v in device.items() if k!='_pointer'} if device else {'description':'CPU — explicitly configured alternative'}
                policy.active=True;policy.state='Protected';policy.blocked_reason=None;policy.actual_confirmation='no active model; old resources unloaded; routing/CPU policy applied, inference device awaits a real load';self._applied_resource_key=key
                return True
            except Exception as e:
                if cfg.cpu_offload_fallback and not self._cpu_fallback:
                    self._cpu_fallback=True;policy.epoch+=1;policy.state='Entering Protection';return False
                policy.active=True;policy.state='Resource Blocked';policy.blocked_reason=str(e);policy.actual_confirmation=None;return False
        finally:self.lock.release()

    def resource_epoch(self):return self.protection.epoch

    def begin_job_profile(self):
        self._resource_local.job_epoch=self.protection.epoch
        return self.resource_receipt(self.protection.epoch)

    def end_job_profile(self):
        if hasattr(self._resource_local,'job_epoch'):del self._resource_local.job_epoch

    def resource_receipt(self,epoch=None):
        runtime=self._effective_settings
        return {'epoch':self.protection.epoch if epoch is None else epoch,'profile_sha256':self._applied_resource_key,'protected':self.protection.active,'model_id':self.current_model_id,'device':getattr(self.backend,'selected_device',None) if self.current_model_id else None,'context':runtime.n_ctx,'generation_threads':runtime.n_threads,'prompt_threads':runtime.n_threads_batch or runtime.n_threads,'allowed_cpu_ids':sorted(self.protection.limits.cpus) if self.protection.limits.cpus is not None else None,'cpu_fallback_explicit':self._cpu_fallback,'native_limits':getattr(self.backend,'native_limits',None)}

    def assert_resource_epoch(self,epoch):
        if epoch!=self.protection.epoch:raise InferenceError('تغيّرت سياسة الموارد؛ أُوقف الاستدلال عند حد آمن وبقيت آخر مراجعة محفوظة. لم تُعد المحاولة تلقائيًا.',409,'protection_interrupted')

    def await_resources(self,messages,tier,model,cancel,deadline,key=None):
        key=key or 'request:'+str(threading.get_native_id())
        try:
            while True:
                self._check(cancel,deadline);ready=self.protection.ensure_active()
                job_epoch=getattr(self._resource_local,'job_epoch',None)
                if job_epoch is not None:self.assert_resource_epoch(job_epoch)
                try:
                    if not ready:raise ResourceBlocked(self.protection.blocked_reason or 'انتظار حد آمن لتغيير سياسة الموارد')
                    selected=self.select(messages,tier,model)
                    return self.protection.epoch,selected
                except ResourceBlocked as e:
                    if getattr(self.lock,'_is_owned',lambda:False)():
                        raise InferenceError('تغيرت الموارد بعد بدء المهمة؛ أُوقف العمل دون حفظ جزئي: '+str(e),409,'protection_interrupted') from e
                    self.protection.note_wait(key,str(e));cancel.wait(.1)
        finally:self.protection.clear_wait(key)

    def project_resource_ready(self):
        if not self.protection.ensure_active():return False,self.protection.blocked_reason or 'انتظار انتقال سياسة الموارد'
        try:
            for tier in ('expert','coder'):self.select([{'role':'user','content':'planned project'}],tier,None)
            return True,None
        except ResourceBlocked as e:return False,str(e)
        except InferenceError:return True,None  # Ordinary model errors retain their existing failure path.

    @contextmanager
    def exclusive(self):
        if not self.lock.acquire(timeout=0.1):
            raise InferenceError('Another inference request is active', 409, 'busy')
        try:
            if self._closed:
                raise InferenceError('Coordinator is shut down')
            if self._maintenance:
                raise InferenceError('التحديث قيد التهيئة؛ أُجّل الطلب ولم يبدأ استدلال جديد.',503,'update_pending')
            yield
        finally:
            self.lock.release()

    def select(self, messages, tier=None, model=None):
        text, has_image = text_and_images(messages)
        policy=self.protection
        if policy.trigger.desired:
            if not policy.active or policy.blocked_reason:raise ResourceBlocked(policy.blocked_reason or 'الحماية قيد الانتقال؛ لا يبدأ استدلال على الرئيسي')
            intent=self.router.detect_intent(text,has_image)
            chosen=(tier.lower() if tier else ('daily' if intent.startswith('tool_') else intent))
            if has_image and chosen!='vision':raise InferenceError('Image messages require VISION',400,'invalid_selection')
            mapped=policy.config.tier_models.get(chosen)
            if not mapped or model and model!=mapped:raise ResourceBlocked('لا يوجد إسناد محمي صريح متوافق للدور '+chosen+' أو لا يطابق النموذج المطلوب')
            info=self._active_residency.get_model_info(mapped)
            if has_image and not (info or {}).get('projector'):raise ResourceBlocked('نموذج النص المحمي ليس نموذج رؤية؛ الطلب ينتظر ملفًا متوافقًا')
            allowed,note=self._active_residency.can_load(mapped,self._effective_settings.n_ctx,tier=chosen)
            if not allowed:
                if policy.config.cpu_offload_fallback and not self._cpu_fallback:
                    self._cpu_fallback=True;policy.epoch+=1;self._applied_resource_key=None
                raise ResourceBlocked(note)
            if self._cpu_fallback and self.current_model_id!=mapped:
                import psutil
                if psutil.virtual_memory().available/1e9<self._active_residency.estimate_vram_usage_gb(mapped,self._effective_settings.n_ctx):raise ResourceBlocked('ذاكرة RAM لا تكفي لبديل CPU المصرح به')
            return chosen,mapped,'explicit protected role/device profile; '+note,intent
        try:
            selected = self.router.route(text, has_image=has_image, context_length=self.settings.n_ctx,
                                         requested_tier=tier, requested_model=model)
        except ValueError as exc:
            raise InferenceError(str(exc), 400, 'invalid_selection') from exc
        allowed, note = self.residency.can_load(selected[1], self.settings.n_ctx, tier=selected[0])
        if not allowed:
            raise InferenceError(note)
        return selected

    def _unload(self):
        self.backend.unload()
        self.current_model_id = None
        self.residency.register_unload()
        if hasattr(self,'_active_residency'):self._active_residency.register_unload()
        if hasattr(self,'protection'):self.protection.actual_confirmation='owned model unloaded; no active inference'

    @contextmanager
    def owned_work(self):
        try:
            with self.protection.limits.scope() as mask:yield mask
        except OSError as e:
            if self.protection.trigger.desired:
                self.protection.blocked_reason='تعذر تأكيد حدود عامل Neura: '+str(e);self.protection.state='Resource Blocked'
                raise ResourceBlocked(self.protection.blocked_reason) from e
            raise

    def _load(self, model_id, tier):
        if self.current_model_id == model_id:
            return
        released_model = self.current_model_id is not None
        self._unload()
        runtime=self._effective_settings;residency=self._active_residency
        ok, reason = residency.can_load(model_id, runtime.n_ctx, tier=tier)
        # AMD counters may lag native buffer destruction briefly. Retain the
        # same model lock and wait only after releasing our own previous model.
        release_deadline=time.monotonic()+2
        while not ok and released_model and residency.gpu_required and time.monotonic()<release_deadline:
            time.sleep(.05)
            ok, reason=residency.can_load(model_id,runtime.n_ctx,tier=tier)
        if not ok:
            if self.protection.trigger.desired:raise ResourceBlocked(reason)
            raise InferenceError(reason)
        info = residency.get_model_info(model_id)
        load_epoch=self.protection.epoch
        self.phase = 'loading'
        try:
            before={int(p.name) for p in Path('/proc/self/task').iterdir()} if Path('/proc/self/task').exists() else set()
            with self.protection.limits.scope() as normal_mask:
                self.backend.load(str(residency.model_path(model_id)), n_ctx=runtime.n_ctx,
                                  n_gpu_layers=runtime.n_gpu_layers, n_threads=runtime.n_threads,
                                  n_threads_batch=runtime.n_threads_batch or runtime.n_threads,
                                  device_name=runtime.gpu_device,
                                  min_free_gb=residency.estimate_vram_usage_gb(model_id,runtime.n_ctx),
                                  n_batch=min(256, runtime.n_ctx),
                                  projector=residency.models_dir / info['projector'] if info.get('projector') else None,
                                  reasoning_end_token=info.get('reasoning_end_token'))
                self.protection.limits.capture_threads(before,normal_mask)
                if self.protection.active and self.protection.limits.errors:raise OSError('Protected worker placement failed')
        except Exception as exc:
            self.backend.unload()
            if self.protection.trigger.desired:
                self.protection.state='Resource Blocked';self.protection.blocked_reason=f'تعذر تحميل النموذج المحمي ({model_id}): {exc}'
                raise ResourceBlocked(self.protection.blocked_reason) from exc
            raise InferenceError(f'Model load failed ({model_id}): {exc}') from exc
        if not self.protection.active:
            selected=getattr(self.backend,'selected_device',None) or {}
            if selected.get('pci_id'):self.protection.primary_pci=selected['pci_id']
        self.current_model_id = model_id
        residency.register_load(model_id)
        self.protection.actual_confirmation={'model_id':model_id,'device':getattr(self.backend,'selected_device',None),'context':runtime.n_ctx,'generation_threads':runtime.n_threads,'prompt_threads':runtime.n_threads_batch or runtime.n_threads}
        if self.protection.active and self.protection.trigger.desired and load_epoch==self.protection.epoch:self.protection.state='Protected';self.protection.blocked_reason=None

    def measure_messages(self,messages,*,tier='coder',max_tokens=1024,cancel,deadline,**options):
        epoch,_=self.await_resources(messages,tier,None,cancel,deadline)
        with self.exclusive(),self.owned_work():
            self._check(cancel,deadline)
            self.assert_resource_epoch(epoch)
            chosen,model_id,_,_=self.select(messages,tier,None)
            try:
                self._load(model_id,chosen)
                if not hasattr(self.backend,'measure_messages'):
                    raise InferenceError('المحرك لا يوفّر عدّ رموز القالب؛ لا يمكن تقسيم التعديل بأمان',422,'token_measurement_unavailable')
                result=self.backend.measure_messages(messages,max_tokens=max_tokens,**options)
                self.assert_resource_epoch(epoch)
                return result
            finally:
                # _load leaves 'loading'; without this a measured-then-cancelled edit reported 'queued' forever.
                self.phase='idle'

    def _options(self, cancel, deadline, options,epoch=None):
        def stop(*_):
            return cancel.is_set() or time.monotonic() >= deadline or epoch is not None and epoch!=self.protection.epoch
        # llama_cpp accepts a list subclass, but a callable list also works for injected backends.
        class StopCriteria(list):
            def __call__(self, *args):
                return any(check(*args) for check in self)
        return {**options, '_neura_deadline':deadline, 'stopping_criteria': StopCriteria([stop])}

    @staticmethod
    def _check(cancel, deadline):
        if time.monotonic() >= deadline:
            raise InferenceError('Inference deadline exceeded', 504, 'timeout')
        if cancel.is_set():
            raise InferenceError('Request cancelled', 499, 'cancelled')

    def complete(self, messages, *, tier=None, model=None, cancel=None, deadline=None, **options):
        cancel = cancel or threading.Event()
        deadline = deadline or time.monotonic() + self.settings.timeout_s
        epoch,_=self.await_resources(messages,tier,model,cancel,deadline)
        with self.exclusive(),self.owned_work():
            start = time.monotonic()
            chosen_tier, model_id, status, usage = tier, model, 'error', None
            try:
                self._check(cancel, deadline)
                self.assert_resource_epoch(epoch)
                selected = self.select(messages, tier, model)
                chosen_tier, model_id, reason, intent = selected
                self._load(model_id, chosen_tier)
                self._check(cancel, deadline)
                self.assert_resource_epoch(epoch)
                self.phase = 'generating'
                result = self.backend.generate(messages=messages, **self._options(cancel, deadline, options,epoch))
                self._check(cancel, deadline)
                self.assert_resource_epoch(epoch)
                choice = result['choices'][0]
                text = choice.get('message', {}).get('content') or ''
                if not text.strip():
                    raise InferenceError('Model returned an empty completion', 502, 'empty_completion')
                result.update(model=model_id, tier=chosen_tier, reason=reason, intent=intent)
                result['resource_profile']=self.resource_receipt(epoch)
                usage = result.get('usage', {})
                status = 'done'
                self.last_error = None
                return result
            except InferenceError as exc:
                self.last_error = str(exc)
                status = 'cancelled' if exc.code == 'cancelled' else 'error'
                raise
            except Exception as exc:
                self.last_error = str(exc)
                http_status = 413 if 'context' in str(exc).lower() else 502
                raise InferenceError(str(exc), http_status, 'generation_failed') from exc
            finally:
                self._record(chosen_tier, model_id, start, status, usage)
                self.phase = 'idle'

    def stream(self, messages, *, tier=None, model=None, cancel=None, deadline=None, **options):
        cancel = cancel or threading.Event()
        deadline = deadline or time.monotonic() + self.settings.timeout_s
        epoch,_=self.await_resources(messages,tier,model,cancel,deadline)
        with self.exclusive(),self.owned_work():
            start = time.monotonic()
            chosen_tier, model_id, status = tier, model, 'cancelled'
            iterator = None
            try:
                self._check(cancel, deadline)
                self.assert_resource_epoch(epoch)
                chosen_tier, model_id, reason, intent = self.select(messages, tier, model)
                self._load(model_id, chosen_tier)
                self._check(cancel, deadline)
                self.assert_resource_epoch(epoch)
                self.phase = 'generating'
                iterator = self.backend.generate(messages=messages, stream=True,
                                                  **self._options(cancel, deadline, options,epoch))
                any_text = False
                for chunk in iterator:
                    self._check(cancel, deadline)
                    self.assert_resource_epoch(epoch)
                    for choice in chunk.get('choices', []):
                        any_text |= bool((choice.get('delta', {}).get('content') or '').strip())
                    chunk['model'] = model_id
                    chunk['tier'] = chosen_tier
                    chunk['resource_profile']=self.resource_receipt(epoch)
                    yield chunk
                self._check(cancel, deadline)
                self.assert_resource_epoch(epoch)
                if not any_text:
                    raise InferenceError('Model returned an empty stream', 502, 'empty_completion')
                self.last_error = None
                status = 'done'
            except InferenceError as exc:
                self.last_error = str(exc)
                status = 'cancelled' if exc.code == 'cancelled' else 'error'
                raise
            except Exception as exc:
                self.last_error = str(exc)
                status = 'error'
                raise InferenceError(str(exc), 502, 'generation_failed') from exc
            finally:
                self._record(chosen_tier, model_id, start, status)
                if iterator is not None and hasattr(iterator, 'close'):
                    iterator.close()
                self.phase = 'idle'

    def process(self, user_input, has_image=False, max_tokens=200, **kwargs):
        if has_image:
            raise InferenceError('Pass image content in structured messages', 400)
        result = self.complete([{'role': 'user', 'content': user_input}], max_tokens=max_tokens, **kwargs)
        return {'action': 'generate', 'tier': result['tier'], 'model_used': result['model'],
                'reason': result['reason'], 'response': result['choices'][0]['message']['content'],
                'usage': result.get('usage', {}), 'finish_reason': result['choices'][0].get('finish_reason')}

    def shutdown(self):
        self._monitor_stop.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2)
        with self.lock:
            self._unload()
            self.protection.shutdown()
            self._closed = True
