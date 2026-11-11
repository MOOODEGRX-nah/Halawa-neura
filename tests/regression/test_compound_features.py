"""Operation/target scope, admission and atomic candidate behavior; fake engine."""
import json
import pytest
from src.core.feature_intent import interpret_features,feature_intents,build_contract
from src.core.project_files import ProjectError
from tests.regression.test_chat_dispatch import application,request_id
from tests.regression.test_project_jobs import wait
from src.core.required_interactions import compile_theme

CASES=[
 ('احذف Login وأضف الوضع الداكن',[('login','remove'),('theme','add')]),
 ('أضف الوضع الداكن واحذف Login',[('theme','add'),('login','remove')]),
 ('Remove Login and add dark mode',[('login','remove'),('theme','add')]),
 ('Add dark mode and remove Login',[('theme','add'),('login','remove')]),
 ('احذف Login ولا تحذف الوضع الداكن',[('login','remove'),('theme','keep')]),
 ('لا تحذف الوضع الداكن واحذف Login',[('theme','keep'),('login','remove')]),
 ("Remove Login and don't remove dark mode",[('login','remove'),('theme','keep')]),
 ('هل يمكنك حذف Login ومن فضلك أضف الوضع الداكن؟',[('login','remove'),('theme','add')]),
 ('أَضِفْ الوضع الداكن وَاحْذِفْ Login',[('theme','add'),('login','remove')]),
 ('احذف Login وحافظ على الوضع الداكن',[('login','remove'),('theme','keep')]),
 ('أضف Login والوضع الداكن',[('login','add'),('theme','add')]),
 ('أضف الوضع الداكن وLogin',[('theme','add'),('login','add')]),
 ('أضف الوضع الداكن لموقع وادي',[('theme','add')]),
]

@pytest.mark.parametrize('text,expected',CASES)
def test_scoped_changes_and_raw_unicode_spans(text,expected):
    result=interpret_features(text)
    assert not result.issues,result.issues
    assert [(x.feature,x.operation) for x in result.changes]==expected
    for change in result.changes:
        a,b=change.source_span
        assert text[a:b]==change.evidence
        a,b=change.operation_span;assert text[a:b]
        a,b=change.feature_span;assert text[a:b]
    if 'ولا' in text:
        keep=result.changes[-1];assert keep.polarity=='negated'
        assert text[slice(*keep.operation_span)].startswith('لا')

@pytest.mark.parametrize('text',[
 'احذف Login وأضفه','أضف Login واحذف Login','احذف Login ولا تحذف Login',
 'Remove Login and keep Login','احذف Login واضف الزر الآخر',
 'أضف الوضع الداكن ولا تضف Login','احذف Login وواجهة الموقع',
 'احذف الوضع الداكن وأضف Login',
 'احذف البيانات وأضف الوضع الداكن','احذف Login وغير الوضع الداكن',
])
def test_ambiguous_compounds_clarify_before_any_job_and_cannot_approve_elsewhere(system,text):
    app,_,dispatch=application(system);store=app.state.project_store;jobs=app.state.project_jobs
    try:
        pid=store.create('CV','Fixture')['project_id'];source='<html><head></head><body><h1>Keep</h1><button>Login</button></body></html>'
        store.commit(pid,{'index.html':source},0);dispatch.bind_project('owner',pid)
        reply=dispatch.dispatch(text,request_id(),session_id='owner')
        assert reply['kind']=='clarification',reply
        assert store.db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]==0
        assert store.get(pid)['project_revision']==1 and not system.backend.calls
        assert dispatch.dispatch('نعم',request_id(),session_id='other')['kind']=='status'
        assert store.db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]==0
        with pytest.raises(ProjectError):jobs.create({'user_request':text,'requirements':[text]})
        assert len(store.list())==1
    finally:jobs.shutdown();store.close()

@pytest.mark.parametrize('text',['"احذف Login وأضف الوضع الداكن"','اشرح: احذف Login ولا تحذف الوضع الداكن','كيف أحذف Login وأضيف الوضع الداكن؟','لا تحذف Login','لا تضف الوضع الداكن'])
def test_quoted_explained_or_single_negated_requests_do_not_authorize_jobs(system,text):
    app,_,dispatch=application(system)
    try:
        assert dispatch.dispatch(text,request_id(),session_id='negative')['kind']!='project'
        assert app.state.project_store.db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]==0
    finally:app.state.project_jobs.shutdown();app.state.project_store.close()

