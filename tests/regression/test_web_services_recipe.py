"""B2: arabic_services_v1 (offline Arabic RTL service directory with a category filter).

Fake inference/browser unless stated; the real renderer gate is exercised by
tools/qa_web_recipe_browser.py --recipe arabic_services_v1 and the composer workflow.
"""
import json,time
from pathlib import Path
import pytest
from pydantic import ValidationError
from src.tools.web_recipes import manifest,select_for_request,validate_source,ServicesRecipeArguments,ID,SERVICES_ID,FILES,skill_for
from src.core.project_files import ProjectError
from tests.regression.test_chat_dispatch import application,request_id
from tests.regression.test_web_recipes import terminal

FIXTURE=Path(__file__).resolve().parents[1]/'fixtures/web_services.json'
CV_MANIFEST_SHA256='77d878e796b58732f849645b938de5406ce51c00cc01e21e14c619d40ee61bf8'

def files():return json.loads(FIXTURE.read_text())


def test_cv_manifest_identity_is_unchanged_by_the_catalog_expansion():
    # Saved projects and queued jobs bind this hash; it must stay byte-identical.
    assert manifest()['sha256']==manifest(ID)['sha256']==CV_MANIFEST_SHA256
    services=manifest(SERVICES_ID)
    assert services['id']==SERVICES_ID and services['sha256']!=CV_MANIFEST_SHA256 and services['required_files']==FILES
    assert skill_for(ID)=='prepare_static_cv' and skill_for(SERVICES_ID)=='prepare_static_services'
    with pytest.raises(ProjectError):manifest('unknown_recipe')


@pytest.mark.parametrize('text',['برمج لي دليل خدمات عربي محلي يعمل بدون إنترنت','أنشئ دليل الخدمات عربي مع تصفية حسب الفئة','Build an offline Arabic services directory'])
def test_services_selection_requires_create_intent_and_local_signal(text):
    assert select_for_request(text,'project.create')==SERVICES_ID
    assert select_for_request(text,'project.edit') is None


@pytest.mark.parametrize('text',['برمج لي دليل خدمات','برمج دليل خدمات عربي باستخدام React','برمج لي دليل خدمات عربي باسم services.html','"برمج لي دليل خدمات عربي محلي"','لا تنشئ دليل خدمات عربي'])
def test_services_selection_declines_generic_stack_named_or_non_authorizing(text):
    assert select_for_request(text,'project.create') is None


def test_cv_requests_still_select_cv_recipe():
    assert select_for_request('برمج لي موقع سيرة ذاتية عربي محلي فيه قسم خدمات','project.create')==ID


def test_services_source_contract_and_rejections():
    assert validate_source(files(),SERVICES_ID)['status']=='passed'
    with pytest.raises(ValidationError):ServicesRecipeArguments.model_validate({'recipe_id':ID})
    mutations=[lambda f:f.update({'index.html':f['index.html'].replace('aria-pressed="true"','aria-pressed="false"')}),
        lambda f:f.update({'index.html':f['index.html'].replace('data-category="maintenance" aria-pressed','data-category="health" aria-pressed')}),
        lambda f:f.update({'index.html':f['index.html'].replace('role="group" ','')}),
        lambda f:f.update({'index.html':f['index.html'].replace(' aria-live="polite"','')}),
        lambda f:f.update({'index.html':f['index.html'].replace('<li class="service-card" data-category="health"><h2>صيدلية','<li class="service-card" data-category="other"><h2>صيدلية')}),
        lambda f:f.update({'index.html':f['index.html'].replace('type="button" class="service-filter" data-category="health"','class="service-filter" data-category="health"')}),
        lambda f:f.update({'style.css':f['style.css'].replace(':focus-visible','.focused')}),
        lambda f:f.update({'style.css':f['style.css'].replace('prefers-reduced-motion','min-resolution')}),
        lambda f:f.update({'script.js':f['script.js']+'\nlocalStorage.setItem("x","1");'}),
        lambda f:f.update({'index.html':f['index.html'].replace('lang="ar" dir="rtl"','lang="en"')}),
        lambda f:f.update({'style.css':'@import url(https://cdn.example/x.css);'+f['style.css']})]
    for mutate in mutations:
        value=files();mutate(value)
        with pytest.raises(ProjectError):validate_source(value,SERVICES_ID)
    # Removing cards below the minimum is rejected.
    value=files();value['index.html']=value['index.html'].replace('<li class="service-card" data-category="maintenance"><h2>كهربائي</h2><p>وصف تجريبي: صيانة مثال.</p></li>\n','')
    with pytest.raises(ProjectError):validate_source(value,SERVICES_ID)


