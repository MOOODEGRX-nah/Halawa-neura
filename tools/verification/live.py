"""Owned QA discovery and optional live trials. Never touches production sessions."""
import base64,json,os,re,struct,subprocess,sys,threading,time,urllib.error,urllib.parse,urllib.request,uuid,zlib
from pathlib import Path


def foreign_instances(owned_pid=None):
    import psutil
    found=[]
    for process in psutil.process_iter(['pid','name','cmdline']):
        try:
            args=process.info['cmdline'] or []
            if 'src.desktop.server' in args and process.pid!=owned_pid:
                found.append({'pid':process.pid,'cwd':process.cwd(),'kind':'existing Neura backend; not stopped or used for QA data'})
        except (psutil.NoSuchProcess,psutil.AccessDenied):continue
    return found


def require_actual(info,suite):
    if suite=='model' and info['model_adapter']!='actual llama.cpp CPU':
        raise ValueError('Fake model evidence cannot satisfy REAL_MODEL')
    if suite=='desktop' and info['desktop_adapter']!='actual trusted GIO':
        raise ValueError('Fake desktop evidence cannot satisfy REAL_DESKTOP')


class Client:
    def __init__(self,run,info):
        self.run,self.info=run,info
        from urllib.parse import urlsplit
        url=urlsplit(info['url'])
        if url.scheme!='http' or url.hostname!='127.0.0.1' or not url.port or url.path not in ('','/'):
            raise ValueError('QA discovery URL rejected')
        if info['run_id']!=run.result['run_id'] or info['target_root']!=str(run.target):raise ValueError('Discovery identity/root mismatch')
        self.token=(run.profile/'data/.api-token').read_text().strip()
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.verify()
    def verify(self):
        health=self.call('/health',verify=False)
        if health.get('instance_id')!=self.info['instance_id'] or health.get('version')!=self.run.result['target_version']:
            raise ValueError('Backend instance/version changed')
        return health
    def call(self,path,body=None,method=None,timeout=10,verify=True):
        if verify:self.verify()
        request=urllib.request.Request(self.info['url']+path,data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,
            headers={'X-Neura-Token':self.token,'Content-Type':'application/json'},method=method)
        with self.opener.open(request,timeout=timeout) as response:
            raw=response.read(8_000_001)
        if len(raw)>8_000_000:raise ValueError('QA response exceeds limit')
        return json.loads(raw)
    def idle(self,seconds=90):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            try:
                health=self.verify()
                if health['phase']=='idle':return True
            except (OSError,ValueError):pass
            threading.Event().wait(.2)
        return False


def start(run,kind):
    if kind=='real':
        foreign=foreign_instances()
        if foreign:raise RuntimeError('REAL_MODEL_BLOCKED_EXISTING_INSTANCE: '+json.dumps(foreign))
        if not run.args.allow_real_model:raise RuntimeError('REAL_MODEL requires --allow-real-model')
        import psutil
        mem=psutil.virtual_memory()
        resources={'captured_at':time.time(),'available_ram_bytes':mem.available,'total_ram_bytes':mem.total,
                   'device':'explicit CPU','minimum_qa_available_ram_bytes':12_000_000_000}
        (run.out/'artifacts/preload-resources.json').write_text(json.dumps(resources,indent=2))
        if mem.available<12_000_000_000:raise RuntimeError('REAL_MODEL blocked: conservative QA RAM budget unavailable; no pressure was induced')
    # No import of the checkout app during installed-target verification.
    os.environ.update(run.env);sys.path.insert(0,str(run.target))
    from src.desktop.service import BackendService
    from src.desktop.paths import DesktopSettings
    settings=DesktopSettings();settings.values.update(models_dir=run.result.get('baseline',{}).get('production_model_options_read_only',{}).get('models_dir') or '/opt/neura-ai/models',
        n_gpu_layers=0,n_ctx=4096,dedicated_coder=True,check_updates=False)
    settings.save();os.environ['NEURA_TIMEOUT_S']='900'
    if kind=='fixture':
        os.environ['NEURA_QA_REAL_DESKTOP']='1' if run.args.allow_desktop else '0'
        fixture=Path(__file__).resolve().parents[2]/'tests/fixtures/chat_first_backend.py'
        service=BackendService(settings,popen=lambda command,**opts:subprocess.Popen([command[0],'-B',str(fixture),'--port',command[-1]],**opts))
    else:service=BackendService(settings)
    service.start();deadline=time.monotonic()+35;health=None
    while time.monotonic()<deadline:
        health=service.health()
        if health:break
        if service.process.poll() is not None:raise RuntimeError('Owned QA backend exited during startup; inspect profile/state/backend.log')
        threading.Event().wait(.1)
    if not health:
        service.stop();raise RuntimeError('Owned QA backend readiness deadline')
    info={'run_id':run.result['run_id'],'url':service.url,'instance_id':service.instance,'pid':service.process.pid,
        'target_root':str(run.target),'model_adapter':'actual llama.cpp CPU' if kind=='real' else 'fake, no inference',
        'desktop_adapter':'actual trusted GIO' if kind=='real' or run.args.allow_desktop else 'fake',
        'device':'explicit CPU','n_ctx':4096,'profile_kind':'qa','startup':'BackendService owned dynamic-port discovery; not native Qt icon test',
        'started_at':time.time()}
    path=run.out/'artifacts/backend.json'
    if path.exists():
        previous=json.loads(path.read_text());history=run.out/'artifacts/backend-history';history.mkdir(exist_ok=True)
        (history/(previous['instance_id']+'.json')).write_text(json.dumps(previous,indent=2))
    path.write_text(json.dumps(info,indent=2));path.chmod(0o600)
    return service,Client(run,info)


