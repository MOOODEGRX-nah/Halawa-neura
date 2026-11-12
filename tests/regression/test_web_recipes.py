"""Bounded web catalog/recipe contracts; fake inference/browser unless stated."""
import json,time
from pathlib import Path
import pytest
from pydantic import ValidationError
from src.tools.web_recipes import manifest,select_for_request,validate_source,RecipeArguments,ID,FILES
from src.tools.desktop_skills import DesktopSkills,PermissionDenied
from src.core.project_files import ProjectError
from tests.regression.test_chat_dispatch import application,request_id

FIXTURE=Path(__file__).resolve().parents[1]/'fixtures/web_cv.json'

def files():return json.loads(FIXTURE.read_text())

@pytest.mark.parametrize('text',['برمج لي موقع CV عربي يعمل بدون إنترنت','صمم لي موقع سيرة ذاتية عربي محلي','هل يمكنك أن تنشئ لي موقع cv عربي؟','Build a CV website in Arabic offline'])
def test_eligible_recipe_requires_validated_create(text):
    assert select_for_request(text,'project.create')==ID
    assert select_for_request(text,'explanation') is None

@pytest.mark.parametrize('text',['لا تنشئ موقع CV عربي','"برمج لي موقع CV عربي"','اشرح كيف أنشئ موقع CV عربي','برمج موقع CV عربي باستخدام React','برمج لي موقع تسوق محلي','برمج لي موقع للcv'])
def test_unselected_or_non_authorizing_text(text):
    assert select_for_request(text,'project.create') is None


def test_unknown_recipes_extra_arguments_and_non_network_source():
    for args in ({'recipe_id':'download_from_model'},{'recipe_id':ID,'shell':'run'}):
        with pytest.raises(ValidationError):RecipeArguments.model_validate(args)
    assert validate_source(files(),ID)['status']=='passed'
    for mutate in [lambda f:f.pop('script.js'),lambda f:f.update({'style.css':'@import "https://bad.example/a.css";'}),lambda f:f.update({'script.js':'fetch("http://127.0.0.1:8000/")'}),lambda f:f.update({'index.html':f['index.html'].replace('href="style.css"','href="file.css"')}),lambda f:f.update({'index.html':f['index.html'].replace('</main>','<p id="cv-content">duplicate</p></main>')})]:
        value=files();mutate(value)
        with pytest.raises(ProjectError):validate_source(value,ID)


def terminal(jobs,key):
    end=time.monotonic()+3
    while time.monotonic()<end:
        job=jobs.get(key)
        if job['state'] in ('completed','failed','cancelled'):return job
        time.sleep(.01)
    raise AssertionError(jobs.get(key))


def test_catalog_selection_reuses_original_request_one_job_and_metadata(system):
    app,desktop,dispatch=application(system);jobs=app.state.project_jobs;store=app.state.project_store
    system.backend.text='\n'.join('```'+{'html':'html','css':'css','js':'javascript'}[p.rsplit('.',1)[1]]+' '+p+'\n'+v+'```' for p,v in files().items())
    text='برمج لي موقع CV عربي يعمل بدون إنترنت';rid=request_id()
    try:
        reply=dispatch.dispatch(text,rid,session_id='recipe-test');assert reply['kind']=='project'
        key=reply['job']['job_id'];job=terminal(jobs,key);assert job['state']=='completed',job['error']
        assert dispatch.dispatch(text,rid,session_id='recipe-test')['job']['job_id']==key
        assert job['invoice']['user_request']==text and job['invoice']['web_recipe']==ID
        assert job['invoice']['web_recipe_sha256']==manifest()['sha256']
        assert set(job['invoice']['expected_files'])==set(FILES)
        project=store.get(job['project_id']);assert project['generation_recipe']['sha256']==manifest()['sha256']
        assert set(store.committed_files(job['project_id']))==set(FILES)
        assert [s['stage'] for s in job['stage_results']].index('planning')<[s['stage'] for s in job['stage_results']].index('generating')
        assert project['validation']['web_recipe']['status']=='passed'
        assert not desktop.calls
        # Origin metadata is retained across ordinary manual saves; it is not a
        # claim that current source passed browser verification.
        value=store.committed_files(job['project_id']);value['style.css']+='\nmain{padding:1rem}'
        updated=store.commit(job['project_id'],value,1);assert updated['generation_recipe']==project['generation_recipe']
    finally:jobs.shutdown();store.close()


def test_disabled_recipe_stops_before_project_or_job(system):
    app,desktop,dispatch=application(system);desktop.disabled=['prepare_static_cv'];store=app.state.project_store
    try:
        result=dispatch.dispatch('برمج لي موقع CV عربي محلي',request_id(),session_id='disabled-recipe')
        assert result['kind']=='action' and result['result']['status']=='unavailable'
        assert not store.list() and not system.backend.calls
        with pytest.raises(ProjectError):app.state.project_jobs.create({'user_request':'CV','requirements':['CV'],'web_recipe':ID})
        assert not store.list()
    finally:app.state.project_jobs.shutdown();store.close()


