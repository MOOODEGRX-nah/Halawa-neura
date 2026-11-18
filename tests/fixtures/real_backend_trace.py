"""QA-only observer of REAL packaged inference; never replaces model output."""
import argparse,base64,hashlib,json,os,time,uuid
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--port',type=int,required=True);a=p.parse_args()
data=Path(os.environ['NEURA_DATA_DIR']).resolve();profile=data.parent
marker=json.loads((profile/'.neura-verification-profile').read_text())
run=Path(os.environ['NEURA_QA_RUN_ROOT']).resolve();traces=Path(os.environ['NEURA_QA_REAL_TRACE']).resolve()
assert marker['run_id']==os.environ['NEURA_QA_RUN_ID'] and traces.is_relative_to(run/'artifacts')
traces.mkdir(parents=True,exist_ok=True)
import uvicorn
from src.backend.api import app
from src.runtime import ROOT
backend=app.state.coordinator.backend;original=backend.generate
# QA-only lifecycle observations, never overrides resource or load policy.
lifecycle=run/'artifacts/model-lifecycle.jsonl'
def lifecycle_record(kind,**values):
    with lifecycle.open('a') as f:f.write(json.dumps({'time':time.time(),'kind':kind,**values},default=str)+'\n')
from src.backends.residency import ResidencyManager
original_guard=ResidencyManager.can_load
from src.backends.residency import gpu_memory
def guarded(residency,model_id,context_length=4096,tier=None):
    result=original_guard(residency,model_id,context_length,tier)
    lifecycle_record('memory_guard',model_id=model_id,tier=tier,selected_device=getattr(backend,'selected_device',None),device_requested=app.state.coordinator._effective_settings.gpu_device,bound_sysfs=residency.bound_sysfs,available_memory=gpu_memory(),estimate_gb=residency.estimate_vram_usage_gb(model_id,context_length),allowed=result[0],reason=result[1])
    return result
ResidencyManager.can_load=guarded
original_load,original_unload=backend.load,backend.unload
def load(*args,**options):
    lifecycle_record('load_start',path=args[0],options=options)
    try:return original_load(*args,**options)
    finally:lifecycle_record('load_end',native_limits=getattr(backend,'native_limits',None),cpu=app.state.coordinator.protection.limits.snapshot(),selected_device=getattr(backend,'selected_device',None),memory=gpu_memory())
def unload():
    lifecycle_record('unload_start',path=backend.model_path)
    try:return original_unload()
    finally:lifecycle_record('unload_end',memory=gpu_memory())
backend.load,backend.unload=load,unload
def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def observed(*args,**options):
    messages=options['messages'];plain={k:v for k,v in options.items() if k not in ('messages','stopping_criteria') and isinstance(v,(str,int,float,bool,list,dict,type(None)))}
    images=[hashlib.sha256(base64.b64decode(p['image_url']['url'].split(',',1)[1])).hexdigest() for m in messages if isinstance(m['content'],list) for p in m['content'] if p['type']=='image_url']
    record={'trace_id':uuid.uuid4().hex,'source_root':str(ROOT),'environment':'actual '+os.environ.get('NEURA_QA_TARGET_KIND','packaged')+' backend with QA observer; NO fake inference',
        'model_id':app.state.coordinator.current_model_id,'model_path':backend.model_path,
        'projector':getattr(backend.handler,'clip_model_path',None),'device':getattr(backend,'selected_device',None),
        'resource_profile':app.state.coordinator.resource_receipt(),'n_ctx':app.state.coordinator._effective_settings.n_ctx,'native_n_gpu_layers':getattr(getattr(backend.model,'model_params',None),'n_gpu_layers',None),
        'chat_template_sha256':digest(getattr(backend.model,'metadata',{}).get('tokenizer.chat_template')),
        'messages':messages,'messages_sha256':digest(messages),'effective_options':plain,
        'options_sha256':digest(plain),'image_sha256':images,'started_at':time.time()}
    path=traces/(record['trace_id']+'.json')
    def save():
        raw=json.dumps(record,ensure_ascii=False,indent=2)
        if len(raw.encode())>2_000_000:raise RuntimeError('Owned QA trace exceeds bound')
        path.write_text(raw)
    save()
    result=original(*args,**options)
    if not options.get('stream'):
        record.update(finished_at=time.time(),finish_reason=result['choices'][0].get('finish_reason'),output=result['choices'][0]['message'],usage=result.get('usage'),token_metrics=getattr(backend,'last_metrics',None));save();return result
    def chunks():
        record['output']=''
        try:
            for chunk in result:
                for choice in chunk.get('choices',[]):
                    piece=choice.get('delta',{}).get('content') or ''
                    if piece and 'first_token_at' not in record:record['first_token_at']=time.time()
                    record['output']+=piece
                    if choice.get('finish_reason'):record['finish_reason']=choice['finish_reason']
                yield chunk
        finally:
            if hasattr(result,'close'):result.close()
            record['finished_at']=time.time();record['token_metrics']=getattr(backend,'last_metrics',None);save()
    return chunks()
backend.generate=observed
# Separate QA sampler: actual memory readings, not estimated token rates.
import threading,psutil
sample_stop=threading.Event()
def memory_samples():
    path=run/'artifacts/runtime-memory.jsonl'
    for _ in range(8000):
        if sample_stop.is_set():break
        try:
            value={'time':time.time(),'phase':app.state.coordinator.phase,'model':app.state.coordinator.current_model_id,'gpu':gpu_memory(),'rss_bytes':psutil.Process().memory_info().rss}
            with path.open('a') as f:f.write(json.dumps(value)+'\n')
        except OSError:pass
        sample_stop.wait(.5)
threading.Thread(target=memory_samples,name='qa-memory-observer',daemon=True).start()
uvicorn.run(app,host='127.0.0.1',port=a.port,log_level='warning',proxy_headers=False)
