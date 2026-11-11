"""Scoped server IDs under controlled token/model boundaries; no native claims."""
import json
import pytest
from src.core.project_store import ProjectStore,digest
from src.core.project_jobs import ProjectJobs
from src.core.repair_targets import RepairTargets
from src.core.project_files import ProjectError
from tests.regression.test_project_jobs import wait


def setup(system,source):
    store=ProjectStore(system.settings.data_dir);pid=store.create('Owned CV','Owned source')['project_id']
    store.commit(pid,{'index.html':source},0,accepted_requirements=[{'origin':'user_request','text':'أضف زر تسجيل دخول'}])
    return store,ProjectJobs(store,system),pid


def request(jobs,pid):
    return jobs.create({'user_request':'هل يمكنك إزالة زر تسجيل الدخول؟','requirements':['Only remove Login, keep all other content'],'project_id':pid,'expected_revision':1,'context_files':['index.html'],'max_tokens':4096})['job']['job_id']


def reply(packet,edits):
    return json.dumps({'base_revision':packet['base_revision'],'path':packet['path'],'source_sha256':packet['source_sha256'],'edits':[],'target_edits':edits,'new_content':None})


def split_fixture(system):
    original=system.backend.measure_messages
    def measure(messages,max_tokens=1024,**options):
        if messages[0]['content'].startswith('Return a bounded source edit'):
            packet=json.loads(messages[1]['content']);size=sum(len(s['source']) for s in packet['source_spans'])
            # Deliberately synthetic fit boundary to force segmentation. These
            # values are NOT measured native tokens or a character estimate.
            return {'prompt_tokens':200 if size<=850 else 4090,'context_size':4096,'requested_output_limit':max_tokens,'effective_output_limit':max_tokens if size<=850 else 6,'measurement':'controlled segmentation fixture, not native tokens'}
        return original(messages,max_tokens=max_tokens,**options)
    system.backend.measure_messages=measure


def test_identical_scopes_cannot_replay_ids_or_bindings():
    source={'index.html':'same text\n'}
    left={'base_file_sha256':'a'*64,'scope_start_char':0,'scope_end_char':10,'job_id':'first'}
    right={**left,'scope_start_char':10,'scope_end_char':20}
    a=RepairTargets(source,7,left);b=RepairTargets(source,7,right)
    assert set(a.targets).isdisjoint(b.targets)
    edit={'target_id':next(iter(a.targets)),'after':'new\n'}
    with pytest.raises(ProjectError):a.apply(source,[edit],7,right)
    with pytest.raises(ProjectError):b.apply(source,[edit],7,right)
    assert a.apply(source,[edit],7,left)['index.html']=='new\n'


def test_multi_scope_removal_assembles_one_atomic_revision(system):
    source='<html><head></head><body>\n'+('<!-- unchanged same source -->\n'*80)+'<p>Keep this</p><button>Login</button>\n</body></html>'
    store,jobs,pid=setup(system,source);split_fixture(system);seen=[]
    def oracle(messages,options):
        packet=json.loads(messages[1]['content']);seen.append(packet)
        edits=[{'target_id':s['target_id'],'after':s['source'].replace('<button>Login</button>','')} for s in packet['source_spans'] if '<button>Login</button>' in s['source']]
        return reply(packet,edits)
    system.backend.text=oracle
    try:
        job=wait(jobs,request(jobs,pid));assert job['state']=='completed',job
        assert store.get(pid)['project_revision']==2
        assert store.read(pid,'index.html')['content']==source.replace('<button>Login</button>','')
        operations=next(s for s in job['stage_results'] if s['stage']=='generating')['result']['operations']
        assert 1<len(operations)<=8
        cursor=0;ids=[]
        for op in operations:
            assert op['source_start_char']==cursor;cursor=op['source_end_char']
            binding=op['scope_targets']['binding']
            assert binding['base_file_sha256']==digest(source) and binding['scope_start_char']==op['source_start_char']
            ids.extend(t['target_id'] for t in op['scope_targets']['targets'])
        assert cursor==len(source) and len(ids)==len(set(ids))
        assert all('source_scope' not in p and p['edit_protocol']=='server_targets' for p in seen)
    finally:jobs.shutdown();store.close()


