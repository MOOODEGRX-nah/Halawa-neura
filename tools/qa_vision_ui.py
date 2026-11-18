"""N093 real vision journey through the candidate Qt UI (isolated QA profile, real local inference).

For each image: start a fresh chat session («مسح»), click the real «إرفاق صورة» control, answer
Chromium's native file chooser with the image path (QWebEnginePage.chooseFiles), type the same
question into the composer and press send. The backend trace records image SHA256, model,
projector and device for every model call.

--missing-projector runs the same journey with an isolated runtime registry whose VISION entry
names a projector file that does not exist. The installed projector stays in place.
"""
import argparse, hashlib, json, os, subprocess, sys, time
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--image', type=Path, action='append', required=True)
p.add_argument('--question', default='ما اللون الموجود في الجهة اليسرى من الصورة؟ أجب باسم اللون فقط.')
p.add_argument('--gpu', default='AMD Radeon RX 9060 XT (RADV GFX1200)')
p.add_argument('--missing-projector', action='store_true')
p.add_argument('--fake-backend', action='store_true', help='Harness debugging only; never vision evidence')
a = p.parse_args(); out = a.output.resolve(); out.mkdir(parents=True, exist_ok=True)
if (out / 'vision.json').exists(): raise SystemExit('Refusing to overwrite an existing run')
root = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(root / 'tools'))
profile = out / 'profile'
os.environ.update(NEURA_SETTINGS_DIR=str(profile / 'config'), NEURA_DATA_DIR=str(profile / 'data'), NEURA_STATE_DIR=str(profile / 'state'), NEURA_TIMEOUT_S='900',
                  NEURA_QA_RUN_ROOT=str(out), NEURA_QA_RUN_ID=out.name, NEURA_QA_REAL_TRACE=str(out / 'artifacts/model-traces'), NEURA_QA_TARGET_KIND='source checkout')
from verification.live import foreign_instances
if foreign_instances(): raise SystemExit('A Neura backend is already running; real QA refused')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
qt = QApplication(['neura-vision-qa'])
from src.desktop.paths import DesktopSettings
from src.desktop import app as desktop_app
from src.desktop.service import BackendService
from src.core.resource_policy import ProtectionConfig, save_config
settings = DesktopSettings()
save_config(profile / 'data', ProtectionConfig(mode='normal'))
settings.values.update(models_dir='/opt/neura-ai/models', n_gpu_layers=-1, gpu_device=a.gpu, n_ctx=4096, dedicated_coder=True, check_updates=False); settings.save()
profile.mkdir(parents=True, exist_ok=True); (profile / '.neura-verification-profile').write_text(json.dumps({'run_id': out.name}))
if a.missing_projector:
    original_environment = BackendService.environment
    def environment(self):
        values = original_environment(self)
        import yaml
        registry = Path(values['NEURA_REGISTRY_DIR']) / 'models.yaml'; data = yaml.safe_load(registry.read_text())
        for model in data['models'].values():
            if model.get('projector'): model['projector'] = 'mmproj-QA-missing-projector.gguf'
        registry.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding='utf-8')
        return values
    BackendService.environment = environment
chosen = []
class ChooserPage(desktop_app.LocalPage):
    """Answers Chromium's native file chooser (opened by a real click) with the declared image."""
    def chooseFiles(self, mode, old_files, accepted_mime_types):
        print('STEP chooser', accepted_mime_types, flush=True)
        return [str(chosen[-1])]


desktop_app.LocalPage = ChooserPage
w = desktop_app.MainWindow(settings)
fixture = root / ('tests/fixtures/chat_first_backend.py' if a.fake_backend else 'tests/fixtures/real_backend_trace.py')
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


def step(name): print('STEP', name, flush=True)


