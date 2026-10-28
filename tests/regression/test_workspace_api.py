import asyncio
import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
import httpx
from src.backend.api import create_app
from src.core.project_preview import PreviewServer
from src.core.project_store import ProjectStore
from src.desktop.preview_policy import navigation_allowed, request_allowed
from tests.regression.test_project_store import WEB


def test_project_api_events_revision_and_origin(system):
    system.backend.text='```html index.html\n<h1>CV</h1>\n```'
    app=create_app(system.settings,system)
    async def invoke():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8000',headers={'X-Neura-Token':app.state.token}) as client:
                assert (await client.get('/projects',headers={'X-Neura-Token':''})).status_code==403
                response=await client.post('/projects',json={'background':True,'title':'CV','user_request':'create website','requirements':['CV']})
                assert response.status_code==202,response.text
                project_id=response.json()['project']['project_id'];job_id=response.json()['job']['job_id']
                for _ in range(200):
                    job=(await client.get('/project-jobs/'+job_id)).json()
                    if job['state'] in ('completed','failed'):break
                    await asyncio.sleep(.005)
                assert job['state']=='completed',job
                stream=await client.get('/project-jobs/'+job_id+'/events')
                events=[json.loads(line[6:]) for line in stream.text.splitlines() if line.startswith('data: ')]
                assert events[-1]['type']=='job_completed'
                assert len(system.backend.calls)==1
                assert (await client.get('/project-jobs/'+job_id+'/events',headers={'Last-Event-ID':str(events[-1]['seq'])})).text==''
                file=(await client.get('/projects/'+project_id+'/file',params={'path':'index.html'})).json()
                saved=await client.put('/projects/'+project_id+'/file',json={'path':'index.html','content':'<h1>Edited</h1>','expected_revision':file['project_revision'],'expected_sha256':file['sha256']})
                assert saved.status_code==200,saved.text
                conflict=await client.put('/projects/'+project_id+'/file',json={'path':'index.html','content':'old','expected_revision':1,'expected_sha256':file['sha256']})
                assert conflict.status_code==409
                assert (await client.get('/projects/'+project_id+'/file',params={'path':'../escape'})).status_code==400
                assert (await client.post('/projects/'+project_id+'/question',json={'question':'ما هو هذا المشروع؟'})).json()['model_called'] is False
                assert len(system.backend.calls)==1
                for headers in [{'Origin':'null'},{'Origin':app.state.preview.origin},{'Sec-Fetch-Site':'cross-site'}]:
                    assert (await client.get('/projects',headers=headers)).status_code==403
                    assert (await client.post('/projects',json={'user_request':'bad','requirements':['bad']},headers=headers)).status_code==403
                preview=await client.post('/projects/'+project_id+'/preview',json={'expected_revision':2})
                assert preview.status_code==200 and preview.json()['origin']!='http://127.0.0.1:8000'
                assert (await client.get('/workspace/preferences')).json()['swapped'] is False
                assert (await client.put('/workspace/preferences',json={'swapped':True,'ratio':60,'last_project':project_id})).status_code==200
    asyncio.run(invoke())


def test_preview_assets_are_capability_scoped_and_sandboxed(tmp_path):
    store=ProjectStore(tmp_path);p=store.create('CV','CV')['project_id']
    store.commit(p,{**WEB,'notes.txt':'private','secret.json':'{}'},0)
    preview=PreviewServer(store)
    try:
        record=preview.issue(p,'http://127.0.0.1:8000',1)
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(record['url']) as response:
            assert b'CV' in response.read()
            policy=response.headers['Content-Security-Policy']
            assert 'sandbox allow-scripts;' in policy and "connect-src 'none'" in policy
            assert 'allow-same-origin' not in policy
            assert 'X-Neura-Token' not in str(response.headers)
            assert 'camera=()' in response.headers['Permissions-Policy']
        prefix=record['url'].rsplit('/',1)[0]+'/'
        for suffix in ['.neura/project.json','%2e%2e/secret.json','notes.txt','secret.json','/etc/passwd','%252e%252e/a']:
            try:opener.open(prefix+suffix)
            except urllib.error.HTTPError as exc:assert exc.code==404
            else:raise AssertionError('Private file served: '+suffix)
        with opener.open(prefix+'style.css') as response:assert response.read()==WEB['style.css'].encode()
        other=store.create('other','other')['project_id'];store.commit(other,{'index.html':'other'},0)
        assert record['project_id']!=other
    finally:
        preview.stop();store.close()


def test_qt_navigation_and_opaque_initiator_policy():
    app='http://127.0.0.1:8000';preview='http://127.0.0.1:8001';url=preview+'/p/'+'a'*48+'/index.html'
    assert navigation_allowed(url,app,preview,False)
    assert not navigation_allowed(app,app,preview,False)
    assert not navigation_allowed('file:///etc/passwd',app,preview,True)
    assert not navigation_allowed('http://127.0.0.1:9999',app,preview,False)
    assert not request_allowed(app+'/projects','null',app,preview)
    assert not request_allowed(app+'/projects',preview,app,preview)
    assert not request_allowed('https://example.com/a.js',url,app,preview)
    assert request_allowed(app+'/projects',app,app,preview)


def test_frontend_sse_utf8_fragmentation_and_project_intent():
    root=Path(__file__).resolve().parents[2]
    script=r'''
const assert=require('node:assert/strict');
const {NeuraSSEDecoder,neuraProjectIntent}=require('./web/workspace.js');
const got=[];const parser=new NeuraSSEDecoder(e=>got.push(e));
const bytes=new TextEncoder().encode('id: 1\r\nevent: file_delta\r\ndata: {"text":"مرحبا 🌍"}\r\n\r\nid: 2\ndata: first\ndata: second\n\n');
for(const byte of bytes)parser.feed(new Uint8Array([byte]));parser.finish();
assert.equal(got.length,2);assert.equal(JSON.parse(got[0].data).text,'مرحبا 🌍');assert.equal(got[1].data,'first\nsecond');
for(const text of ['أنشئ موقع سيرة ذاتية','اكتب برنامج Python','Build a website'])assert.equal(neuraProjectIntent(text),true,text);
for(const text of ['اشرح كيف أكتب برنامج','كيف أصنع موقع؟','debug this app','اكتب دالة add','ما هو هذا الكود؟'])assert.equal(neuraProjectIntent(text),false,text);
'''
    result=subprocess.run(['node','-e',script],cwd=root,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
