"""Held-out request forms and one admission contract across real job boundaries."""
import json,threading,time
import pytest
from src.core.feature_intent import build_contract,contract_features
from src.core.edit_preservation import requested_web_features,require_preserved
from src.core.project_store import digest
from src.core.project_files import ProjectError
from tests.regression.test_chat_dispatch import application,request_id
from tests.regression.test_project_jobs import wait

SOURCE='<html><head></head><body><h1>Owned CV</h1></body></html>'

@pytest.mark.parametrize('text,feature',[
 ('هل يمكنك أن تضيف الوضع الداكن إلى هذا المشروع؟','theme'),
 ('اجعل الموقع يدعم الوضع الداكن','theme'),
 ('أريد زرًا لتبديل الوضع الداكن','theme'),
 ('هل يمكنك إضافة زر تسجيل دخول؟','login'),
 ('لو سمحت ضيف لي زر تسجيل الدخول','login'),
 ('ابغى تضيف لي الوضع الليلي','theme'),
 ('خلي الموقع فيه الوضع الداكن','theme'),
 ('ممكن تضيفلي زر تسجيل الدخول','login'),
])
def test_held_out_composer_dispatch_passes_one_contract_to_job_stages(system,text,feature):
    app,_,dispatch=application(system);store=app.state.project_store;jobs=app.state.project_jobs
    try:
        pid=store.create('Owned CV','Fixture')['project_id'];store.commit(pid,{'index.html':SOURCE},0)
        dispatch.bind_project('qa-held-out',pid)
        payload={'base_revision':1,'path':'index.html','source_sha256':digest(SOURCE),'edits':[],'new_content':None}
        if feature=='theme':payload['interaction']='theme'
        else:payload['html_fragment']='<button type="button">Login</button>'
        system.backend.text=json.dumps(payload)
        rid=request_id();response=dispatch.dispatch(text,rid,session_id='qa-held-out')
        assert response['kind']=='project',response
        job=wait(jobs,response['job']['job_id']);assert job['state']=='completed',job
        contract=job['invoice']['required_feature_contract']
        assert contract['required']=={feature:True}
        assert contract['provenance']['source_turn_id']==rid and contract['provenance']['session_id']=='qa-held-out'
        assert response['decision']['required_feature_contract']==contract
        assert job['execution']['required_feature_contract']==contract
        assert job['validation']['required_feature_contract']==contract
        assert all(s['result']['required_feature_contract']==contract for s in job['stage_results'] if s['stage'] in ('planning','generating'))
        saved=store.get(pid)['accepted_requirements'][-1]
        assert saved['feature_contract']==contract
        for call in system.backend.calls:
            if call['messages'][0]['content'].startswith(('Return ONLY a compact','Return a bounded')):
                assert json.loads(call['messages'][1]['content'])['required_feature_contract']==contract
    finally:jobs.shutdown();store.close()


@pytest.mark.parametrize('text',['الوضع الداكن مفيد','هل الوضع الداكن موجود؟','لا تضف الوضع الداكن','لا تحذف الوضع الداكن','كيف يمكنني إضافة زر تسجيل دخول؟','"أريد زرًا لتبديل الوضع الداكن"','مثال: هل يمكنك إضافة زر تسجيل دخول؟'])
def test_mention_negation_explanation_quote_do_not_authorize_job(system,text):
    app,_,dispatch=application(system)
    try:
        pid=app.state.project_store.create('Owned','Fixture')['project_id']
        app.state.project_store.commit(pid,{'index.html':SOURCE},0);dispatch.bind_project('qa-negative',pid)
        value=dispatch.dispatch(text,request_id(),session_id='qa-negative')
        assert value['kind']!='project'
        assert app.state.project_store.db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]==0
        assert not system.backend.calls
    finally:app.state.project_jobs.shutdown();app.state.project_store.close()


