"""N065/N066/N071/N073/N097: fake adapters only; no real desktop launches."""
import time
import asyncio
import httpx
import pytest
from src.core.project_files import ProjectError
from tests.regression.test_chat_dispatch import Desktop, application, request_id


class Applications(Desktop):
    def __init__(self, apps=None):
        super().__init__()
        self.apps = apps if apps is not None else [
            {'id':'discord.desktop','name':'Discord','names':['Discord','ديسكورد']},
            {'id':'brave-browser.desktop','name':'Brave'},
            {'id':'Alacritty.desktop','name':'Alacritty'},
            {'id':'cmake.desktop','name':'CMake'},
        ]
    def status(self): return {**super().status(), 'applications':self.apps}
    def launch(self, app_id, uris=()):
        if self.failure: raise self.failure
        return super().launch(app_id, uris)


@pytest.mark.parametrize('text',[
    'هل يمكنك ان تفتح ديسكورد', 'هل يمكنك أن تفتح الديسكورد؟',
    'افتح دِيسْكورد', 'افتح دسكورد', 'افتح تطبيق discord',
    'Please open Discord', 'افتح  تطبيق   DISCORD',
])
def test_discord_aliases_launch_only_the_validated_id(system,text):
    app,desktop,dispatch=application(system,Applications())
    result=dispatch.dispatch(text,request_id(),session_id='chat_a')
    assert result['kind']=='action' and result['result']['status']=='launched'
    assert desktop.calls==[('app','discord.desktop',[])]
    assert 'Discord' in result['result']['message']
    assert not system.backend.calls and not system.backend.loads
    app.state.project_store.close()


@pytest.mark.parametrize('followup',['هذا هو افتحه','هذا هوا افتحه','افتحه','نعم افتح هذا التطبيق'])
def test_user_knowledge_question_then_explicit_followup(system,followup):
    app,desktop,dispatch=application(system,Applications())
    answer=dispatch.dispatch('هل تعرف الديسكورد بالإنجليزي',request_id(),session_id='chat_a')
    assert answer['kind']=='knowledge' and 'Discord' in answer['message']
    assert not desktop.calls and not system.backend.calls
    rid=request_id();opened=dispatch.dispatch(followup,rid,session_id='chat_a')
    assert opened['kind']=='action' and opened['result']['status']=='launched'
    assert desktop.calls==[('app','discord.desktop',[])]
    assert dispatch.dispatch(followup,rid,session_id='chat_a')==opened
    assert len(desktop.calls)==1 and not system.backend.calls
    app.state.project_store.close()


def test_unknown_and_relevant_ambiguity_never_fall_back_to_catalog(system):
    desktop=Applications([
        {'id':'discord-canary.desktop','name':'Discord Canary'},
        {'id':'discord-ptb.desktop','name':'Discord PTB'},
        {'id':'cmake.desktop','name':'CMake'},
    ])
    app,desktop,dispatch=application(system,desktop)
    result=dispatch.dispatch('افتح ديسكورد',request_id(),session_id='chat_a')
    assert result['kind']=='clarification'
    assert {c['label'] for c in result['choices']}=={'Discord Canary','Discord PTB'}
    missing=dispatch.dispatch('افتح تطبيق يونيكورن',request_id(),session_id='chat_a')
    assert missing['kind']=='action' and missing['result']['status']=='unavailable'
    assert not missing.get('choices') and not desktop.calls
    app.state.project_store.close()


def test_unavailable_discord_no_arbitrary_match(system):
    app,desktop,dispatch=application(system,Applications([{'id':'cmake.desktop','name':'CMake'}]))
    result=dispatch.dispatch('افتح الديسكورد',request_id(),session_id='chat_a')
    assert result['kind']=='action' and result['result']['status']=='unavailable'
    assert 'Discord' in result['result']['message'] and not desktop.calls
    app.state.project_store.close()


@pytest.mark.parametrize('text',['لا تفتح ديسكورد','"افتح ديسكورد"','```text\nافتح ديسكورد\n```',
                               'اشرح كيف أفتح ديسكورد','لا تفتحه','«هذا هوا افتحه»'])
def test_protected_user_text_cannot_launch_or_establish_context(system,text):
    app,desktop,dispatch=application(system,Applications())
    assert dispatch.dispatch(text,request_id(),session_id='chat_a')=={'kind':'chat'}
    answer=dispatch.dispatch('افتحه',request_id(),session_id='chat_a')
    assert answer['kind']=='action' and answer['result']['status']!='launched'
    assert not desktop.calls
    app.state.project_store.close()


def test_expiry_session_replacement_and_forged_choice(system):
    app,desktop,dispatch=application(system,Applications())
    dispatch.dispatch('هل تعرف الديسكورد بالإنجليزي',request_id(),session_id='chat_a')
    other=dispatch.dispatch('افتحه',request_id(),session_id='chat_b')
    assert other['result']['status']!='launched' and not desktop.calls
    dispatch.targets.clock=lambda:time.time()+301
    expired=dispatch.dispatch('افتحه',request_id(),session_id='chat_a')
    assert expired['result']['status']!='launched' and not desktop.calls
    dispatch.targets.clock=time.time
    dispatch.dispatch('هل تعرف الديسكورد بالإنجليزي',request_id(),session_id='chat_a')
    dispatch.dispatch('هل تعرف Brave',request_id(),session_id='chat_a')
    result=dispatch.dispatch('هذا هو افتحه',request_id(),session_id='chat_a')
    assert result['result']['status']=='launched' and desktop.calls==[('app','brave-browser.desktop',[])]
    app.state.project_store.close()


