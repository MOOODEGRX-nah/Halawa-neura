"""Local API and web UI sharing one coordinator. Start with one worker only."""
import asyncio
import html
import importlib.util
import json
import os
import queue
import secrets
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse, FileResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import ValidationError

from src.runtime import ROOT, Settings
from src.desktop.paths import VERSION
from src.backend.schemas import ChatRequest, RouteRequest, VaultSave, ToolRequest, PendingID, TTSRequest
from src.core.neura_loop import NeuraLoop, InferenceError
from src.core.invoice_orchestrator import InvoiceOrchestrator, ProjectRequest
from src.core.vault import ConversationVault
from src.core.voice_service import VoiceService
from src.backends.residency import gpu_memory
from src.tools.safe_actions import SafeActions
from src.core.project_store import ProjectStore
from src.core.project_jobs import ProjectJobs, WorkspaceRequest
from src.core.project_preview import PreviewServer
from src.backend.project_api import attach_projects
from src.backend.skills_api import attach_skills
from src.tools.desktop_skills import DesktopSkills


def error_response(message, status, code):
    return JSONResponse({'error': {'message': message, 'type': code}}, status_code=status)


def local_token(settings):
    if settings.token:
        return settings.token
    path = settings.data_dir / '.api-token'
    settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        token = path.read_text().strip()
        if len(token) >= 32:
            path.chmod(0o600)
            return token
    except FileNotFoundError:
        pass
    token = secrets.token_urlsafe(32)
    with path.open('w', encoding='utf-8') as f:
        path.chmod(0o600)
        f.write(token)
    return token


async def run_worker(request, coordinator, callback):
    cancel = threading.Event()
    deadline = time.monotonic() + coordinator.settings.timeout_s
    task = asyncio.create_task(asyncio.to_thread(callback, cancel, deadline))
    try:
        while not task.done():
            if await request.is_disconnected():
                raise InferenceError('Client disconnected', 499, 'cancelled')
            if time.monotonic() >= deadline:
                raise InferenceError('Request deadline exceeded; cancellation requested', 504, 'timeout')
            await asyncio.wait({task}, timeout=0.05)
        return await task
    finally:
        cancel.set()
        if not task.done():
            # Native prompt evaluation can finish later; the coordinator keeps its lock.
            task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)


