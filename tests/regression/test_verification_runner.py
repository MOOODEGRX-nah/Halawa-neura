"""Runner safety and accounting, independent of inference and desktop tools."""
import importlib.util
import json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('verification_runner',ROOT/'tools/verify_neura.py')
verify=importlib.util.module_from_spec(spec);spec.loader.exec_module(verify)


def test_catalog_is_exactly_all_109_unique_references():
    rows=verify.load_catalog()
    assert len(rows)==109
    assert {r['task_id'] for r in rows}=={f'N{i:03}' for i in range(1,110)}
    assert sum(r['category']=='active' for r in rows)==80
    assert sum(r['category']=='reported_done' for r in rows)==17
    assert sum(r['feature_state']=='DEFERRED' for r in rows)==10
    assert sum(r['feature_state']=='SUPERSEDED' for r in rows)==2


@pytest.mark.parametrize('path',[Path.home()/'.local/share/neura-ai',Path.home()/'.local/share/neura-ai/qa',Path.home(),Path('/opt/neura-ai/app')])
def test_production_or_parent_profile_paths_are_refused(path):
    with pytest.raises(ValueError):verify.safe_root(path)


def test_resolved_symlink_cannot_reuse_production_profile(tmp_path):
    p=tmp_path/'looks-like-qa';p.symlink_to(Path.home()/'.local/share/neura-ai',target_is_directory=True)
    with pytest.raises(ValueError):verify.safe_root(p)


def test_fake_and_source_passes_do_not_close_real_acceptance():
    row={'task_id':'N049','feature_state':'IMPLEMENTED','cases':[
        verify.case('source','PASS','SOURCE'),verify.case('contract','PASS','CONTRACT_FAKE',required=True),
        verify.case('real','BLOCKED','REAL_MODEL',required=True)]}
    result=verify.summarize([row])
    assert result['acceptance_exit_code']==3 and not result['accepted_requirement_ids']
    row['cases'][-1]['case_result']='FAIL'
    assert verify.summarize([row])['acceptance_exit_code']==1


def test_negative_unavailable_pass_is_not_an_implemented_feature():
    row={'task_id':'N085','feature_state':'MISSING','cases':[verify.case('unavailable','PASS','CONTRACT_FAKE',required=True)]}
    assert verify.summarize([row])['acceptance']=='INCOMPLETE'


def test_repeated_methods_keep_failures_from_another_suite():
    run=object.__new__(verify.Run);run.by_id={'N057':{'feature_state':'IMPLEMENTED','required_evidence':['UI_FIXTURE'],'cases':[]}}
    run.gate(['N057'],'UI_FIXTURE','FAIL',{},['qt-main.json'])
    run.gate(['N057'],'UI_FIXTURE','PASS',{},['qt-extra.json'])
    cases=run.by_id['N057']['cases'];assert len(cases)==2 and any(c['case_result']=='FAIL' for c in cases)


def test_same_artifact_keeps_distinct_scenario_failures():
    run=object.__new__(verify.Run);run.by_id={'N005':{'feature_state':'IMPLEMENTED','required_evidence':['REAL_MODEL'],'cases':[]}}
    run.gate(['N005'],'REAL_MODEL','FAIL',{'name':'arabic'},['models.json'])
    run.gate(['N005'],'REAL_MODEL','PASS',{'name':'english'},['models.json'])
    assert len(run.by_id['N005']['cases'])==2
    assert any(c['case_result']=='FAIL' for c in run.by_id['N005']['cases'])


def test_evidence_levels_alone_do_not_close_an_unreviewed_requirement():
    row={'task_id':'N001','feature_state':'IMPLEMENTED','cases':[verify.case('static','PASS','STATIC',required=True)]}
    assert not verify.summarize([row])['accepted_requirement_ids']
    row['acceptance_reviewed']=True
    assert verify.summarize([row])['accepted_requirement_ids']==['N001']


def test_historical_observation_cannot_be_imported(tmp_path):
    run=object.__new__(verify.Run);run.result={'run_id':'today'}
    p=tmp_path/'old.json';p.write_text(json.dumps({'run_id':'yesterday','cases':[]}))
    with pytest.raises(ValueError,match='historical'):run.observations(p)


def test_required_observation_replaces_placeholder_but_keeps_prior_failure(tmp_path):
    run=object.__new__(verify.Run);run.out=tmp_path
    row={'task_id':'N057','feature_state':'IMPLEMENTED','cases':[
        verify.case('acceptance_ui_fixture','NOT_RUN','UI_FIXTURE',required=True),
        verify.case('older_actual_failure','FAIL','UI_FIXTURE',{'error':'blocked escape failed'},required=True)]}
    run.by_id={'N057':row};run.result={'run_id':'current','requirements':[row],'screenshots':[]};run.save=lambda:None
    p=tmp_path/'observation.json';p.write_text(json.dumps({'run_id':'current','cases':[{
        'task_ids':['N057'],'case_id':'new_observed_case','case_result':'PASS','evidence_method':'UI_FIXTURE','required':True}]}))
    run.observations(p)
    assert {c['case_id'] for c in row['cases']}=={'older_actual_failure','new_observed_case'}
    assert verify.summarize([row])['acceptance']=='FAILED'