def click(selector):
    step('click ' + selector)
    rect = json.loads(js('(()=>{const e=document.querySelector(%s);e.scrollIntoView({block:"center"});const r=e.getBoundingClientRect();return JSON.stringify({x:r.left+r.width/2,y:r.top+r.height/2})})()' % json.dumps(selector)))
    target = w.view.focusProxy() or w.view; step('target %s visible=%s' % (type(target).__name__, target.isVisible()))
    QTest.mouseClick(target, Qt.LeftButton, Qt.NoModifier, QPoint(int(rect['x']), int(rect['y']))); pump(.4)


def type_text(text):
    """Real Qt key events carrying Unicode text (QTest.keyClicks asserts on non-Latin-1)."""
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent
    target = w.view.focusProxy() or w.view; step('type %d chars' % len(text))
    for char in text:
        for kind in (QEvent.KeyPress, QEvent.KeyRelease):
            qt.sendEvent(target, QKeyEvent(kind, Qt.Key_unknown if char != ' ' else Qt.Key_Space, Qt.NoModifier, char))
        pump(.01)


report = {'environment': 'Qt offscreen (QTWEBENGINE_CHROMIUM_FLAGS=' + os.environ.get('QTWEBENGINE_CHROMIUM_FLAGS', '') + '); real Qt mouse clicks and Unicode key events; native file chooser answered via QWebEnginePage.chooseFiles; actual local inference',
          'missing_projector_configuration': a.missing_projector, 'question': a.question, 'cases': []}
try:
    wait(lambda: w.loaded, 60); wait(lambda: js('!!window.NeuraChat'))
    for image in a.image:
        data = image.read_bytes(); case = {'file': image.name, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
        traces = out / 'artifacts/model-traces'; before = set(os.listdir(traces)) if traces.is_dir() else set()
        wait(lambda: not js('busy'), 900)
        click('#clr'); case['session_before'] = js('sid')
        chosen.append(image.resolve()); click('#chat-actions label[aria-label="إرفاق صورة"]')
        wait(lambda: js('document.querySelector("#image-label").textContent').startswith('صورة مرفقة'), 10)
        case['attachment_label'] = js('document.querySelector("#image-label").textContent')
        click('#in'); type_text(a.question); pump(.3)
        case['typed'] = js('document.querySelector("#in").value')
        started = time.time(); click('#go')
        wait(lambda: js('busy'), 10); wait(lambda: not js('busy'), 900); case['duration_s'] = time.time() - started
        case['session'] = js('sid'); case['visible_bubbles'] = js('JSON.stringify(Array.from(document.querySelectorAll("#log > *")).slice(-2).map(e=>e.textContent.trim().slice(0,600)))')
        case['status_note'] = js('(document.querySelector("#stt")||{}).textContent||""')
        new = sorted(set(os.listdir(traces)) - before) if traces.is_dir() else []
        case['model_calls'] = []
        for name in new:
            t = json.loads((traces / name).read_text())
            case['model_calls'].append({k: t.get(k) for k in ('trace_id', 'model_id', 'model_path', 'projector', 'device', 'n_ctx', 'image_sha256', 'finish_reason', 'output', 'usage', 'started_at', 'first_token_at', 'finished_at')})
        w.grab().save(str(out / ('case-' + str(len(report['cases']) + 1) + '.png')))
        report['cases'].append(case); (out / 'vision.json').write_text(json.dumps(report, ensure_ascii=False, indent=1))
        print(json.dumps({'file': case['file'], 'sha256': case['sha256'][:12], 'calls': [(c['model_id'], (c['device'] or {}).get('pci_id'), c['projector'], c['image_sha256'], (c['output'] or '')[-120:] if isinstance(c['output'], str) else c['output']) for c in case['model_calls']], 'bubbles': case['visible_bubbles'][-400:]}, ensure_ascii=False), flush=True)
except BaseException as error:
    report['failure'] = {'type': type(error).__name__, 'error': str(error)}; raise
finally:
    (out / 'vision.json').write_text(json.dumps(report, ensure_ascii=False, indent=1))
    w.close_checked = True; w.close(); wait(lambda: not w.tasks, 25); w.service.stop()
