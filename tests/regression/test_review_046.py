"""Independent-review regressions: real contracts, fake inference, owned files."""
import json
import time
import threading
from urllib.request import urlopen
from urllib.error import HTTPError
import pytest
from src.core.chat_dispatch import project_intent,active_edit_intent
from src.core.project_store import ProjectStore
from src.core.project_preview import PreviewServer
from src.core.project_files import Conflict
from src.core.invoice_orchestrator import InvoiceOrchestrator,ProjectRequest
from tests.regression.test_chat_dispatch import application,request_id

PLAN=json.dumps({'steps':['Define the required inputs.','Implement the requested files.','Statically validate the files.'],'files':['main.py']})
GOOD='```python main.py\ndef add(a,b):\n    return a+b\n```'

@pytest.mark.parametrize('text',['برمج لي لعبة XO','برمج لي لعبة ثعبان باستخدام Python','اكتب لي كود Python لحساب المصروفات','Create a game of tic tac toe','Write a Python script for expenses'])
def test_creation_variants_dispatch_one_job(system,text):
    assert project_intent(text)
    system.backend.text=GOOD
    app,desktop,dispatch=application(system)
    try:
        rid=request_id();value=dispatch.dispatch(text,rid)
        assert value['kind']=='project'
        assert dispatch.dispatch(text,rid)['job']['job_id']==value['job']['job_id']
        assert len(app.state.project_store.list())==1
        assert app.state.project_store.db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]==1
        assert not desktop.calls
    finally:app.state.project_jobs.shutdown();app.state.project_store.close()

@pytest.mark.parametrize('text',['أضف زر تسجيل دخول','أضف الوضع الداكن إلى هذا المشروع','Add a login button','Enable dark mode in this project'])
def test_current_project_additions_use_actual_source(system,text):
    assert active_edit_intent(text)
    app,desktop,dispatch=application(system);store=app.state.project_store
    try:
        pid=store.create('QA site','Owned current source')['project_id']
        store.commit(pid,{'index.html':'<h1 id="actual-source">Current source</h1>'},0)
        system.backend.text='```html index.html\n<h1 id="actual-source">Current source</h1><button>Login</button>\n```'
        rid=request_id();value=dispatch.dispatch(text,rid,pid)
        assert value['kind']=='project' and value['operation']=='edit' and value['project']['project_id']==pid
        assert dispatch.dispatch(text,rid,pid)['job']['job_id']==value['job']['job_id']
        end=time.monotonic()+3
        while time.monotonic()<end:
            job=app.state.project_jobs.get(value['job']['job_id'])
            if job['state'] in ('completed','failed','cancelled'):break
            time.sleep(.005)
        assert job['state']=='completed',job
        assert 'actual-source' in str(system.backend.calls[0]['messages'])
        assert len(store.list())==1 and not desktop.calls
    finally:app.state.project_jobs.shutdown();store.close()

@pytest.mark.parametrize('text',['اشرح كيف أبرمج لعبة XO','لا تبرمج لي لعبة XO','"برمج لي لعبة XO"','```اكتب لي كود Python```','لا تضف زر تسجيل دخول','Explain how to add a login button'])
def test_creation_and_edit_examples_never_authorize_jobs(system,text):
    app,desktop,dispatch=application(system)
    try:
        assert dispatch.dispatch(text,request_id())=={'kind':'chat'}
        assert not app.state.project_store.list() and not system.backend.calls and not desktop.calls
    finally:app.state.project_jobs.shutdown();app.state.project_store.close()

def test_edit_without_unique_current_project_does_not_create_job(system):
    app,_,dispatch=application(system);store=app.state.project_store
    try:
        for name in ['First','Second']:store.create(name,'QA')
        value=dispatch.dispatch('أضف زر تسجيل دخول',request_id())
        assert value['kind']=='clarification' and len(value['choices'])==2
        assert store.db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]==0
    finally:app.state.project_jobs.shutdown();store.close()

@pytest.mark.parametrize('legacy',[False,True])
def test_truncated_required_plan_never_reaches_coder(system,legacy):
    system.backend.plan_replies=[PLAN]
    system.backend.replies=[GOOD]
    original=system.complete
    def completion(*args,**options):
        system.backend.finish='length'
        try:return original(*args,**options)
        finally:system.backend.finish='stop'
    system.complete=completion
    req={'user_request':'Create addition with a complete plan','requirements':['complete plan and main.py'],'plan':True,'required_files':['main.py']}
    if legacy:
        result=InvoiceOrchestrator(system).process_request(req)
        assert not result['success'] and result['error_code']=='incomplete_plan'
    else:
        app,_,_=application(system);jobs=app.state.project_jobs;store=app.state.project_store
        try:
            created=jobs.create(req);jid=created['job']['job_id'];end=time.monotonic()+3
            while time.monotonic()<end:
                result=jobs.get(jid)
                if result['state'] in ('completed','failed','cancelled'):break
                time.sleep(.005)
            assert result['state']=='failed' and not result['saved_files']
            stage=next(s for s in result['stage_results'] if s['stage']=='planning')
            assert stage['status']=='failed' and stage['result']['finish_reason']=='length'
            assert stage['result']['accepted'] is False
        finally:jobs.shutdown();store.close()
    assert len(system.backend.calls)==1,'Coder must not run after an incomplete required plan'

