import asyncio
import base64
import json
import threading
import httpx
import pytest
from src.backend.api import create_app
from src.tools.safe_actions import SafeActions


def run(system, callback, *, actions=None):
    app=create_app(system.settings,system,actions=actions)
    async def invoke():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8000',headers={'X-Neura-Token':app.state.token}) as client:
            return await callback(client,app)
    return asyncio.run(invoke())


def test_route_is_selection_only(system):
    async def check(client,app):
        response=await client.post('/route',json={'text':'اكتب دالة Python'})
        assert response.status_code==200
        assert response.json()['model_id']=='qwen3.5-9b-claude-distilled-q4'
        assert not system.backend.loads and not system.backend.calls
    run(system,check)


def test_health_and_stats_are_truthful(system):
    async def check(client,app):
        health=(await client.get('/health')).json()
        assert health['tiers']['daily']['available'] and not health['tiers']['daily']['loaded']
        assert health['inference_verified'] is False
        stats=(await client.get('/stats')).json()
        assert stats['gpu']['temperature'] is None
        assert stats['live']['tps'] is None
        assert stats['mgr']['vram_is_estimate']
    run(system,check)


def test_cpu_inference_does_not_claim_unrelated_gpu_usage(system,monkeypatch):
    monkeypatch.setattr('src.backend.api.gpu_memory',lambda:{'device':'/unknown','used_gb':14,'total_gb':16,'free_gb':2})
    system.current_model_id='gemma-4-e4b-q4'
    system.backend.selected_device={'description':'CPU'}
    async def check(client,app):
        gpu=(await client.get('/stats')).json()['gpu']
        assert gpu['selected_device']['description']=='CPU'
        assert gpu['vram_gb'] is None and gpu['load'] is None
    run(system,check)


def test_chat_history_parameters_and_tier(system,messages):
    async def check(client,app):
        response=await client.post('/v1/chat/completions',json={'messages':messages,'neura':{'tier':'fast'},'temperature':.3,'max_tokens':123,'top_p':.8})
        assert response.status_code==200,response.text
        result=response.json();assert result['model']=='gemma-4-e4b-q4'
        assert system.backend.calls[-1]['messages']==messages
        assert system.backend.calls[-1]['max_tokens']==123
        assert result['usage']['total_tokens']==8
    run(system,check)


@pytest.mark.parametrize('payload', [
 {'messages':[]},
 {'messages':[{'role':'user','content':''}]},
 {'messages':[{'role':'invalid','content':'hi'}]},
 {'messages':[{'role':'user','content':'hi'}],'max_tokens':999999},
 {'messages':[{'role':'user','content':'hi'}],'temperature':-1},
 {'messages':[{'role':'user','content':'hi'}],'tier':'bad'},
 {'messages':[{'role':'user','content':'hi'}],'unknown':'field'},
])
def test_chat_contract_rejects_invalid_requests(system,payload):
    async def check(client,app):
        response=await client.post('/v1/chat/completions',json=payload)
        assert response.status_code==422
        assert 'error' in response.json()
        assert not system.backend.loads
    run(system,check)


def test_empty_generation_and_selection_errors(system,messages):
    async def check(client,app):
        response=await client.post('/route',json={'text':'hi','tier':'fast','deep':True})
        assert response.status_code==400
        response=await client.post('/v1/chat/completions',json={'messages':messages,'tier':'fast','model':'qwen3.5-9b-q4'})
        assert response.status_code==400
        system.backend.text=''
        response=await client.post('/v1/chat/completions',json={'messages':messages})
        assert response.status_code==502
        assert response.json()['error']['type']=='empty_completion'
    run(system,check)


def test_native_sse_and_finish_reason(system,messages):
    system.backend.finish='length'
    async def check(client,app):
        response=await client.post('/v1/chat/completions',json={'messages':messages,'stream':True})
        assert response.status_code==200,response.text
        assert response.headers['x-neura-model']=='qwen3.5-9b-q4'
        events=[line[6:] for line in response.text.splitlines() if line.startswith('data: ')]
        assert events[-1]=='[DONE]'
        chunks=[json.loads(line) for line in events[:-1]]
        assert chunks[-1]['choices'][0]['finish_reason']=='length'
        assert ''.join(c['choices'][0]['delta'].get('content','') for c in chunks)=='answer'
    run(system,check)


def test_error_before_stream_starts_is_http_error(system,messages):
    system.backend.failure=ValueError('broken')
    async def check(client,app):
        response=await client.post('/v1/chat/completions',json={'messages':messages,'stream':True})
        assert response.status_code==502
    run(system,check)


def test_empty_stream_has_explicit_sse_error(system,messages):
    system.backend.text=''
    async def check(client,app):
        response=await client.post('/v1/chat/completions',json={'messages':messages,'stream':True})
        assert 'empty_completion' in response.text
        assert '[DONE]' not in response.text
    run(system,check)


