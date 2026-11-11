"""Deterministic policy/queue tests: fake inference and synthetic process samples."""
import json,time,threading
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import pytest
from src.core.resource_policy import ProtectionConfig,TriggerState,ProcessRule,save_config,read_config
from src.core.resource_detection import game_processes,parse_fdinfo,cpu_pressure
from src.core.project_store import ProjectStore
from src.core.project_jobs import ProjectJobs
from src.core.neura_loop import InferenceError,ResourceBlocked


def process(pid=1,name='game',exe='/games/game',ppid=0,appid=None,started=1,cmdline=None):
    return dict(pid=pid,name=name,exe=exe,ppid=ppid,started=started,env={'SteamAppId':appid} if appid else {},cmdline=cmdline or [])

@pytest.mark.parametrize('name',['steam','lutris','heroic','wine','wineserver','proton','steamwebhelper'])
def test_launchers_not_games(name):
    assert not game_processes([process(name=name,appid='123')])

@pytest.mark.parametrize('p',[process(exe='/home/g/Steam/steamapps/common/Tiny/Game',appid='42'),process(name='game.exe',exe='/games/game.exe',ppid=4,appid='42'),process(name='wine64',exe='/usr/bin/wine64',cmdline=['wine64','/steamapps/common/Tiny/game.exe'],ppid=4,appid='42')])
def test_light_native_and_proton_game_identity(p):
    found=game_processes([process(4,'steam','/usr/bin/steam'),p]);assert len(found)==1
    assert 'Steam application ID' in found[0]['signals']


def test_rules_exclusions_owned_pid_and_simultaneous_games():
    rules=[{'kind':'name','value':'native'}];a=process(name='native');b=process(2,'native',started=3)
    assert len(game_processes([a,b],rules))==2
    assert len(game_processes([a,b],rules,owned={1}))==1
    assert not game_processes([a,b],rules,exclusions=rules)
    assert game_processes([process(1,'native',started=7)],rules)[0]['started']==7
    assert not game_processes([process(1,'native-child')],rules)

@pytest.mark.parametrize('key,value',[('primary_gpu_fallback_while_protected',True),('physical_cpu_core_limit',3),('generation_threads',3),('gpu_exit_percent',95),('tier_models',{'expert':'x;sh'}),('mode','guess')])
def test_invalid_profiles_rejected(key,value):
    with pytest.raises(ValueError):ProtectionConfig.model_validate({key:value})


def test_config_roundtrip_and_exact_paths(tmp_path):
    cfg=ProtectionConfig(mode='protected',process_rules=[ProcessRule(kind='path',value='/games/test')]);save_config(tmp_path,cfg)
    assert read_config(tmp_path)==cfg
    assert (tmp_path/'resource-protection.json').stat().st_mode & 0o777==0o600


def sample(t,**kw):return {'time':t,'games':[],**kw}


def test_game_immediate_hysteresis_multiple_and_unknown_pressure():
    cfg=ProtectionConfig();t=TriggerState()
    assert t.evaluate(sample(0,games=[{'name':'light'}]),cfg) and t.desired
    assert not t.evaluate(sample(12,games=[{'name':'second'}]),cfg)
    assert not t.evaluate(sample(13,cpu_percent=1,gpu_percent=1,hot_core_percent=1),cfg)
    assert not t.evaluate(sample(31,cpu_percent=1,gpu_percent=1,hot_core_percent=1),cfg)
    assert t.evaluate(sample(34,cpu_percent=1,gpu_percent=1,hot_core_percent=1),cfg) and not t.desired
    for now in (40,42,44):assert not t.evaluate(sample(now,gpu_percent=99),cfg)
    assert t.evaluate(sample(45,gpu_percent=99),cfg) and t.desired
    t.evaluate(sample(100,gpu_percent=None),cfg);assert t.desired

@pytest.mark.parametrize('metric',['cpu_percent','hot_core_percent','gpu_percent'])
def test_pressure_needs_full_window(metric):
    t=TriggerState();cfg=ProtectionConfig()
    for now in (0,2,4):t.evaluate(sample(now,**{metric:99}),cfg);assert not t.desired
    t.evaluate(sample(5,**{metric:99}),cfg);assert t.desired
    t.evaluate(sample(6,**{metric:0}),cfg);assert t.desired
    t.evaluate(sample(36,**{metric:0}),cfg);assert not t.desired


