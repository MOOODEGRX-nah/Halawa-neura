"""Independent post-save interaction check of a SAVED static project revision (QA only).

Loads the saved files in an offline Qt WebEngine view (network blocked) and drives the page with
real Qt input events (mouse clicks at the rendered control centre, Tab/Space/Enter keys):

  theme     -- toggles the theme control on and back off; records body state and surface
               backgrounds in each direction; confirms Login and baseline content/links survive.
  services  -- keyboard-operates the arabic_services_v1 category filter (Tab to a filter, Space,
               then Enter on «الكل»), records visible cards, aria-pressed and :focus-visible.

This is not the in-job gate (src/core/candidate_browser.py). It is evidence for a saved revision.
"""
import argparse, hashlib, json, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--project-dir', type=Path, required=True)
p.add_argument('--mode', choices=['theme', 'services'], required=True)
p.add_argument('--baseline-dir', type=Path, help='Earlier revision whose visible text/controls must survive')
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QUrl, Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWebEngineCore import QWebEngineUrlRequestInterceptor, QWebEngineProfile, QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView

root = a.project_dir.resolve()
files = {f.name: f.read_bytes() for f in root.iterdir() if f.is_file()}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def do_GET(self):
        name = self.path.split('?')[0].lstrip('/') or 'index.html'
        if name not in files: self.send_error(404); return
        kind = {'html': 'text/html', 'css': 'text/css', 'js': 'text/javascript'}.get(name.rsplit('.', 1)[-1], 'application/octet-stream')
        self.send_response(200); self.send_header('Content-Type', kind + '; charset=utf-8'); self.end_headers(); self.wfile.write(files[name])


server = ThreadingHTTPServer(('127.0.0.1', 0), Handler); threading.Thread(target=server.serve_forever, daemon=True).start()
origin = 'http://127.0.0.1:%d/' % server.server_port
app = QApplication(['neura-saved-qa']); profile = QWebEngineProfile()