def test_registry_lists_both_recipes_and_grant_is_scoped(system):
    app,desktop,_=application(system);skills=app.state.desktop_skills
    try:
        web=skills.describe()['web_skills']
        assert [w['id'] for w in web]==[ID,SERVICES_ID,'arabic_landing_v1','arabic_dashboard_v1','arabic_blog_v1','arabic_store_v1','arabic_saas_v1'] and web[0]['sha256']==CV_MANIFEST_SHA256 and all(w['available'] for w in web)
        grant=skills.authorize('prepare_static_services',{'recipe_id':SERVICES_ID})['permission_id']
        result=skills.execute('prepare_static_services',{'recipe_id':SERVICES_ID},grant)
        assert result['status']=='selected' and result['recipe']==manifest(SERVICES_ID)
        assert not app.state.project_store.list() and not system.backend.calls and not desktop.calls
        with pytest.raises(ValidationError):skills.validate('prepare_static_cv',{'recipe_id':SERVICES_ID})
    finally:app.state.project_store.close()


def test_services_create_then_edit_keeps_recipe_contract_planning_and_one_revision_each(system):
    app,desktop,dispatch=application(system);jobs=app.state.project_jobs;store=app.state.project_store
    system.backend.text='\n'.join('```'+{'html':'html','css':'css','js':'javascript'}[p.rsplit('.',1)[1]]+' '+p+'\n'+v+'```' for p,v in files().items())
    text='برمج لي موقع دليل خدمات عربي محلي يعمل بدون إنترنت مع تصفية حسب الفئة'
    try:
        reply=dispatch.dispatch(text,request_id(),session_id='services');assert reply['kind']=='project'
        job=terminal(jobs,reply['job']['job_id']);assert job['state']=='completed',job['error']
        assert job['invoice']['web_recipe']==SERVICES_ID and job['invoice']['web_recipe_sha256']==manifest(SERVICES_ID)['sha256']
        assert set(job['invoice']['expected_files'])==set(FILES)
        assert any('service-filters' in c for c in job['invoice']['constraints'])
        stages=[s['stage'] for s in job['stage_results']];assert stages.index('planning')<stages.index('generating')
        project=store.get(job['project_id'])
        assert project['project_revision']==1 and project['generation_recipe']['id']==SERVICES_ID
        assert project['validation']['web_recipe']['status']=='passed' and project['validation']['web_recipe']['cards']==6
        # Persisted recipe drives the edit; a candidate breaking the filter contract is rejected
        # and leaves revision 1 and its files intact.
        before=store.committed_files(job['project_id'])
        broken=files();broken['index.html']=broken['index.html'].replace(' aria-live="polite"','')
        system.backend.text='\n'.join('```'+{'html':'html','css':'css','js':'javascript'}[p.rsplit('.',1)[1]]+' '+p+'\n'+v+'```' for p,v in broken.items())
        edit=jobs.create({'user_request':'أضف وصفًا أطول لكل خدمة','requirements':['وصف أطول'],'project_id':job['project_id'],'expected_revision':1,'context_files':FILES})
        result=terminal(jobs,edit['job']['job_id'])
        assert result['invoice']['web_recipe']==SERVICES_ID
        if result['state']=='completed':assert store.get(job['project_id'])['validation']['web_recipe']['status']=='passed'
        else:assert store.get(job['project_id'])['project_revision']==1 and store.committed_files(job['project_id'])==before
        assert not desktop.calls
    finally:jobs.shutdown();store.close()


