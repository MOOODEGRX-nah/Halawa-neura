"""WEB B3 first slice: advisory quality report on every saved static-web revision; never blocks."""
import json
from pathlib import Path
from src.core.web_quality import report
from src.core.project_store import ProjectStore

SERVICES=json.loads((Path(__file__).resolve().parents[1]/'fixtures/web_services.json').read_text())


def test_report_observes_metadata_structure_and_weight():
    r=report(SERVICES,'index.html')
    assert r['items']['title']['ok'] and r['items']['viewport']['ok'] and r['items']['charset']['ok'] and r['items']['single_h1']['ok']
    assert r['items']['lang_dir']['value']==['ar','rtl'] and r['items']['external_references']['ok'] and r['items']['inline_event_handlers']['ok']
    assert r['items']['meta_description']['ok'] and not r['advice'] and r['items']['page_weight_bytes']['value']==sum(len(v.encode()) for v in SERVICES.values())


def test_report_flags_problems_without_inventing_values():
    bad={'index.html':'<html><head><title>x</title></head><body><h1>a</h1><h1>b</h1><img src="https://cdn.example/a.png"><button onclick="go()">x</button></body></html>'}
    r=report(bad,'index.html')
    assert set(r['advice'])>={'title','meta_description','viewport','charset','lang_dir','single_h1','image_alt','external_references','inline_event_handlers'}
    assert r['items']['image_alt']['value']==[1,1] and r['items']['external_references']['value']==['https://cdn.example/a.png']
    assert report({'main.py':'print(1)'},None) is None


def test_quality_report_is_saved_with_revision_and_never_blocks(tmp_path):
    store=ProjectStore(tmp_path/'data')
    try:
        pid=store.create('Services','QA')['project_id']
        bare={'index.html':'<html><body><p>no metadata</p></body></html>'}
        meta=store.commit(pid,bare,0)
        assert meta['project_revision']==1 and 'title' in meta['validation']['quality']['advice']
        meta=store.commit(pid,SERVICES,1)
        assert meta['project_revision']==2 and meta['validation']['quality']['items']['title']['ok']
    finally:store.close()