def test_accepted_contract_survives_redesign_and_explicit_removal_without_reclassification(monkeypatch):
    decision={'intent':'project.edit','resolution_source':'validated_user_dispatch'}
    text='هل يمكنك إضافة زر تسجيل دخول؟';login=build_contract(text,[],decision)
    history=[{'origin':'user_request','text':text,'feature_contract':login}]
    text='أريد زرًا لتبديل الوضع الداكن';both=build_contract(text,history,decision)
    history.append({'origin':'user_request','text':text,'feature_contract':both})
    redesigned=build_contract('حسن واجهة الموقع',history,decision)
    assert redesigned['required']=={'login':True,'theme':True} and redesigned['changes']==[]
    remove=build_contract('هل يمكنك إزالة زر تسجيل الدخول؟',history,decision)
    assert remove['required']=={'theme':True} and remove['changes'][0]['operation']=='remove'
    before={'index.html':'<h1>Dark career</h1><button>Login</button><button>Theme</button>'}
    after={'index.html':'<h1>Dark career</h1><button>Theme</button>'}
    assert require_preserved(before,after,'هل يمكنك إزالة زر تسجيل الدخول؟',remove)['status']=='passed'
    with pytest.raises(ProjectError):require_preserved(before,{'index.html':'<button>Theme</button>'},'هل يمكنك إزالة زر تسجيل الدخول؟',remove)
    monkeypatch.setattr('src.core.feature_intent.feature_intents',lambda *_:(_ for _ in ()).throw(AssertionError('Downstream reclassification')))
    assert requested_web_features(redesigned)=={'login':True,'theme':True}
    assert contract_features(remove)=={'theme':True}


def test_client_cannot_supply_a_weaker_contract(system):
    app,_,_=application(system);store=app.state.project_store;jobs=app.state.project_jobs
    try:
        pid=store.create('Owned','Fixture')['project_id'];store.commit(pid,{'index.html':SOURCE},0)
        system.backend.text=json.dumps({'base_revision':1,'path':'index.html','source_sha256':digest(SOURCE),'edits':[],'interaction':'theme'})
        created=jobs.create({'user_request':'أريد زرًا لتبديل الوضع الداكن','requirements':['Model says no theme needed'],'project_id':pid,'expected_revision':1,'context_files':['index.html'],'required_feature_contract':{'required':{}}})
        job=wait(jobs,created['job']['job_id'])
        assert job['invoice']['required_feature_contract']['required']=={'theme':True}
    finally:jobs.shutdown();store.close()


def test_repair_receives_the_same_user_contract(system):
    from src.core.invoice_orchestrator import InvoiceOrchestrator,ProjectRequest
    from src.core.repair_targets import RepairTargets
    contract=build_contract('أريد زرًا لتبديل الوضع الداكن',[],{'intent':'project.edit'})
    files={'index.html':'<p>CV</p>'};targets=RepairTargets(files)
    system.backend.text=json.dumps({'edits':[{'target_id':next(iter(targets.targets)),'after':'<p>CV</p>\n'}]})
    InvoiceOrchestrator(system).repair_candidate(files,ProjectRequest(user_request='أريد زرًا لتبديل الوضع الداكن',requirements=['Keep source'],required_feature_contract=contract),'fixture',{},cancel=threading.Event(),deadline=time.monotonic()+3,max_tokens=256)
    assert json.loads(system.backend.calls[-1]['messages'][1]['content'])['required_feature_contract']==contract


@pytest.mark.parametrize('text',['احذف Login','هل يمكنك إزالة زر تسجيل الدخول؟','هل يمكنك حذف زر تسجيل الدخول؟','أزل زر تسجيل الدخول','Remove Login'])
def test_explicit_removal_variants_use_validated_job_admission(system,text):
    from src.core.chat_dispatch import active_edit_intent
    assert active_edit_intent(text)
    app,_,dispatch=application(system);store=app.state.project_store;jobs=app.state.project_jobs
    source=SOURCE.replace('</body>','<button>Login</button></body>')
    try:
        pid=store.create('Owned','Fixture')['project_id']
        store.commit(pid,{'index.html':source},0,accepted_requirements=[{'origin':'user_request','text':'أضف زر تسجيل دخول'}])
        dispatch.bind_project('qa-removal',pid)
        system.backend.text=json.dumps({'base_revision':1,'path':'index.html','source_sha256':digest(source),'edits':[{'before':'<button>Login</button>','after':''}],'new_content':None})
        result=dispatch.dispatch(text,request_id(),session_id='qa-removal');assert result['kind']=='project'
        job=wait(jobs,result['job']['job_id']);assert job['state']=='completed',job
        contract=job['invoice']['required_feature_contract']
        assert contract['prior_required']=={'login':True} and contract['required']=={}
        assert contract['changes'][0]['operation']=='remove'
        assert 'Login' not in store.read(pid,'index.html')['content']
    finally:jobs.shutdown();store.close()


@pytest.mark.parametrize('text',['لا تحذف Login','اشرح إزالة زر تسجيل الدخول','"هل يمكنك إزالة زر تسجيل الدخول؟"','هل حذف زر تسجيل الدخول آمن؟'])
def test_removal_normalization_does_not_authorize_mentions_or_negation(text):
    from src.core.chat_dispatch import active_edit_intent
    assert not active_edit_intent(text)