def test_controlled_fixture_cannot_initialize_vulkan_or_read_vram():
    from src.backends.devices import probe_devices
    from src.backends.residency import gpu_memory
    import psutil
    assert gpu_memory() is None and psutil.virtual_memory().available==24_000_000_000
    with pytest.raises(AssertionError,match='Vulkan'):probe_devices()


def test_fake_adapters_cannot_satisfy_a_real_suite():
    other=importlib.util.spec_from_file_location('verification_live',ROOT/'tools/verification/live.py')
    live=importlib.util.module_from_spec(other);other.loader.exec_module(live)
    for suite in ('model','desktop'):
        with pytest.raises(ValueError,match='Fake'):
            live.require_actual({'model_adapter':'fake','desktop_adapter':'fake'},suite)


def test_nonempty_numbered_refusal_is_not_a_planning_pass():
    other=importlib.util.spec_from_file_location('verification_plan',ROOT/'tools/verification/live.py')
    live=importlib.util.module_from_spec(other);other.loader.exec_module(live)
    assert not live.valid_plan('لا يمكنني إنشاء موقع\n1. لا أملك قدرات HTML\n2. لا أملك قدرات كتابة\n3. لا أملك قدرات بناء')
    assert not live.valid_plan('This is a nonempty answer, but not a plan')
    assert live.valid_plan('1. حدد محتوى صفحة السيرة.\n2. صمم هيكل HTML وCSS.\n3. راجع الموقع الثابت في المعاينة.')


def test_original_generation_evidence_is_not_replaced_by_latest_edit(tmp_path):
    import sqlite3
    other=importlib.util.spec_from_file_location('verification_jobs',ROOT/'tools/verification/live.py')
    live=importlib.util.module_from_spec(other);other.loader.exec_module(live)
    workspace=tmp_path/'data/workspace';workspace.mkdir(parents=True)
    with sqlite3.connect(workspace/'catalog.sqlite3') as db:
        db.execute('CREATE TABLE jobs(id TEXT,project_id TEXT,request TEXT,created TEXT)')
        db.executemany('INSERT INTO jobs VALUES(?,?,?,?)',[
            ('original','p1',json.dumps({'user_request':'برمج لي موقع للcv'}),'1'),
            ('later_edit','p1',json.dumps({'user_request':'غير الخلفية'}),'2')])
    assert live.original_job_id(tmp_path,'p1','برمج لي موقع للcv')=='original'
    with pytest.raises(ValueError,match='not found'):live.original_job_id(tmp_path,'p2','برمج لي موقع للcv')


def test_quality_failure_does_not_falsely_fail_routing_or_transport():
    other=importlib.util.spec_from_file_location('verification_outcomes',ROOT/'tools/verification/live.py')
    live=importlib.util.module_from_spec(other);other.loader.exec_module(live)
    recorded={}
    class Recorder:
        def gate(self,ids,method,result,*args,**kwargs):
            for identifier in ids:recorded[identifier]=result
    live.record_chat_trial(Recorder(),{'name':'expert_plan','native_returned_idle':True,'error':None,
        'actual_model':'expert-weights','routed_model':'expert-weights','output':'1. Incomplete plan',
        'first_nonempty_chunk_s':1,'duration_s':2,'finish_reason':'length','passed':False})
    assert recorded['N006']=='FAIL' and recorded['N004']=='PASS' and recorded['N012']=='PASS'


def test_model_harness_continues_independent_checks_after_quality_failure(tmp_path,monkeypatch):
    """Synthetic HTTP only; this is a harness regression, not native inference."""
    import io,psutil
    from types import SimpleNamespace
    other=importlib.util.spec_from_file_location('verification_harness',ROOT/'tools/verification/live.py')
    live=importlib.util.module_from_spec(other);other.loader.exec_module(live)
    calls=[]
    monkeypatch.setattr(live,'history',lambda *a:calls.append('history') or 0)
    monkeypatch.setattr(live,'budget',lambda *a:calls.append('budget') or 0)
    monkeypatch.setattr(psutil,'Process',lambda pid:SimpleNamespace(memory_info=lambda:SimpleNamespace(rss=0)))
    class FakeClient:
        info={'pid':0,'url':'http://127.0.0.1:1'};token='synthetic';opener=None
        def idle(self,*a):return True
        def verify(self):return {'current_model':None,'phase':'idle'}
        def call(self,path,body=None,**kwargs):
            if path=='/route':return {'model_id':'synthetic'}
            if path=='/projects':return {'projects':[]}
            if path=='/chat/dispatch':return {'kind':'chat'}
            return {'choices':[{'message':{'content':'أحمر، أزرق'}}]}
        def open(self,*a,**k):
            payload={'id':'synthetic','choices':[{'delta':{'content':'READY'},'finish_reason':'stop'}]}
            class Response(io.BytesIO):headers={'X-Neura-Model':'synthetic'}
            return Response(('data: '+json.dumps(payload)+'\n\ndata: [DONE]\n\n').encode())
    client=FakeClient();client.opener=client
    class FakeRun:
        out=tmp_path;result={'requirements':[]}
        def gate(self,*a,**k):pass
        def save(self):pass
    (tmp_path/'artifacts').mkdir()
    assert live.models(FakeRun(),client)==1
    assert calls==['history','budget']
