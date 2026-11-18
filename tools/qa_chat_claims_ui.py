"""Real Qt composer check of the chat claim guard (isolated QA profile, real local inference).

Each message is sent in a fresh session through the composer (#in/#go). Records the dispatch
decision, the visible reply, whether the Neura notice was appended, and the model trace.
"""
import argparse, json, os, subprocess, sys, time
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--resource-config', type=Path, required=True)
p.add_argument('--gpu', default='AMD Radeon RX 9060 XT (RADV GFX1200)')
p.add_argument('--message', action='append', required=True)
p.add_argument('--fake-chat-text', help='UI rendering check only: fake backend replies with this recorded text (NOT model behavior)')
a = p.parse_args(); out = a.output.resolve(); out.mkdir(parents=True, exist_ok=True)
if (out / 'claims.json').exists(): raise SystemExit('Refusing to overwrite an existing run')
root = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(root / 'tools'))
profile = out / 'profile'
os.environ.update(NEURA_SETTINGS_DIR=str(profile / 'config'), NEURA_DATA_DIR=str(profile / 'data'), NEURA_STATE_DIR=str(profile / 'state'), NEURA_TIMEOUT_S='900',
                  NEURA_QA_RUN_ROOT=str(out), NEURA_QA_RUN_ID=out.name, NEURA_QA_REAL_TRACE=str(out / 'artifacts/model-traces'), NEURA_QA_TARGET_KIND='source checkout')
from verification.live import foreign_instances
if foreign_instances(): raise SystemExit('A Neura backend is already running; real QA refused')
from PySide6.QtWidgets import QApplication
qt = QApplication(['neura-claims-qa'])
from src.desktop.paths import DesktopSettings
from src.desktop.app import MainWindow
from src.core.resource_policy import ProtectionConfig, save_config
from src.core.chat_claims import NOTICE
settings = DesktopSettings(); save_config(profile / 'data', ProtectionConfig.model_validate_json(a.resource_config.read_text()))
settings.values.update(models_dir='/opt/neura-ai/models', n_gpu_layers=-1, gpu_device=a.gpu, n_ctx=4096, dedicated_coder=True, check_updates=False); settings.save()
profile.mkdir(parents=True, exist_ok=True); (profile / '.neura-verification-profile').write_text(json.dumps({'run_id': out.name}))
w = MainWindow(settings)
fixture = root / ('tests/fixtures/chat_first_backend.py' if a.fake_chat_text else 'tests/fixtures/real_backend_trace.py')
if a.fake_chat_text: os.environ['NEURA_QA_CHAT_TEXT'] = a.fake_chat_text
w.service.popen = lambda command, **opts: subprocess.Popen([command[0], '-B', str(fixture), '--port', command[-1]], **opts)
w.resize(1280, 900); w.show()


def pump(d=.005):
    end = time.monotonic() + d
    while True:
        qt.processEvents(); time.sleep(.005)
        if time.monotonic() >= end: return


def wait(check, seconds=30):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check(): return
        pump()
    raise TimeoutError('QA condition timed out')


def js(source):
    result = []; w.page.runJavaScript(source, lambda value: result.append(value)); wait(lambda: bool(result), 5); return result[0]


report = {'environment': 'Qt offscreen (' + os.environ.get('QTWEBENGINE_CHROMIUM_FLAGS', '') + '); actual composer; ' + ('FAKE backend replaying recorded text (UI rendering check, not model behavior)' if a.fake_chat_text else 'actual local inference; explicit resource profile'), 'cases': []}
try:
    wait(lambda: w.loaded, 60); wait(lambda: js('!!window.NeuraChat'))
    js('window.__qaDispatch=[];window.__qaFetch=window.fetch;window.fetch=async(...args)=>{const r=await window.__qaFetch(...args);if(String(args[0]).includes("/chat/dispatch")){window.__qaDispatch.push(await r.clone().json());}return r;};true;')
    for text in a.message:
        traces = out / 'artifacts/model-traces'; before = set(os.listdir(traces)) if traces.is_dir() else set()
        wait(lambda: not js('busy'), 900); js('document.querySelector("#clr").click();true;')
        offset = js('(window.__qaDispatch||[]).length'); bubbles = js('document.querySelectorAll("#log > *").length')
        js('document.querySelector("#in").value=' + json.dumps(text) + ';document.querySelector("#go").click();true;')
        wait(lambda: js('document.querySelectorAll("#log > *").length') >= bubbles + 2 and not js('busy'), 900); pump(1)
        reply = js('(Array.from(document.querySelectorAll("#log > *")).slice(-1)[0]||{}).textContent||""')
        new = sorted(set(os.listdir(traces)) - before) if traces.is_dir() else []
        calls = [json.loads((traces / n).read_text()) for n in new]
        case = {'text': text, 'dispatch': json.loads(js('JSON.stringify((window.__qaDispatch||[]).slice(' + str(offset) + '))')), 'visible_reply': reply[-1500:],
                'notice_visible': NOTICE.strip()[:40] in reply, 'model_calls': [{k: c.get(k) for k in ('model_id', 'device', 'finish_reason', 'output', 'usage')} for c in calls]}
        report['cases'].append(case); (out / 'claims.json').write_text(json.dumps(report, ensure_ascii=False, indent=1))
        print(json.dumps({'text': text[:50], 'dispatch': [d.get('kind') for d in case['dispatch']], 'notice_visible': case['notice_visible'],
                          'devices': [(c.get('device') or {}).get('pci_id') for c in calls], 'reply_tail': reply[-260:]}, ensure_ascii=False), flush=True)
finally:
    (out / 'claims.json').write_text(json.dumps(report, ensure_ascii=False, indent=1))
    w.close_checked = True; w.close(); wait(lambda: not w.tasks, 25); w.service.stop()
