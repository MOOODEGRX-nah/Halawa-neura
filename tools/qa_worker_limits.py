"""Isolated real Linux affinity trial; never changes another application's mask."""
import json,os,threading,sys
from pathlib import Path
from src.core.worker_limits import WorkerLimits,topology
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
limits=WorkerLimits();records=[];release=threading.Event();ready=threading.Event()
def existing():
    with limits.scope(persistent=True):ready.set();release.wait(15)
t=threading.Thread(target=existing,name='qa-owned-existing');t.start();assert ready.wait(2)
original={tid:set(os.sched_getaffinity(tid)) for pid,tid in limits.tasks}
try:
 for count in (1,2):
    cpus=set(limits.activate(count,10));assert len(cpus)==count
    selected=[c for c in topology() if cpus & set(c['logical_cpus'])];assert len(selected)==count
    seen=[]
    def future():
        with limits.scope():seen.extend(sorted(os.sched_getaffinity(0)))
    child=threading.Thread(target=future);child.start();child.join(2);assert set(seen)==cpus
    snapshot=limits.snapshot();assert all(set(v['allowed_cpus'])<=cpus for v in snapshot['registered_tasks'])
    records.append({'core_limit':count,'future_worker_cpus':seen,'snapshot':snapshot})
 limits.restore()
 assert all(set(os.sched_getaffinity(tid))==mask for tid,mask in original.items())
 records.append({'restored':limits.snapshot(),'original':{str(k):sorted(v) for k,v in original.items()}})
 # A separately observed external restriction is never widened on restoration.
 limits.activate(2,10);tid=t.native_id;restricted={min(os.sched_getaffinity(tid))};os.sched_setaffinity(tid,restricted);limits.refresh();limits.restore();assert set(os.sched_getaffinity(tid))==restricted
 records.append({'external_restriction_preserved':sorted(os.sched_getaffinity(tid))})
finally:limits.restore();release.set();t.join(2)
(out/'worker-limits.json').write_text(json.dumps({'environment':'actual Linux affinity in isolated QA process; no exclusive cores and no game FPS measurement','outcome':'passed','records':records},indent=2))
print('Actual existing/future worker one/two-core placement and restoration passed')
