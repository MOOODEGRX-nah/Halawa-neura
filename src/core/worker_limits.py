"""Limits for registered Neura inference threads/helpers, never arbitrary apps."""
from pathlib import Path
from contextlib import contextmanager
import os,threading,time
try:import resource
except ImportError:resource=None
import psutil


def cpu_list(text):
    result=set()
    for part in text.strip().split(','):
        if not part:continue
        bounds=part.split('-');a=int(bounds[0]);b=int(bounds[-1])
        if not 0<=a<=b<=65535:raise ValueError('Invalid CPU list')
        result.update(range(a,b+1))
    return result


def topology(allowed=None,root=Path('/sys/devices/system/cpu')):
    allowed=set(os.sched_getaffinity(0) if allowed is None else allowed);cores={}
    for cpu in sorted(allowed):
        try:
            p=root/f'cpu{cpu}/topology';key=((p/'physical_package_id').read_text().strip(),(p/'core_id').read_text().strip());cores.setdefault(key,[]).append(cpu)
        except OSError:continue
    return [{'package':k[0],'core':k[1],'logical_cpus':v} for k,v in cores.items()]


def choose_cpus(limit,allowed=None):
    if limit not in (1,2):raise ValueError('Protected profile supports one or two physical cores')
    cores=topology(allowed)
    if len(cores)<limit:raise ValueError('لا تتوفر نوى فعلية مميزة كافية ضمن حدود Neura الحالية')
    return {c['logical_cpus'][0] for c in cores[:limit]}


def task_identity(pid,tid):
    text=(Path('/proc')/str(pid)/'task'/str(tid)/'stat').read_text();return text[text.rfind(')')+2:].split()[19]


def cgroup_cpus():
    try:
        line=next(l for l in Path('/proc/self/cgroup').read_text().splitlines() if l.startswith('0::'));path=Path('/sys/fs/cgroup')/line[3:].lstrip('/')/'cpuset.cpus.effective'
        return cpu_list(path.read_text())
    except (OSError,ValueError,StopIteration):return None