def test_disabled_services_recipe_stops_before_project_or_job(system):
    app,desktop,dispatch=application(system);desktop.disabled=['prepare_static_services'];store=app.state.project_store
    try:
        result=dispatch.dispatch('برمج لي موقع دليل خدمات عربي محلي',request_id(),session_id='disabled-services')
        assert result['kind']=='action' and result['result']['status']=='unavailable'
        assert not store.list() and not system.backend.calls
        with pytest.raises(ProjectError):app.state.project_jobs.create({'user_request':'services','requirements':['services'],'web_recipe':SERVICES_ID})
        # CV recipe stays available.
        assert select_for_request('برمج لي موقع CV عربي محلي','project.create')==ID
    finally:app.state.project_jobs.shutdown();store.close()


def test_recorded_14b_filter_shape_gap_repairs_only_missing_attributes():
    """Observed (web-services-1): 14B omitted type=button and aria-pressed=false on filters."""
    from src.tools.web_recipes import repair_missing_button_type,FILTER_SHAPE_ERROR
    f=files();broken=dict(f)
    broken['index.html']=f['index.html'].replace('type="button" class="service-filter"','class="service-filter"').replace(' aria-pressed="false"','')
    with pytest.raises(ProjectError,match='أزرار التصفية'):validate_source(broken,SERVICES_ID)
    binding={'project_id':'qa','job_id':'qa','purpose':'required_recipe_control_shape'}
    after,receipt=repair_missing_button_type(broken,SERVICES_ID,FILTER_SHAPE_ERROR,0,binding)
    assert validate_source(after,SERVICES_ID)['status']=='passed' and not receipt['model_called'] and len(receipt['edits'])==4
    assert after['style.css']==f['style.css'] and after['script.js']==f['script.js']
    assert after['index.html'].replace(' type="button"','').replace(' aria-pressed="false"','').replace(' aria-pressed="true"','')==broken['index.html'].replace(' aria-pressed="true"','')
    assert 'data-category="all" aria-pressed="true"' in after['index.html']
    # Other failures, conflicting values, non-buttons and the CV error text are never rewritten.
    assert repair_missing_button_type(broken,SERVICES_ID,'غير ذلك',0,binding) is None
    assert repair_missing_button_type({**broken,'index.html':broken['index.html'].replace('data-category="health">','data-category="health" type="submit">',1)},SERVICES_ID,FILTER_SHAPE_ERROR,0,binding) is None
    assert repair_missing_button_type({**broken,'index.html':broken['index.html'].replace('<button class="service-filter" data-category="health"','<a class="service-filter" data-category="health"',1)},SERVICES_ID,FILTER_SHAPE_ERROR,0,binding) is None
    assert repair_missing_button_type(broken,SERVICES_ID,'زر الخط لا يطابق عقد الوصفة',0,binding) is None