def test_choices_requests_are_bound_to_the_conversation_and_failure_is_authoritative(system):
    desktop=Applications([{'id':'editor-one.desktop','name':'Editor One'}, {'id':'editor-two.desktop','name':'Editor Two'}])
    app,desktop,dispatch=application(system,desktop)
    rid=request_id();result=dispatch.dispatch('افتح تطبيق Editor',rid,session_id='chat_a')
    assert result['kind']=='clarification'
    with pytest.raises(ProjectError):dispatch.choose(rid,result['choices'][0]['id'],session_id='chat_b')
    with pytest.raises(ProjectError):dispatch.get(rid,session_id='chat_b')
    desktop.failure=ProjectError('رفض GIO طلب Editor')
    failed=dispatch.choose(rid,result['choices'][0]['id'],session_id='chat_a')
    assert failed['kind']=='action' and failed['result']['status']=='error'
    assert failed['result']['message']=='رفض GIO طلب Editor' and not desktop.calls
    assert dispatch.choose(rid,result['choices'][0]['id'],session_id='chat_a')==failed
    assert not system.backend.calls
    app.state.project_store.close()


def test_authenticated_api_sessions_and_actual_failure_do_not_call_model(system):
    app,desktop,dispatch=application(system,Applications())
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8000',headers={'X-Neura-Token':app.state.token}) as client:
            rid=request_id()
            payload={'text':'هل تعرف الديسكورد بالإنجليزي','request_id':rid,'session_id':'api_a'}
            assert (await client.post('/chat/dispatch',json=payload)).json()['kind']=='knowledge'
            assert (await client.get('/chat/requests/'+rid,params={'session_id':'api_b'})).status_code==403
            assert (await client.post('/chat/dispatch',json={**payload,'session_id':'api_b'})).status_code==403
            bad={**payload,'request_id':request_id(),'session_id':'../escape'}
            assert (await client.post('/chat/dispatch',json=bad)).status_code==422
            desktop.failure=ProjectError('تعذر تشغيل Discord الحقيقي في محاكاة الفشل')
            body={'text':'هذا هوا افتحه','request_id':request_id(),'session_id':'api_a'}
            result=(await client.post('/chat/dispatch',json=body)).json()
            assert result['kind']=='action' and result['result']['status']=='error'
            assert 'تعذر' in result['result']['message'] and not desktop.calls and not system.backend.calls
            assert (await client.post('/chat/dispatch',json=body)).json()==result
    asyncio.run(check());app.state.project_store.close()


def test_context_is_bounded_and_uses_only_live_catalog_ids(system):
    app,desktop,dispatch=application(system,Applications())
    for i in range(135):
        dispatch.targets.set('session_'+str(i),desktop.apps,'user mention')
    assert app.state.project_store.db.execute('SELECT COUNT(*) FROM chat_target_context').fetchone()[0]==128
    dispatch.dispatch('هل تعرف ديسكورد',request_id(),session_id='live')
    desktop.apps=[{'id':'cmake.desktop','name':'CMake'}]
    result=dispatch.dispatch('افتحه',request_id(),session_id='live')
    assert result['result']['status']=='unavailable' and not desktop.calls
    app.state.project_store.close()


def test_new_topic_or_project_question_cannot_reuse_a_previous_app(system):
    app,desktop,dispatch=application(system,Applications());store=app.state.project_store
    pid=store.create('CV','test')['project_id'];store.commit(pid,{'main.py':'pass\n'},0)
    dispatch.dispatch('هل تعرف ديسكورد',request_id(),session_id='chat_a')
    dispatch.dispatch('ما هي لغات هذا المشروع؟',request_id(),pid,session_id='chat_a')
    assert dispatch.dispatch('افتحه',request_id(),session_id='chat_a')['result']['status']=='unavailable'
    dispatch.dispatch('هل تعرف ديسكورد',request_id(),session_id='chat_a')
    dispatch.dispatch('مرحبا',request_id(),session_id='chat_a')
    assert dispatch.dispatch('افتحه',request_id(),session_id='chat_a')['result']['status']=='unavailable'
    assert not desktop.calls
    store.close()


def test_multiple_user_targets_cannot_silently_become_one_available_app(system):
    app,desktop,dispatch=application(system,Applications([{'id':'brave-browser.desktop','name':'Brave'}]))
    response=dispatch.dispatch('هل تعرف Discord، أو Brave بالإنجليزي؟',request_id(),session_id='chat_a')
    assert response['kind']=='knowledge' and 'أكثر من تطبيق' in response['message']
    result=dispatch.dispatch('هذا هوا افتحه',request_id(),session_id='chat_a')
    assert result['result']['status']=='unavailable' and not desktop.calls
    app.state.project_store.close()