@pytest.mark.parametrize('text',[CASES[i][0] for i in (0,1,2,4,5)])
def test_atomic_compound_edit_preserves_only_intended_features(system,text):
    app,_,dispatch=application(system);store=app.state.project_store;jobs=app.state.project_jobs
    try:
        files={'index.html':'<html><head></head><body><h1>Keep CV content</h1><button id="login">Login</button><script>document.getElementById("login").onclick=()=>alert("placeholder");</script></body></html>'}
        history=[{'origin':'user_request','text':'أضف Login'}]
        # keep requests start with both features; mixed adds start without theme.
        if any(x.operation=='keep' for x in feature_intents(text)):
            files,_=compile_theme(files,'index.html');history.append({'origin':'user_request','text':'أضف الوضع الداكن'})
        pid=store.create('CV','Fixture')['project_id'];store.commit(pid,files,0,accepted_requirements=history);dispatch.bind_project('compound',pid)
        def oracle(messages,options):
            packet=json.loads(messages[1]['content'])
            return json.dumps({'base_revision':packet['base_revision'],'path':packet['path'],'source_sha256':packet['source_sha256'],'edits':[],
                'target_edits':[{'target_id':s['target_id'],'after':''} for s in packet['source_spans'] if s['target_id']],
                'interaction':'theme' if packet['required_interaction'] and packet['at_eof'] else None})
        system.backend.text=oracle
        result=dispatch.dispatch(text,request_id(),session_id='compound');assert result['kind']=='project',result
        job=wait(jobs,result['job']['job_id']);assert job['state']=='completed',job
        contract=job['invoice']['required_feature_contract'];assert contract['required']=={'theme':True}
        assert {x['feature'] for x in contract['changes'] if x['operation']=='remove'}=={'login'}
        assert store.get(pid)['project_revision']==2
        saved=store.read(pid,'index.html')['content'];assert '>Login<' not in saved and 'getElementById("login")' not in saved
        assert 'Keep CV content' in saved and 'neura-theme-toggle' in saved
        # Persisted intent is authoritative for future redesign, not old text order.
        next_contract=build_contract('حسن واجهة الموقع',store.get(pid)['accepted_requirements'],{'intent':'project.edit'})
        assert next_contract['required']=={'theme':True} and not next_contract['changes']
    finally:jobs.shutdown();store.close()


def test_negated_theme_mention_cannot_waive_theme_source_preservation():
    from src.core.edit_preservation import require_preserved
    text='احذف Login ولا تحذف الوضع الداكن'
    contract=build_contract(text,[{'origin':'user_request','text':'أضف Login والوضع الداكن'}],{'intent':'project.edit'})
    before={'index.html':'<h1>CV</h1><button>Login</button><button>الوضع الداكن</button>'}
    with pytest.raises(ProjectError):require_preserved(before,{'index.html':'<h1>CV</h1>'},text,contract)
    assert require_preserved(before,{'index.html':'<h1>CV</h1><button>الوضع الداكن</button>'},text,contract)['status']=='passed'


def test_explicit_removal_persists_as_exclusion_until_explicit_user_add():
    from src.core.edit_preservation import require_preserved
    decision={'intent':'project.edit'};text='احذف Login ولا تحذف الوضع الداكن'
    history=[{'origin':'user_request','text':'أضف Login والوضع الداكن'}]
    removed=build_contract(text,history,decision);history.append({'origin':'user_request','text':text,'feature_contract':removed})
    for text in ['أضف الوضع الداكن','حسن واجهة الموقع']:
        contract=build_contract(text,history,decision)
        assert contract['required']=={'theme':True} and contract['excluded']=={'login':True}
        before={'index.html':'<h1>CV</h1><button>Theme</button>'}
        after={'index.html':'<h1>CV</h1><button>Theme</button><button>Login</button>'}
        with pytest.raises(ProjectError):require_preserved(before,after,text,contract)
        history.append({'origin':'user_request','text':text,'feature_contract':contract})
    added=build_contract('أضف Login',history,decision)
    assert added['required']=={'theme':True,'login':True} and added['excluded']=={}