def serve(run,kind):
    try:service,client=start(run,kind)
    except (RuntimeError,OSError) as exc:
        ids=[r['task_id'] for r in run.result['requirements']]
        run.gate(ids,'REAL_MODEL','BLOCKED',str(exc),limitation='النسخة القائمة لم تُغلق؛ لم يبدأ استدلال ثانٍ.');run.save();print(str(exc),flush=True);return 3
    print('QA_DISCOVERY '+str(run.out/'artifacts/backend.json'),flush=True)
    stop=run.out/'stop-server';deadline=time.monotonic()+3600
    try:
        while not stop.exists() and time.monotonic()<deadline:
            if service.process.poll() is not None:raise RuntimeError('Owned QA server exited')
            threading.Event().wait(.2)
    finally:
        # Do not equate a client timeout with the native worker returning.
        if kind=='fixture' or client.idle(900):service.stop()
        else:
            run.add(['N013'],__import__('verify_neura').case('native_owner_retained','BLOCKED','REAL_MODEL',client.info,
                limitation='لم تثبت نهاية العمل الأصلي؛ أبقيت العملية المملوكة وملف اكتشافها، ولم أحررها أو أبدأ نموذجًا آخر.',required=True))
            run.save()
    return 0


def png_fixture():
    def chunk(name,data):return struct.pack('>I',len(data))+name+data+struct.pack('>I',zlib.crc32(name+data)&0xffffffff)
    raw=b''.join(b'\0'+bytes((255,0,0))*32+bytes((0,0,255))*32 for _ in range(64))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',64,64,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')