def test_pressure_own_load_and_hot_core():
    from collections import namedtuple
    C=namedtuple('C','user system idle iowait');old=[C(0,0,0,0)]*4;new=[C(2,0,0,0),C(0,0,2,0),C(0,0,2,0),C(0,0,2,0)]
    assert cpu_pressure(old,new,2,2)==(0,0)
    total,hot=cpu_pressure(old,new,0,2);assert total==25 and hot==100
    assert cpu_pressure(old,new,None,2)==(None,None)
    assert parse_fdinfo('drm-pdev: 0000:03:00.0\ndrm-client-id: 5\ndrm-engine-gfx: 123 ns\ndrm-engine-capacity-gfx: 2')['engines']=={'gfx':123}
    assert parse_fdinfo('drm-memory-vram: 123 KiB') is None


def test_bound_secondary_memory_never_uses_primary_or_unknown(system,monkeypatch):
    r=system.residency;r.bound_sysfs='/secondary';r.memory_reserve_gb=.25
    d=[{'device':'/primary','total_gb':17,'free_gb':16},{'device':'/secondary','total_gb':8.59,'free_gb':7}]
    monkeypatch.setattr('src.backends.residency.gpu_memory',lambda:{**d[0],'devices':d})
    assert not r.can_load('qwen3.5-9b-q4')[0]
    r.register_load('qwen3.5-9b-q4');assert not r.can_load('qwen3.5-9b-q4')[0]
    monkeypatch.setattr('src.backends.residency.gpu_memory',lambda:None)
    assert not r.can_load('gemma-4-e4b-q4')[0]


def test_device_identity_survives_enumeration_and_absence():
    from src.backends.devices import select_device
    a={'stable_id':'pci1','description':'A','free_bytes':8e9,'total_bytes':8e9,'gpu_index':0};b={'stable_id':'pci2','description':'B','free_bytes':16e9,'total_bytes':16e9,'gpu_index':1}
    assert select_device([b,a],'pci1')['description']=='A'
    with pytest.raises(ValueError):select_device([b],'pci1')


def test_resource_epoch_interrupt_does_not_unload_active_call(system):
    backend=system.backend;backend.delay=.2;errors=[]
    thread=threading.Thread(target=lambda:invoke())
    def invoke():
        try:system.complete([{'role':'user','content':'hi'}],tier='fast')
        except InferenceError as e:errors.append(e.code)
    thread.start();assert backend.entered.wait(2)
    system.protection.epoch+=1
    assert backend.unloads==0
    thread.join(3);assert not thread.is_alive() and errors==['protection_interrupted']


def test_unmapped_protected_role_cannot_fall_back(system):
    p=system.protection;p.trigger.desired=True;p.active=True
    with pytest.raises(ResourceBlocked,match='صريح'):system.select([{'role':'user','content':'hi'}],'expert')
    assert not system.backend.loads
    p.trigger.desired=False;p.active=False


def wait_terminal(jobs,key):
    end=time.monotonic()+4
    while time.monotonic()<end:
        value=jobs.get(key)
        if value['state'] in ('failed','cancelled','completed'):return value
        time.sleep(.02)
    raise AssertionError(jobs.get(key))


def test_resource_wait_is_bounded_cancelable_and_restorable(system,tmp_path,monkeypatch):
    system.settings.timeout_s=1
    monkeypatch.setattr(system,'project_resource_ready',lambda:(False,'planner does not fit secondary'))
    store=ProjectStore(tmp_path/'projects');jobs=ProjectJobs(store,system)
    key=jobs.create({'user_request':'create a Python hello','project_type':'python','requirements':['hello']})['job']['job_id']
    end=time.monotonic()+2
    while not jobs.get(key)['blocked_reason'] and time.monotonic()<end:time.sleep(.01)
    assert jobs.get(key)['state']=='queued' and not system.backend.calls
    # Stop thread without user-cancelling the durable, never-started wait.
    jobs.stopping.set();jobs.worker.join(2)
    restored=ProjectJobs(store,system)
    try:
        assert restored.get(key)['state']=='queued'
        restored.cancel(key);assert wait_terminal(restored,key)['state']=='cancelled'
        assert not system.backend.calls
    finally:restored.shutdown();store.close()


