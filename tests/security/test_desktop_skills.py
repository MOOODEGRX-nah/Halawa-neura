import asyncio
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs,urlsplit
import httpx
import pytest
from pydantic import ValidationError
from src.tools.desktop_skills import DesktopSkills,PermissionDenied,website_url
from src.core.project_store import ProjectStore
from src.core.project_files import ProjectError
from src.desktop.actions import DesktopAdapter
from src.backend.api import create_app


class FakeDesktop:
    def __init__(self):self.calls=[]
    def status(self):return {'desktop_available':True,'brave_available':True,'reason':'','applications':[{'id':'calc.desktop','name':'Calculator'}],'locations':[]}
    def browser(self,url):self.calls.append(('browser',url));return {'status':'launched','message':'launch request','application_id':'brave-browser.desktop'}
    def launch(self,app,uris=()):self.calls.append(('app',app,list(uris)));return {'status':'launched','message':'launch request','application_id':app}
    def open_file(self,args):self.calls.append(('file',args));return {'status':'launched','message':'view request'}
    def open_folder(self,args):self.calls.append(('folder',args));return {'status':'launched','message':'folder request'}


def test_specific_grant_cannot_be_reused_or_changed(tmp_path):
    store=ProjectStore(tmp_path);fake=FakeDesktop();skills=DesktopSkills(store,fake)
    grant=skills.authorize('open_website',{'destination':'يوتيوب'})['permission_id']
    with pytest.raises(PermissionDenied):skills.execute('open_website',{'destination':'https://example.com/'},grant)
    assert not fake.calls
    assert skills.execute('open_website',{'destination':'يوتيوب'},grant)['status']=='launched'
    with pytest.raises(PermissionDenied):skills.execute('open_website',{'destination':'يوتيوب'},grant)
    remembered=skills.authorize('open_application',{'application_id':'calc.desktop'},True)['permission_id']
    skills.execute('open_application',{'application_id':'calc.desktop'},remembered)
    assert skills.recent()[0]['application_id']=='calc.desktop'
    skills.revoke(remembered)
    with pytest.raises(PermissionDenied):skills.execute('open_application',{'application_id':'calc.desktop'},remembered)
    store.close()


@pytest.mark.parametrize('url',['javascript:alert(1)','file:///tmp/a','ftp://example.com','https://user:password@example.com','https://example.com\n/path','https://example.com:bad/'])
def test_website_scheme_and_credentials_rejected(url):
    with pytest.raises(ProjectError):website_url(url)


def test_arabic_search_encoding_and_private_history(tmp_path):
    store=ProjectStore(tmp_path);fake=FakeDesktop();skills=DesktopSkills(store,fake)
    query='تعلم Python بالعربي & password=do-not-store'
    for name,param in [('search_web','q'),('search_youtube','search_query')]:
        grant=skills.authorize(name,{'query':query})['permission_id']
        result=skills.execute(name,{'query':query},grant)
        assert parse_qs(urlsplit(fake.calls[-1][1]).query)[param]==[query]
        assert 'لم تُقرأ' in result['message']
    assert query not in str(skills.history())
    assert 'do-not-store' not in str(skills.grants())
    for name,args in [('terminal',{'command':'touch marker'}),('install_skill',{'path':'bad.py'})]:
        with pytest.raises(ProjectError):skills.authorize(name,args)
    with pytest.raises(ValidationError):skills.authorize('open_application',{'application_id':'calc.desktop','command':'bad'})
    store.close()


def test_source_files_open_in_editor_and_never_execute(tmp_path,monkeypatch):
    store=ProjectStore(tmp_path);project=store.create('Python','test')['project_id']
    marker=tmp_path/'executed'
    store.commit(project,{'main.py':f'from pathlib import Path\nPath({str(marker)!r}).touch()\n'},0)
    calls=[]
    def runner(command,**kwargs):calls.append((command,kwargs));return SimpleNamespace(returncode=0)
    adapter=DesktopAdapter(store,settings={'approved_locations':{},'brave_desktop_id':'brave-browser.desktop'},runner=runner)
    monkeypatch.setattr(adapter,'status',lambda:{'desktop_available':True})
    monkeypatch.setattr(adapter,'catalog',lambda:{'org.kde.kate.desktop':{'id':'org.kde.kate.desktop','entry':'/usr/share/applications/org.kde.kate.desktop','name':'Kate'}})
    result=adapter.open_file({'project_id':project,'path':'main.py'})
    assert result['status']=='launched' and not marker.exists()
    assert calls[0][0][1:3]==['launch','/usr/share/applications/org.kde.kate.desktop']
    assert calls[0][1]['shell'] is False
    assert '/view-cache/' in calls[0][0][3]
    assert str(marker) not in str(calls[0][0])
    store.close()


def test_arbitrary_paths_and_untrusted_desktop_entries_rejected(tmp_path):
    store=ProjectStore(tmp_path);skills=DesktopSkills(store,FakeDesktop())
    with pytest.raises(ValidationError):skills.authorize('open_file',{'path':'/etc/passwd'})
    with pytest.raises(ValidationError):skills.authorize('open_folder',{'selection_id':'l_'+'a'*32,'path':'/tmp'})
    root=tmp_path/'applications';root.mkdir()
    (root/'evil.desktop').write_text('[Desktop Entry]\nType=Application\nName=Evil\nExec=sh -c bad\n')
    (root/'linked.desktop').symlink_to(root/'evil.desktop')
    adapter=DesktopAdapter(store,settings={},roots=[root])
    assert not adapter.catalog()  # User-created/untrusted launchers never enter the catalog.
    store.close()


def test_api_grants_require_app_origin_and_token(system):
    fake=FakeDesktop();app=create_app(system.settings,system,desktop_adapter=fake)
    async def invoke():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8000',headers={'X-Neura-Token':app.state.token}) as client:
                for headers in [{'X-Neura-Token':''},{'Origin':'null'},{'Origin':'http://127.0.0.1:9999'}]:
                    response=await client.post('/skills/authorize',json={'name':'open_application','args':{'application_id':'calc.desktop'}},headers=headers)
                    assert response.status_code==403
                response=await client.post('/skills/execute',json={'name':'open_application','args':{'application_id':'calc.desktop'},'permission_id':'g_'+'a'*32})
                assert response.status_code==403 and not fake.calls
                grant=(await client.post('/skills/authorize',json={'name':'open_application','args':{'application_id':'calc.desktop'}})).json()
                result=await client.post('/skills/execute',json={'name':'open_application','args':{'application_id':'calc.desktop'},**grant})
                assert result.status_code==422  # Extra fields in the response cannot be replayed as request fields.
                result=await client.post('/skills/execute',json={'name':'open_application','args':{'application_id':'calc.desktop'},'permission_id':grant['permission_id']})
                assert result.status_code==200 and len(fake.calls)==1
                description=(await client.get('/skills')).json()
                assert len(description['desktop_skills'])==7
                assert all(x['input_schema'] and x['permissions'] for x in description['desktop_skills'])
    asyncio.run(invoke())
