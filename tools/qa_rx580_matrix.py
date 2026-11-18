"""Protected RX 580 case matrix (isolated QA profile, real local inference, explicit Protected).

Each case declares its expectation before it runs and records what actually happened: model,
device (PCI), native limits, CPU IDs, timings, job states, blocked reasons and files. A sampler
records both GPUs plus the backend's DRM clients for the whole run, so any use of the primary
(gaming) GPU by Neura would be visible. Nothing here closes, launches or touches user apps.
"""
import argparse, base64, copy, glob, json, os, subprocess, sys, threading, time, urllib.error, urllib.request, uuid
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--out', type=Path, required=True)
p.add_argument('--resource-config', type=Path, required=True)
p.add_argument('--image', type=Path, required=True)
p.add_argument('--big-models-dir', default='/opt/neura-ai/models')
p.add_argument('--only', default='', help='comma-separated case numbers to run')
a = p.parse_args(); out = a.out.resolve(); out.mkdir(parents=True, exist_ok=True)
if (out / 'matrix.json').exists(): raise SystemExit('Refusing to overwrite an existing run')
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'tools'))
profile = out / 'profile'
os.environ.update(NEURA_SETTINGS_DIR=str(profile / 'config'), NEURA_DATA_DIR=str(profile / 'data'), NEURA_STATE_DIR=str(profile / 'state'), NEURA_TIMEOUT_S='600',
                  NEURA_QA_RUN_ROOT=str(out), NEURA_QA_RUN_ID=out.name, NEURA_QA_REAL_TRACE=str(out / 'artifacts/model-traces'), NEURA_QA_TARGET_KIND='source checkout')
from verification.live import foreign_instances
if foreign_instances(): raise SystemExit('A Neura backend is already running; real QA refused')
from src.desktop.paths import DesktopSettings
from src.desktop.service import BackendService
from src.core.resource_policy import ProtectionConfig, save_config
from qa_game_mode import fdinfo, affinity
base_config = ProtectionConfig.model_validate_json(a.resource_config.read_text())
settings = DesktopSettings(); save_config(profile / 'data', base_config)
settings.values.update(models_dir='/opt/neura-ai/models', n_gpu_layers=-1, gpu_device='AMD Radeon RX 9060 XT (RADV GFX1200)', n_ctx=4096, dedicated_coder=True, check_updates=False); settings.save()
profile.mkdir(parents=True, exist_ok=True); (profile / '.neura-verification-profile').write_text(json.dumps({'run_id': out.name}))
fixture = ROOT / 'tests/fixtures/real_backend_trace.py'
service = BackendService(settings, popen=lambda command, **opts: subprocess.Popen([command[0], '-B', str(fixture), '--port', command[-1]], **opts))
service.start()
end = time.monotonic() + 60
while not service.health() and time.monotonic() < end: time.sleep(.2)
if not service.health(): raise SystemExit('backend not healthy')
TOKEN = (profile / 'data/.api-token').read_text().strip(); PID = service.process.pid
traces = out / 'artifacts/model-traces'; lifecycle = out / 'artifacts/model-lifecycle.jsonl'


def api(path, body=None, timeout=30, method=None):
    """Like a browser abort: on timeout the TCP connection is closed so the server sees the disconnect."""
    import http.client
    from urllib.parse import urlsplit
    u = urlsplit(service.url); conn = http.client.HTTPConnection(u.hostname, u.port, timeout=timeout)
    try:
        payload = None if body is None else json.dumps(body).encode()
        conn.request(method or ('POST' if payload is not None else 'GET'), path, body=payload, headers={'X-Neura-Token': TOKEN, 'Content-Type': 'application/json'})
        r = conn.getresponse(); raw = r.read(); ctype = r.getheader('Content-Type', '')
        try: data = json.loads(raw) if 'json' in ctype else raw.decode(errors='replace')
        except ValueError: data = raw.decode(errors='replace')
        return r.status, data
    except Exception as e:
        return None, type(e).__name__ + ': ' + str(e)[:200]
    finally:
        conn.close()


