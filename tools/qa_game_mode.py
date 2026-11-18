"""N016 real gaming-cycle QA harness (isolated QA profile, real local inference, no fake model).

Subcommands (all write under --out; nothing touches ~/.config/neura-ai or ~/.local/share/neura-ai):

  serve     Start the candidate backend through the desktop BackendService launch path with an
            isolated profile and an explicit Auto resource profile; then sample, every 0.5 s,
            /resources (mode, triggers, device, CPU limits), per-GPU sysfs busy/VRAM, and DRM
            fdinfo (drm-pdev + engine counters) of the backend and of any process whose
            environment carries SteamAppId (the game). Runs until Ctrl+C.
  snapshot  Save /resources plus the backend's thread affinity to a labelled JSON file.
  request   Send the same small project request (planner + coder) through /chat/dispatch in a
            fresh session; wait for the job; save submit/first-token/finish times, traces,
            the resource receipt (GPU, threads, CPU IDs) and the worker affinity.

Model loading is recorded separately from the request (model-lifecycle.jsonl load_start/load_end).
FPS/frame times come from MangoHud CSV logs of the game; see the run instructions in the report.
"""
import argparse, glob, json, os, signal, subprocess, sys, time, urllib.request, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPT = 'برمج سكربت Python بسيط باسم main.py يطبع مرحبا دون أي اعتماد خارجي'


def env_for(out):
    profile = out / 'profile'
    return profile, {'NEURA_SETTINGS_DIR': str(profile / 'config'), 'NEURA_DATA_DIR': str(profile / 'data'), 'NEURA_STATE_DIR': str(profile / 'state'),
                     'NEURA_TIMEOUT_S': '900', 'NEURA_QA_RUN_ROOT': str(out), 'NEURA_QA_RUN_ID': out.name,
                     'NEURA_QA_REAL_TRACE': str(out / 'artifacts/model-traces'), 'NEURA_QA_TARGET_KIND': 'source checkout'}