def test_missing_model_is_503_without_silent_substitution(system,messages):
    system.residency.model_path('gemma-4-e4b-q4').unlink()
    async def check(client,app):
        response=await client.post('/v1/chat/completions',json={'messages':messages,'tier':'fast'})
        assert response.status_code==503
        assert not system.backend.loads
    run(system,check)


def test_auth_origin_and_host(system):
    async def check(client,app):
        for headers in [{'x-neura-token':''}, {'x-neura-token':'wrong'}, {'origin':'https://example.com'}, {'sec-fetch-site':'cross-site'}]:
            response=await client.post('/route',json={'text':'hello'},headers=headers)
            assert response.status_code==403
        assert (await client.get('/health',headers={'host':'evil.example'})).status_code==400
        assert (await client.get('/vault/sessions',headers={'x-neura-token':''})).status_code==403
        root=await client.get('/')
        assert app.state.token in root.text
        assert 'cdn.tailwindcss.com' not in root.text
        assert 'Content-Security-Policy' in root.headers
    run(system,check)


def test_vault_crud_and_reopen(system,messages):
    async def check(client,app):
        response=await client.post('/vault/save',json={'session':'test-session','messages':messages})
        assert response.status_code==200
        assert (await client.get('/vault/sessions/test-session')).json()['messages']==messages
        assert len((await client.get('/vault/sessions')).json()['sessions'])==1
    run(system,check)
    async def reopen(client,app):
        assert (await client.get('/vault/sessions/test-session')).status_code==200
        assert (await client.delete('/vault/sessions/test-session')).status_code==200
        assert (await client.get('/vault/sessions/test-session')).status_code==404
        assert (await client.post('/vault/save',json={'session':'../escape','messages':messages})).status_code==422
    run(system,reopen)


def test_tools_are_real_or_explicitly_unavailable(system):
    actions=SafeActions(search_provider=lambda *a,**k:[{'title':'test','body':'content','href':'https://example.com'}])
    async def check(client,app):
        assert (await client.post('/tool/call',json={'tool':'terminal','args':{'command':'echo hi'}})).status_code==501
        assert (await client.post('/tool/approve',json={'id':'made-up'})).status_code==404
        assert (await client.post('/tool/call',json={'tool':'search_web','args':{'query':'hi'}})).json()['results'][0]['title']=='test'
        assert (await client.post('/tool/call',json={'tool':'search_web','args':{'query':'hi','command':'bad'}})).status_code==422
        assert (await client.get('/tool/pending')).json()['pending']==[]
    run(system,check,actions=actions)


def test_optional_voice_reports_unavailable(system,monkeypatch):
    from src.core.voice_service import VoiceService
    monkeypatch.setattr(VoiceService,'capabilities',lambda s:{'stt':False,'tts':False,'stt_reason':'missing CLI','tts_reason':'missing voice'})
    async def check(client,app):
        assert (await client.post('/stt',content=b'audio')).status_code==501
        assert (await client.post('/tts',json={'text':'hi'})).status_code==501
    run(system,check)


def test_image_data_reaches_same_coordinator(system):
    image='data:image/png;base64,'+base64.b64encode(b'\x89PNG\r\n\x1a\ntest').decode()
    async def check(client,app):
        content=[{'type':'text','text':'describe'},{'type':'image_url','image_url':{'url':image}}]
        response=await client.post('/v1/chat/completions',json={'messages':[{'role':'user','content':content}]})
        assert response.status_code==200,response.text
        assert response.json()['tier']=='vision'
        assert system.backend.calls[-1]['messages'][0]['content']==content
        assert system.backend.loads[-1][1]['projector'].name.startswith('mmproj')
        content[1]['image_url']['url']='http://127.0.0.1/private'
        assert (await client.post('/v1/chat/completions',json={'messages':[{'role':'user','content':content}]})).status_code==422
    run(system,check)


def test_health_responsive_during_generation(system,messages):
    async def check(client,app):
        system.backend.release=threading.Event()
        task=asyncio.create_task(client.post('/v1/chat/completions',json={'messages':messages}))
        while not system.backend.entered.is_set():await asyncio.sleep(.005)
        health=await asyncio.wait_for(client.get('/health'),timeout=.5)
        assert health.status_code==200
        system.backend.release.set()
        assert (await task).status_code==200
    run(system,check)


def test_timeout_is_504(system,messages):
    system.settings.timeout_s=.03
    system.backend.delay=.4
    async def check(client,app):
        response=await client.post('/v1/chat/completions',json={'messages':messages})
        assert response.status_code==504,response.text
    run(system,check)


def test_expert_deep_alias_and_empty_content_parts(system,messages):
    async def check(client,app):
        response=await client.post('/v1/chat/completions',json={'messages':messages,'tier':'expert','neura':{'deep':True}})
        assert response.status_code==200
        assert response.json()['tier']=='expert'
        response=await client.post('/v1/chat/completions',json={'messages':[{'role':'user','content':[{'type':'text','text':'  '}]}]})
        assert response.status_code==422
    run(system,check)
