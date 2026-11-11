"""Bounded Linux process/pressure observations. Unknown is never fabricated zero."""
from pathlib import Path
import os,re,time
import psutil

LAUNCHERS={'steam','steam.exe','steamwebhelper','lutris','heroic','heroic.exe','wine','wine64','wine-preloader','wine64-preloader','wineserver','proton','pressure-vessel-wrap','pv-bwrap','bwrap','reaper'}
HELPERS=LAUNCHERS|{'sh','bash','dash','zsh','fish','python','python3','services.exe','explorer.exe','winedevice.exe','rundll32.exe','rpcss.exe','unitycrashhandler64','crashpad_handler','crashreportclient.exe'}
DESKTOP={'kwin_wayland','kwin_x11','xorg','xwayland','gnome-shell','plasmashell','weston'}


def game_processes(processes,rules=(),exclusions=(),owned=()):
    """Exact reviewed rules or corroborated Steam ID + executable + ancestry/path."""
    by_pid={p['pid']:p for p in processes};found=[]
    def matches(p,rule):return (p.get('exe')==rule['value'] if rule['kind']=='path' else p.get('name','').casefold()==rule['value'].casefold())
    for p in processes:
        if p['pid'] in owned or any(matches(p,r) for r in exclusions):continue
        name=p.get('name','').casefold();exe=p.get('exe','');cmd=[str(v) for v in p.get('cmdline',[])];normalized='/'.join([exe,*cmd]).replace('\\','/').casefold()
        if name in LAUNCHERS and name not in {'wine','wine64','wine-preloader','wine64-preloader'}:continue
        signals=[]
        if name not in LAUNCHERS and any(matches(p,r) for r in rules):signals.append('exact configured executable/path')
        env=p.get('env') or {};appid=env.get('SteamAppId') or env.get('SteamGameId')
        valid_id=isinstance(appid,str) and appid.isdecimal() and int(appid)>0
        ancestors=[];parent=p.get('ppid');seen=set()
        while parent in by_pid and parent not in seen and len(ancestors)<12:
            seen.add(parent);a=by_pid[parent];ancestors.append(a.get('name','').casefold());parent=a.get('ppid')
        ancestry=bool(set(ancestors)&{'steam','steam.exe','proton','pressure-vessel-wrap','pv-bwrap','reaper'})
        steam_path='/steamapps/common/' in normalized
        proton_target=any(v.casefold().endswith('.exe') and Path(v.replace('\\','/')).name.casefold() not in HELPERS for v in cmd)
        if valid_id and name not in HELPERS and (steam_path or ancestry):signals+=['Steam application ID','game executable/path or Steam ancestry']
        elif valid_id and name in {'wine','wine64','wine-preloader','wine64-preloader'} and proton_target and (steam_path or ancestry):signals+=['Steam application ID','Proton game executable','Steam path/ancestry']
        if signals:found.append({'pid':p['pid'],'started':p['started'],'name':p.get('name') or Path(exe).name,'exe':exe,'steam_app_id':appid if valid_id else None,'signals':signals})
    # Native child handoff without a copied environment: require an identified
    # parent AND an executable in its exact installation directory. Generic
    # launchers, browsers and unrelated descendants are not inherited blindly.
    for _ in range(12):
        known={g['pid']:g for g in found};added=[]
        for p in processes:
            parent=known.get(p.get('ppid'))
            if not parent or p['pid'] in known or p['pid'] in owned or p.get('name','').casefold() in HELPERS or any(matches(p,r) for r in exclusions):continue
            exe=p.get('exe') or ''
            if exe and parent['exe'] and Path(exe).parent==Path(parent['exe']).parent:
                added.append({'pid':p['pid'],'started':p['started'],'name':p['name'],'exe':exe,'steam_app_id':parent.get('steam_app_id'),'signals':['identified game ancestry','same installation directory']})
        if not added:break
        found.extend(added)
    return found


def parse_fdinfo(text):
    fields={}
    for line in text.splitlines():
        key,sep,value=line.partition(':')
        if sep:fields[key.strip()]=value.strip()
    pci=fields.get('drm-pdev');client=fields.get('drm-client-id')
    if not pci or client is None:return None
    engines={};capacity={}
    for key,value in fields.items():
        if key.startswith('drm-engine-capacity-') and value.isdecimal():capacity[key[20:]]=max(1,int(value))
        elif key.startswith('drm-engine-'):
            match=re.fullmatch(r'(\d+)\s+ns',value)
            if match:engines[key[11:]]=int(match[1])
    return {'pci':pci,'client':client,'engines':engines,'capacity':capacity} if engines else None


