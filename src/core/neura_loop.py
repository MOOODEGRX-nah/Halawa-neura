"""Single serialized model lifecycle, shared by chat, vision and projects."""
import threading
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
        # Game monitoring is opt-in. It uses the same lock and never closes a busy model.
        self.game_monitor = None
        self._monitor_stop = threading.Event()
        self._monitor_thread = None
        if enable_game_mode:
            from src.core.game_monitor import GameMonitor
            self.game_monitor = GameMonitor()
            self._monitor_thread = threading.Thread(target=self.game_monitor.monitor_loop,
                kwargs={'on_game_start': self._on_game, 'stop_event': self._monitor_stop}, daemon=True)
            self._monitor_thread.start()

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
        if self.lock.acquire(blocking=False):
            try:
                self._unload()
            finally:
                self.lock.release()

    @contextmanager
    def exclusive(self):
        if not self.lock.acquire(timeout=0.1):
            raise InferenceError('Another inference request is active', 409, 'busy')
        try:
            if self._closed:
                raise InferenceError('Coordinator is shut down')
            yield
        finally:
            self.lock.release()

    def select(self, messages, tier=None, model=None):
        text, has_image = text_and_images(messages)
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

    def _load(self, model_id, tier):
        if self.current_model_id == model_id:
            return
        released_model = self.current_model_id is not None
        self._unload()
        ok, reason = self.residency.can_load(model_id, self.settings.n_ctx, tier=tier)
        # AMD counters may lag native buffer destruction briefly. Retain the
        # same model lock and wait only after releasing our own previous model.
        release_deadline=time.monotonic()+2
        while not ok and released_model and self.residency.gpu_required and time.monotonic()<release_deadline:
            time.sleep(.05)
            ok, reason=self.residency.can_load(model_id,self.settings.n_ctx,tier=tier)
        if not ok:
            raise InferenceError(reason)
        info = self.residency.get_model_info(model_id)
        self.phase = 'loading'
        try:
            self.backend.load(str(self.residency.model_path(model_id)), n_ctx=self.settings.n_ctx,
                              n_gpu_layers=self.settings.n_gpu_layers, n_threads=self.settings.n_threads,
                              device_name=self.settings.gpu_device,
                              min_free_gb=self.residency.estimate_vram_usage_gb(model_id,self.settings.n_ctx),
                              n_batch=min(256, self.settings.n_ctx),
                              projector=self.models_dir / info['projector'] if info.get('projector') else None,
                              reasoning_end_token=info.get('reasoning_end_token'))
        except Exception as exc:
            raise InferenceError(f'Model load failed ({model_id}): {exc}') from exc
        self.current_model_id = model_id
        self.residency.register_load(model_id)

    def _options(self, cancel, deadline, options):
        def stop(*_):
            return cancel.is_set() or time.monotonic() >= deadline
        # llama_cpp accepts a list subclass, but a callable list also works for injected backends.
        class StopCriteria(list):
            def __call__(self, *args):
                return any(check(*args) for check in self)
        return {**options, 'stopping_criteria': StopCriteria([stop])}

    @staticmethod
    def _check(cancel, deadline):
        if time.monotonic() >= deadline:
            raise InferenceError('Inference deadline exceeded', 504, 'timeout')
        if cancel.is_set():
            raise InferenceError('Request cancelled', 499, 'cancelled')

    def complete(self, messages, *, tier=None, model=None, cancel=None, deadline=None, **options):
        cancel = cancel or threading.Event()
        deadline = deadline or time.monotonic() + self.settings.timeout_s
        with self.exclusive():
            start = time.monotonic()
            chosen_tier, model_id, status, usage = tier, model, 'error', None
            try:
                self._check(cancel, deadline)
                selected = self.select(messages, tier, model)
                chosen_tier, model_id, reason, intent = selected
                self._load(model_id, chosen_tier)
                self._check(cancel, deadline)
                self.phase = 'generating'
                result = self.backend.generate(messages=messages, **self._options(cancel, deadline, options))
                self._check(cancel, deadline)
                choice = result['choices'][0]
                text = choice.get('message', {}).get('content') or ''
                if not text.strip():
                    raise InferenceError('Model returned an empty completion', 502, 'empty_completion')
                result.update(model=model_id, tier=chosen_tier, reason=reason, intent=intent)
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
        with self.exclusive():
            start = time.monotonic()
            chosen_tier, model_id, status = tier, model, 'cancelled'
            iterator = None
            try:
                self._check(cancel, deadline)
                chosen_tier, model_id, reason, intent = self.select(messages, tier, model)
                self._load(model_id, chosen_tier)
                self._check(cancel, deadline)
                self.phase = 'generating'
                iterator = self.backend.generate(messages=messages, stream=True,
                                                  **self._options(cancel, deadline, options))
                any_text = False
                for chunk in iterator:
                    self._check(cancel, deadline)
                    for choice in chunk.get('choices', []):
                        any_text |= bool((choice.get('delta', {}).get('content') or '').strip())
                    chunk['model'] = model_id
                    yield chunk
                self._check(cancel, deadline)
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
            self._closed = True