def test_bound_session_imperative_edit_is_a_job_not_fabricating_chat(system):
    """Observed (web-services-2): «أضف فئة جديدة…» right after creation went to DAILY chat, which
    claimed index.html/script.js were updated while revision 1 stayed unchanged."""
    app,desktop,dispatch=application(system);jobs=app.state.project_jobs;store=app.state.project_store
    system.backend.text='\n'.join('```'+{'html':'html','css':'css','js':'javascript'}[p.rsplit('.',1)[1]]+' '+p+'\n'+v+'```' for p,v in files().items())
    try:
        created=dispatch.dispatch('برمج لي موقع دليل خدمات عربي محلي يعمل بدون إنترنت',request_id(),session_id='bound')
        job=terminal(jobs,created['job']['job_id']);assert job['state']=='completed'
        follow=dispatch.dispatch('أضف فئة جديدة باسم النقل مع خدمتين تجريبيتين تحت هذه الفئة',request_id(),session_id='bound')
        assert follow['kind']=='project' and follow['project']['project_id']==job['project_id']
        edit=terminal(jobs,follow['job']['job_id'])
        assert edit['invoice']['web_recipe']==SERVICES_ID and edit['invoice']['user_request'].startswith('أضف فئة')
        stages=[s['stage'] for s in edit['stage_results']];assert stages.index('planning')<stages.index('generating')
        # Unbound session, questions and explanations keep their previous routing.
        assert dispatch.dispatch('أضف فئة جديدة باسم النقل',request_id(),session_id='unbound')['kind']=='chat'
        assert dispatch.dispatch('أضف فئة جديدة باسم النقل؟',request_id(),session_id='bound')['kind']!='project'
        assert not desktop.calls
    finally:jobs.shutdown();store.close()



def test_edit_plan_need_not_list_existing_recipe_files_but_creation_still_must(system):
    """Observed (web-services-3): a correct edit plan naming only index.html was rejected."""
    app,desktop,dispatch=application(system);jobs=app.state.project_jobs;store=app.state.project_store
    system.backend.text='\n'.join('```'+{'html':'html','css':'css','js':'javascript'}[p.rsplit('.',1)[1]]+' '+p+'\n'+v+'```' for p,v in files().items())
    try:
        created=dispatch.dispatch('برمج لي موقع دليل خدمات عربي محلي يعمل بدون إنترنت',request_id(),session_id='plan-files')
        job=terminal(jobs,created['job']['job_id']);assert job['state']=='completed'
        system.backend.plan_replies=[json.dumps({'steps':['أضف زر فئة النقل','أضف بطاقتين للنقل','حدّث العداد'],'files':['index.html']},ensure_ascii=False)]
        source=files()['index.html']
        system.backend.replies=[json.dumps({'base_revision':1,'path':'index.html','source_sha256':__import__('hashlib').sha256(source.encode()).hexdigest(),
            'edits':[{'before':'<li class="service-card" data-category="maintenance"><h2>كهربائي</h2>','after':'<li class="service-card" data-category="maintenance"><h2>كهربائي معتمد</h2>'}],'new_content':None},ensure_ascii=False)]
        edit=jobs.create({'user_request':'غيّر اسم خدمة الكهربائي','requirements':['تعديل'],'project_id':job['project_id'],'expected_revision':1,'context_files':['index.html']})
        result=terminal(jobs,edit['job']['job_id'])
        plan=next(s for s in result['stage_results'] if s['stage']=='planning')['result']
        assert plan['accepted'] and plan['plan']['files']==['index.html'] and plan['plan_required_files']==[]
        assert result['state']=='completed',result['error']
        assert store.get(job['project_id'])['project_revision']==2 and set(store.committed_files(job['project_id']))==set(FILES)
    finally:jobs.shutdown();store.close()



@pytest.mark.parametrize('text',['غير واضح','غير صحيح','بدل ذلك اشرح لي','حسن جدا شكرا','عدل','fix it','add more','update me later','لا تضف شيئا','أضف ذلك','أضف فئة جديدة؟'])
def test_bound_edit_command_rejects_complaints_adjectives_and_vague_objects(text):
    from src.core.chat_dispatch import bound_edit_command
    from src.core.user_commands import command_text
    assert not bound_edit_command(command_text(text),text)


@pytest.mark.parametrize('text',['أضف فئة جديدة باسم النقل','احذف بطاقة الصيانة','انقل قسم التعليم إلى الأعلى','remove the transport category'])
def test_bound_edit_command_accepts_explicit_imperatives(text):
    from src.core.chat_dispatch import bound_edit_command
    from src.core.user_commands import command_text
    assert bound_edit_command(command_text(text),text)