def test_preview_never_labels_new_snapshot_as_old_revision(tmp_path,monkeypatch):
    store=ProjectStore(tmp_path);preview=PreviewServer(store)
    try:
        pid=store.create('QA preview','Owned race fixture')['project_id']
        old='<h1>OLD</h1>';new='<h1>NEW</h1>'
        store.commit(pid,{'index.html':old},0);original=store.committed_files
        def interleaving(ident):
            monkeypatch.setattr(store,'committed_files',original)
            store.commit(ident,{'index.html':new},1)
            return original(ident)
        monkeypatch.setattr(store,'committed_files',interleaving)
        try:value=preview.issue(pid,'http://127.0.0.1:8000',1)
        except Conflict:return
        with urlopen(value['url'],timeout=3) as response:body=response.read().decode()
        assert value['revision']==1 and body==old
    finally:preview.stop();store.close()


@pytest.mark.parametrize('raw,finish,accepted',[(PLAN,'stop',True),(PLAN,'length',False),('Use a file.','stop',False),('{"steps":["one"],"files":["main.py"]}','stop',False),(PLAN.replace('main.py','../unsafe.py'),'stop',False)])
def test_required_plan_contract_is_explicit(raw,finish,accepted):
    request=ProjectRequest(user_request='Build addition',requirements=['main.py'],required_files=['main.py'])
    result=InvoiceOrchestrator.inspect_plan({'choices':[{'message':{'content':raw},'finish_reason':finish}]},request)
    assert result['accepted'] is accepted
    if not accepted:assert result['validation_errors']


def test_failed_planning_edit_preserves_last_good_revision(system):
    app,_,_=application(system);store=app.state.project_store;jobs=app.state.project_jobs
    pid=store.create('Existing','Owned last-good fixture')['project_id'];store.commit(pid,{'main.py':'def add(a,b): return a+b\n'},0)
    before=store.get(pid);system.backend.text=PLAN;system.backend.finish='length'
    try:
        created=jobs.create({'user_request':'Plan and improve existing addition','requirements':['Keep add'],'plan':True,'project_id':pid,'expected_revision':1,'context_files':['main.py']})
        end=time.monotonic()+3
        while time.monotonic()<end:
            job=jobs.get(created['job']['job_id'])
            if job['state'] in ('completed','failed','cancelled'):break
            time.sleep(.005)
        assert job['state']=='failed' and not job['saved_files']
        assert store.get(pid)['project_revision']==1 and store.get(pid)['files']==before['files']
        assert len(system.backend.calls)==1
    finally:jobs.shutdown();store.close()


@pytest.mark.parametrize('change_assets',[False,True])
def test_concurrent_commit_keeps_preview_bytes_and_asset_manifest_bound(tmp_path,monkeypatch,change_assets):
    store=ProjectStore(tmp_path);preview=PreviewServer(store);inspected=threading.Event();attempt=threading.Event();done=threading.Event();failures=[]
    pid=store.create('QA concurrent preview','Owned two-writer fixture')['project_id']
    old={'index.html':'<link rel="stylesheet" href="old.css"><h1>OLD</h1>','old.css':'h1{color:red}'}
    new={'index.html':'<link rel="stylesheet" href="new.css"><h1>NEW</h1>','new.css':'h1{color:blue}'} if change_assets else {**old,'index.html':'<h1>NEW</h1>'}
    store.commit(pid,old,0);original=store.get
    def writer():
        try:
            assert inspected.wait(3);attempt.set();store.commit(pid,new,1)
        except BaseException as exc:failures.append(str(exc))
        finally:done.set()
    def observed(ident,*args,**kwargs):
        meta=original(ident,*args,**kwargs)
        if threading.current_thread() is threading.main_thread() and not inspected.is_set():
            inspected.set();assert attempt.wait(3)
        return meta
    monkeypatch.setattr(store,'get',observed);thread=threading.Thread(target=writer);thread.start()
    try:
        issued=preview.issue(pid,'http://127.0.0.1:8000',1)
        assert done.wait(3) and not failures
        for consumer in ('embedded','full-page'):
            with urlopen(issued['url'],timeout=3) as response:assert response.read().decode()==old['index.html'],consumer
        with urlopen(issued['url'].replace('index.html','old.css'),timeout=3) as response:assert response.read().decode()==old['old.css']
        if change_assets:
            with pytest.raises(HTTPError):urlopen(issued['url'].replace('index.html','new.css'),timeout=3)
        with pytest.raises(Conflict):preview.issue(pid,'http://127.0.0.1:8000',1)
        current=preview.issue(pid,'http://127.0.0.1:8000',2)
        with urlopen(current['url'],timeout=3) as response:assert response.read().decode()==new['index.html']
    finally:inspected.set();thread.join(3);preview.stop();store.close()