stop = threading.Event()
def sampler():
    cards = {os.path.basename(os.path.realpath(d + '/device')): d + '/device' for d in glob.glob('/sys/class/drm/card[0-9]')}
    with (out / 'monitor.jsonl').open('a') as log:
        while not stop.is_set():
            row = {'t': time.time(), 'gpu': {}}
            for pci, path in cards.items():
                try: row['gpu'][pci] = {'busy': int(open(path + '/gpu_busy_percent').read()), 'vram': int(open(path + '/mem_info_vram_used').read())}
                except OSError: pass
            row['backend_fdinfo'] = fdinfo(PID); log.write(json.dumps(row) + '\n'); log.flush(); stop.wait(.5)
threading.Thread(target=sampler, daemon=True).start()


def new_traces(before):
    rows = []
    for name in sorted(set(os.listdir(traces)) - before) if traces.is_dir() else []:
        t = json.loads((traces / name).read_text()); rp = t.get('resource_profile') or {}
        rows.append({'model': t['model_id'], 'device': (t.get('device') or {}).get('pci_id'), 'protected': rp.get('protected'), 'native_limits': rp.get('native_limits'),
                     'allowed_cpu_ids': rp.get('allowed_cpu_ids'), 'projector': t.get('projector'), 'finish': t.get('finish_reason'),
                     'seconds': round((t.get('finished_at') or t['started_at']) - t['started_at'], 2), 'usage': t.get('usage')})
    return rows


def snapshot_traces(): return set(os.listdir(traces)) if traces.is_dir() else set()


def rid(): return 'r_' + str(int(time.time() * 1000)) + '_' + uuid.uuid4().hex


def wait_job(job_id, seconds=600):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        code, job = api('/project-jobs/' + job_id)
        if code == 200 and job['state'] in ('completed', 'failed', 'cancelled'): return job
        time.sleep(.5)
    return api('/project-jobs/' + job_id)[1]


results = []
def case(name, expected, fn):
    if a.only and name.split()[0] not in a.only.split(','): return
    before = snapshot_traces(); started = time.time(); print('CASE', name, flush=True)
    try: observed = fn()
    except Exception as e: observed = {'exception': type(e).__name__ + ': ' + str(e)[:300]}
    observed['model_calls'] = new_traces(before); observed['seconds'] = round(time.time() - started, 2)
    observed['resources'] = {k: v for k, v in (api('/resources')[1] or {}).items() if k in ('configured_mode', 'state', 'active_protected', 'blocked_reason', 'queued', 'target_device')} if True else None
    calls = observed['model_calls']
    observed['all_calls_on_rx580'] = all(c['device'] == '0000:07:00.0' for c in calls) if calls else None
    results.append({'case': name, 'expected': expected, 'observed': observed})
    (out / 'matrix.json').write_text(json.dumps(results, ensure_ascii=False, indent=1, default=str))
    print('  ->', json.dumps({k: observed.get(k) for k in ('verdict', 'all_calls_on_rx580', 'seconds')}, ensure_ascii=False), flush=True)


def chat(text, tier, stream=False, timeout=180, extra=None):
    body = {'messages': [{'role': 'user', 'content': text}], 'tier': tier, 'max_tokens': 48, 'temperature': 0.2, 'stream': stream}
    if extra: body.update(extra)
    return api('/v1/chat/completions', body, timeout=timeout)


def c_chat():
    code, r = chat('ما عاصمة فرنسا؟ أجب بكلمة واحدة.', 'daily')
    text = (r or {}).get('choices', [{}])[0].get('message', {}).get('content') if isinstance(r, dict) else None
    return {'http': code, 'answer': text, 'verdict': 'pass' if code == 200 and text else 'fail'}


def c_stream():
    code, raw = chat('اكتب كلمة: مرحبا', 'daily', stream=True)
    pieces = [json.loads(l[6:]) for l in (raw or '').splitlines() if l.startswith('data: {')] if isinstance(raw, str) else []
    text = ''.join(c['choices'][0].get('delta', {}).get('content', '') for c in pieces if c.get('choices'))
    return {'http': code, 'chunks': len(pieces), 'answer': text[:120], 'done': isinstance(raw, str) and '[DONE]' in raw, 'verdict': 'pass' if code == 200 and text else 'fail'}