def test_services_gate_requires_visible_active_filter_state():
    """Observed (followup-visual-3): inline background on every filter hid which filter is active."""
    from src.core.candidate_browser import services_failures
    def state(looks,pressed):
        return {'total':6,'visible':['a','a','b','b','c','c'],'filters':[{'category':c,'pressed':'true' if c==pressed else 'false','look':looks[c]} for c in ('all','a','b','c')],'count':'6','text':'x'}
    distinct={'all':'blue|white','a':'lightblue|black','b':'lightblue|black','c':'lightblue|black'};same={k:'green|white' for k in distinct}
    chosen={'active':{'category':'a','focus_visible':True,'outline':'solid','outline_width':3,'shadow':'none'}}
    after=lambda looks:{**state(looks,'a'),'visible':['a','a']}
    ok=services_failures(state(distinct,'all'),chosen,after({**distinct,'a':'blue|white','all':'lightblue|black'}),state(distinct,'all'),'t')
    assert not [e for e in ok if 'visually' in e]
    bad=services_failures(state(same,'all'),chosen,after(same),state(same,'all'),'t')
    assert sum('visually distinguishable' in e for e in bad)==2


def test_services_v2_requires_metadata_and_single_h1_measured_missing_on_real_sites():
    """B3 input: no generated site had a meta description; services sites had no h1."""
    assert manifest(SERVICES_ID)['version']==2 and manifest(ID)['version']==1 and manifest(ID)['sha256']==CV_MANIFEST_SHA256
    for mutate in [lambda h:h.replace('<meta name="description"','<meta name="x-description"'),
                   lambda h:h.replace('<meta name="viewport" content="width=device-width, initial-scale=1">',''),
                   lambda h:h.replace('<h1>دليل الخدمات</h1>','<h2>دليل الخدمات</h2>'),
                   lambda h:h.replace('<h1>دليل الخدمات</h1>','<h1>دليل الخدمات</h1><h1>ثان</h1>')]:
        value=files();value['index.html']=mutate(value['index.html'])
        with pytest.raises(ProjectError):validate_source(value,SERVICES_ID)



def test_filter_shape_repair_does_not_end_the_job_on_an_unrelated_remaining_error():
    """Observed (web-services-v2-rx580-1): shape repair re-validated and raised on a short description."""
    from src.tools.web_recipes import repair_missing_button_type,FILTER_SHAPE_ERROR
    f=files();f['index.html']=f['index.html'].replace('type="button" class="service-filter"','class="service-filter"')
    f['index.html']=f['index.html'].replace('دليل تجريبي محلي للخدمات مع تصفية حسب الفئة؛ بيانات للعرض فقط ويمكن استبدالها بخدماتك الفعلية.','قصير')
    repaired,receipt=repair_missing_button_type(f,SERVICES_ID,FILTER_SHAPE_ERROR,0,{'project_id':'qa','job_id':'qa','purpose':'required_recipe_control_shape'})
    assert 'type="button" data-category="all"' in repaired['index.html'] or 'data-category="all" aria-pressed="true" type="button"' in repaired['index.html']
    with pytest.raises(ProjectError,match='meta description'):validate_source(repaired,SERVICES_ID)


@pytest.mark.parametrize('text,expected',[('أنشئ دليل خدمات محلي بدون إنترنت لمركز صيانة',True),('انشئ دليلا للخدمات',True),('Build a services directory',True),
    ('اكتب دليل استخدام للبرنامج',False),('ما هو دليل الخدمات؟',False)])
def test_services_directory_request_is_a_project(text,expected):
    """Found by the installed-app question battery: this request went to plain chat, which claimed to have prepared it."""
    from src.core.chat_dispatch import project_intent
    assert project_intent(text) is expected


@pytest.mark.parametrize('text',['افتح موقع example.com','افتح example.com','أضف رابط https://example.com/how في التذييل'])
def test_domain_names_are_not_explanation_words(text):
    from src.core.feature_intent import interpret_features
    assert interpret_features(text).issues==[]