class Block(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        if not info.requestUrl().toString().startswith(origin): info.block(True)


blocker = Block(); profile.setUrlRequestInterceptor(blocker)
view = QWebEngineView(); view.setPage(QWebEnginePage(profile, view)); view.show()


def pump(d=.25):
    end = time.monotonic() + d
    while time.monotonic() < end: app.processEvents(); time.sleep(.005)


def js(code):
    out = []; view.page().runJavaScript(code, 0, lambda v: out.append(v)); end = time.monotonic() + 5
    while not out and time.monotonic() < end: pump(.01)
    return out[0] if out else None


def load(width):
    view.resize(width, 800); ok = []; view.loadFinished.connect(ok.append); view.load(QUrl(origin + 'index.html'))
    end = time.monotonic() + 10
    while not ok and time.monotonic() < end: pump(.02)
    view.loadFinished.disconnect(); pump(.5); view.setFocus(); return bool(ok and ok[0])


def click(selector):
    """Scroll into view, then a REAL Qt mouse click at the element's rendered centre."""
    rect = json.loads(js('(()=>{const e=document.querySelector(%s);if(!e)return "null";e.scrollIntoView({block:"center",behavior:"instant"});const r=e.getBoundingClientRect();const h=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);return JSON.stringify({x:r.left+r.width/2,y:r.top+r.height/2,hit:h===e||e.contains(h)})})()' % json.dumps(selector)))
    if not rect or not rect['hit']: return {'clicked': False, 'rect': rect}
    pump(.1); target = view.focusProxy() or view
    QTest.mouseClick(target, Qt.LeftButton, Qt.NoModifier, QPoint(int(rect['x']), int(rect['y']))); pump(.4)
    return {'clicked': True, 'rect': rect}


STATE = r'''(()=>{const vis=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';};
return JSON.stringify({body_class:document.body.className,body_attrs:Array.from(document.body.attributes).map(x=>x.name+'='+x.value),
surfaces:Array.from(document.querySelectorAll('body,body div,body header,body main,body section,body footer')).filter(vis).slice(0,40).map(e=>getComputedStyle(e).backgroundColor),
text:document.body.innerText.replace(/\s+/g,' ').trim(),controls:Array.from(document.querySelectorAll('a,button,input')).filter(vis).map(e=>({tag:e.tagName.toLowerCase(),label:e.textContent.trim().replace(/\s+/g,' '),id:e.id||null,href:e.getAttribute('href')})),
overflow:document.documentElement.scrollWidth>innerWidth+2,reduced_motion:matchMedia('(prefers-reduced-motion: reduce)').matches})})()'''
THEME_SELECTOR = r'''(()=>{const c=document.getElementById('neura-theme-toggle')||Array.from(document.querySelectorAll('button,[role=button]')).find(e=>/dark|theme|داكن|مظلم/i.test(e.textContent+' '+e.id+' '+(e.getAttribute('aria-label')||'')));if(!c)return null;if(!c.id)c.id='qa-theme-control';return '#'+c.id;})()'''

report = {'project_dir': str(root), 'mode': a.mode, 'environment': 'Qt offscreen WebEngine, network blocked, real Qt mouse/keyboard events; not native KDE',
          'file_sha256': {k: hashlib.sha256(v).hexdigest() for k, v in sorted(files.items())}, 'samples': [], 'errors': []}
baseline = None
if a.baseline_dir:
    import re
    from html.parser import HTMLParser
    class Text(HTMLParser):
        def __init__(self): super().__init__(); self.words = []; self.skip = 0
        def handle_starttag(self, t, _):
            if t in ('script', 'style', 'head'): self.skip += 1
        def handle_endtag(self, t):
            if t in ('script', 'style', 'head'): self.skip = max(0, self.skip - 1)
        def handle_data(self, d):
            if not self.skip and d.strip(): self.words.append(re.sub(r'\s+', ' ', d.strip()))
    parser = Text(); parser.feed((a.baseline_dir / 'index.html').read_text()); baseline = parser.words
try:
    for width in (1280, 480):
        if not load(width): report['errors'].append('page did not load at %d' % width); continue
        initial = json.loads(js(STATE)); sample = {'width': width, 'initial': initial}
        if initial['overflow']: report['errors'].append('%dpx horizontal overflow' % width)
        if baseline:
            missing = [t for t in baseline if t.casefold() not in initial['text'].casefold()]
            if missing: report['errors'].append('%dpx baseline text missing: %s' % (width, missing[:5]))
        if a.mode == 'theme':
            selector = js(THEME_SELECTOR)
            if not selector: report['errors'].append('%dpx no theme control' % width); report['samples'].append(sample); continue
            sample['on'] = click(selector); sample['after_on'] = json.loads(js(STATE))
            sample['off'] = click(selector); sample['after_off'] = json.loads(js(STATE))
            changed = sample['after_on']['surfaces'] != initial['surfaces'] or sample['after_on']['body_class'] != initial['body_class']
            restored = sample['after_off']['surfaces'] == initial['surfaces'] and sample['after_off']['body_class'] == initial['body_class']
            sample['theme_changed_on'] = changed and sample['on']['clicked']; sample['theme_restored_off'] = restored and sample['off']['clicked']
            if not sample['theme_changed_on']: report['errors'].append('%dpx theme did not change on first activation' % width)
            if not sample['theme_restored_off']: report['errors'].append('%dpx theme did not restore on second activation' % width)
            import re
            for state in ('initial', 'after_on', 'after_off'):
                s = sample[state]
                if not any(re.search(r'login|sign.?in|دخول', c['label'], re.I) for c in s['controls']): report['errors'].append('%dpx %s Login missing' % (width, state))
                if [c for c in s['controls'] if c['tag'] == 'a'] != [c for c in initial['controls'] if c['tag'] == 'a']: report['errors'].append('%dpx %s links changed' % (width, state))
        else:
            target = view.focusProxy() or view
            def active():
                return json.loads(js('JSON.stringify((()=>{const e=document.activeElement;return {id:e&&e.id,cls:e&&e.className,cat:e&&e.dataset&&e.dataset.category,focus_visible:!!e&&e!==document.body&&e.matches(":focus-visible"),outline:e?getComputedStyle(e).outlineStyle+" "+getComputedStyle(e).outlineWidth:null,shadow:e?getComputedStyle(e).boxShadow:null}})())'))
            def cards():
                return json.loads(js('JSON.stringify({visible:Array.from(document.querySelectorAll("#service-list .service-card")).filter(e=>e.getClientRects().length&&getComputedStyle(e).display!=="none"&&!e.hidden).map(e=>e.dataset.category),total:document.querySelectorAll("#service-list .service-card").length,pressed:Array.from(document.querySelectorAll(".service-filter")).map(b=>[b.dataset.category,b.getAttribute("aria-pressed")]),count:(document.getElementById("service-count")||{}).textContent||null})'))
            sample['cards_initial'] = cards(); tabs = []; chosen = None
            for _ in range(30):
                QTest.keyClick(target, Qt.Key_Tab); pump(.15); now = active(); tabs.append(now)
                if now.get('cat') and now['cat'] != 'all': chosen = now; break
            sample['tab_path'] = tabs
            if not chosen: report['errors'].append('%dpx keyboard Tab never reached a category filter' % width); report['samples'].append(sample); continue
            if not chosen['focus_visible'] or (chosen['outline'].startswith('none') and chosen['shadow'] in (None, 'none')): report['errors'].append('%dpx focused filter has no visible focus indicator' % width)
            QTest.keyClick(target, Qt.Key_Space); pump(.4); sample['cards_after_space'] = cards(); sample['chosen'] = chosen['cat']
            vis = sample['cards_after_space']['visible']
            if not vis or any(c != chosen['cat'] for c in vis) or len(vis) >= sample['cards_initial']['total']: report['errors'].append('%dpx Space on filter %s did not filter cards: %s' % (width, chosen['cat'], vis))
            if dict(sample['cards_after_space']['pressed']).get(chosen['cat']) != 'true': report['errors'].append('%dpx filter aria-pressed not true after Space' % width)
            for _ in range(30):
                QTest.keyClick(target, Qt.Key_Tab, Qt.ShiftModifier); pump(.15); now = active()
                if now.get('cat') == 'all': break
            QTest.keyClick(target, Qt.Key_Return); pump(.4); sample['cards_after_enter_all'] = cards()
            if len(sample['cards_after_enter_all']['visible']) != sample['cards_initial']['total']: report['errors'].append('%dpx Enter on «الكل» did not restore all cards' % width)
        report['samples'].append(sample)
except Exception as exc:
    report['errors'].append('%s: %s' % (type(exc).__name__, exc))
report['status'] = 'failed' if report['errors'] else 'passed'
a.output.write_text(json.dumps(report, ensure_ascii=False, indent=1)); print(json.dumps({'status': report['status'], 'errors': report['errors']}, ensure_ascii=False))
server.shutdown(); sys.exit(0 if report['status'] == 'passed' else 1)