def c_tiers():
    seen = {}
    for tier in ('expert', 'coder', 'fast'):
        code, r = chat('أجب بكلمة: نعم', tier); seen[tier] = {'http': code, 'model': (r or {}).get('model') if isinstance(r, dict) else None}
    return {'tiers': seen, 'verdict': 'pass' if all(v['http'] == 200 and v['model'] == 'qwen2.5-coder-7b-q4' for v in seen.values()) else 'fail'}


def c_vision():
    data = base64.b64encode(a.image.read_bytes()).decode()
    body = {'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': 'ما اللون على اليسار؟'}, {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + data}}]}], 'tier': 'vision', 'max_tokens': 16}
    code, r = api('/v1/chat/completions', body, timeout=25)
    res = api('/resources')[1] or {}
    loads = [json.loads(l) for l in lifecycle.read_text().splitlines()] if lifecycle.exists() else []
    vision_loads = [e for e in loads if e['kind'] == 'load_start' and 'VL' in str(e.get('path'))]
    return {'http': code, 'response': str(r)[:240], 'blocked_reason': res.get('blocked_reason'), 'queued': res.get('queued'), 'vision_model_loaded': bool(vision_loads),
            'verdict': 'pass' if code != 200 and not vision_loads else 'fail', 'note': 'expected: no text-only answer and no vision load on the primary GPU while Protected'}


def dispatch(text, session, active=None):
    body = {'text': text, 'request_id': rid(), 'session_id': session}
    if active: body['active_project_id'] = active
    return api('/chat/dispatch', body, timeout=60)


def c_create(text):
    def run():
        session = 'mx-' + uuid.uuid4().hex[:8]; code, r = dispatch(text, session)
        job_id = ((r or {}).get('job') or {}).get('job_id') if isinstance(r, dict) else None
        if not job_id: return {'http': code, 'reply': str(r)[:300], 'verdict': 'fail'}
        job = wait_job(job_id); project = api('/projects/' + job['project_id'])[1]
        stages = [s['stage'] for s in job.get('stage_results', [])]
        ok = job['state'] == 'completed' and 'planning' in stages and stages.index('planning') < stages.index('generating')
        visible = None
        if ok and 'index.html' in [f['path'] for f in project.get('files', [])]:
            import re as _re
            html = (api('/projects/' + job['project_id'] + '/file?path=index.html')[1] or {}).get('content', '')
            visible = ' '.join(_re.sub(r'<(script|style|title|head)\b.*?</\1\s*>|<[^>]+>', ' ', html, flags=_re.S | _re.I).split())
            ok = ok and 'مرحبا' in visible
        return {'visible_text': visible[:200] if visible else visible, 'session': session, 'job': job_id, 'state': job['state'], 'error': job.get('error'), 'project_id': job['project_id'], 'revision': project.get('project_revision'),
                'files': [f['path'] for f in project.get('files', [])], 'planning_first': 'planning' in stages, 'verdict': 'pass' if ok else 'fail'}
    return run


created = {}
def c_edit():
    web = created.get('web') or {}
    if not web.get('project_id') or web.get('verdict') != 'pass': return {'verdict': 'skipped', 'reason': 'web create did not pass'}
    before_rev = web['revision']; before_files = {f: api('/projects/' + web['project_id'] + '/file?path=' + f)[1].get('sha256') for f in web['files']}
    code, r = dispatch('غيّر العنوان إلى «أهلًا وسهلًا»', web['session'], web['project_id'])
    job_id = ((r or {}).get('job') or {}).get('job_id') if isinstance(r, dict) else None
    if not job_id: return {'http': code, 'reply': str(r)[:300], 'verdict': 'fail'}
    job = wait_job(job_id); project = api('/projects/' + web['project_id'])[1]
    after_files = {f['path']: f['sha256'] for f in project.get('files', [])}
    if job['state'] == 'completed': ok = project['project_revision'] == before_rev + 1
    else: ok = project['project_revision'] == before_rev and after_files == before_files
    return {'state': job['state'], 'error': job.get('error'), 'revision': [before_rev, project['project_revision']], 'previous_files_intact_if_failed': after_files == before_files,
            'verdict': 'pass' if ok else 'fail', 'note': 'pass = saved exactly one revision, or failed with the previous revision and hashes intact'}


