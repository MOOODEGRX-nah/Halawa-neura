"""Explicit, observable resource policy. No cloud or silent GPU/model fallback."""
import json,os,re,time,threading,hashlib,secrets
from pathlib import Path
from pydantic import BaseModel,ConfigDict,Field,model_validator
from typing import Literal
from src.core.resource_detection import LinuxSampler,game_processes
from src.core.worker_limits import WorkerLimits


class ProcessRule(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    kind:Literal['name','path']
    value:str=Field(min_length=1,max_length=512)
    @model_validator(mode='after')
    def exact(self):
        if any(ord(c)<32 for c in self.value) or (self.kind=='path' and not Path(self.value).is_absolute()) or (self.kind=='name' and '/' in self.value):raise ValueError('Use an exact executable name or absolute path')
        return self


class ProtectionConfig(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    version:Literal[1]=1
    mode:Literal['auto','normal','protected']='auto'
    game_detection:bool=True
    process_rules:list[ProcessRule]=Field(default_factory=list,max_length=128)
    exclusions:list[ProcessRule]=Field(default_factory=list,max_length=128)
    sampling_interval_seconds:float=Field(default=2,ge=.5,le=30)
    gpu_enter_percent:float=Field(default=90,ge=10,le=100)
    cpu_enter_percent:float=Field(default=85,ge=10,le=100)
    cpu_hot_core_percent:float=Field(default=95,ge=10,le=100)
    pressure_hold_seconds:float=Field(default=5,ge=1,le=120)
    gpu_exit_percent:float=Field(default=60,ge=0,le=99)
    cpu_exit_percent:float=Field(default=60,ge=0,le=99)
    exit_hold_seconds:float=Field(default=20,ge=1,le=300)
    minimum_mode_dwell_seconds:float=Field(default=30,ge=0,le=600)
    protected_gpu:str=Field(default='',max_length=200)
    protected_models_dir:str=Field(default='',max_length=4096)
    tier_models:dict[str,str]=Field(default_factory=dict,max_length=16)
    physical_cpu_core_limit:int=Field(default=2,ge=1,le=2)
    generation_threads:int=Field(default=2,ge=1,le=2)
    prompt_threads:int=Field(default=2,ge=1,le=2)
    protected_cpu_nice:int=Field(default=10,ge=0,le=19)
    protected_context:int=Field(default=4096,ge=512,le=32768)
    primary_gpu_fallback_while_protected:Literal[False]=False
    cpu_offload_fallback:bool=False
    memory_reserve_gb:float=Field(default=.25,ge=0,le=8)

    @model_validator(mode='after')
    def coherent(self):
        if self.gpu_exit_percent>=self.gpu_enter_percent or self.cpu_exit_percent>=min(self.cpu_enter_percent,self.cpu_hot_core_percent):raise ValueError('Exit thresholds must be below entry thresholds')
        if max(self.generation_threads,self.prompt_threads)>self.physical_cpu_core_limit:raise ValueError('Thread limits exceed selected physical cores')
        if any(k not in {'fast','daily','expert','coder','vision','embedding'} or not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{0,120}',v) for k,v in self.tier_models.items()):raise ValueError('Unsupported tier/model binding')
        if any(ord(c)<32 for c in self.protected_gpu+self.protected_models_dir):raise ValueError('Invalid hardware/path selection')
        return self


def read_config(data_dir,fallback=None):
    p=Path(data_dir)/'resource-protection.json'
    if p.exists():return ProtectionConfig.model_validate_json(p.read_text())
    return ProtectionConfig.model_validate(fallback or {})


def save_config(data_dir,config):
    config=ProtectionConfig.model_validate(config);root=Path(data_dir);root.mkdir(parents=True,exist_ok=True)
    p=root/'resource-protection.json';temp=root/('.resource-'+secrets.token_hex(8));temp.write_text(config.model_dump_json(indent=2));temp.chmod(0o600);os.replace(temp,p)


def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


class TriggerState:
    """Pure hysteresis over observed signals; lightweight games need no load."""
    def __init__(self):self.desired=False;self.high_since={};self.latched=set();self.clear_since=None;self.entered=None;self.reasons=[]
    def evaluate(self,sample,cfg):
        now=sample['time'];games=sample.get('games',[]);high=[]
        values={'gpu':(sample.get('gpu_percent'),cfg.gpu_enter_percent,cfg.gpu_exit_percent),'cpu':(sample.get('cpu_percent'),cfg.cpu_enter_percent,cfg.cpu_exit_percent),'hot_core':(sample.get('hot_core_percent'),cfg.cpu_hot_core_percent,cfg.cpu_exit_percent)}
        for name,(value,enter,exit_) in values.items():
            if value is not None and value>=enter:
                since=self.high_since.setdefault(name,now)
                if now-since>=cfg.pressure_hold_seconds:self.latched.add(name)
            else:self.high_since.pop(name,None)
            if name in self.latched:
                if value is None or value>exit_:high.append(name+(' metrics unavailable' if value is None else ' pressure'))
                elif name=='gpu' and not sample.get('gpu_complete',True):high.append('gpu coverage unavailable')
                else:self.latched.discard(name)
        if cfg.mode=='normal':wanted=False;reasons=['اختيار Normal يدوي؛ لن تعمل الحماية التلقائية']
        elif cfg.mode=='protected':wanted=True;reasons=['اختيار Protected يدوي']
        else:
            reasons=[g['name'] for g in games]+high;wanted=bool(reasons)
            if wanted:self.clear_since=None
            elif self.desired:
                if self.clear_since is None:self.clear_since=now
                wanted=(now-self.clear_since<cfg.exit_hold_seconds or self.entered is not None and now-self.entered<cfg.minimum_mode_dwell_seconds)
                if wanted:reasons=['انتظار انتهاء مهلة الخروج وثبات الحالة']
        changed=wanted!=self.desired
        if changed and wanted:self.entered=now
        if changed and not wanted:self.latched.clear();self.high_since.clear();self.clear_since=None
        self.desired=wanted;self.reasons=reasons
        return changed


# Internal helper registration; never a WebChannel or generated-code capability.
_active=None

def register_owned_child(pid):
    if _active:_active.limits.register_child(pid)


class ResourcePolicy:
    def __init__(self,coordinator,config,*,start=True,sampler=None,limits=None):
        global _active
        self.coordinator=coordinator;self.config=ProtectionConfig.model_validate(config);self.limits=limits or WorkerLimits();self.trigger=TriggerState();self.lock=threading.RLock();self.wake=threading.Event();self.stop=threading.Event();self.thread=None
        self.epoch=0;self.active=False;self.state='Normal';self.blocked_reason=None;self.device=None;self.actual_confirmation=None;self.waiters={};self.last_sample={};self.primary_pci=None;self.config_error=None
        self.initial_observation=self.config.mode!='auto'
        try:
            from src.backends.devices import physical_gpus
            physical=physical_gpus()
            selected=next((d for d in physical if d['stable_id']==coordinator.settings.gpu_device),None)
            if selected or coordinator.settings.gpu_device=='auto':self.primary_pci=(selected or max(physical,key=lambda d:d['total_bytes']))['pci_id']
        except (ValueError,OSError):pass
        self.sampler=sampler or LinuxSampler(self.owned_pids,lambda:self.primary_pci)
        _active=self
        if self.config.mode=='protected':self.trigger.desired=True;self.trigger.reasons=['اختيار Protected يدوي'];self.epoch=1;self.state='Entering Protection'
        if start:
            self.thread=threading.Thread(target=self._run,name='neura-resource-monitor',daemon=True);self.thread.start()

    def update(self,config,persist=True):
        cfg=ProtectionConfig.model_validate(config)
        if persist:save_config(self.coordinator.settings.data_dir,cfg)
        runtime_keys=('protected_gpu','protected_models_dir','tier_models','physical_cpu_core_limit','generation_threads','prompt_threads','protected_cpu_nice','protected_context','cpu_offload_fallback','memory_reserve_gb')
        changed=any(getattr(cfg,k)!=getattr(self.config,k) for k in runtime_keys)
        with self.lock:
            self.config=cfg;self.blocked_reason=None
            if changed and (self.active or self.trigger.desired):
                self.epoch+=1;self.actual_confirmation=None;self.coordinator._cpu_fallback=False;self.coordinator._applied_resource_key=None
            if cfg.mode=='auto' and not self.last_sample.get('identity_available'):self.initial_observation=False
        if self.thread is None and cfg.mode!='normal':
            self.thread=threading.Thread(target=self._run,name='neura-resource-monitor',daemon=True);self.thread.start()
        self.observe({**self.last_sample,'time':time.monotonic(),'cached_observation':True,'identity_available':bool(self.last_sample.get('identity_available'))})
        self.wake.set()

    def observe(self,sample):
        cfg=self.config;sample=dict(sample)
        if not sample.get('cached_observation'):
            sample['games']=game_processes(sample.get('processes',[]),[r.model_dump() for r in cfg.process_rules],[r.model_dump() for r in cfg.exclusions],sample.get('owned_pids',[])) if cfg.game_detection else []
            if cfg.game_detection:
                # Missing/unreadable observations do not prove a known game exited.
                observed={(p['pid'],p['started']):p for p in sample.get('processes',[])};known={(g['pid'],g['started']) for g in sample['games']}
                for previous in self.last_sample.get('games',[]):
                    identity=(previous['pid'],previous['started']);p=observed.get(identity)
                    if identity in known:continue
                    if p and p.get('exe')!=previous.get('exe') and not p.get('identity_unknown'):continue
                    if p and any(p.get('exe')==r.value if r.kind=='path' else p.get('name','').casefold()==r.value.casefold() for r in cfg.exclusions):continue
                    try:
                        import psutil
                        current=psutil.Process(previous['pid'])
                        if current.create_time()==previous['started']:sample['games'].append({**previous,'signals':previous['signals']+['observation unavailable; process lifetime still present']})
                    except psutil.NoSuchProcess:pass
                    except (psutil.AccessDenied,OSError):sample['games'].append(previous)
        with self.lock:
            if sample.get('identity_available',True) or cfg.mode!='auto':self.initial_observation=True
            changed=self.trigger.evaluate(sample,cfg)
            if changed:
                self.epoch+=1;self.state='Entering Protection' if self.trigger.desired else 'Returning';self.actual_confirmation=None
            self.last_sample={k:v for k,v in sample.items() if k!='processes'}
        self.ensure_active()

    def ensure_active(self):
        # No state lock held while asking the coordinator for its exclusive lock.
        if not self.initial_observation or self.stop.is_set():return False
        if self.blocked_reason and getattr(self,'_last_failed_epoch',None)==self.epoch and time.monotonic()-getattr(self,'_last_failed_at',0)<1:return False
        result=self.coordinator._transition_resources(self)
        if not result and self.blocked_reason:self._last_failed_epoch=self.epoch;self._last_failed_at=time.monotonic()
        return result

    def owned_pids(self):
        result=self.limits.owned_pids()
        # Only the verified desktop parent and its exact WebEngine helper are
        # excluded; launched user applications/games are not owned AI workers.
        try:
            import psutil
            owner=json.loads(os.environ.get('NEURA_DESKTOP_OWNER','{}'));p=psutil.Process(owner['pid'])
            if p.pid==os.getppid() and p.create_time()==owner['started']:
                result.add(p.pid)
                for child in p.children(recursive=True):
                    if child.exe()==owner.get('webengine_executable'):result.add(child.pid)
        except Exception:pass
        return result

    def note_wait(self,key,reason):
        with self.lock:
            if len(self.waiters)<128 or key in self.waiters:self.waiters[key]=reason[:500]
            if self.trigger.desired:self.state='Resource Blocked'

    def clear_wait(self,key):
        with self.lock:
            self.waiters.pop(key,None)
            if not self.waiters and not self.blocked_reason and self.active==self.trigger.desired:self.state='Protected' if self.active else 'Normal'

    def _run(self):
        with self.limits.scope(persistent=True):
            while not self.stop.is_set():
                try:
                    sample=self.sampler.sample()
                    if self.stop.is_set():break
                    self.observe(sample);self.limits.refresh()
                    if self.trigger.desired and self.limits.errors:
                        with self.lock:
                            if not self.blocked_reason:self.epoch+=1
                            self.blocked_reason='تعذر تأكيد حدود CPU: '+'; '.join(self.limits.errors);self.state='Resource Blocked'
                except Exception as e:
                    with self.lock:self.last_sample={'time':time.monotonic(),'errors':[str(e)[:240]],'coverage':'unavailable'}
                self.wake.wait(self.config.sampling_interval_seconds);self.wake.clear()

    def snapshot(self):
        with self.lock:
            return {'configured_mode':self.config.mode,'state':self.state,'desired_protected':self.trigger.desired,'active_protected':self.active,'epoch':self.epoch,'config_sha256':fingerprint(self.config.model_dump()),'trigger_reasons':list(self.trigger.reasons),'sensors':dict(self.last_sample),'target_device':self.device,'confirmation':self.actual_confirmation,'blocked_reason':self.blocked_reason or next(iter(self.waiters.values()),None),'queued':dict(self.waiters),'cpu':self.limits.snapshot(),'primary_gpu_fallback':False,'unsupported':'Unconfigured tiers/accelerators remain queued or blocked; no inferred cloud capability'}

    def shutdown(self):
        global _active
        self.stop.set();self.wake.set()
        if self.thread and self.thread is not threading.current_thread():self.thread.join(timeout=3)
        self.limits.restore()
        if _active is self:_active=None


def owned_popen(arguments,**kwargs):
    import subprocess
    from contextlib import nullcontext
    with _active.limits.scope() if _active else nullcontext():
        child=subprocess.Popen(arguments,**kwargs)
        register_owned_child(child.pid)
    return child


def owned_run(arguments,*,timeout,**kwargs):
    """Trusted internal CLI only, bounded lifetime and registered CPU placement."""
    import subprocess
    with owned_popen(arguments,stdin=subprocess.PIPE if 'input' in kwargs else None,stdout=subprocess.PIPE,stderr=subprocess.PIPE) as child:
        register_owned_child(child.pid)
        try:stdout,stderr=child.communicate(kwargs.get('input'),timeout=timeout)
        except BaseException:
            child.kill();child.communicate();raise
        if child.returncode:raise subprocess.CalledProcessError(child.returncode,arguments,stdout,stderr)
        return subprocess.CompletedProcess(arguments,child.returncode,stdout,stderr)


def accelerator_allowed():
    # Whisper CLI does not share llama.cpp's selected Vulkan device. Until a
    # verified adapter exists it cannot silently use the primary GPU.
    if _active and (_active.trigger.desired or not _active.initial_observation):
        from src.core.neura_loop import ResourceBlocked
        raise ResourceBlocked('التعرف الصوتي GPU غير مدعوم في الملف المحمي؛ لم يبدأ Whisper ولم يستخدم البطاقة الرئيسية')