@pytest.mark.parametrize('failure',['duplicate','cross_scope','length','legacy_anchor'])
def test_invalid_or_incomplete_scope_set_cannot_commit_partial_removal(system,failure):
    source='<html><head></head><body><button>Login</button>\n'+('<!-- unchanged same source -->\n'*80)+'</body></html>'
    store,jobs,pid=setup(system,source);split_fixture(system);first=[]
    def oracle(messages,options):
        packet=json.loads(messages[1]['content']);spans=packet['source_spans']
        if not first:
            first.extend(s['target_id'] for s in spans)
            edits=[{'target_id':s['target_id'],'after':s['source'].replace('<button>Login</button>','')} for s in spans if 'Login' in s['source']]
            if failure=='legacy_anchor':return json.dumps({'base_revision':1,'path':'index.html','source_sha256':digest(source),'edits':[{'before':'<button>Login</button>','after':''}]})
            if failure=='duplicate':edits=edits+edits
            return reply(packet,edits)
        return reply(packet,[{'target_id':first[0],'after':''}])
    system.backend.text=oracle
    if failure=='length':system.backend.plan_finish='stop';system.backend.finish='length'
    try:
        job=wait(jobs,request(jobs,pid));assert job['state']=='failed',job
        assert store.get(pid)['project_revision']==1 and store.read(pid,'index.html')['content']==source
    finally:jobs.shutdown();store.close()


def test_source_rewriting_is_rejected_by_deletion_only_protocol(system,monkeypatch):
    source='<html><head></head><body><h1>Keep</h1><button>Login</button></body></html>'
    store,jobs,pid=setup(system,source);observed=[]
    def oracle(messages,options):
        packet=json.loads(messages[1]['content']);s=next(s for s in packet['source_spans'] if s['target_id'])
        return reply(packet,[{'target_id':s['target_id'],'after':s['source'].replace('<button>','<button style="display:none">')}])
    system.backend.text=oracle
    def browser(files,preview,cancel,deadline,required):
        observed.append(required)
        assert required['removed_features']==['login'] and not required.get('login')
        assert not any(c['label']=='Login' for c in required['controls']) and 'Login' not in required['text']
        return {'status':'fixture_not_run'}
    monkeypatch.setattr('src.core.project_jobs.check_candidate',browser)
    try:
        job=wait(jobs,request(jobs,pid));assert job['state']=='failed',job
        assert not observed and store.get(pid)['project_revision']==1
        assert store.read(pid,'index.html')['content']==source
    finally:jobs.shutdown();store.close()


@pytest.mark.parametrize('name',['remove-polite','remove-bare'])
def test_recorded_native_anchor_failures_use_bound_span_ids(name):
    from pathlib import Path
    import re
    from src.core.feature_intent import build_contract
    from src.core.edit_preservation import require_preserved
    from src.core.project_validation import inspect_files
    fixture=Path(__file__).parents[1]/'fixtures/ax07_review/removal'/(name+'.json')
    data=json.loads(fixture.read_text());files=data['files'];source=files['index.html']
    assert data['state']=='failed' and 'مرساة' in data['error']
    matches=re.findall(r'<button\b[^>]*class="login-button"[^>]*>Login</button>',source)
    assert len(matches)==1
    binding={'base_file_sha256':digest(source),'scope_start_char':0,'scope_end_char':len(source),'job_id':'recorded-regression'}
    targets=RepairTargets({'index.html':source},1,binding)
    spans=targets.source[0]['spans'];edits=[{'target_id':s['target_id'],'after':s['source'].replace(matches[0],'')} for s in spans if matches[0] in s['source']]
    assert len(edits)==1
    candidate={**files,**targets.apply({'index.html':source},edits,1,binding)}
    contract=build_contract(data['request'],data['accepted_requirements'],{'intent':'project.edit'})
    assert contract['required']=={'theme':True}
    assert require_preserved(files,candidate,data['request'],contract)['status']=='passed'
    assert not inspect_files(candidate)[2]['errors']
    assert matches[0] in files['index.html'] and matches[0] not in candidate['index.html']