def c_cancel():
    code, r = dispatch('برمج سكربت Python باسم counter.py يعد من 1 إلى 5 دون أي اعتماد خارجي', 'mx-cancel-' + uuid.uuid4().hex[:6])
    job_id = ((r or {}).get('job') or {}).get('job_id') if isinstance(r, dict) else None
    if not job_id: return {'http': code, 'reply': str(r)[:200], 'verdict': 'fail'}
    end = time.monotonic() + 60
    while time.monotonic() < end and api('/project-jobs/' + job_id)[1]['state'] not in ('planning', 'generating', 'completed', 'failed'): time.sleep(.2)
    seen = api('/project-jobs/' + job_id)[1]['state']; c2, _ = api('/project-jobs/' + job_id + '/cancel', {}, method='POST')
    job = wait_job(job_id); project = api('/projects/' + job['project_id'])[1]
    return {'state_when_cancelled': seen, 'cancel_http': c2, 'final': job['state'], 'files': [f['path'] for f in project.get('files', [])],
            'verdict': 'pass' if job['state'] == 'cancelled' and not project.get('files') else ('inconclusive' if seen in ('completed', 'failed') else 'fail')}


def c_queue():
    ids, refused = [], []
    for i in range(7):
        code, r = dispatch('برمج سكربت Python باسم q%d.py يطبع %d' % (i, i), 'mx-q%d-%s' % (i, uuid.uuid4().hex[:4]))
        job = ((r or {}).get('job') or {}).get('job_id') if isinstance(r, dict) else None
        if job: ids.append(job)
        else: refused.append(str((r or {}).get('result', r) if isinstance(r, dict) else r)[:160])
    for j in ids: api('/project-jobs/' + j + '/cancel', {}, method='POST')
    finals = [wait_job(j, 300)['state'] for j in ids]
    return {'accepted': len(ids), 'refused': len(refused), 'refusal_messages': refused[:3], 'finals': finals,
            'verdict': 'pass' if len(ids) <= 5 and len(refused) >= 2 else 'fail'}


def with_config(change, fn):
    cfg = copy.deepcopy(base_config.model_dump()); change(cfg)
    c1, r1 = api('/resources/config', cfg, timeout=120, method='POST')
    try: result = fn()
    finally: c2, r2 = api('/resources/config', base_config.model_dump(), timeout=120, method='POST')
    result['config_http'] = [c1, c2]; return result


def c_14b():
    def change(cfg): cfg['protected_models_dir'] = a.big_models_dir; cfg['tier_models'] = {k: 'qwen2.5-coder-14b-q4' for k in ('expert', 'coder', 'daily', 'fast')}
    def run():
        code, r = chat('أجب بكلمة: نعم', 'coder', timeout=25)
        res = api('/resources')[1] or {}
        loads = [json.loads(l) for l in lifecycle.read_text().splitlines()] if lifecycle.exists() else []
        big = [e for e in loads if e['kind'] == 'load_start' and '14B' in str(e.get('path'))]
        return {'http': code, 'response': str(r)[:200], 'blocked_reason': res.get('blocked_reason'), 'queued': res.get('queued'), 'loaded_14b': bool(big),
                'verdict': 'pass' if code != 200 and not big else 'fail', 'note': 'expected: 14B (≈9 GB) does not fit 8 GB RX 580; queued/refused, never moved to the primary GPU'}
    return with_config(change, run)


def c_one_core():
    def change(cfg): cfg['physical_cpu_core_limit'] = 1; cfg['generation_threads'] = 1; cfg['prompt_threads'] = 1
    def run():
        before = snapshot_traces(); code, r = chat('أجب بكلمة: نعم', 'daily'); calls = new_traces(before)
        lim = calls[0]['native_limits'] if calls else {}
        ok = code == 200 and calls and lim.get('generation_threads') == 1 and lim.get('prompt_threads') == 1 and len(calls[0]['allowed_cpu_ids'] or []) == 1
        res = api('/resources')[1] or {}
        return {'http': code, 'response': str(r)[:300], 'native_limits': lim, 'allowed_cpu_ids': calls[0]['allowed_cpu_ids'] if calls else None, 'requested_cpus_during': (res.get('cpu') or {}).get('requested_cpus'), 'verdict': 'pass' if ok else 'fail'}
    return with_config(change, run)