def test_registry_recipe_grant_returns_manifest_without_running_generation(system):
    app,desktop,_=application(system);skills=app.state.desktop_skills
    try:
        assert skills.describe()['web_skills'][0]['id']==ID
        grant=skills.authorize('prepare_static_cv',{'recipe_id':ID})['permission_id']
        result=skills.execute('prepare_static_cv',{'recipe_id':ID},grant)
        assert result['status']=='selected' and result['recipe']==manifest()
        assert not app.state.project_store.list() and not system.backend.calls and not desktop.calls
        with pytest.raises(PermissionDenied):skills.execute('prepare_static_cv',{'recipe_id':ID},grant)
    finally:app.state.project_store.close()


def test_recipe_does_not_override_explicit_other_filenames():
    assert select_for_request('برمج لي موقع CV عربي باسم resume.html','project.create') is None
    assert select_for_request('برمج لي موقع CV عربي index.html وstyle.css وscript.js','project.create') is None  # prefixed filename ambiguity declines safely


def test_edit_uses_persisted_recipe_and_rejects_changed_contract(system,monkeypatch):
    app,_,dispatch=application(system);store=app.state.project_store;jobs=app.state.project_jobs
    system.backend.text='\n'.join('```'+{'html':'html','css':'css','js':'javascript'}[p.rsplit('.',1)[1]]+' '+p+'\n'+v+'```' for p,v in files().items())
    try:
        created=dispatch.dispatch('برمج لي موقع CV عربي محلي',request_id(),session_id='recipe-edit');job=terminal(jobs,created['job']['job_id']);assert job['state']=='completed'
        pid=job['project_id'];meta=store.get(pid);meta['generation_recipe']['sha256']='0'*64
        store.db.execute('UPDATE projects SET metadata=? WHERE id=?',(json.dumps(meta),pid));store.db.commit()
        with pytest.raises(ProjectError,match='وصفة'):jobs.create({'user_request':'أضف الوضع الداكن','requirements':['theme'],'project_id':pid,'expected_revision':1,'context_files':FILES})
        assert store.get(pid)['project_revision']==1
    finally:jobs.shutdown();store.close()


def test_changed_recipe_while_resource_waiting_never_replays_new_contract(system,tmp_path,monkeypatch):
    from src.core.project_jobs import ProjectJobs
    from src.core.project_store import ProjectStore
    ready=[False];monkeypatch.setattr(system,'project_resource_ready',lambda:(ready[0],'waiting' if not ready[0] else None))
    store=ProjectStore(tmp_path/'recipes');jobs=ProjectJobs(store,system)
    try:
        key=jobs.create({'user_request':'CV offline','requirements':['CV'],'web_recipe':ID,'web_recipe_sha256':'0'*64})['job']['job_id']
        end=time.monotonic()+2
        while not jobs.get(key)['blocked_reason'] and time.monotonic()<end:time.sleep(.01)
        assert jobs.get(key)['invoice']['web_recipe_sha256']==manifest()['sha256']
        old=manifest();monkeypatch.setattr('src.tools.web_recipes.manifest',lambda:{**old,'sha256':'f'*64});ready[0]=True
        job=terminal(jobs,key);assert job['state']=='failed' and 'وصفة' in job['error']
        assert not system.backend.calls and not store.committed_files(job['project_id'])
    finally:jobs.shutdown();store.close()


def test_recorded_missing_type_repairs_only_bound_start_tag():
    from src.tools.web_recipes import repair_missing_button_type
    fixture=json.loads(FIXTURE.with_name('web_cv_rejected_native.json').read_text());before=fixture['missing_type']
    with pytest.raises(ProjectError,match='زر الخط'):validate_source(before,ID)
    binding={'project_id':'qa','job_id':'qa','purpose':'required_recipe_control_shape'}
    after,receipt=repair_missing_button_type(before,ID,'زر الخط لا يطابق عقد الوصفة',0,binding)
    assert after['index.html']==before['index.html'].replace('aria-pressed="false">','aria-pressed="false" type="button">')
    assert after['style.css']==before['style.css'] and after['script.js']==before['script.js']
    assert not receipt['model_called'] and len(receipt['repair_targets']['targets'])==1
    assert receipt['repair_targets']['base_revision']==0 and receipt['repair_targets']['binding']==binding
    assert validate_source(after,ID)['status']=='passed'
    with pytest.raises(ProjectError):validate_source(fixture['bad_model_repair'],ID)


def test_recipe_shape_repair_rejects_duplicate_conflicting_or_unknown_targets():
    from src.tools.web_recipes import repair_missing_button_type
    f=files();f['index.html']=f['index.html'].replace('type="button" ','')
    for bad in [f['index.html'].replace('</body>','<button id="cv-font-toggle"></button></body>'),f['index.html'].replace('aria-pressed="false"','aria-pressed="false" type="submit"'),f['index.html'].replace('id="cv-font-toggle"','id="wrong" id="cv-font-toggle"')]:
        assert repair_missing_button_type({**f,'index.html':bad},ID,'زر الخط لا يطابق عقد الوصفة',1,{}) is None
    assert repair_missing_button_type(f,ID,'unrelated failure',1,{}) is None