def api(out, path, body=None, timeout=10):
    info = json.loads((out / 'server.json').read_text())
    token = (out / 'profile/data/.api-token').read_text().strip()
    request = urllib.request.Request('http://127.0.0.1:%d%s' % (info['port'], path), data=None if body is None else json.dumps(body).encode(),
                                     headers={'X-Neura-Token': token, 'Content-Type': 'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=timeout) as r: return json.load(r)


def fdinfo(pid):
    """DRM client usage per PCI device for one process (Linux drm-usage-stats)."""
    devices = {}
    for path in glob.glob('/proc/%d/fdinfo/*' % pid)[:4096]:
        try: text = open(path).read()
        except OSError: continue
        if 'drm-pdev' not in text: continue
        fields = dict(line.split(':', 1) for line in text.splitlines() if ':' in line)
        pdev = fields.get('drm-pdev', '').strip(); client = fields.get('drm-client-id', '').strip()
        engines = {k[len('drm-engine-'):]: int(v.split()[0]) for k, v in fields.items() if k.startswith('drm-engine-') and v.split()[0].isdigit()}
        devices.setdefault(pdev, {})[client] = engines
    return {p: {e: sum(c.get(e, 0) for c in clients.values()) for e in {e for c in clients.values() for e in c}} for p, clients in devices.items()}


def game_pids():
    found = []
    for env in glob.glob('/proc/[0-9]*/environ'):
        try: raw = open(env, 'rb').read()
        except OSError: continue
        if b'SteamAppId=' not in raw and b'SteamGameId=' not in raw: continue
        pid = int(env.split('/')[2])
        try: cmd = open('/proc/%d/cmdline' % pid, 'rb').read().replace(b'\0', b' ').decode(errors='replace')[:200]
        except OSError: continue
        app = next((v.split(b'=', 1)[1].decode() for v in raw.split(b'\0') if v.startswith(b'SteamAppId=')), None)
        found.append({'pid': pid, 'app_id': app, 'cmd': cmd})
    return found


def affinity(pid):
    tasks = []
    for task in glob.glob('/proc/%d/task/*' % pid):
        try:
            status = dict(l.split(':', 1) for l in open(task + '/status').read().splitlines() if ':' in l)
            comm = open(task + '/comm').read().strip()
        except OSError: continue
        tasks.append({'tid': int(task.rsplit('/', 1)[1]), 'comm': comm, 'cpus_allowed_list': status.get('Cpus_allowed_list', '').strip()})
    distinct = sorted({t['cpus_allowed_list'] for t in tasks})
    return {'pid': pid, 'threads': len(tasks), 'distinct_cpus_allowed': distinct, 'restricted_threads': [t for t in tasks if t['cpus_allowed_list'] != distinct[-1]] if len(distinct) > 1 else []}


def serve(a):
    out = a.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    if (out / 'server.json').exists(): raise SystemExit('Refusing to reuse an existing run directory')
    profile, extra = env_for(out); os.environ.update(extra)
    sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'tools'))
    from verification.live import foreign_instances
    if foreign_instances(): raise SystemExit('A Neura backend is already running; real QA refused')
    from src.desktop.paths import DesktopSettings
    from src.desktop.service import BackendService
    from src.core.resource_policy import ProtectionConfig, save_config
    settings = DesktopSettings()
    resource = ProtectionConfig.model_validate_json(a.resource_config.read_text())
    save_config(profile / 'data', resource)
    settings.values.update(models_dir='/opt/neura-ai/models', n_gpu_layers=-1, gpu_device=a.gpu, n_ctx=4096, dedicated_coder=True, check_updates=False); settings.save()
    profile.mkdir(parents=True, exist_ok=True); (profile / '.neura-verification-profile').write_text(json.dumps({'run_id': out.name}))
    fixture = ROOT / 'tests/fixtures/real_backend_trace.py'
    service = BackendService(settings, popen=lambda command, **opts: subprocess.Popen([command[0], '-B', str(fixture), '--port', command[-1]], **opts))
    service.start()
    (out / 'server.json').write_text(json.dumps({'port': service.port, 'pid': service.process.pid, 'started_at': time.time(), 'gpu_setting': a.gpu,
        'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), 'resource_configuration': resource.model_dump()}, indent=1))
    end = time.monotonic() + 60
    while not service.health() and time.monotonic() < end: time.sleep(.2)
    if not service.health(): raise SystemExit('Backend did not become healthy; see ' + str(out / 'profile/state/backend.log'))
    print('READY port=%d pid=%d' % (service.port, service.process.pid), flush=True)
    stop = []
    signal.signal(signal.SIGINT, lambda *_: stop.append(1)); signal.signal(signal.SIGTERM, lambda *_: stop.append(1))
    cards = {os.path.basename(os.path.realpath(d + '/device')): d + '/device' for d in glob.glob('/sys/class/drm/card[0-9]')}
    with (out / 'monitor.jsonl').open('a') as log:
        while not stop and service.process.poll() is None:
            row = {'t': time.time()}
            try: row['resources'] = api(out, '/resources', timeout=2)
            except Exception as exc: row['resources_error'] = str(exc)
            row['gpu'] = {}
            for pci, path in cards.items():
                v = {}
                for key in ('gpu_busy_percent', 'mem_info_vram_used'):
                    try: v[key] = int(open(path + '/' + key).read())
                    except OSError: v[key] = None
                row['gpu'][pci] = v
            row['backend_fdinfo'] = fdinfo(service.process.pid)
            row['games'] = [{**g, 'fdinfo': fdinfo(g['pid'])} for g in game_pids()]
            log.write(json.dumps(row) + '\n'); log.flush(); time.sleep(.5)
    service.stop(); print('STOPPED', flush=True)


def snapshot(a):
    out = a.out.resolve(); info = json.loads((out / 'server.json').read_text())
    value = {'label': a.label, 'time': time.time(), 'resources': api(out, '/resources'), 'backend_affinity': affinity(info['pid']), 'games': game_pids()}
    (out / ('snapshot-' + a.label + '.json')).write_text(json.dumps(value, ensure_ascii=False, indent=1)); print(json.dumps({k: value['resources'].get(k) for k in ('configured_mode', 'state', 'active_protected', 'trigger_reasons')}, ensure_ascii=False))


def request(a):
    out = a.out.resolve(); info = json.loads((out / 'server.json').read_text())
    traces = out / 'artifacts/model-traces'; before = set(os.listdir(traces)) if traces.is_dir() else set()
    lifecycle = out / 'artifacts/model-lifecycle.jsonl'; offset = lifecycle.stat().st_size if lifecycle.exists() else 0
    record = {'label': a.label, 'prompt': PROMPT, 'resources_before': api(out, '/resources'), 'affinity_before': affinity(info['pid'])}
    rid = 'r_' + str(int(time.time() * 1000)) + '_' + uuid.uuid4().hex
    record['submitted_at'] = time.time()
    reply = api(out, '/chat/dispatch', {'text': PROMPT, 'request_id': rid, 'session_id': 'qa-game-' + a.label + '-' + uuid.uuid4().hex[:8]}, timeout=30)
    record['dispatch_kind'] = reply.get('kind')
    job_id = (reply.get('job') or {}).get('job_id')
    if not job_id: record['error'] = 'no job: ' + json.dumps(reply, ensure_ascii=False)[:500]
    else:
        end = time.monotonic() + 900; peak_affinity = None
        while time.monotonic() < end:
            job = api(out, '/project-jobs/' + job_id)
            if job['state'] in ('generating', 'planning') and peak_affinity is None: peak_affinity = affinity(info['pid'])
            if job['state'] in ('completed', 'failed', 'cancelled'): break
            time.sleep(.25)
        record['finished_at'] = time.time(); record['job'] = {k: job.get(k) for k in ('job_id', 'state', 'error', 'saved_files', 'stage_results', 'blocked_reason')}
        record['affinity_during_job'] = peak_affinity
    record['resources_after'] = api(out, '/resources'); record['affinity_after'] = affinity(info['pid'])
    new = sorted(set(os.listdir(traces)) - before) if traces.is_dir() else []
    calls = []
    for name in new:
        t = json.loads((traces / name).read_text())
        calls.append({'trace_id': t['trace_id'], 'model_id': t['model_id'], 'device': t['device'], 'resource_profile': t['resource_profile'], 'n_ctx': t['n_ctx'],
                      'started_at': t['started_at'], 'first_token_at': t.get('first_token_at'), 'finished_at': t.get('finished_at'), 'finish_reason': t.get('finish_reason'),
                      'usage': t.get('usage'), 'token_metrics': t.get('token_metrics'), 'role': 'planner' if 'implementation plan' in t['messages'][0]['content'] else 'coder'})
    calls.sort(key=lambda c: c['started_at']); record['model_calls'] = calls
    record['model_lifecycle'] = [json.loads(l) for l in lifecycle.read_text()[offset:].splitlines() if l.strip()] if lifecycle.exists() else []
    loads = [e for e in record['model_lifecycle'] if e['kind'] in ('load_start', 'load_end')]
    first_token = next((c['first_token_at'] for c in calls if c.get('first_token_at')), None)
    record['metrics'] = {'time_to_first_token_s': None if first_token is None else first_token - record['submitted_at'],
                         'total_request_s': record.get('finished_at', time.time()) - record['submitted_at'],
                         'model_load_s': sum(e['time'] - s['time'] for s, e in zip(loads[::2], loads[1::2])) if loads else 0.0,
                         'devices': sorted({(c['device'] or {}).get('pci_id') or 'unknown' for c in calls}),
                         'definition': 'TTFT = submit -> first streamed coder content token (planner is non-streamed JSON); model load from lifecycle, included in TTFT when it happened'}
    (out / ('request-' + a.label + '.json')).write_text(json.dumps(record, ensure_ascii=False, indent=1, default=str))
    print(json.dumps({'label': a.label, 'state': record.get('job', {}).get('state'), **record['metrics']}, ensure_ascii=False, default=str))


def watch(a):
    """For each declared run, wait for the NEXT MangoHud CSV; for a B run send the request at once."""
    out = a.out.resolve(); folder = a.mangohud_dir.resolve(); folder.mkdir(parents=True, exist_ok=True)
    known = {f.name for f in folder.glob('*.csv')}; runs = []
    for index, kind in enumerate(a.sequence.split(','), 1):
        label = kind + str(sum(k == kind for k in a.sequence.split(',')[:index]))
        print('WAITING for MangoHud log of run %s (%s)' % (label, 'Neura idle' if kind == 'A' else 'Neura generating'), flush=True)
        while True:
            new = sorted(f for f in folder.glob('*.csv') if f.name not in known and not f.name.endswith('_summary.csv'))
            if new: break
            time.sleep(.05)
        log = new[0]; known.add(log.name); seen = time.time(); entry = {'label': label, 'kind': kind, 'csv': log.name, 'log_first_seen_at': seen}
        print('LOG %s started' % log.name, flush=True)
        if kind == 'B':
            r = argparse.Namespace(out=out, label=label); request(r)
            entry['request'] = 'request-' + label + '.json'
        last = -1
        while True:
            size = log.stat().st_size
            if size == last: break
            last = size; time.sleep(3)
        entry['log_finished_at'] = time.time(); runs.append(entry)
        (out / 'runs.json').write_text(json.dumps(runs, indent=1)); print('DONE', label, flush=True)


def frames(path):
    lines = path.read_text(errors='replace').splitlines()
    header = next(i for i, l in enumerate(lines) if l.startswith('fps,frametime'))
    cols = lines[header].split(','); rows = []
    for l in lines[header + 1:]:
        v = l.split(',')
        if len(v) != len(cols): continue
        try: rows.append({'fps': float(v[cols.index('fps')]), 'frametime_ms': float(v[cols.index('frametime')]), 'elapsed_s': float(v[cols.index('elapsed')]) / 1e9})
        except ValueError: continue
    return rows


def stats(rows, start, end, per_frame=True):
    window = [r for r in rows if start <= r['elapsed_s'] <= end]
    if not per_frame:
        # Interval log (log_interval>0): each row is MangoHud's per-interval average. Average FPS is
        # valid; a true per-frame p99 frame time is NOT derivable and is reported as None.
        if len(window) < 3: return {'rows': len(window), 'note': 'too few interval rows'}
        return {'window_s': [round(start, 3), round(end, 3)], 'interval_rows': len(window), 'average_fps': round(sum(r['fps'] for r in window) / len(window), 2),
                'p99_frametime_ms': None, 'max_interval_frametime_ms': round(max(r['frametime_ms'] for r in window), 3), 'note': 'interval log: per-frame p99 not measurable'}
    if len(window) < 10: return {'frames': len(window), 'note': 'too few frames'}
    times = sorted(r['frametime_ms'] for r in window); span = window[-1]['elapsed_s'] - window[0]['elapsed_s']
    p99 = times[min(len(times) - 1, int(round(.99 * (len(times) - 1))))]
    return {'window_s': [round(start, 3), round(end, 3)], 'frames': len(window), 'average_fps': round(len(window) / span, 2) if span > 0 else None,
            'mean_frametime_ms': round(sum(times) / len(times), 3), 'p99_frametime_ms': round(p99, 3)}


def analyze(a):
    out = a.out.resolve(); folder = a.mangohud_dir.resolve(); runs = json.loads((out / 'runs.json').read_text()); result = {'runs': [], 'pairs': []}
    data = {}
    for run in runs:
        rows = frames(folder / run['csv'])
        span = rows[-1]['elapsed_s'] - rows[0]['elapsed_s'] if rows else 0
        per_frame = bool(rows) and abs(sum(r['frametime_ms'] for r in rows) / 1000 - span) <= max(.5, .05 * span)
        entry = {**run, 'total_frames': len(rows), 'per_frame_log': per_frame, 'whole_log': stats(rows, a.skip, 1e9, per_frame)}
        if run['kind'] == 'B':
            req = json.loads((out / run['request']).read_text())
            gen = [c for c in req['model_calls'] if c.get('finished_at')]
            first = min((c['started_at'] for c in gen), default=req['submitted_at']); last = max((c['finished_at'] for c in gen), default=req['finished_at'])
            loads = [e for e in req['model_lifecycle'] if e['kind'] in ('load_start', 'load_end')]
            entry['generation_window_s'] = [first - run['log_first_seen_at'], last - run['log_first_seen_at']]
            entry['model_load_during_run'] = bool(loads)
            entry['request_metrics'] = req['metrics']; entry['job_state'] = req.get('job', {}).get('state')
        data[run['label']] = (entry, rows); result['runs'].append(entry)
    for i in range(1, 10):
        if 'A%d' % i not in data or 'B%d' % i not in data: continue
        b, brows = data['B%d' % i]; a_, arows = data['A%d' % i]; start, end = b['generation_window_s']
        result['pairs'].append({'pair': i, 'matched_window_s': [round(start, 3), round(end, 3)], 'A_idle': stats(arows, start, end, a_['per_frame_log']), 'B_generating': stats(brows, start, end, b['per_frame_log']),
                                'B_ttft_s': b['request_metrics']['time_to_first_token_s'], 'B_total_request_s': b['request_metrics']['total_request_s'],
                                'B_model_load_s': b['request_metrics']['model_load_s'], 'B_devices': b['request_metrics']['devices']})
    (out / 'analysis.json').write_text(json.dumps(result, indent=1)); print(json.dumps(result['pairs'], indent=1))


def schedule(a):
    """One continuous MangoHud capture (autostart_log) of a static scene; B requests fired at fixed
    offsets, A windows are the matching idle intervals one period earlier. Then exit/restoration."""
    out = a.out.resolve(); folder = a.mangohud_dir.resolve(); folder.mkdir(parents=True, exist_ok=True)
    offsets = [float(x) for x in a.b_offsets.split(',')]
    if a.wait_relaunch:
        print('WAITING for the running game to exit before relaunch', flush=True)
        while game_pids(): time.sleep(.5)
        time.sleep(3)
        while not game_pids(): time.sleep(.5)
    print('WAITING for game detection (Protected)', flush=True)
    while not api(out, '/resources')['active_protected']: time.sleep(.5)
    detected = time.time(); snapshot(argparse.Namespace(out=out, label='game-detected'))
    known = {f.name for f in folder.glob('*.csv')}
    request(argparse.Namespace(out=out, label='warmup-protected'))
    print('WARM; waiting for the MangoHud autostart log', flush=True)
    deadline = time.time() + a.capture_timeout; new = []
    while time.time() < deadline and game_pids():
        new = sorted(f for f in folder.glob('*.csv') if f.name not in known and not f.name.endswith('_summary.csv'))
        if new: break
        time.sleep(.05)
    if not new:
        plan = {'capture': 'no MangoHud log within %ds (launch option not set or game exited); FPS/p99 not measured' % a.capture_timeout, 'game_detected_at': detected}
        (out / 'schedule.json').write_text(json.dumps(plan, indent=1)); print('NO CAPTURE; waiting for the user to quit the game', flush=True)
        while game_pids(): time.sleep(.5)
        plan['game_exited_at'] = time.time()
        while api(out, '/resources')['active_protected']: time.sleep(.5)
        plan['normal_restored_at'] = time.time(); (out / 'schedule.json').write_text(json.dumps(plan, indent=1))
        snapshot(argparse.Namespace(out=out, label='post-exit')); request(argparse.Namespace(out=out, label='post-exit')); print('RESTORATION DONE', flush=True); return
    log = new[0]; t0 = time.time(); print('LOG', log.name, flush=True)
    plan = {'csv': log.name, 'log_first_seen_at': t0, 'game_detected_at': detected, 'b_offsets_s': offsets, 'a_period_shift_s': a.period, 'b_requests': []}
    for i, off in enumerate(offsets, 1):
        while time.time() < t0 + off: time.sleep(.02)
        request(argparse.Namespace(out=out, label='B%d' % i)); plan['b_requests'].append('request-B%d.json' % i)
        (out / 'schedule.json').write_text(json.dumps(plan, indent=1))
    last = -1
    while True:
        size = log.stat().st_size
        if size == last: break
        last = size; time.sleep(3)
    plan['log_finished_at'] = time.time(); (out / 'schedule.json').write_text(json.dumps(plan, indent=1))
    print('CAPTURE DONE - quit the game now (leave Steam open)', flush=True)
    while game_pids(): time.sleep(.5)
    plan['game_exited_at'] = time.time(); print('GAME EXITED; waiting for exit hold + dwell', flush=True)
    end = time.time() + 900
    while api(out, '/resources')['active_protected'] and time.time() < end: time.sleep(.5)
    plan['normal_restored_at'] = time.time(); plan['restored'] = not api(out, '/resources')['active_protected']
    (out / 'schedule.json').write_text(json.dumps(plan, indent=1))
    snapshot(argparse.Namespace(out=out, label='post-exit')); request(argparse.Namespace(out=out, label='post-exit'))
    print('RESTORATION DONE', flush=True)


def analyze_schedule(a):
    out = a.out.resolve(); plan = json.loads((out / 'schedule.json').read_text())
    rows = frames(a.mangohud_dir.resolve() / plan['csv'])
    span = rows[-1]['elapsed_s'] - rows[0]['elapsed_s'] if rows else 0
    per_frame = bool(rows) and abs(sum(r['frametime_ms'] for r in rows) / 1000 - span) <= max(.5, .05 * span)
    t0 = plan['log_first_seen_at'] - (rows[0]['elapsed_s'] if rows else 0) * 0  # elapsed starts at log start
    result = {'csv': plan['csv'], 'rows': len(rows), 'span_s': round(span, 2), 'per_frame_log': per_frame, 'whole_log': stats(rows, 0, 1e9, per_frame), 'pairs': []}
    for i, name in enumerate(plan['b_requests'], 1):
        req = json.loads((out / name).read_text()); calls = [c for c in req['model_calls'] if c.get('finished_at')]
        start = min(c['started_at'] for c in calls) - plan['log_first_seen_at']; end = max(c['finished_at'] for c in calls) - plan['log_first_seen_at']
        result['pairs'].append({'pair': i, 'B_window_s': [round(start, 2), round(end, 2)], 'A_window_s': [round(start - plan['a_period_shift_s'], 2), round(end - plan['a_period_shift_s'], 2)],
            'A_idle': stats(rows, start - plan['a_period_shift_s'], end - plan['a_period_shift_s'], per_frame), 'B_generating': stats(rows, start, end, per_frame),
            'B_ttft_s': req['metrics']['time_to_first_token_s'], 'B_total_request_s': req['metrics']['total_request_s'], 'B_model_load_s': req['metrics']['model_load_s'],
            'B_devices': req['metrics']['devices'], 'B_job_state': req.get('job', {}).get('state'),
            'B_threads_cpus': [((c['resource_profile'] or {}).get('native_limits') or {}).get('generation_threads') for c in calls] + [(calls[0]['resource_profile'] or {}).get('allowed_cpu_ids') if calls else None]})
    (out / 'analysis-schedule.json').write_text(json.dumps(result, indent=1)); print(json.dumps(result, indent=1))


def restore(a):
    """Wait for every detected game to exit, then for Auto to leave Protected; record a fresh request."""
    out = a.out.resolve(); record = {'started_at': time.time()}
    print('WAITING for the game to exit', flush=True)
    while game_pids(): time.sleep(.5)
    record['game_exited_at'] = time.time(); print('GAME EXITED', flush=True)
    end = time.time() + 1800
    while api(out, '/resources')['active_protected'] and time.time() < end: time.sleep(.5)
    record['normal_at'] = time.time(); record['protected_after_wait'] = api(out, '/resources')['active_protected']
    record['seconds_exit_to_normal'] = record['normal_at'] - record['game_exited_at']
    snapshot(argparse.Namespace(out=out, label='post-exit')); request(argparse.Namespace(out=out, label='post-exit'))
    post = json.loads((out / 'request-post-exit.json').read_text())
    def summary(req):
        calls = req['model_calls']; rp = [(c['resource_profile'] or {}) for c in calls]
        return {'models': [c['model_id'] for c in calls], 'devices': [(c['device'] or {}).get('pci_id') for c in calls], 'protected': [r.get('protected') for r in rp],
                'threads': [(r.get('native_limits') or {}).get('generation_threads') for r in rp], 'allowed_cpu_ids': [r.get('allowed_cpu_ids') for r in rp],
                'worker_affinity_during_job': (req.get('affinity_during_job') or {}).get('distinct_cpus_allowed'), 'job_state': req.get('job', {}).get('state'), **req['metrics']}
    record['post_exit'] = summary(post)
    if a.baseline: record['pre_game_baseline'] = {'source': str(a.baseline), **summary(json.loads(a.baseline.read_text()))}
    (out / 'restoration.json').write_text(json.dumps(record, ensure_ascii=False, indent=1, default=str)); print(json.dumps(record, ensure_ascii=False, indent=1, default=str), flush=True)


p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
sub = p.add_subparsers(dest='command', required=True)
s = sub.add_parser('serve'); s.add_argument('--out', type=Path, required=True); s.add_argument('--resource-config', type=Path, required=True)
s.add_argument('--gpu', default='AMD Radeon RX 9060 XT (RADV GFX1200)', help='Normal-profile device (observed unique description)')
for name in ('snapshot', 'request'):
    s = sub.add_parser(name); s.add_argument('--out', type=Path, required=True); s.add_argument('--label', required=True)
s = sub.add_parser('watch'); s.add_argument('--out', type=Path, required=True); s.add_argument('--mangohud-dir', type=Path, required=True); s.add_argument('--sequence', default='A,B,A,B,A,B')
s = sub.add_parser('analyze'); s.add_argument('--out', type=Path, required=True); s.add_argument('--mangohud-dir', type=Path, required=True); s.add_argument('--skip', type=float, default=0.0)
s = sub.add_parser('schedule'); s.add_argument('--out', type=Path, required=True); s.add_argument('--mangohud-dir', type=Path, required=True); s.add_argument('--b-offsets', default='45,125,205'); s.add_argument('--period', type=float, default=40.0); s.add_argument('--wait-relaunch', action='store_true'); s.add_argument('--capture-timeout', type=float, default=420.0)
s = sub.add_parser('analyze-schedule'); s.add_argument('--out', type=Path, required=True); s.add_argument('--mangohud-dir', type=Path, required=True)
s = sub.add_parser('restore'); s.add_argument('--out', type=Path, required=True); s.add_argument('--baseline', type=Path)
if __name__ == '__main__':
    a = p.parse_args(); {'restore': restore, 'serve': serve, 'snapshot': snapshot, 'request': request, 'watch': watch, 'analyze': analyze, 'schedule': schedule, 'analyze-schedule': analyze_schedule}[a.command](a)
