"""No administrative updates: admission gate and Qt callbacks use fake work."""
import asyncio,threading
from types import SimpleNamespace
import httpx,pytest
from src.backend.api import create_app
from src.core.neura_loop import InferenceError
from src.core.project_files import Conflict
from src.desktop.app import UpdateDialog

def test_downloaded_package_does_not_stop_before_work_review():
    events=[]
    class Window:
        service=SimpleNamespace(stop=lambda:events.append('STOP'))
        def task(self,fn,success,failure):success(fn(None))
        def prepare_update(self,success,failure):events.append('REVIEW')
    dialog=SimpleNamespace(cancelled=False,window=Window(),status=SimpleNamespace(setText=lambda _:None),
        authorize=lambda _:events.append('AUTHORIZE'),error=lambda _:None)
    UpdateDialog.downloaded(dialog,'owned-qa-package')
    assert events==['REVIEW']

def test_backend_reservation_blocks_admission_and_releases_safely(system):
    app=create_app(system.settings,system);jobs=app.state.project_jobs
    reservation='u_'+'a'*32
    async def check():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8000',headers={'X-Neura-Token':app.state.token}) as client:
                assert (await client.post('/lifecycle/update/prepare',json={'reservation_id':reservation},headers={'Origin':'null'})).status_code==403
                value=await client.post('/lifecycle/update/prepare',json={'reservation_id':reservation})
                assert value.status_code==200,value.text
                assert (await client.post('/lifecycle/update/prepare',json={'reservation_id':reservation})).status_code==200
                with pytest.raises(InferenceError,match='update|تحديث'):system.complete([{'role':'user','content':'QA'}])
                with pytest.raises(Conflict):jobs.create({'user_request':'Create QA','requirements':['QA']})
                assert (await client.post('/lifecycle/update/release',json={'reservation_id':'u_'+'b'*32})).status_code==409
                assert (await client.post('/lifecycle/update/release',json={'reservation_id':reservation})).status_code==200
                assert (await client.post('/lifecycle/update/release',json={'reservation_id':reservation})).status_code==200
                assert system.complete([{'role':'user','content':'QA'}])['choices'][0]['message']['content']=='answer'
    asyncio.run(check())

def test_update_gate_does_not_cancel_an_active_native_request(system):
    app=create_app(system.settings,system);jobs=app.state.project_jobs
    release=threading.Event();system.backend.release=release;errors=[]
    def run():
        try:system.complete([{'role':'user','content':'QA active'}])
        except Exception as exc:errors.append(str(exc))
    thread=threading.Thread(target=run);thread.start()
    try:
        assert system.backend.entered.wait(2)
        with pytest.raises(Conflict):jobs.prepare_update('u_'+'c'*32)
        assert not release.is_set() and thread.is_alive()
    finally:release.set();thread.join(3);jobs.shutdown();app.state.project_store.close()
    assert not errors and not thread.is_alive()

def test_update_gate_rejects_queued_job_even_before_native_load(system):
    app=create_app(system.settings,system);store=app.state.project_store;jobs=app.state.project_jobs
    # A durable queued job is an admission conflict even when no model runs yet.
    with store.lock:
        store.db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)",('j_'+'a'*32,'p_'+'b'*32,'queued','{}','{}',0,0,None,'QA','QA'));store.db.commit()
    try:
        with pytest.raises(Conflict):jobs.prepare_update('u_'+'d'*32)
        assert not getattr(system,'_maintenance',False)
    finally:jobs.shutdown();store.close()
