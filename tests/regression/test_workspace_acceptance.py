import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
import pytest
from src.core.project_files import ProjectError,SafeTree
from src.core.project_store import ProjectStore
from src.core.source_syntax import javascript,css
from src.desktop.actions import DesktopAdapter
from src.desktop.paths import setup_preview_environment,DesktopSettings
from tests.regression.test_project_store import WEB


def test_invalid_js_css_never_replace_last_good_preview(tmp_path):
    store=ProjectStore(tmp_path);p=store.create('CV','CV')['project_id'];store.commit(p,WEB,0)
    for path,broken in [('style.css','h1 { color: red'),('script.js','function broken( {')]:
        opened=store.read(p,path)
        with pytest.raises(ProjectError):store.save_file(p,path,broken,1,opened['sha256'])
        assert store.get(p)['project_revision']==1
        assert store.read(p,path)['content']==WEB[path]
        assert store.get(p)['preview']['supported']
    assert javascript('process.exit(); throw new Error("not executed");')=={'build_required':False}
    css('body { --color: #123; color: var(--color); background: url("data:image/svg+xml,<svg>{}</svg>"); }')
    store.close()


def test_build_dependent_sources_are_saved_without_running_builds(tmp_path):
    store=ProjectStore(tmp_path);p=store.create('React','React')['project_id']
    marker=tmp_path/'build-ran'
    files={'index.html':'<script type="module" src="app.js"></script>',
           'app.js':'import React from "react"; export default ()=> <h1>Hello</h1>;',
           'package.json':json.dumps({'dependencies':{'react':'*'},'scripts':{'build':'touch '+str(marker)}})}
    meta=store.commit(p,files,0)
    assert len(meta['files'])==3 and not meta['preview']['supported']
    assert not marker.exists()
    assert meta['validation']['executed'] is False
    store.close()


def test_inline_languages_and_invalid_inline_script(tmp_path):
    store=ProjectStore(tmp_path);p=store.create('Inline CV','CV')['project_id']
    html='<style>h1{color:red}</style><h1 style="margin:0" onclick="this.textContent=\'ok\'">CV</h1><script>const x=1;</script>'
    meta=store.commit(p,{'index.html':html},0)
    assert meta['languages']==['CSS','HTML','JavaScript']
    opened=store.read(p,'index.html')
    with pytest.raises(ProjectError):store.save_file(p,'index.html','<script>function broken( {</script>',1,opened['sha256'])
    assert store.read(p,'index.html')['content']==html
    store.close()


def test_write_failure_recovers_committed_revision(tmp_path,monkeypatch):
    store=ProjectStore(tmp_path);p=store.create('CV','CV')['project_id'];store.commit(p,WEB,0)
    write=SafeTree.write;failed=[False]
    def fail_once(self,path,data,**kwargs):
        if path=='style.css' and not failed[0]:failed[0]=True;raise OSError('simulated storage failure')
        return write(self,path,data,**kwargs)
    monkeypatch.setattr(SafeTree,'write',fail_once)
    with pytest.raises(OSError):store.commit(p,{**WEB,'index.html':WEB['index.html']+'changed','style.css':'h1{color:red}'},1)
    assert store.get(p)['project_revision']==1
    assert store.read(p,'index.html')['content']==WEB['index.html']
    assert store.read(p,'style.css')['content']==WEB['style.css']
    store.close()


def test_preview_profile_never_copies_production_tokens_or_grants(tmp_path,monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path/'config'))
    monkeypatch.setenv('XDG_DATA_HOME',str(tmp_path/'data'))
    monkeypatch.setenv('XDG_STATE_HOME',str(tmp_path/'state'))
    monkeypatch.setenv('NEURA_SETTINGS_DIR',str(tmp_path/'config/neura-ai'))
    monkeypatch.setenv('NEURA_DATA_DIR',str(tmp_path/'data/neura-ai'))
    monkeypatch.setenv('NEURA_STATE_DIR',str(tmp_path/'state/neura-ai'))
    monkeypatch.setenv('NEURA_PREVIEW','0')
    original=tmp_path/'config/neura-ai/settings.json'
    settings=DesktopSettings(original)
    settings.values.update(models_dir=str(tmp_path/'models'),dedicated_coder=True,check_updates=True,
        approved_locations={'l_'+'a'*32:{'path':str(tmp_path/'private.txt'),'kind':'file'}})
    settings.save();before=original.read_bytes()
    setup_preview_environment()
    preview=DesktopSettings()
    assert preview.values['models_dir']==str(tmp_path/'models') and preview.values['dedicated_coder']
    assert not preview.values['approved_locations'] and not preview.values['check_updates']
    assert os.environ['NEURA_DATA_DIR']==str(tmp_path/'data/neura-ai-preview')
    assert original.read_bytes()==before
    assert not (Path(os.environ['NEURA_DATA_DIR'])/'.api-token').exists()


def test_desktop_ack_does_not_wait_for_gui_child_exit(tmp_path,monkeypatch):
    store=ProjectStore(tmp_path);pidfile=tmp_path/'child.pid'
    code='import subprocess,sys; from pathlib import Path; p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(5)"]); Path(sys.argv[1]).write_text(str(p.pid))'
    def launcher(command,**kwargs):return subprocess.run([sys.executable,'-c',code,str(pidfile)],**kwargs)
    adapter=DesktopAdapter(store,settings={},runner=launcher)
    monkeypatch.setattr(adapter,'status',lambda:{'desktop_available':True})
    monkeypatch.setattr(adapter,'catalog',lambda:{'test.desktop':{'entry':'/trusted/test.desktop','name':'Test'}})
    start=time.monotonic()
    try:
        assert adapter.launch('test.desktop')['status']=='launched'
        assert time.monotonic()-start<2
    finally:
        if pidfile.exists():
            try:os.kill(int(pidfile.read_text()),15)
            except ProcessLookupError:pass
        store.close()
