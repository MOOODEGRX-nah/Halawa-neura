import json,time
from src.core.invoice_parser import InvoiceParser
from src.core.invoice_orchestrator import InvoiceOrchestrator
from tests.regression.test_chat_dispatch import application


def test_n041_invoice_identity_constraints_expected_files_and_stage_results(system):
    app,desktop,dispatch=application(system);store=app.state.project_store;jobs=app.state.project_jobs
    system.backend.text='```python result.py\ndef answer():\n    return 42\n```'
    created=jobs.create({'user_request':'Build answer','requirements':['return 42'],'constraints':['offline only'],
        'required_files':['result.py'],'required_python_symbols':['answer'],'background':True})
    job=created['job']['job_id'];project=created['project']['project_id']
    for _ in range(300):
        result=jobs.get(job)
        if result['state'] in ('completed','failed'):break
        time.sleep(.005)
    assert result['state']=='completed',result
    invoice=result['invoice']
    assert invoice['task_id']==job and invoice['project_id']==project
    assert invoice['user_request']=='Build answer' and 'offline only' in invoice['constraints']
    assert invoice['expected_files']==['result.py'] and invoice['required_python_symbols']==['answer']
    sent=json.loads(system.backend.calls[0]['messages'][1]['content'].split('\nOptional implementation plan:')[0])
    assert sent['task_id']==job and sent['project_id']==project and sent['expected_files']==['result.py']
    assert sent['constraints']==invoice['constraints']
    assert any(stage['stage']=='generating' and stage['status']=='completed' for stage in result['stage_results'])
    assert any(stage['stage']=='validating' and stage['status']=='completed' for stage in result['stage_results'])
    assert result['validation']['static_checks']=='passed'
    assert result['saved_files'][0]['path']=='result.py' and result['saved_files'][0]['project_id']==project
    jobs.shutdown();store.close()


def test_n045_explicit_verdict_and_deterministic_checks_cannot_be_overridden(system):
    assert InvoiceParser.parse_review('GRADE: B\nVERDICT: NEEDS_FIX','qa').verdict=='NEEDS_FIX'
    assert InvoiceParser.parse_review('GRADE: B','qa').verdict=='NEEDS_FIX'
    system.backend.text='GRADE: A\nVERDICT: APPROVED\nEverything is good.'
    result=InvoiceOrchestrator(system,max_fix_retries=50).process_request({'user_request':'Build a file','requirements':['main.py'],'required_files':['main.py']})
    assert not result['success'] and result['files']==[] and len(system.backend.calls)==2
    assert 'No named code files' in result['error'] and result['executed'] is False


def test_n065_invalid_adapter_output_is_uncertain_not_false_success(system):
    from tests.regression.test_chat_dispatch import Desktop,request_id
    class Broken(Desktop):
        def browser(self,url):self.calls.append(('browser',url));return {'status':'anything','message':None}
    app,desktop,dispatch=application(system,Broken());rid=request_id()
    result=dispatch.dispatch('افتح يوتيوب',rid)
    assert result['result']['status']=='unknown' and result['result']['message']
    assert dispatch.dispatch('افتح يوتيوب',rid)==result and len(desktop.calls)==1
    app.state.project_store.close()


def test_n041_plan_contract_preserved_and_legacy_rows_are_not_fabricated(system):
    from src.core.project_jobs import ProjectJobs
    app,desktop,dispatch=application(system);store=app.state.project_store;jobs=app.state.project_jobs
    system.backend.replies=['Use one Python file.','```python main.py\ndef add(a,b):return a+b\n```']
    created=jobs.create({'user_request':'Create add','requirements':['addition'],'required_files':['main.py'],'plan':True,'background':True})
    job=created['job']['job_id'];project=created['project']['project_id']
    for _ in range(300):
        result=jobs.get(job)
        if result['state'] in ('completed','failed'):break
        time.sleep(.005)
    assert result['state']=='completed' and len(system.backend.calls)==2
    assert next(s for s in result['stage_results'] if s['stage']=='planning')['result']['output']=='Use one Python file.'
    sent=[json.loads(c['messages'][1]['content'].split('\nOptional implementation plan:')[0]) for c in system.backend.calls]
    assert all(i['expected_files']==['main.py'] and i['project_id']==project and i['task_id']==job for i in sent)
    recorded=jobs.get(job)['saved_files'];opened=store.read(project,'main.py')
    store.save_file(project,'main.py',opened['content']+'\n# saved later\n',1,opened['sha256'])
    assert jobs.get(job)['saved_files']==recorded and recorded[0]['sha256']==opened['sha256']
    jobs.shutdown()
    store.db.execute('DELETE FROM job_contracts WHERE job_id=?',(job,));store.db.commit()
    restored=ProjectJobs(store,system)
    old=restored.get(job)
    assert old['state']=='completed' and old['invoice'] is None and old['invoice_provenance']=='unavailable_legacy'
    assert store.get(project)['project_revision']==2
    restored.shutdown();store.close()


def test_n072_history_is_bounded_and_n073_expired_grant_never_launches(tmp_path):
    import pytest
    from src.core.project_store import ProjectStore
    from src.tools.desktop_skills import DesktopSkills,PermissionDenied
    from tests.security.test_desktop_skills import FakeDesktop
    store=ProjectStore(tmp_path);desktop=FakeDesktop();skills=DesktopSkills(store,desktop)
    for _ in range(105):
        args={'application_id':'calc.desktop'};grant=skills.authorize('open_application',args)['permission_id'];skills.execute('open_application',args,grant)
    assert store.db.execute('SELECT COUNT(*) FROM skill_history').fetchone()[0]==100
    assert len(skills.history())==50
    grant=skills.authorize('open_application',args,True)['permission_id'];store.db.execute('UPDATE skill_grants SET expires=0 WHERE id=?',(grant,));store.db.commit()
    with pytest.raises(PermissionDenied):skills.execute('open_application',args,grant)
    assert len(desktop.calls)==105
    before=skills.recent();store.close();store=ProjectStore(tmp_path)
    assert DesktopSkills(store,FakeDesktop()).recent()==before
    store.close()