def test_resource_wait_expiry_keeps_zero_files(system,tmp_path,monkeypatch):
    system.settings.timeout_s=.2
    monkeypatch.setattr(system,'project_resource_ready',lambda:(False,'no compatible model'))
    store=ProjectStore(tmp_path/'projects');jobs=ProjectJobs(store,system)
    try:
        created=jobs.create({'user_request':'create hello Python','project_type':'python','requirements':['hello']});key=created['job']['job_id']
        final=wait_terminal(jobs,key);assert final['state']=='failed' and 'deadline' in final['error']
        assert not store.committed_files(created['project']['project_id']) and not system.backend.calls
    finally:jobs.shutdown();store.close()


def test_permissions_resources_and_forged_profile(system):
    import asyncio,httpx
    from src.backend.api import create_app
    app=create_app(system.settings,system)
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1') as client:
            assert (await client.get('/resources')).status_code==403
            h={'X-Neura-Token':'test-token'}
            assert (await client.get('/resources',headers=h)).json()['state']=='Normal'
            assert (await client.post('/resources/config',headers={**h,'Origin':'https://hostile.example'},json={'mode':'protected'})).status_code==403
            assert (await client.post('/resources/config',headers=h,json={'mode':'protected','primary_gpu_fallback_while_protected':True})).status_code==422
            assert system.protection.config.mode=='normal'
    asyncio.run(check());app.state.project_store.close()


def test_missing_gpu_keeps_no_primary_load(system,monkeypatch):
    p=system.protection;p.config=ProtectionConfig(mode='protected',protected_gpu='absent',protected_models_dir=str(system.models_dir));p.trigger.desired=True;p.epoch+=1
    monkeypatch.setattr('src.backends.devices.probe_devices',lambda:[])
    assert not p.ensure_active()
    assert p.state=='Resource Blocked' and not system.backend.loads
    p.trigger.desired=False;p.ensure_active()


def test_planner_must_fit_before_any_project_stage(system,monkeypatch):
    p=system.protection;p.config=ProtectionConfig(mode='protected',tier_models={'coder':'gemma-4-e4b-q4'});p.trigger.desired=True;p.active=True
    monkeypatch.setattr(p,'ensure_active',lambda:True)
    ready,reason=system.project_resource_ready()
    assert not ready and 'expert' in reason and not system.backend.calls
    p.trigger.desired=False;p.active=False


def test_manual_normal_and_protected_overrides():
    t=TriggerState();t.evaluate(sample(0,games=[{'name':'game'}]),ProtectionConfig(mode='normal'));assert not t.desired
    t.evaluate(sample(1),ProtectionConfig(mode='protected'));assert t.desired
    t.evaluate(sample(2,games=[{'name':'game'}]),ProtectionConfig(mode='normal'));assert not t.desired


def test_native_child_handoff_needs_installation_provenance():
    game=process(1,'native',exe='/games/demo/game');child=process(2,'renderer',exe='/games/demo/renderer',ppid=1);browser=process(3,'brave',exe='/usr/bin/brave',ppid=1)
    assert [g['pid'] for g in game_processes([game,child,browser],[{'kind':'name','value':'native'}])]==[1,2]


def test_partial_gpu_observation_cannot_prove_trigger_cleared():
    cfg=ProtectionConfig();t=TriggerState()
    t.evaluate(sample(0,gpu_percent=99,gpu_complete=False),cfg);t.evaluate(sample(6,gpu_percent=99,gpu_complete=False),cfg);assert t.desired
    t.evaluate(sample(100,gpu_percent=0,gpu_complete=False),cfg);assert t.desired
    t.evaluate(sample(101,gpu_percent=0,gpu_complete=True),cfg);t.evaluate(sample(123,gpu_percent=0,gpu_complete=True),cfg);assert not t.desired


def test_cancelled_wait_is_not_replayed_after_crash(system,tmp_path,monkeypatch):
    monkeypatch.setattr(system,'project_resource_ready',lambda:(False,'blocked'))
    store=ProjectStore(tmp_path/'data');jobs=ProjectJobs(store,system)
    key=jobs.create({'user_request':'create hello Python','requirements':['hello'],'project_type':'python'})['job']['job_id']
    end=time.monotonic()+2
    while not jobs.get(key)['blocked_reason'] and time.monotonic()<end:time.sleep(.01)
    jobs.stopping.set();jobs.worker.join(2)
    store.db.execute('UPDATE jobs SET cancel=1 WHERE id=?',(key,));store.db.commit()
    recovered=ProjectJobs(store,system)
    try:
        assert wait_terminal(recovered,key)['state']=='cancelled'
        assert not system.backend.calls
    finally:recovered.shutdown();store.close()
