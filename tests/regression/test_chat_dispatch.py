import asyncio
import concurrent.futures
import time
import uuid
from urllib.parse import parse_qs,urlsplit
import httpx
import pytest
from src.backend.api import create_app
from src.core.chat_dispatch import ChatDispatcher,project_intent
from src.core.project_files import ProjectError,Conflict
from tests.security.test_desktop_skills import FakeDesktop


def request_id(offset=0):return 'r_'+str(int((time.time()+offset)*1000))+'_'+uuid.uuid4().hex


class Desktop(FakeDesktop):
    def __init__(self):super().__init__();self.brave=True;self.disabled=[];self.failure=None
    def configuration(self):return {'brave_desktop_id':'brave-browser.desktop','disabled_skills':self.disabled}
    def status(self):return {**super().status(),'brave_available':self.brave,'applications':[{'id':'brave-browser.desktop','name':'Brave'},{'id':'calc.desktop','name':'Calculator'}]}
    def browser(self,url):
        if self.failure:raise self.failure
        return super().browser(url)


def application(system,desktop=None):
    fake=desktop or Desktop();app=create_app(system.settings,system,desktop_adapter=fake)
    return app,fake,app.state.chat_dispatcher


@pytest.mark.parametrize('text',['افتح يوتيوب','افتح لي موقع يوتيوب','هل يمكنك ان تفتح لي موقع youtube','هل يمكنك أن تفتح لي موقع YouTube؟','من فضلك افتح موقع يوتيوب','ممكن تفتحلي يوتيوب','Could you open YouTube?','هل يمكنك فتح موقع youtube','هل تقدر تفتح اليوتيوب','افتح يو تيوب'])
def test_natural_user_request_launches_known_site_without_model(system,text):
    app,fake,dispatch=application(system)
    result=dispatch.dispatch(text,request_id())
    assert result['kind']=='action' and result['result']['status']=='launched'
    assert fake.calls==[('browser','https://www.youtube.com/')]
    assert not system.backend.calls and not system.backend.loads
    app.state.project_store.close()


@pytest.mark.parametrize('text',['كيف أفتح يوتيوب بنفسي؟','لا تفتح يوتيوب','اشرح الجملة: افتح يوتيوب','"افتح يوتيوب"','«افتح يوتيوب»','```text\nافتح يوتيوب\n```','هل يمكنك أن لا تفتح يوتيوب','Please do not open YouTube','اكتب دالة add','اشرح كيف أنشئ موقعًا'])
def test_explanation_negation_quotation_code_stay_chat(system,text):
    app,fake,dispatch=application(system)
    assert dispatch.dispatch(text,request_id())=={'kind':'chat'}
    assert not fake.calls and not app.state.project_store.list()
    app.state.project_store.close()


def test_search_app_and_named_project_folder(system):
    app,fake,dispatch=application(system)
    dispatch.dispatch('ابحث في يوتيوب عن تعلم Python بالعربي',request_id())
    assert parse_qs(urlsplit(fake.calls[-1][1]).query)['search_query']==['تعلم Python بالعربي']
    dispatch.dispatch('افتح Brave',request_id());assert fake.calls[-1][0:2]==('app','brave-browser.desktop')
    store=app.state.project_store;p=store.create('موقع السيرة الذاتية','CV')['project_id']
    dispatch.dispatch('افتح مجلد مشروع السيرة الذاتية',request_id())
    assert fake.calls[-1]==('folder',{'project_id':p})
    store.close()


def test_ambiguity_choices_are_server_bound_and_execute_once(system):
    app,fake,dispatch=application(system);store=app.state.project_store
    for name in ('موقع السيرة الذاتية الأول','موقع السيرة الذاتية الثاني'):store.create(name,'CV')
    rid=request_id();result=dispatch.dispatch('افتح مجلد مشروع السيرة الذاتية',rid)
    assert result['kind']=='clarification' and len(result['choices'])==2 and not fake.calls
    with pytest.raises(ProjectError):dispatch.choose(rid,'o_'+'a'*32)
    choice=result['choices'][0]['id'];opened=dispatch.choose(rid,choice)
    assert opened['result']['status']=='launched'
    assert dispatch.choose(rid,choice)==opened and len(fake.calls)==1
    with pytest.raises(Conflict):dispatch.choose(rid,result['choices'][1]['id'])
    store.close()


def test_retry_failure_and_restart_never_repeat_launch(system):
    app,fake,dispatch=application(system);rid=request_id()
    first=dispatch.dispatch('افتح يوتيوب',rid)
    assert dispatch.dispatch('افتح يوتيوب',rid)==first and len(fake.calls)==1
    with pytest.raises(Conflict):dispatch.dispatch('افتح Brave',rid)
    store=app.state.project_store
    store.db.execute("UPDATE chat_requests SET state='running' WHERE id=?",(rid,));store.db.commit()
    restored=ChatDispatcher(store,app.state.desktop_skills,app.state.project_jobs)
    assert restored.dispatch('افتح يوتيوب',rid)['result']['status']=='unknown' and len(fake.calls)==1
    fake.failure=ProjectError('فشل مشغل سطح المكتب');rid=request_id()
    failed=restored.dispatch('افتح يوتيوب',rid)
    assert failed['result']['message']=='فشل مشغل سطح المكتب'
    fake.failure=None
    assert restored.dispatch('افتح يوتيوب',rid)==failed and len(fake.calls)==1
    with pytest.raises(ProjectError):restored.dispatch('افتح يوتيوب',request_id(-3*86400))
    store.close()