class WorkerLimits:
    def __init__(self):
        self.lock=threading.RLock();self.tasks={};self.children={};self.cpus=None;self.nice=10;self.errors=[];self.nice_status='not requested';self.base=set(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else set()

    def _remember(self,pid,tid,inherited=None):
        key=(pid,tid)
        try:
            ident=task_identity(pid,tid);mask=set(os.sched_getaffinity(tid))
            if key not in self.tasks or self.tasks[key]['identity']!=ident:
                normal=set(inherited) if inherited is not None and self.cpus and mask==self.cpus else mask
                self.tasks[key]={'identity':ident,'original':normal,'applied':None,'nice':os.getpriority(os.PRIO_PROCESS,tid),'applied_nice':None}
            return key
        except (OSError,ValueError):return None

    def _apply(self,key):
        pid,tid=key;t=self.tasks[key]
        if self.cpus is None and t['applied'] is None:return
        try:
            if task_identity(pid,tid)!=t['identity']:self.tasks.pop(key,None);return
            current=set(os.sched_getaffinity(tid));cpuset=cgroup_cpus();original=t['original'] & cpuset if cpuset is not None else set(t['original'])
            # Preserve an external affinity change observed since our last write.
            if t['applied'] is not None and current!=t['applied']:original &= current;t['original']=original
            target=original & self.cpus if self.cpus is not None else original
            if not target:raise OSError('No allowed protected CPU remains')
            os.sched_setaffinity(tid,target)
            if set(os.sched_getaffinity(tid))!=target:raise OSError('CPU affinity not confirmed')
            t['applied']=target
            if self.cpus is not None:
                observed_nice=os.getpriority(os.PRIO_PROCESS,tid)
                if t['applied_nice'] is not None and observed_nice!=t['applied_nice']:t['nice']=max(t['nice'],observed_nice)
                target_nice=max(t['nice'],self.nice)
                soft,_=resource.getrlimit(resource.RLIMIT_NICE) if resource else (0,0)
                if target_nice==t['nice'] or soft>=20-t['nice']:
                    os.setpriority(os.PRIO_PROCESS,tid,target_nice);t['applied_nice']=target_nice;self.nice_status='applied and restorable'
                else:self.nice_status='not applied: raising priority back is not permitted by RLIMIT_NICE'
            elif t['applied_nice'] is not None:
                # Never override a later external priority restriction.
                if os.getpriority(os.PRIO_PROCESS,tid)==t['applied_nice']:os.setpriority(os.PRIO_PROCESS,tid,t['nice'])
                t['applied_nice']=None
        except FileNotFoundError:self.tasks.pop(key,None)
        except ProcessLookupError:self.tasks.pop(key,None)
        except (OSError,ValueError) as e:self.errors.append(str(e)[:240]);self.errors=self.errors[-12:]

    @contextmanager
    def scope(self,persistent=False):
        if not hasattr(os,'sched_getaffinity'):
            if self.cpus is not None:raise OSError('CPU affinity unavailable')
            yield set();return
        pid=os.getpid();tid=threading.get_native_id()
        with self.lock:
            existed=(pid,tid) in self.tasks;key=self._remember(pid,tid)
            if key:self._apply(key)
            if self.cpus is not None and (not key or self.errors or not set(os.sched_getaffinity(tid))<=self.cpus):raise OSError('Protected inference CPU placement was not confirmed')
            original=set(self.tasks[key]['original']) if key else set(self.base)
        try:yield original
        finally:
            if key and not existed and not persistent:
                with self.lock:
                    cpus=self.cpus;self.cpus=None
                    self._apply(key);self.cpus=cpus;self.tasks.pop(key,None)

    def capture_threads(self,before,normal_mask):
        with self.lock:
            try:now={int(p.name) for p in Path('/proc/self/task').iterdir()}
            except OSError:return
            python_tids={t.native_id for t in threading.enumerate()}
            for tid in now-set(before)-python_tids:
                key=self._remember(os.getpid(),tid,inherited=normal_mask)
                if key:self._apply(key)

    def register_child(self,pid,normal_mask=None):
        try:
            p=psutil.Process(pid)
            with self.lock:self.children[pid]={'started':p.create_time(),'original':set(normal_mask or self.base)}
            self.refresh()
        except psutil.Error:return

    def refresh(self):
        with self.lock:
            for pid,record in list(self.children.items()):
                try:
                    p=psutil.Process(pid)
                    if p.create_time()!=record['started']:self.children.pop(pid,None);continue
                    for child in [p,*p.children(recursive=True)]:
                        for thread in child.threads():
                            key=self._remember(child.pid,thread.id,inherited=record['original'])
                            if key:self._apply(key)
                except psutil.Error:self.children.pop(pid,None)
            for key in list(self.tasks):self._apply(key)

    def owned_pids(self):
        with self.lock:
            result={os.getpid()}
            for pid,r in self.children.items():
                try:
                    p=psutil.Process(pid)
                    if p.create_time()==r['started']:result|={p.pid,*[c.pid for c in p.children(recursive=True)]}
                except psutil.Error:continue
            return result

    def activate(self,count,nice):
        with self.lock:
            # Selection is bounded by the original process restriction and current cgroup.
            allowed=set(self.base);cg=cgroup_cpus()
            if cg is not None:allowed &= cg
            self.cpus=choose_cpus(count,allowed);self.nice=nice;self.errors=[];self.refresh()
            if self.errors:raise OSError('; '.join(self.errors))
            return sorted(self.cpus)

    def restore(self):
        with self.lock:self.errors=[];self.cpus=None;self.refresh()

    def snapshot(self):
        with self.lock:
            actual=[]
            for (pid,tid),t in list(self.tasks.items()):
                try:
                    if task_identity(pid,tid)==t['identity']:actual.append({'pid':pid,'tid':tid,'allowed_cpus':sorted(os.sched_getaffinity(tid)),'nice':os.getpriority(os.PRIO_PROCESS,tid),'nice_applied':t['applied_nice']})
                except OSError:continue
            return {'requested_cpus':sorted(self.cpus) if self.cpus is not None else None,'registered_tasks':actual,'physical_topology':topology(self.base),'nice_status':self.nice_status,'errors':list(self.errors),'scope':'Registered inference threads/helpers only; no exclusive cores; external desktop launches are not registered'}
