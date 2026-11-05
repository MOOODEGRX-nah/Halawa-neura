"""AX deterministic contracts. Fake model/desktop/browser, real state/dispatch/store."""
import json
import time
from pathlib import Path
import pytest
from src.core.chat_dispatch import ChatDispatcher
from src.core.project_files import Conflict
from src.core.project_conversation import ProjectDecision
from src.core.edit_preservation import preservation_errors
from tests.regression.test_chat_dispatch import application,request_id

CASES=json.loads((Path(__file__).parents[1]/'fixtures/accuracy_v1.json').read_text())['cases']
BASE='<html><h1>QA CV</h1><p>Original content</p><a href="#" id="login">Login</a></html>\n'
GOOD='```html index.html\n'+BASE.replace('</html>','<style>body{color:#111;background:white}</style></html>')+'```'


def wait(jobs,jid):
    end=time.monotonic()+4
    while time.monotonic()<end:
        value=jobs.get(jid)
        if value['state'] in ('completed','failed','cancelled'):return value
        time.sleep(.005)
    raise AssertionError('job timeout')


def setup(system):
    app,desktop,dispatch=application(system);store=app.state.project_store
    pid=store.create('QA CV','Original CV')['project_id'];store.commit(pid,{'index.html':BASE},0)
    dispatch.bind_project('qa',pid);system.backend.text=GOOD
    return app,desktop,dispatch,pid


@pytest.mark.parametrize('case',CASES,ids=[c['id']+'-'+c['split'] for c in CASES])
def test_accuracy_v1(system,case):
    app,desktop,dispatch,pid=setup(system)
    try:
        result=dispatch.dispatch(case['text'],request_id(),session_id='qa')
        actual='edit' if result['kind']=='project' and result.get('operation')=='edit' else 'create' if result['kind']=='project' else 'website' if result.get('skill')=='open_website' else result['kind']
        assert actual==case['expected'],{'actual':actual,'result':result,'expected':case['expected']}
        if case['expected']=='edit':assert result['project']['project_id']==pid
        if case['expected']=='create':assert result['project']['project_id']!=pid
        if case['expected'] in ('chat','status'):
            assert not system.backend.calls and not desktop.calls
            assert app.state.project_store.get(pid)['project_revision']==1
        if result['kind']=='project':wait(app.state.project_jobs,result['job']['job_id'])
    finally:app.state.project_jobs.shutdown();app.state.project_store.close()


@pytest.mark.parametrize('language',['ar','en'])
@pytest.mark.parametrize('scenario',['direct_yes','absent','expired','wrong_session','restart','rejected','changed_revision','duplicate','complaint','switch','dirty','no_change'])
def test_multiturn_24(system,language,scenario):
    app,desktop,dispatch,pid=setup(system);store=app.state.project_store;jobs=app.state.project_jobs
    approve='نعم' if language=='ar' else 'yes';edit='حسن واجهة الموقع' if language=='ar' else 'Improve this website'
    try:
        if scenario not in ('direct_yes','absent','complaint','dirty','no_change'):
            dispatch.conversations.propose('qa',pid,edit)
        if scenario=='expired':store.db.execute('UPDATE project_proposals SET expires=0');store.db.commit()
        if scenario=='wrong_session':session='other'
        else:session='qa'
        if scenario=='restart':dispatch=ChatDispatcher(store,app.state.desktop_skills,jobs)
        if scenario=='rejected':dispatch.dispatch('لا' if language=='ar' else 'no',request_id(),session_id='qa')
        if scenario=='changed_revision':store.save_file(pid,'index.html',BASE+'<!-- local -->',1,store.get(pid)['files'][0]['sha256'])
        if scenario=='switch':
            other=store.create('Other','Other')['project_id'];store.commit(other,{'index.html':BASE},0);dispatch.bind_project('qa',other)
        if scenario in ('direct_yes','complaint','dirty','no_change'):
            if scenario=='no_change':system.backend.text='```html index.html\n'+BASE+'```'
            first=dispatch.dispatch(edit,request_id(),session_id='qa',workspace_dirty=scenario=='dirty')
            if scenario=='dirty':assert first['kind']=='workspace'
            else:
                job=wait(jobs,first['job']['job_id']);assert job['state']=='completed',job
                if scenario=='no_change':assert job['execution']['outcome']=='no_change' and store.get(pid)['project_revision']==1
        rid=request_id()
        response=dispatch.dispatch('لم تفعل شي حتى الان؟' if scenario=='complaint' else approve,rid,session_id=session)
        if scenario=='duplicate':
            assert response['kind']=='project';jid=response['job']['job_id']
            assert dispatch.dispatch(approve,rid,session_id=session)['job']['job_id']==jid
            dispatch.dispatch(approve,request_id(),session_id=session);wait(jobs,jid)
        count=store.db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]
        assert count==(1 if scenario in ('direct_yes','complaint','duplicate','no_change') else 0)
        assert not desktop.calls
    finally:jobs.shutdown();store.close()