def test_unavailable_disabled_and_missing_location_are_truthful(system):
    app,fake,dispatch=application(system)
    fake.brave=False
    result=dispatch.dispatch('افتح يوتيوب',request_id());assert result['result']['status']=='unavailable' and 'Brave' in result['result']['message']
    fake.brave=True;fake.disabled=['open_website']
    assert 'معطلة' in dispatch.dispatch('افتح يوتيوب',request_id())['result']['message']
    assert not fake.calls and not system.backend.calls
    app.state.project_store.close()


def test_project_metadata_questions_avoid_model_after_edits(system):
    app,fake,dispatch=application(system);store=app.state.project_store
    p=store.create('موقع سيرة','سيرة مطور')['project_id']
    store.commit(p,{'index.html':'<h1>CV</h1>'},0)
    result=dispatch.dispatch('ما لغة هذا المشروع؟',request_id(),p)
    assert result['kind']=='metadata' and 'HTML' in result['message'] and not result['model_called']
    opened=store.read(p,'index.html');store.save_file(p,'index.html','<h1>CV</h1><style>h1{color:red}</style>',1,opened['sha256'])
    result=dispatch.dispatch('ما هي لغات المشروع؟',request_id(),p)
    assert 'CSS' in result['message'] and 'HTML' in result['message']
    assert dispatch.dispatch('لماذا يتعطل هذا المشروع؟',request_id(),p)=={'kind':'chat'}
    assert not fake.calls and not system.backend.calls
    store.close()


def test_concurrent_reconnection_observes_pending_without_second_launch(system):
    import threading
    entered=threading.Event();release=threading.Event()
    class Slow(Desktop):
        def browser(self,url):
            entered.set();release.wait(3)
            return super().browser(url)
    app,fake,dispatch=application(system,Slow());rid=request_id()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        first=executor.submit(dispatch.dispatch,'افتح يوتيوب',rid)
        assert entered.wait(2)
        try:
            assert dispatch.dispatch('افتح يوتيوب',rid)['kind']=='pending'
            assert not fake.calls
        finally:release.set()
        result=first.result(timeout=3)
    assert dispatch.get(rid)==result and len(fake.calls)==1
    app.state.project_store.close()


def test_missing_approved_file_reports_specific_error(system):
    class Missing(Desktop):
        def status(self):return {**super().status(),'locations':[{'id':'l_'+'a'*32,'kind':'file','name':'notes.txt'}]}
        def open_file(self,args):raise FileNotFoundError('removed after selection')
    app,fake,dispatch=application(system,Missing())
    result=dispatch.dispatch('افتح ملف notes.txt',request_id())
    assert result['result']['status']=='error' and 'غير موجود' in result['result']['message']
    assert not fake.calls and not system.backend.calls
    app.state.project_store.close()


def test_chat_api_strict_auth_and_shared_manual_dispatch(system):
    app,fake,dispatch=application(system)
    async def invoke():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8000',headers={'X-Neura-Token':app.state.token}) as client:
                payload={'text':'هل يمكنك ان تفتح لي موقع youtube','request_id':request_id()}
                for headers in ({'Origin':'null'},{'X-Neura-Token':''}):assert (await client.post('/chat/dispatch',json=payload,headers=headers)).status_code==403
                for extra in ({'name':'terminal','args':{'command':'bad'}},{'source':'assistant'},{'permission_id':'g_'+'a'*32}):assert (await client.post('/chat/dispatch',json={**payload,**extra})).status_code==422
                result=(await client.post('/chat/dispatch',json=payload)).json()
                assert result['result']['status']=='launched' and len(fake.calls)==1
                assert (await client.post('/chat/dispatch',json=payload)).json()==result
                assert (await client.get('/chat/requests/'+payload['request_id'])).json()==result
                assert (await client.get('/chat/requests/'+payload['request_id'],headers={'X-Neura-Token':''})).status_code==403
                grant=(await client.post('/skills/authorize',json={'name':'open_application','args':{'application_id':'calc.desktop'},'remember':True})).json()
                manual={'name':'open_application','args':{'application_id':'calc.desktop'},'permission_id':grant['permission_id'],'request_id':request_id()}
                response=(await client.post('/skills/execute',json=manual)).json()
                assert response['kind']=='action' and response['result']['status']=='launched'
                assert (await client.post('/skills/execute',json=manual)).json()==response
                assert len(fake.calls)==2 and not system.backend.calls
    asyncio.run(invoke())


def test_cv_chat_request_creates_one_durable_job_with_real_events(system):
    app,fake,dispatch=application(system);store=app.state.project_store
    system.backend.text='```html index.html\n<link rel="stylesheet" href="style.css"><h1>CV</h1><script src="script.js"></script>\n```\n```css style.css\nh1{color:red}\n```\n```javascript script.js\ndocument.querySelector("h1").textContent="CV";\n```'
    text='أنشئ لي موقع سيرة ذاتية باستخدام HTML وCSS وJavaScript';rid=request_id()
    result=dispatch.dispatch(text,rid);assert result['kind']=='project'
    assert dispatch.dispatch(text,rid)==result and len(store.list())==1
    job=result['job']['job_id'];jobs=app.state.project_jobs
    for _ in range(300):
        snapshot=jobs.get(job)
        if snapshot['state'] in ('completed','failed'):break
        time.sleep(.005)
    assert snapshot['state']=='completed',snapshot
    meta=store.get(result['project']['project_id'])
    assert {f['path'] for f in meta['files']}=={'index.html','style.css','script.js'}
    assert meta['preview']['supported'] and len(system.backend.calls)==2
    events=jobs.events(job,0);assert any(e['type']=='file_delta' for e in events) and events[-1]['type']=='job_completed'
    jobs.shutdown();store.close()