def c_voice():
    c1, r1 = api('/tts', {'text': 'مرحبا', 'lang': 'ar'}, timeout=60, method='POST')
    c2, r2 = api('/stt', None, timeout=30, method='POST')
    res = api('/resources')[1] or {}
    return {'tts_http': c1, 'tts': str(r1)[:200], 'stt_http': c2, 'stt': str(r2)[:200], 'unsupported_statement': res.get('unsupported'),
            'verdict': 'observed', 'note': 'Whisper GPU is blocked while Protected; Piper/ffmpeg are CPU helpers; outcome recorded as observed'}


def c_status():
    res = api('/resources')[1] or {}
    cpu = res.get('cpu') or {}
    return {'state': res.get('state'), 'target_device': res.get('target_device'), 'requested_cpus': cpu.get('requested_cpus'), 'overrides': [t.get('override') for t in cpu.get('registered_tasks', []) if t.get('override')][:5],
            'errors': cpu.get('errors'), 'backend_affinity': affinity(PID)['distinct_cpus_allowed'], 'verdict': 'pass' if res.get('active_protected') and not cpu.get('errors') else 'fail'}


try:
    case('1 chat non-stream (daily)', '7B on 07:00.0, 2/2 threads, CPU [0,1]', c_chat)
    case('2 chat streaming', 'streamed answer from 7B on 07:00.0', c_stream)
    case('3 tier routing expert/coder/fast', 'every tier served by the configured 7B', c_tiers)
    case('4 image while Protected', 'refused/queued with reason; no vision load; no primary GPU use', c_vision)
    created['py'] = None; case('5 create Python project', 'completed, planning before generating, on 07:00.0', c_create('برمج سكربت Python بسيط باسم main.py يطبع مرحبا دون أي اعتماد خارجي'))
    case('6 create small web page', 'completed with preview checks, on 07:00.0', c_create('برمج لي موقع صفحة واحدة فيها عنوان مرحبا فقط'))
    created['web'] = results[-1]['observed'] if results else {}
    case('7 small edit of saved web page', 'exactly one new revision, or failed with previous revision intact', c_edit)
    case('8 cancel running job', 'cancelled, no saved files', c_cancel)
    case('9 queue bound (7 submissions)', 'at most 5 accepted, the rest refused with a reason', c_queue)
    case('10 14B on RX 580', 'memory guard: not loaded, no primary fallback', c_14b)
    case('11 one physical core, threads 1/1', 'native threads 1/1 and a single CPU id', c_one_core)
    case('12 voice paths while Protected', 'recorded as observed', c_voice)
    case('13 status/CPU placement report', 'Protected, no CPU errors, overrides listed', c_status)
    case('14 status after config restore', 'requested CPUs back to the configured 2 physical cores', lambda: {**c_status(), 'verdict': 'pass' if (api('/resources')[1] or {}).get('cpu', {}).get('requested_cpus') and len((api('/resources')[1] or {}).get('cpu', {}).get('requested_cpus')) == base_config.physical_cpu_core_limit else 'fail'})
finally:
    stop.set(); time.sleep(.6)
    rows = [json.loads(l) for l in (out / 'monitor.jsonl').read_text().splitlines()] if (out / 'monitor.jsonl').exists() else []
    primary_clients = sorted({k for r in rows for k in r['backend_fdinfo'] if k == '0000:03:00.0' and any(r['backend_fdinfo'][k].values())})
    summary = {'cases': len(results), 'passed': sum(r['observed'].get('verdict') == 'pass' for r in results), 'failed': [r['case'] for r in results if r['observed'].get('verdict') == 'fail'],
               'other': [(r['case'], r['observed'].get('verdict')) for r in results if r['observed'].get('verdict') not in ('pass', 'fail')],
               'neura_engine_time_on_primary_gpu': bool(primary_clients), 'rx580_peak_vram_gb': round(max((r['gpu'].get('0000:07:00.0', {}).get('vram', 0) for r in rows), default=0) / 1e9, 3),
               'rx580_peak_busy': max((r['gpu'].get('0000:07:00.0', {}).get('busy', 0) for r in rows), default=0)}
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1)); print('SUMMARY', json.dumps(summary, ensure_ascii=False), flush=True)
    service.stop()