def create_app(settings=None, coordinator=None, actions=None, voice=None, desktop_adapter=None):
    settings = settings or Settings()
    coordinator = coordinator or NeuraLoop(settings=settings)
    actions = actions or SafeActions()
    voice = voice or VoiceService()
    token = local_token(settings)
    vault = ConversationVault(settings.data_dir)
    projects = InvoiceOrchestrator(coordinator)
    project_store = ProjectStore(settings.data_dir)
    project_jobs = ProjectJobs(project_store, coordinator)
    preview = PreviewServer(project_store)
    desktop_skills = DesktopSkills(project_store, desktop_adapter)
    started = time.monotonic()

    @asynccontextmanager
    async def lifespan(application):
        preview.start()
        yield
        await asyncio.to_thread(project_jobs.shutdown)
        await asyncio.to_thread(preview.stop)
        await asyncio.to_thread(coordinator.shutdown)
        project_store.close()

    app = FastAPI(title='Neura Local API', version=VERSION, lifespan=lifespan)
    app.state.coordinator, app.state.token = coordinator, token
    app.state.project_store, app.state.project_jobs, app.state.preview = project_store, project_jobs, preview
    attach_projects(app, project_store, project_jobs, preview)
    attach_skills(app,desktop_skills)
    app.state.desktop_skills=desktop_skills
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]'])

    @app.middleware('http')
    async def local_boundary(request, call_next):
        origin = request.headers.get('origin')
        allowed_origin = str(request.base_url).rstrip('/')
        if origin and origin != allowed_origin:
            return error_response('Open the UI from this API origin', 403, 'origin_denied')
        if request.headers.get('sec-fetch-site') == 'cross-site':
            return error_response('Cross-site requests are disabled', 403, 'origin_denied')
        private = request.method not in ('GET', 'HEAD', 'OPTIONS') or request.url.path.startswith(('/vault', '/projects', '/project-jobs', '/workspace', '/skills'))
        if private:
            supplied = request.headers.get('x-neura-token', '')
            if not secrets.compare_digest(supplied.encode(), token.encode()):
                return error_response('Missing or invalid X-Neura-Token', 403, 'authentication_required')
            size = 0
            chunks = []
            async for chunk in request.stream():
                size += len(chunk)
                if size > 26_000_000:
                    return error_response('Request exceeds 26 MB', 413, 'request_too_large')
                chunks.append(chunk)
            request._body = b''.join(chunks)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; frame-src " + (preview.origin or "'none'")
        return response

    @app.exception_handler(InferenceError)
    async def inference_error(request, exc):
        return error_response(str(exc), exc.status, exc.code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Do not echo entire image payloads or conversation bodies in errors.
        details = '; '.join('.'.join(map(str, e['loc'])) + ': ' + e['msg'] for e in exc.errors())
        return error_response(details, 422, 'invalid_request')

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error_response(str(exc.detail), exc.status_code, 'http_error')

    def tiers_snapshot():
        tiers = {}
        installed = importlib.util.find_spec('llama_cpp') is not None
        for name, info in coordinator.residency.tiers.items():
            mid = info['model_id']
            model = coordinator.residency.get_model_info(mid) or {}
            available, note = coordinator.residency.availability(mid)
            tiers[name] = {'model_id': mid, 'label': model.get('name', mid),
                           'enabled': available and installed, 'available': available,
                           'loaded': coordinator.current_model_id == mid,
                           'up': coordinator.current_model_id == mid, 'note': note,
                           'ctx': settings.n_ctx, 'port': None,
                           'vram_gb': coordinator.residency.estimate_vram_usage_gb(mid, settings.n_ctx),
                           'vram_is_estimate': True}
        return tiers

    def capabilities():
        speech = voice.capabilities()
        return {'chat': importlib.util.find_spec('llama_cpp') is not None,
                'streaming': True, 'vision': tiers_snapshot().get('vision', {}).get('enabled', False),
                'vision_validation': 'requires hardware image acceptance test',
                'vault': True, 'projects': True, 'project_validation': 'static checks only',
                'workspace': True, 'preview_origin': preview.origin,
                'tools': actions.capabilities(), 'shell': False, 'email_send': False, **speech}

    @app.get('/', response_class=HTMLResponse)
    async def index():
        page = (ROOT / 'web/index.html').read_text(encoding='utf-8')
        page = page.replace('<meta name="neura-token" content="">',
                            '<meta name="neura-token" content="' + html.escape(token, quote=True) + '">')
        return HTMLResponse(page)

    @app.get('/assets/styles.css')
    async def styles():
        return FileResponse(ROOT / 'web/styles.css', media_type='text/css')

    @app.get('/assets/workspace.js')
    async def workspace_script():
        return FileResponse(ROOT / 'web/workspace.js', media_type='text/javascript')

    @app.get('/assets/skills.js')
    async def skills_script():
        return FileResponse(ROOT / 'web/skills.js', media_type='text/javascript')

    @app.get('/assets/workspace.css')
    async def workspace_style():
        return FileResponse(ROOT / 'web/workspace.css', media_type='text/css')

    @app.get('/health')
    async def health():
        tiers = tiers_snapshot()
        daily = tiers.get('daily', {})
        status = 'ready' if daily.get('enabled') and not coordinator.last_error else 'degraded'
        return {'status': status, 'state': status.upper(), 'version': VERSION, 'instance_id': os.environ.get('NEURA_INSTANCE_ID'),
                'current_model': coordinator.current_model_id, 'phase': coordinator.phase,
                'readiness': 'loadable' if daily.get('enabled') else 'unavailable',
                'inference_verified': False, 'tiers': tiers, 'capabilities': capabilities(),
                'last_error': coordinator.last_error, 'pending': 0, 'budget_gb': coordinator.residency.total_vram_gb}

    @app.get('/stats')
    async def stats():
        try:
            import psutil
            mem = psutil.virtual_memory()
            system = {'cpu': psutil.cpu_percent(), 'ram_gb': mem.used / 1e9, 'ram_total_gb': mem.total / 1e9}
        except (ImportError, OSError):
            system = {'cpu': None, 'ram_gb': None, 'ram_total_gb': None}
        memory = gpu_memory()
        chosen=getattr(coordinator.backend,'selected_device',None)
        if coordinator.current_model_id and chosen and chosen.get('description')=='CPU':
            memory=None  # Do not attribute another application's GPU usage to CPU inference.
        if coordinator.current_model_id and chosen and chosen.get('total_bytes') and memory:
            matches=[device for device in memory.get('devices',[memory])
                     if abs(device['total_gb']*1e9-chosen['total_bytes'])/chosen['total_bytes']<.1]
            # Equal-capacity adapters cannot be safely matched by capacity alone.
            memory=matches[0] if len(matches)==1 else None
        gpu = {'available': memory is not None, 'load': None, 'vram_gb': memory['used_gb'] if memory else None,
               'vram_total_gb': memory['total_gb'] if memory else None, 'temperature': None}
        gpu['selected_device']=getattr(coordinator.backend,'selected_device',None)
        if memory:
            try:
                gpu['load'] = int((Path(memory['device']) / 'gpu_busy_percent').read_text())
            except (OSError, ValueError):
                pass
        mid = coordinator.current_model_id
        return {'current_model': mid, 'uptime_s': time.monotonic() - started,
                'phase': 'queued' if coordinator.phase == 'loading' else coordinator.phase,
                'sys': system, 'gpu': gpu, 'live': {'tokens': None, 'tps': None},
                **coordinator.metrics_snapshot(), 'uptime': time.monotonic() - started,
                'mgr': {'tiers': tiers_snapshot(), 'loading': coordinator.phase == 'loading',
                        'vram_est': coordinator.residency.estimate_vram_usage_gb(mid, settings.n_ctx) if mid else None,
                        'vram_is_estimate': True, 'state': 'READY' if not coordinator.last_error else 'DEGRADED',
                        'budget_gb': coordinator.residency.total_vram_gb,
                        'resident': [name for name,info in coordinator.residency.tiers.items() if info['model_id']==mid] if mid else []}}

    @app.post('/route')
    async def route_message(req: RouteRequest):
        if not req.text.strip():
            raise HTTPException(400, 'Empty routing input')
        tier = 'expert' if req.deep else req.tier
        if req.deep and req.tier not in (None, 'expert'):
            raise HTTPException(400, 'Conflicting deep and tier fields')
        try:
            tier, mid, reason, intent = coordinator.router.route(req.text, req.has_image, settings.n_ctx, tier, req.model)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        allowed, note = coordinator.residency.can_load(mid, settings.n_ctx, tier=tier)
        return {'tier': tier, 'model_id': mid, 'model': mid, 'reason': reason, 'intent': intent,
                'available': allowed, 'enabled': allowed, 'up': coordinator.current_model_id == mid, 'note': note}

    @app.post('/v1/chat/completions')
    async def chat_completions(req: ChatRequest, request: Request):
        messages = [m.model_dump() for m in req.messages]
        try:
            tier = req.selected_tier()
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        chosen, mid, reason, intent = coordinator.select(messages, tier, req.model)
        options = dict(tier=chosen, model=mid, max_tokens=req.max_tokens, temperature=req.temperature, top_p=req.top_p)
        if not req.stream:
            return await run_worker(request, coordinator,
                lambda cancel, deadline: coordinator.complete(messages, cancel=cancel, deadline=deadline, **options))
        cancel = threading.Event()
        deadline = time.monotonic() + settings.timeout_s
        events = queue.Queue(maxsize=32)

        def put(kind, value=None):
            while not cancel.is_set():
                try:
                    events.put((kind, value), timeout=0.05)
                    return
                except queue.Full:
                    continue

        def produce():
            try:
                for chunk in coordinator.stream(messages, cancel=cancel, deadline=deadline, **options):
                    put('data', chunk)
                put('done')
            except InferenceError as exc:
                put('error', exc)
            except Exception as exc:
                put('error', InferenceError(str(exc), 502, 'stream_failed'))

        task = asyncio.create_task(asyncio.to_thread(produce))

        async def pull():
            while True:
                if time.monotonic() >= deadline:
                    raise InferenceError('Streaming deadline exceeded', 504, 'timeout')
                if await request.is_disconnected():
                    raise InferenceError('Client disconnected', 499, 'cancelled')
                try:
                    return events.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.01)

        try:
            first = await pull()
            if first[0] == 'error':
                raise first[1]
        except BaseException:
            cancel.set()
            raise

        async def send():
            event = first
            try:
                while True:
                    kind, value = event
                    if kind == 'done':
                        yield 'data: [DONE]\n\n'
                        break
                    if kind == 'error':
                        yield 'data: ' + json.dumps({'error': {'message': str(value), 'type': value.code}}) + '\n\n'
                        break
                    yield 'data: ' + json.dumps(value, ensure_ascii=False) + '\n\n'
                    event = await pull()
            except InferenceError as exc:
                yield 'data: ' + json.dumps({'error': {'message': str(exc), 'type': exc.code}}) + '\n\n'
            finally:
                cancel.set()
        return StreamingResponse(send(), media_type='text/event-stream', headers={
            'X-Neura-Tier': chosen, 'X-Neura-Model': mid, 'X-Accel-Buffering': 'no'})

    @app.post('/projects')
    async def create_project(req: WorkspaceRequest, request: Request):
        if req.background:
            result = await asyncio.to_thread(project_jobs.create, req)
            return JSONResponse(result, status_code=202)
        result = await run_worker(request, coordinator, lambda cancel, deadline:
                                  projects.process_request(req.legacy(), cancel=cancel, deadline=deadline))
        return JSONResponse(result, status_code=201 if result['success'] else result.get('http_status', 422))

    @app.post('/vault/save')
    async def save_session(req: VaultSave):
        try:
            return vault.save(req.session, [m.model_dump() for m in req.messages])
        except ValueError as exc:
            raise HTTPException(413, str(exc)) from exc

    @app.get('/vault/sessions')
    async def sessions():
        return {'sessions': vault.list()}

    @app.get('/vault/sessions/{session}')
    async def get_session(session: str):
        try:
            return vault.get(session)
        except KeyError as exc:
            raise HTTPException(404, 'Session not found') from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.delete('/vault/sessions/{session}')
    async def delete_session(session: str):
        try:
            return vault.delete(session)
        except KeyError as exc:
            raise HTTPException(404, 'Session not found') from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post('/vault/harvest')
    async def harvest():
        raise HTTPException(501, 'Automatic knowledge extraction is not implemented; save chat sessions explicitly')

    @app.get('/skills')
    async def skills():
        description=await asyncio.to_thread(desktop_skills.describe)
        return {'skills': actions.capabilities(), 'fail_soft': True,
                'desktop_skills':description['skills'],'desktop':description['desktop'],'recent_scope':description['recent_scope']}

    @app.post('/tool/call')
    async def tool_call(req: ToolRequest):
        try:
            result = await asyncio.to_thread(actions.dispatch, req.tool, req.args)
        except ValidationError as exc:
            raise HTTPException(422, 'Invalid tool arguments') from exc
        status = result.get('status')
        return JSONResponse(result, status_code=501 if status == 'unavailable' else 502 if status == 'error' else 200)

    @app.get('/tool/pending')
    async def pending():
        return {'pending': [], 'execution_enabled': False}

    @app.post('/tool/approve')
    @app.post('/tool/deny')
    async def decide(req: PendingID):
        raise HTTPException(404, 'No such pending operation; system execution is disabled')

    @app.post('/stt')
    async def stt(request: Request):
        return await asyncio.to_thread(voice.transcribe, await request.body(), request.headers.get('x-neura-lang', 'ar'))

    @app.post('/tts')
    async def tts(req: TTSRequest):
        audio = await asyncio.to_thread(voice.synthesize, req.text, req.lang)
        return Response(audio, media_type='audio/wav')

    return app


# No models are loaded at import time. Data is created only when the app is built.
app = create_app()

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8000, workers=1, proxy_headers=False)