def test_semantic_candidate_has_no_execution_authority(system,monkeypatch):
    app,desktop,dispatch,pid=setup(system)
    try:
        monkeypatch.setattr(dispatch,'_semantic_decision',lambda text:ProjectDecision(intent='edit',reason='candidate'))
        result=dispatch.dispatch('واجهة مميزة تناسب العرض',request_id(),session_id='qa')
        assert result['kind']=='proposal' and not app.state.project_jobs.queue.qsize()
        accepted=dispatch.dispatch('طبقها',request_id(),session_id='qa');assert accepted['kind']=='project'
        assert wait(app.state.project_jobs,accepted['job']['job_id'])['state']=='completed'
    finally:app.state.project_jobs.shutdown();app.state.project_store.close()


def test_preservation_rejects_login_loss_and_keeps_revision(system):
    app,desktop,dispatch,pid=setup(system)
    try:
        system.backend.text='```html index.html\n<h1>QA CV</h1><button>Dark mode</button>\n```'
        result=dispatch.dispatch('أضف الوضع الداكن',request_id(),session_id='qa')
        job=wait(app.state.project_jobs,result['job']['job_id'])
        assert job['state']=='failed' and len(job['attempts'])==2
        assert app.state.project_store.get(pid)['project_revision']==1
        assert app.state.project_store.read(pid,'index.html')['content']==BASE
        assert all(x['status']=='rejected' for x in job['attempts'])
        assert not job['saved_files'] and not job['execution']
    finally:app.state.project_jobs.shutdown();app.state.project_store.close()


def test_scoped_removal_does_not_waive_other_controls():
    before={'index.html':'<a href="#">Login</a><button>Save</button>'}
    assert not preservation_errors(before,{'index.html':'<button>Save</button>'},'remove Login')
    assert preservation_errors(before,{'index.html':'<h1>None</h1>'},'remove Login')


def test_explicit_named_project_wins_and_unknown_name_does_not_edit_current(system):
    app,desktop,dispatch,pid=setup(system);store=app.state.project_store;jobs=app.state.project_jobs
    try:
        other=store.create('المتجر','Other')['project_id'];store.commit(other,{'index.html':BASE},0)
        result=dispatch.dispatch('حسن واجهة مشروع المتجر',request_id(),session_id='qa')
        assert result['kind']=='project' and result['project']['project_id']==other
        wait(jobs,result['job']['job_id']);assert store.get(pid)['project_revision']==1
        result=dispatch.dispatch('حسن واجهة مشروع مجهول',request_id(),session_id='qa')
        assert result['kind']=='clarification' and store.db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]==1
    finally:jobs.shutdown();store.close()


def test_context_choice_executes_original_request_without_retyping(system):
    app,desktop,dispatch,pid=setup(system);jobs=app.state.project_jobs
    try:
        result=dispatch.dispatch('حسن واجهة الموقع',request_id(),session_id='new_session')
        assert result['kind']=='clarification'
        created=dispatch.choose(result['request_id'],result['choices'][0]['id'],'new_session')
        assert created['kind']=='project' and created['project']['project_id']==pid
        assert wait(jobs,created['job']['job_id'])['state']=='completed'
    finally:jobs.shutdown();app.state.project_store.close()


