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
def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def observed(*args,**options):
    messages=options['messages'];plain={k:v for k,v in options.items() if k not in ('messages','stopping_criteria') and isinstance(v,(str,int,float,bool,list,dict,type(None)))}
    images=[hashlib.sha256(base64.b64decode(p['image_url']['url'].split(',',1)[1])).hexdigest() for m in messages if isinstance(m['content'],list) for p in m['content'] if p['type']=='image_url']
    record={'trace_id':uuid.uuid4().hex,'source_root':str(ROOT),'environment':'actual '+os.environ.get('NEURA_QA_TARGET_KIND','packaged')+' backend with QA observer; NO fake inference',
        'model_id':app.state.coordinator.current_model_id,'model_path':backend.model_path,
        'projector':getattr(backend.handler,'clip_model_path',None),'device':getattr(backend,'selected_device',None),
        'n_ctx':app.state.coordinator.settings.n_ctx,'native_n_gpu_layers':getattr(getattr(backend.model,'model_params',None),'n_gpu_layers',None),
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
        record.update(finished_at=time.time(),finish_reason=result['choices'][0].get('finish_reason'),output=result['choices'][0]['message'],usage=result.get('usage'));save();return result
    def chunks():
        record['output']=''
        try:
            for chunk in result:
                for choice in chunk.get('choices',[]):
                    record['output']+=choice.get('delta',{}).get('content') or ''
                    if choice.get('finish_reason'):record['finish_reason']=choice['finish_reason']
                yield chunk
        finally:
            if hasattr(result,'close'):result.close()
            record['finished_at']=time.time();save()
    return chunks()
backend.generate=observed
uvicorn.run(app,host='127.0.0.1',port=a.port,log_level='warning',proxy_headers=False)