def cpu_pressure(previous,current,excluded_seconds,interval):
    """Per-core conservative LOWER BOUND: subtract ALL owned/desktop CPU time.

    We cannot infer per-core thread residency from end-of-window CPU IDs. This
    avoids treating Neura-only hot cores as external pressure, but can undercount
    concurrent external hot cores. The UI exposes that limitation.
    """
    if not previous or len(previous)!=len(current) or interval<=0 or excluded_seconds is None:return None,None
    busy=[];total=[]
    for a,b in zip(previous,current):
        elapsed=sum(b)-sum(a);idle=(b.idle-a.idle)+(getattr(b,'iowait',0)-getattr(a,'iowait',0))
        if elapsed<=0:return None,None
        total.append(elapsed);busy.append(max(0,elapsed-idle))
    aggregate=max(0,sum(busy)-excluded_seconds)/sum(total)*100
    hot=max(max(0,v-excluded_seconds)/t*100 for v,t in zip(busy,total))
    return min(100,aggregate),min(100,hot)


class LinuxSampler:
    def __init__(self,owned,primary_pci):
        self.owned=owned;self.primary_pci=primary_pci;self.previous=None;self.previous_clients={}

    def sample(self):
        now=time.monotonic();owned=set(self.owned());processes=[];errors=[];clients={};cpu_excluded={};permission_denied=0;fd_reads=0
        try:iterator=psutil.process_iter(['pid','name','exe','ppid','create_time','cmdline'])
        except Exception:iterator=()
        for index,proc in enumerate(iterator):
            if index>=2048:errors.append('process scan bounded at2048');break
            try:
                info=proc.info;pid=info['pid'];name=info.get('name') or '';exe=info.get('exe') or '';started=info.get('create_time')
                if not isinstance(started,(int,float)):continue
                p={'pid':pid,'name':name,'exe':exe,'ppid':info.get('ppid'),'started':started,'cmdline':info.get('cmdline') or []}
                if '/steamapps/' in exe.casefold() or name.casefold() not in HELPERS and pid not in owned or name.casefold() in LAUNCHERS:
                    try:
                        env=proc.environ();p['env']={k:env[k] for k in ('SteamAppId','SteamGameId') if k in env} if isinstance(env,dict) else {}
                    except (psutil.Error,OSError):permission_denied+=1;p['identity_unknown']=True
                processes.append(p)
                excluded=pid in owned or name.casefold() in DESKTOP
                if excluded:
                    try:
                        t=proc.cpu_times();cpu_excluded[(pid,started)]=t.user+t.system
                    except (psutil.Error,OSError):cpu_excluded[(pid,started)]=None
                try:
                    for i,fd in enumerate((Path('/proc')/str(pid)/'fdinfo').iterdir()):
                        if i>=64 or fd_reads>=8192:break
                        fd_reads+=1
                        try:
                            with fd.open() as f:item=parse_fdinfo(f.read(16000))
                        except (OSError,ValueError):continue
                        if not item or item['pci']!=self.primary_pci():continue
                        key=(item['pci'],item['client']);old=clients.get(key)
                        if old:item['engines']={engine:max(value,old['engines'].get(engine,0)) for engine,value in item['engines'].items()}
                        clients[key]={**item,'excluded':excluded or bool(old and old['excluded']),'pid':pid,'started':started}
                except (OSError,psutil.Error):permission_denied+=1
            except (psutil.Error,OSError,KeyError,TypeError):permission_denied+=1
        try:
            cpus=psutil.cpu_times(percpu=True)
            if not isinstance(cpus,list):cpus=[]
        except Exception:cpus=[]
        aggregate=hot=gpu=None;dt=now-self.previous['time'] if self.previous else 0;gpu_pids=[]
        if self.previous:
            excluded_delta=0
            for key,value in cpu_excluded.items():
                previous=self.previous['excluded'].get(key)
                if value is None or previous is None:excluded_delta=None;break
                excluded_delta+=max(0,value-previous)
            aggregate,hot=cpu_pressure(self.previous['cpus'],cpus,excluded_delta,dt)
            utilization=[]
            for key,item in clients.items():
                before=self.previous_clients.get(key)
                if not before or item['excluded'] or dt<=0:continue
                values=[max(0,value-before['engines'].get(e,value))/(dt*1e9*item['capacity'].get(e,1))*100 for e,value in item['engines'].items()]
                if any(value<before['engines'].get(e,value) for e,value in item['engines'].items()):permission_denied+=1;continue
                if values:utilization.append(max(values));gpu_pids.append({'pid':item['pid'],'started':item['started']})
            comparable=any(k in self.previous_clients for k in clients)
            if comparable and (utilization or not permission_denied):gpu=min(100,sum(utilization))
            if gpu==0 and permission_denied:gpu=None
        self.previous={'time':now,'cpus':cpus,'excluded':cpu_excluded};self.previous_clients=clients
        return {'time':now,'processes':processes,'identity_available':bool(processes),'owned_pids':sorted(owned),'cpu_percent':aggregate,'hot_core_percent':hot,'gpu_percent':gpu,'gpu_complete':not permission_denied and fd_reads<8192,'gpu_clients':gpu_pids,'permission_denied':permission_denied,'errors':errors,
                'gpu_scope':'readable per-client DRM engine lower bound; shared clients deduplicated; desktop/owned excluded','cpu_scope':'external aggregate and conservative per-core lower bound; may undercount concurrent hot cores','coverage':'partial' if permission_denied else 'observed','vram_is_not_activity':True}