def test_restart_recovers_committed_receipt_without_model_replay(system):
    from src.core.project_jobs import ProjectJobs
    app,desktop,dispatch,pid=setup(system);jobs=app.state.project_jobs;store=app.state.project_store
    try:
        value=dispatch.dispatch('حسن واجهة الموقع',request_id(),session_id='qa');jid=value['job']['job_id']
        final=wait(jobs,jid);jobs.shutdown();assert final['state']=='completed'
        store.db.execute("UPDATE jobs SET state='validating' WHERE id=?",(jid,))
        store.db.execute("UPDATE job_contracts SET result='{}' WHERE job_id=?",(jid,));store.db.commit()
        calls=len(system.backend.calls);restarted=ProjectJobs(store,system)
        assert restarted.get(jid)['state']=='completed'
        assert restarted.get(jid)['execution']==final['execution']
        assert len(system.backend.calls)==calls
        restarted.shutdown()
    finally:jobs.shutdown();store.close()


def test_plan_is_structured_read_only_and_rejects_wrong_step_count(system):
    app,desktop,dispatch,pid=setup(system)
    try:
        system.backend.plan_replies=[json.dumps({'steps':['حدد أقسام السيرة','صمم واجهة HTML','افحص العرض المحلي'],'files':['index.html']})]
        result=dispatch.dispatch('خطط لموقع سيرة ذاتية ثابت بثلاث خطوات مرقمة. بدون cloud وبدون تثبيت أي شيء.',request_id(),session_id='qa')
        assert result['kind']=='plan' and len(result['planning']['plan']['steps'])==3
        assert app.state.project_store.get(pid)['project_revision']==1
        assert system.backend.calls[-1]['response_format']['type']=='json_object'
        system.backend.plan_replies=[json.dumps({'steps':['one','two','three','four'],'files':['index.html']})]
        result=dispatch.dispatch('ضع خطة',request_id(),session_id='qa')
        assert result['kind']=='action' and result['result']['status']!='launched'
        assert not desktop.calls
    finally:app.state.project_jobs.shutdown();app.state.project_store.close()


@pytest.mark.parametrize('replacement,accepted',[
 ({'path':'index.html','before':'color:white;background:blue','after':'color:black;background:blue'},True),
 ({'path':'../outside.html','before':'color:white','after':'color:black'},False),
 ({'path':'other.html','before':'color:white','after':'color:black'},False),
 ({'path':'index.html','before':'missing','after':'color:black'},False),
])
def test_candidate_patch_is_bounded_to_rejected_source(system,replacement,accepted):
    import threading
    from src.core.invoice_orchestrator import InvoiceOrchestrator,ProjectRequest
    from src.core.project_files import ProjectError
    source={'index.html':'<p style="color:white;background:blue">Login</p>'}
    system.backend.text=json.dumps({'edits':[replacement]})
    invoice=InvoiceOrchestrator(system)
    def repair():return invoice.repair_candidate(source,ProjectRequest(user_request='Improve contrast',requirements=['Keep Login']),'contrast',{},cancel=threading.Event(),deadline=time.monotonic()+3,max_tokens=256)
    if accepted:
        candidate,result=repair();assert candidate['index.html']=='<p style="color:black;background:blue">Login</p>'
        assert 'color:white' in source['index.html'] and result['finish_reason']=='stop'
    else:
        with pytest.raises(ProjectError):repair()


def test_native_grammar_does_not_expand_large_strings_but_validation_remains():
    from src.core.invoice_orchestrator import generation_schema,CandidateRepairs
    from pydantic import ValidationError
    schema=generation_schema(CandidateRepairs)
    assert 'maxLength' not in json.dumps(schema)
    with pytest.raises(ValidationError):
        CandidateRepairs.model_validate({'edits':[{'path':'index.html','before':'x'*4001,'after':'y'}]})