def history(run,client):
    if not client.idle(900):return 3
    payload={'messages':[{'role':'system','content':'Retain the verification code in this synthetic test.'},
        {'role':'user','content':'My verification code is QA742.'},{'role':'assistant','content':'I will remember QA742 for this conversation.'},
        {'role':'user','content':'ما رمز الفحص الذي ذكرته؟ أجب بالرمز فقط.'}], 'tier':'fast','max_tokens':64,'temperature':0}
    try:
        value=client.call('/v1/chat/completions',payload,timeout=930)
        passed='QA742' in value['choices'][0]['message']['content']
    except urllib.error.HTTPError as exc:
        raw=exc.read(4096)
        try:detail=json.loads(raw)
        except ValueError:detail={'error_type':'non_json_error'}
        value={'http_status':exc.code,'error':detail};passed=False
    evidence={'request':payload,'response':value,'passed':passed,'scope':'system/user/assistant history, English-to-Arabic recall; no persistent personal memory claim'}
    (run.out/'artifacts/multiturn-history.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
    run.gate(['N005'],'REAL_MODEL','PASS' if passed else 'FAIL',evidence,['artifacts/multiturn-history.json']);run.save();return int(not passed)


def valid_plan(text):
    # A nonempty refusal is not a plan. No model grade substitutes for these
    # prompt-specific criteria; the actual output is retained for human review.
    headings=re.findall(r'(?m)^\s*(?:[#>*-]\s*)?(?:\*\*)?([123١٢٣])[.)،:\-]',text)
    refusal=re.search(r'لا\s+(?:يمكنني|استطيع|أستطيع|أملك|املك).{0,70}(?:إنشاء|انشاء|بناء|كتابة|برمج|قدرات)',text)
    commands=re.search(r'(?mi)^\s*(?:\$\s*)?(?:sudo|npm install|pip install|npx)\b',text)
    return len(headings)==3 and not refusal and not commands and bool(re.search(r'HTML|CSS|هيكل|تصميم|صفحة',text,re.I))


def original_job_id(profile,project_id,request):
    import sqlite3
    path=Path(profile)/'data/workspace/catalog.sqlite3'
    with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
        for jid,raw in db.execute('SELECT id,request FROM jobs WHERE project_id=? ORDER BY created',(project_id,)):
            if json.loads(raw)['user_request']==request:return jid
    raise ValueError('Original generation job not found; latest edit is not a substitute')


def budget(run,client):
    if not client.idle(900):return 3
    request={'messages':[{'role':'user','content':'0 '*5000}],'tier':'fast','max_tokens':16,'temperature':0}
    value={};rejected=False
    try:value=client.call('/v1/chat/completions',request,timeout=930)
    except urllib.error.HTTPError as exc:
        raw=exc.read(4096)
        try:value={'status':exc.code,'error':json.loads(raw)}
        except ValueError:value={'status':exc.code,'error':'non-JSON response'}
        rejected=bool(re.search(r'context|token|length',json.dumps(value),re.I))
    idle=client.idle(900)
    recovered=client.call('/v1/chat/completions',{'messages':[{'role':'user','content':'Reply only OK'}],'tier':'fast','max_tokens':32,'temperature':0},timeout=930) if idle else {}
    passed=rejected and idle and 'OK' in recovered.get('choices',[{}])[0].get('message',{}).get('content','')
    evidence={'request_shape':{'text':'0 repeated 5000 times','characters':10000,'n_ctx':4096,'max_tokens':16,'tier':'fast'},'response':value,'native_idle':idle,'later_response':recovered,'passed':passed,'scope':'Bounded context-overflow negative test, not RAM/VRAM exhaustion or automatic long-chat summarization'}
    (run.out/'artifacts/context-budget.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
    run.gate(['N006','N013'],'REAL_MODEL','PASS' if passed else 'FAIL',evidence,['artifacts/context-budget.json']);run.save();return int(not passed)


def transport(run,client):
    if not client.idle(900):return 3
    payload={'messages':[{'role':'user','content':'Write three short lines about a static HTML page.'}],'tier':'fast','max_tokens':96,'stream':True,'temperature':0}
    request=urllib.request.Request(client.info['url']+'/v1/chat/completions',data=json.dumps(payload).encode(),headers={'X-Neura-Token':client.token,'Content-Type':'application/json'})
    started=time.monotonic();records=[];ids=set();finished=False;finish=None;first=None;error=None
    with client.opener.open(request,timeout=930) as response:
        model=response.headers.get('X-Neura-Model')
        for raw in response:
            if len(raw)>1_000_000:raise ValueError('SSE line exceeds QA bound')
            if not raw.startswith(b'data: '):continue
            if raw[6:].strip()==b'[DONE]':finished=True;break
            value=json.loads(raw[6:]);error=value.get('error') or error
            if value.get('id'):ids.add(value['id'])
            for choice in value.get('choices',[]):
                if choice.get('delta',{}).get('content') and first is None:first=time.monotonic()-started
                finish=choice.get('finish_reason') or finish
            records.append(value)
            if len(records)>5000:raise ValueError('SSE event count exceeds QA bound')
    duration=time.monotonic()-started
    passed=finished and not error and finish=='stop' and len(ids)==1 and first is not None and first<duration
    evidence={'request':payload,'actual_model':model,'stable_response_ids':sorted(ids),'first_content_s':first,'total_s':duration,'finish_reason':finish,'done':finished,'error':error,'chunks':records,'passed':passed}
    (run.out/'artifacts/native-transport.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
    run.gate(['N003','N012'],'REAL_MODEL','PASS' if passed else 'FAIL',evidence,['artifacts/native-transport.json']);run.save();return int(not passed)


def record_chat_trial(run,observation):
    """Quality, routing, template validity and transport are separate claims."""
    artifacts=['artifacts/models.json']
    valid=observation['native_returned_idle'] and observation['error'] is None
    routing=valid and observation['actual_model']==observation['routed_model']
    rendered=valid and bool(observation['output'].strip()) and not any(marker in observation['output'] for marker in ('<start_of_turn>','<|im_start|>'))
    streamed=valid and observation['first_nonempty_chunk_s'] is not None and observation['first_nonempty_chunk_s']<observation['duration_s'] and observation['finish_reason'] in ('stop','length')
    for ids,passed in [(['N004'],routing),(['N005'],rendered),(['N012'],streamed),(['N006'],observation['passed'])]:
        run.gate(ids,'REAL_MODEL','PASS' if passed else 'FAIL',observation,artifacts,limitation='Packaged CPU trial; quality is distinct from routing and truthful partial-output transport.')
    run.gate(['N097'],'REAL_MODEL','PASS',{'name':observation['name'],'recorded':'Prompt/config/expectation/output/outcome/timing','quality_passed':observation['passed']},artifacts,
             limitation='An accurately recorded model failure is not evaluator success for the model quality requirement.')


def desktop(run,client):
    scenarios=[('discord_ar','هل يمكنك ان تفتح ديسكورد',['N066','N071']),
        ('discord_knowledge','هل تعرف الديسكورد بالإنجليزي',['N066','N073']),
        ('discord_followup','هذا هوا افتحه',['N066','N071','N073']),
        ('discord_en','افتح تطبيق discord',['N071']),
        ('youtube','هل يمكنك ان تفتح لي موقع youtube',['N066','N067']),
        ('brave_search','ابحث في الويب عن تعلم البرمجة بالعربي',['N068']),
        ('youtube_search','ابحث في يوتيوب عن تعلم Python بالعربي',['N069'])]
    records=[];session='qa_desktop_'+uuid.uuid4().hex
    for name,text,ids in scenarios:
        rid='r_'+str(int(time.time()*1000))+'_'+uuid.uuid4().hex
        value=client.call('/chat/dispatch',{'text':text,'request_id':rid,'session_id':session},timeout=15)
        # Knowledge must not issue a launch; all positive cases require the actual adapter result.
        passed=value.get('kind')=='knowledge' if name=='discord_knowledge' else value.get('result',{}).get('status')=='launched'
        repeat=client.call('/chat/dispatch',{'text':text,'request_id':rid,'session_id':session})
        passed=passed and repeat==value
        records.append({'case':name,'text':text,'response':value,'retry_equal':repeat==value,'passed':passed,'window_observed':False,'remote_page_loaded':'not verified'})
        run.gate(ids,'REAL_DESKTOP','PASS' if passed else 'FAIL',records[-1],['artifacts/desktop.json'],limitation='GIO acceptance only; no native window observation. API journey, composer separately tested.')
        (run.out/'artifacts/desktop.json').write_text(json.dumps(records,ensure_ascii=False,indent=2));run.save()
    return int(not all(r['passed'] for r in records))


def models(run,client):
    if not client.idle(900):
        run.gate(['N013'],'REAL_MODEL','BLOCKED','Existing owned native work has not returned; no second request started.');run.save();return 3
    foreign=foreign_instances(client.info['pid'])
    if foreign:
        run.gate([r['task_id'] for r in run.result['requirements']],'REAL_MODEL','BLOCKED',foreign,limitation='Another Neura instance appeared; no concurrent inference started.');run.save();return 3
    import psutil
    samples=[];sampling=threading.Event()
    def sample():
        while not sampling.is_set():
            try:
                started=time.monotonic();health=client.verify();memory=psutil.virtual_memory()
                if len(samples)<8000:samples.append({'t':time.time(),'phase':health['phase'],'model':health['current_model'],
                    'poll_s':time.monotonic()-started,'rss_bytes':psutil.Process(client.info['pid']).memory_info().rss,'available_ram_bytes':memory.available})
            except (OSError,ValueError,psutil.Error):pass
            sampling.wait(.5)
    monitor=threading.Thread(target=sample,daemon=True);monitor.start()
    observations=[];failed=False
    prompts=[('fast_ar','fast','اكتب كلمة مرحبا فقط.',64,lambda s:'مرحبا' in s),
        ('fast_en','fast','Reply with exactly READY.',64,lambda s:'READY' in s.upper()),
        ('fast_mixed','fast','اكتب فقط: Python جاهز',96,lambda s:'python' in s.lower() and 'جاهز' in s),
        ('daily_ar','daily','أجب باختصار: ما عاصمة السعودية؟',512,lambda s:'الرياض' in s),
        ('daily_en','daily','Reply with the number: 7 plus 5 equals?',512,lambda s:'12' in s),
        ('daily_mixed','daily','أجب بسطر: HTML for structure وCSS لماذا؟',512,lambda s:'css' in s.lower()),
        ('expert_plan','expert','خطط لموقع سيرة ذاتية ثابت بثلاث خطوات مرقمة. بدون cloud وبدون تثبيت أي شيء.',768,valid_plan)]
    health=client.verify();before=health.get('current_model')
    for name,tier,prompt,token_budget,predicate in prompts:
        if foreign_instances(client.info['pid']):
            sampling.set();monitor.join(timeout=5);run.gate(['N010'],'REAL_MODEL','BLOCKED','Another Neura instance appeared; further loads stopped.');run.save();return 3
        started=time.monotonic();payload={'messages':[{'role':'user','content':prompt}],'tier':tier,'stream':True,'max_tokens':token_budget,'temperature':0}
        route=client.call('/route',{'text':prompt,'tier':tier});request=urllib.request.Request(client.info['url']+'/v1/chat/completions',data=json.dumps(payload,ensure_ascii=False).encode(),headers={'X-Neura-Token':client.token,'Content-Type':'application/json'})
        first=None;finish=None;pieces=[];error=None;model=None;chunks=0
        try:
            with client.opener.open(request,timeout=930) as response:
                model=response.headers.get('X-Neura-Model')
                for raw in response:
                    if not raw.startswith(b'data: '):continue
                    data=raw[6:].strip()
                    if data==b'[DONE]':break
                    item=json.loads(data)
                    if 'error' in item:error=item['error'];break
                    for choice in item.get('choices',[]):
                        text=choice.get('delta',{}).get('content') or ''
                        if text:
                            if first is None:first=time.monotonic()-started
                            chunks+=1;pieces.append(text)
                        if choice.get('finish_reason'):finish=choice['finish_reason']
        except (OSError,ValueError) as exc:error={'type':type(exc).__name__,'message':str(exc)[:500]}
        safe=client.idle(900);answer=''.join(pieces)
        passed=safe and error is None and bool(answer.strip()) and predicate(answer) and model==route.get('model_id') and finish=='stop'
        observation={'name':name,'tier':tier,'request':payload,'expected':'Three actual numbered static-site steps, no false inability refusal or install commands' if name=='expert_plan' else 'Objective prompt-specific expected answer: '+prompt,
            'routed_model':route.get('model_id'),'actual_model':model,'output':answer,'finish_reason':finish,'error':error,
            'first_nonempty_chunk_s':first,'duration_s':time.monotonic()-started,'chunks':chunks,'cold_or_warm':'warm_same_weights' if before==model else 'cold_or_model_change',
            'queue_s':None,'load_s':None,'prefill_s':None,'decode_tps':None,'metrics_limitation':'No fabricated per-phase/token rates; first chunk includes load/prefill/queue.','native_returned_idle':safe,'passed':passed}
        observations.append(observation);before=model
        path=run.out/'artifacts/models.json';path.write_text(json.dumps(observations,ensure_ascii=False,indent=2))
        record_chat_trial(run,observation);run.save();failed|=not passed
        if not safe:
            sampling.set();monitor.join(timeout=5);return 3
    image=png_fixture();(run.out/'artifacts/vision-qa.png').write_bytes(image)
    payload={'messages':[{'role':'user','content':[{'type':'text','text':'ما اللونان الظاهران في الصورة؟ اذكر اللونين فقط.'},{'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(image).decode()}}]}],'tier':'vision','max_tokens':256,'temperature':0}
    try:
        result=client.call('/v1/chat/completions',payload,timeout=930);answer=result['choices'][0]['message']['content'];passed=('أحمر' in answer or 'احمر' in answer or 'red' in answer.lower()) and ('أزرق' in answer or 'ازرق' in answer or 'blue' in answer.lower())
        result['expected']='red and blue, actual inline image/projector path'
    except (OSError,ValueError) as exc:result={'error':str(exc)[:500]};passed=False
    (run.out/'artifacts/vision.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));run.gate(['N093'],'REAL_MODEL','PASS' if passed else 'FAIL',result,['artifacts/vision.json','artifacts/vision-qa.png']);run.save();failed|=not passed
    if not client.idle(900):sampling.set();monitor.join(timeout=5);return 3

    def job_done(jid,seconds=930):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            job=client.call('/project-jobs/'+jid)
            if job['state'] in ('completed','failed','cancelled'):return job
            sampling.wait(.25)
        client.call('/project-jobs/'+jid+'/cancel',{},'POST')
        if not client.idle(900):raise RuntimeError('Native job has not returned; ownership retained')
        raise TimeoutError('Project deadline exceeded; cancellation requested and native returned')
    # The composer creates CV first when CUA is available. Reuse its saved job,
    # rather than silently generating a duplicate just for a second proof count.
    projects=client.call('/projects')['projects'];cv=next((p for p in projects if p['purpose']=='برمج لي موقع للcv'),None)
    if cv:
        cv=client.call('/projects/'+cv['project_id']);cvjob=job_done(original_job_id(run.profile,cv['project_id'],'برمج لي موقع للcv'))
        run.gate(['N008','N041','N043','N044','N049','N050','N051','N052','N055'],'REAL_MODEL','PASS' if cvjob['state']=='completed' else 'FAIL',
                 {'original_request':cv['purpose'],'project':cv,'job':cvjob},['artifacts/cv-job.json'],limitation='Real model files; CUA navigation, pane geometry, JS and preview behavior are separate evidence.')
        (run.out/'artifacts/cv-job.json').write_text(json.dumps(cvjob,ensure_ascii=False,indent=2))
    else:
        run.gate(['N049'],'REAL_MODEL','NOT_RUN','Exact CV composer journey not yet performed; not substituted by API tutorial.',limitation='Use --serve real and the actual composer to complete the release gate.')
    rid='r_'+str(int(time.time()*1000))+'_'+uuid.uuid4().hex
    req={'text':'اكتب برنامج Python لحساب المصروفات','request_id':rid,'session_id':'qa_model_python'}
    created=client.call('/chat/dispatch',req);repeat=client.call('/chat/dispatch',req)
    if created.get('kind')!='project':
        run.gate(['N049'],'REAL_MODEL','FAIL',created,limitation='Python request did not create a durable project.');failed=True
    else:
        job=job_done(created['job']['job_id']);pid=created['project']['project_id'];meta=client.call('/projects/'+pid)
        files={f['path']:client.call('/projects/'+pid+'/file?path='+urllib.parse.quote(f['path'])) for f in meta['files']}
        passed=job['state']=='completed' and bool(files) and not meta['preview']['supported'] and repeat['job']['job_id']==job['job_id']
        value={'request':req,'job':job,'project':meta,'files':files,'retry_same_job':repeat['job']['job_id']==job['job_id'],'executed_generated_program':False,'passed':passed}
        (run.out/'artifacts/python-project.json').write_text(json.dumps(value,ensure_ascii=False,indent=2));run.gate(['N008','N043','N044','N049','N050','N051'],'REAL_MODEL','PASS' if passed else 'FAIL',value,['artifacts/python-project.json']);run.save();failed|=not passed
        if passed:
            # Cancel an edit of the same saved Python project; last-good bytes
            # must survive. A later valid request uses the same coordinator.
            paths=[f['path'] for f in meta['files'] if f['path'].endswith('.py')]
            edit=client.call('/projects',{'user_request':'أضف تعليقات توضيحية مفصلة إلى الملف الموجود مع الحفاظ على الحسابات.','requirements':['Preserve existing calculation functions'],
                'project_id':pid,'expected_revision':meta['project_revision'],'context_files':paths[:8],'background':True,'max_tokens':2048})
            jid=edit['job']['job_id'];deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                current=client.call('/project-jobs/'+jid)
                if current['state'] in ('generating','completed','failed'):break
                sampling.wait(.1)
            client.call('/project-jobs/'+jid+'/cancel',{},'POST');cancelled=job_done(jid);idle=client.idle(900)
            after=client.call('/projects/'+pid);same=after['project_revision']==meta['project_revision'] and {x['path']:x['sha256'] for x in after['files']}=={x['path']:x['sha256'] for x in meta['files']}
            later=client.call('/v1/chat/completions',{'messages':[{'role':'user','content':'Reply only OK'}],'tier':'fast','max_tokens':32,'temperature':0},timeout=930) if idle else {}
            recovered=bool(later.get('choices',[{}])[0].get('message',{}).get('content','').strip())
            passed=cancelled['state']=='cancelled' and same and idle and recovered
            value={'cancelled_job':cancelled,'native_idle':idle,'last_good_same':same,'later_reply':later,'passed':passed}
            (run.out/'artifacts/native-cancel.json').write_text(json.dumps(value,ensure_ascii=False,indent=2));run.gate(['N012','N013','N050','N052'],'REAL_MODEL','PASS' if passed else 'FAIL',value,['artifacts/native-cancel.json']);run.save();failed|=not passed
    sampling.set();monitor.join(timeout=5)
    (run.out/'artifacts/resource-samples.json').write_text(json.dumps({'samples':samples,'interval_s':.5,'sample_limit':8000,'thread_stopped':not monitor.is_alive(),'rates_not_inferred_from_characters':True},indent=2))
    run.gate(['N108'],'REAL_MODEL','PASS' if samples and max(x['poll_s'] for x in samples)<3 else 'FAIL',{'samples':len(samples),'max_health_poll_s':max((x['poll_s'] for x in samples),default=None)},['artifacts/resource-samples.json']);run.save()
    history_code=history(run,client)
    budget_code=budget(run,client)
    return int(failed or history_code or budget_code)


def execute_live(run,suite):
    if suite=='model' and not run.args.allow_real_model or suite=='desktop' and not run.args.allow_desktop:
        method='REAL_MODEL' if suite=='model' else 'REAL_DESKTOP'
        run.gate([r['task_id'] for r in run.result['requirements']],method,'BLOCKED','Explicit opt-in flag absent',limitation='No launch or inference was attempted.');run.save();return 3
    infofile=run.out/'artifacts/backend.json';service=None
    try:
        if infofile.exists():
            info=json.loads(infofile.read_text());client=Client(run,info)
            require_actual(info,suite)
        else:service,client=start(run,'real' if suite=='model' else 'fixture')
    except (OSError,RuntimeError,ValueError) as exc:
        run.gate([r['task_id'] for r in run.result['requirements']],'REAL_MODEL' if suite=='model' else 'REAL_DESKTOP','BLOCKED',str(exc),limitation='Actual acceptance unavailable; no foreign process was stopped.');run.save();return 3
    try:return ({'history':history,'budget':budget,'transport':transport,'all':models}[run.args.model_case](run,client)) if suite=='model' else desktop(run,client)
    except Exception as exc:
        # Credentials stay in Client; record the error class and safe HTTP status,
        # never request headers or raw token-bearing request representations.
        run.add(['N097'],__import__('verify_neura').case('live_suite_exception','FAIL','REAL_MODEL' if suite=='model' else 'REAL_DESKTOP',
            {'type':type(exc).__name__,'http_status':getattr(exc,'code',None)},limitation='Live suite stopped on an exception; inspect owned QA logs. Remaining cases were not counted as passed.',required=True));run.save();return 1
    finally:
        if service:
            if suite=='desktop' or client.idle(900):service.stop()
            else:run.result['native_owner_retained']=client.info;run.save()
