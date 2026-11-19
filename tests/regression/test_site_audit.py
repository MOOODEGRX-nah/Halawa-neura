"""WEB13/WEB14: measured performance findings and truthful metadata for saved static sites."""
import json

from fastapi.testclient import TestClient

from src.core.site_audit import apply_metadata, metadata_plan, performance
from tests.regression.test_chat_dispatch import application

H = {'X-Neura-Token': 'test-token'}
PAGE = ('<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>قديم</title>'
        '<script src="app.js"></script><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cairo"></head>'
        '<body><h1>مرحبا</h1><img src="a.png" alt=""><img src="b.png" alt="" width="10" height="10"></body></html>')


def test_performance_is_measured_from_source_with_named_fixes():
    files = {'index.html': PAGE, 'app.js': 'setInterval(()=>{},100);', 'style.css': '@import "x.css"; @keyframes a{}', 'a.png': b'\x89PNG' + b'0' * 250_000}
    report = performance(files, 'index.html')
    measured = report['measured']
    assert measured['bytes_by_kind']['image'] == 250_004 and measured['images'] == 2 and measured['images_without_dimensions'] == 1
    assert measured['render_blocking_scripts'] == ['app.js'] and measured['js_timers'] == 1 and measured['css_imports'] == 1
    assert {'image_weight', 'image_dimensions', 'lazy_images', 'blocking_scripts', 'css_imports', 'external_fonts'} <= set(report['advice'])
    assert 'ليست درجة سرعة' in report['environment'] and all(f['fix'] for f in report['findings'] if not f['ok'])


def test_metadata_uses_only_supplied_facts_and_never_overwrites_by_default():
    plan = metadata_plan({'index.html': PAGE}, 'index.html', {'name': 'مقهى الورد', 'description': 'قهوة مختصة في الرياض', 'url': 'javascript:alert(1)'})
    names = [t['name'] for t in plan['suggested']]
    assert 'og:url' not in names and plan['json_ld']['name'] == 'مقهى الورد' and 'مفهرس' in plan['note']
    markup, changes = apply_metadata(PAGE, plan)
    assert '<title>قديم</title>' in markup and 'title' not in changes
    assert 'name="description" content="قهوة مختصة في الرياض"' in markup and 'application/ld+json' in markup
    again, more = apply_metadata(markup, plan)
    assert more == [] and again == markup
    replaced, changed = apply_metadata(markup, plan, replace=True)
    assert '<title>مقهى الورد</title>' in replaced and 'title' in changed
    hostile = metadata_plan({'index.html': PAGE}, 'index.html', {'name': '</script><script>alert(1)</script>'})
    out, _ = apply_metadata(PAGE, hostile)
    assert '<script>alert(1)' not in out


def test_audit_and_metadata_api_save_evidence_and_new_revision(system, tmp_path):
    app, desktop, dispatch = application(system)
    store = app.state.project_store
    pid = store.create('مقهى', 'موقع مقهى عربي')['project_id']
    store.commit(pid, {'index.html': PAGE, 'app.js': 'console.log(1)', 'a.png': b'\x89PNG0', 'b.png': b'\x89PNG0'}, 0)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        report = client.get('/projects/' + pid + '/audit', headers=H).json()
        assert report['revision'] == 1 and report['performance']['measured']['images'] == 2
        evidence = json.loads(open(report['evidence'], encoding='utf-8').read())
        assert evidence['performance']['entry'] == 'index.html'
        assert client.post('/projects/' + pid + '/metadata', json={'expected_revision': 1}, headers=H).status_code == 422
        applied = client.post('/projects/' + pid + '/metadata', json={'expected_revision': 1, 'name': 'مقهى الورد', 'description': 'قهوة مختصة'}, headers=H).json()
        assert applied['revision'] == 2 and 'description' in applied['changed']
        assert client.post('/projects/' + pid + '/metadata', json={'expected_revision': 1, 'name': 'x'}, headers=H).status_code == 409
        assert 'og:title' in store.read(pid, 'index.html')['content']
    store.close()
