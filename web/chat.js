/* Only newly submitted user text enters dispatch. Assistant/rendered text never does. */
(()=>{
  const newRequestId=()=>'r_'+Date.now()+'_'+crypto.randomUUID().replaceAll('-','');
  async function call(path,body,signal){const r=await api(path,{...(body===undefined?{}:{method:'POST',body:JSON.stringify(body)}),signal});const result=await r.json();if(!r.ok)throw Error(result.error?.message||result.detail||'تعذر تنفيذ الطلب');return result;}
  async function settle(result,signal,session){for(let tries=0;result.kind==='pending'&&tries<120;tries++){await sleep(400);result=await call('/chat/requests/'+result.request_id+'?session_id='+encodeURIComponent(session),undefined,signal);}return result;}
  async function save(){if(!TOKEN)return;try{const r=await api('/vault/save',{method:'POST',body:JSON.stringify({session:sid,messages:hist})});if(!r.ok)note('تعذر حفظ الجلسة؛ النتيجة ما زالت ظاهرة.');}catch(_){note('تعذر حفظ الجلسة؛ النتيجة ما زالت ظاهرة.');}}
  function remember(q,message,context){
    if(sid!==context.session)return;
    const value={role:'assistant',content:message,...(context.jobId?{project_job_id:context.jobId}:{})};
    if(context.historyIndex===undefined){hist.push({role:'user',content:q});context.historyIndex=hist.length;hist.push(value);}else hist[context.historyIndex]=value;
    save();
  }
  const receipts=new Map();
  function jobText(job){
    const r=job.execution;
    if(job.state==='failed'||job.state==='cancelled')return 'لم يُحفظ التعديل: '+(job.error||'أُلغيت المهمة')+'. بقيت آخر مراجعة محفوظة.';
    if(job.state==='queued'&&job.blocked_reason)return 'المهمة تنتظر الموارد: '+job.blocked_reason;
    if(job.state!=='completed')return ({queued:'المهمة في قائمة الانتظار.',planning:'يجري التخطيط قبل توليد الملفات.',generating:'يجري توليد الملفات.',validating:'يجري فحص المرشح قبل الحفظ.'})[job.state]||'تعذر تأكيد حالة المهمة.';
    if(r?.outcome==='no_change')return 'لم يتغير محتوى الملفات؛ لم تُنشأ مراجعة جديدة.';
    if(r?.outcome==='saved'&&r.changed_files?.length)return 'حُفظت المراجعة '+r.result_revision+' بدل '+r.base_revision+'؛ الملفات المتغيرة: '+r.changed_files.join('، ')+'. اجتاز الفحص الساكن.'+(r.browser?.status==='passed'?' اجتاز فحوص المعاينة المحدودة؛ لا يثبت ذلك كل وظائف الموقع.':'');
    return 'انتهت المهمة دون إيصال تغيير موثق؛ راجع الملفات.';
  }
  async function reconcile(jobId,session=sid){
    const job=await call('/project-jobs/'+jobId);
    if(session!==sid)return;
    const text=jobText(job),entry=receipts.get(jobId);
    if(entry?.session===session)remember(entry.q,text,entry.context);
    else {let changed=false;for(const m of hist)if(m.role==='assistant'&&m.project_job_id===jobId&&m.content!==text){m.content=text;changed=true;}if(changed)save();}
    for(const card of document.querySelectorAll('[data-project-job-id]'))if(card.dataset.projectJobId===jobId){
      const body=card.querySelector('[data-job-text]');if(body)body.textContent=text;else {const body=card.querySelector('.t');if(body)body.textContent=text;}
      card.dataset.jobState=job.state;
    }
  }
  async function updateReceipt(job){try{await reconcile(job);}catch(_){/* Keep last observed state; reconnect reconciles from durable state. */}}
  async function restoreStatus(){
    const session=sid;
    // Migrate only an exact legacy request/start-card pair for the durable latest
    // job. Unmatched historical prose is not authority to attach another job.
    try{
      const status=await call('/chat/status/'+encodeURIComponent(session));
      if(session!==sid)return;
      if(status.job_id&&!hist.some(m=>m.project_job_id===status.job_id)){
        const job=await call('/project-jobs/'+status.job_id);
        if(session!==sid)return;
        for(let i=hist.length-1;i>0;i--){
          if(hist[i].role==='assistant'&&!hist[i].project_job_id&&/^(?:أُنشئ المشروع|بدأ تعديل المشروع)/.test(hist[i].content)&&hist[i-1].role==='user'&&hist[i-1].content===job.invoice?.user_request){
            hist[i].project_job_id=status.job_id;
            for(const card of document.querySelectorAll('[data-history-index]'))if(Number(card.dataset.historyIndex)===i)card.dataset.projectJobId=status.job_id;
            break;
          }
        }
      }
    }catch(_){}
    // An unmatched historical start message is an observation from the past,
    // not evidence that a job is still running now. Do not attach an arbitrary job.
    let migrated=false;
    for(let i=0;i<hist.length;i++)if(hist[i].role==='assistant'&&!hist[i].project_job_id&&/^(?:أُنشئ المشروع|بدأ تعديل المشروع)/.test(hist[i].content)){
      const text='سجل بدء قديم؛ لم تُطابق حالته بمهمة محفوظة. افتح المشروع للتحقق من المراجعة الحالية.';
      hist[i]={...hist[i],content:text};migrated=true;
      for(const card of document.querySelectorAll('[data-history-index]'))if(Number(card.dataset.historyIndex)===i){const body=card.querySelector('.t');if(body)body.textContent=text;card.dataset.jobState='unknown';}
    }
    if(migrated)save();
    const ids=new Set(hist.map(m=>m.project_job_id).filter(Boolean));
    for(const card of document.querySelectorAll('[data-project-job-id]'))ids.add(card.dataset.projectJobId);
    for(const id of ids){if(session!==sid)return;try{await reconcile(id,session);}catch(_){}}
  }
  async function handleChat(q){
    const context={id:newRequestId(),card:null,session:sid},body={text:q,request_id:context.id,session_id:context.session,active_project_id:null,workspace_dirty:!!window.NeuraWorkspace?.dirty};
    async function display(data){
      if(data.kind==='chat')return false;
      if(data.kind==='project'){
        context.jobId=data.job.job_id;
        receipts.set(context.jobId,{session:context.session,q,context});
        remember(q,jobText(data.job),context);
        await window.NeuraWorkspace.acceptCreated(data,q);
        await updateReceipt(context.jobId);
        return true;
      }
      if(data.kind==='workspace'){
        const opened=await window.NeuraWorkspace.openForEdit(data.project_id,data.edit_request);
        if(opened){remember(q,data.message,context);if(context.card)context.card.t.replaceChildren(document.createTextNode(data.message));else{setHas(true);bubble('u','You','#42A5F5','code',q);bubble('n','Neura [المشروع]','#81C784','code',data.message);}}
        return true;
      }
      if(!context.card){setHas(true);bubble('u','You','#42A5F5','spark',q);context.card=bubble('n',data.kind==='metadata'?'Neura [المشروع]':data.kind==='clarification'?'Neura [تحديد الهدف]':data.kind==='assistant'?'Neura [المساعد]':'Neura [إجراء]',data.kind==='assistant'?'#FFCA28':'#81C784',data.kind==='assistant'?'zap':'shield','');}
      const result=data.result||{},message=data.message||result.message||'تعذر تأكيد نتيجة الطلب.';
      const box=context.card.t;box.replaceChildren(document.createTextNode(message));
      context.card.d.dataset.actionStatus=result.status||data.kind;
      if(['error','unavailable','unknown'].includes(result.status))context.card.d.style.setProperty('--mc','#FFB74D');
      for(const choice of data.choices||[]){const button=document.createElement('button');button.type='button';button.className='chat-action-choice';button.textContent=choice.label;button.onclick=()=>run('/chat/choose',{request_id:context.id,choice_id:choice.id,session_id:context.session});box.append(document.createElement('br'),button);}
      for(const app of result.applications||[]){const button=document.createElement('button');button.type='button';button.className='chat-action-choice';button.textContent=app.display_name||app.application_id;button.onclick=async()=>{if(busy)return;ui(true);try{const opened=await executeManual('open_application',{application_id:app.application_id});await display({kind:'action',result:opened});}catch(e){note(e.message);}finally{ui(false);}};box.append(document.createElement('br'),button);}
      if(data.kind==='pending'||data.retry){const button=document.createElement('button');button.type='button';button.className='chat-action-choice';button.textContent='استعادة نتيجة الطلب نفسه';button.onclick=()=>run('/chat/dispatch',body);box.append(document.createElement('br'),button);}
      remember(q,message,context);sc(true);
      if(data.kind==='assistant'){if(data.reminder&&page==='assistant')window.NeuraAssistant?.refresh();if(typeof speak==='function')speak(message,!!window.voiceTurn);}
      return true;
    }
    async function submit(path,payload){const controller=new AbortController();curAC=controller;try{return await display(await settle(await call(path,payload,controller.signal),controller.signal,context.session));}catch(e){return display({kind:'action',retry:true,result:{status:'unknown',message:e.name==='AbortError'?'توقف انتظار النتيجة؛ قد يكون طلب الفتح وصل. استعد نتيجة الطلب نفسه قبل تكراره.':e instanceof TypeError?'تعذر الاتصال بالخادم. استعد نتيجة الطلب نفسه؛ لن يُرسل تنفيذ مكرر.':e.message}});}finally{if(curAC===controller)curAC=null;}}
    async function run(path,payload){if(busy)return;if(sid!==context.session){note('هذا الاختيار يخص محادثة أخرى؛ اكتب طلبًا جديدًا في المحادثة الحالية.');return;}ui(true);setSt('thinking');try{await submit(path,payload);}finally{setSt('ready');ui(false);}}
    return submit('/chat/dispatch',body);
  }
  async function executeManual(name,args,{remember=false}={}){
    const id=newRequestId(),session=sid,grant=await call('/skills/authorize',{name,args,remember});
    const response=await settle(await call('/skills/execute',{name,args,permission_id:grant.permission_id,request_id:id,session_id:session}),undefined,session);
    if(response.kind==='pending')throw Error('ما زال الطلب نفسه قيد التنفيذ؛ انتظر نتيجته قبل طلب جديد.');
    const result=response.result||response;
    if(['error','unavailable','unknown'].includes(result.status))throw Error(result.message);
    return result;
  }
  window.addEventListener('online',()=>restoreStatus());
  window.NeuraChat={jobText,handleChat,executeManual,newRequestId,updateReceipt,restoreStatus};
})();
