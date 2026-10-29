/* Only newly submitted user text enters dispatch. Assistant/rendered text never does. */
(()=>{
  const newRequestId=()=>'r_'+Date.now()+'_'+crypto.randomUUID().replaceAll('-','');
  async function call(path,body,signal){const r=await api(path,{...(body===undefined?{}:{method:'POST',body:JSON.stringify(body)}),signal});const result=await r.json();if(!r.ok)throw Error(result.error?.message||result.detail||'تعذر تنفيذ الطلب');return result;}
  async function settle(result,signal){for(let tries=0;result.kind==='pending'&&tries<120;tries++){await sleep(400);result=await call('/chat/requests/'+result.request_id,undefined,signal);}return result;}
  async function save(){if(!TOKEN)return;try{const r=await api('/vault/save',{method:'POST',body:JSON.stringify({session:sid,messages:hist})});if(!r.ok)note('تعذر حفظ الجلسة؛ النتيجة ما زالت ظاهرة.');}catch(_){note('تعذر حفظ الجلسة؛ النتيجة ما زالت ظاهرة.');}}
  function remember(q,message,context){if(context.historyIndex===undefined){hist.push({role:'user',content:q});context.historyIndex=hist.length;hist.push({role:'assistant',content:message});}else hist[context.historyIndex]={role:'assistant',content:message};save();}
  async function handleChat(q){
    const context={id:newRequestId(),card:null},body={text:q,request_id:context.id,active_project_id:window.NeuraWorkspace?.projectId||null};
    async function display(data){
      if(data.kind==='chat')return false;
      if(data.kind==='project'){
        await window.NeuraWorkspace.acceptCreated(data,q);
        remember(q,'أُنشئ المشروع «'+data.project.display_name+'». الملفات والتقدم في مساحة المبرمج.',context);
        return true;
      }
      if(data.kind==='workspace'){
        const opened=await window.NeuraWorkspace.openForEdit(data.project_id,data.edit_request);
        if(opened){remember(q,data.message,context);if(context.card)context.card.t.replaceChildren(document.createTextNode(data.message));else{setHas(true);bubble('u','You','#42A5F5','code',q);bubble('n','Neura [المشروع]','#81C784','code',data.message);}}
        return true;
      }
      if(!context.card){setHas(true);bubble('u','You','#42A5F5','spark',q);context.card=bubble('n',data.kind==='metadata'?'Neura [المشروع]':data.kind==='clarification'?'Neura [تحديد الهدف]':'Neura [إجراء]','#81C784','shield','');}
      const result=data.result||{},message=data.message||result.message||'تعذر تأكيد نتيجة الطلب.';
      const box=context.card.t;box.replaceChildren(document.createTextNode(message));
      context.card.d.dataset.actionStatus=result.status||data.kind;
      if(['error','unavailable','unknown'].includes(result.status))context.card.d.style.setProperty('--mc','#FFB74D');
      for(const choice of data.choices||[]){const button=document.createElement('button');button.type='button';button.className='chat-action-choice';button.textContent=choice.label;button.onclick=()=>run('/chat/choose',{request_id:context.id,choice_id:choice.id});box.append(document.createElement('br'),button);}
      for(const app of result.applications||[]){const button=document.createElement('button');button.type='button';button.className='chat-action-choice';button.textContent=app.display_name||app.application_id;button.onclick=async()=>{if(busy)return;ui(true);try{const opened=await executeManual('open_application',{application_id:app.application_id});await display({kind:'action',result:opened});}catch(e){note(e.message);}finally{ui(false);}};box.append(document.createElement('br'),button);}
      if(data.kind==='pending'||data.retry){const button=document.createElement('button');button.type='button';button.className='chat-action-choice';button.textContent='استعادة نتيجة الطلب نفسه';button.onclick=()=>run('/chat/dispatch',body);box.append(document.createElement('br'),button);}
      remember(q,message,context);sc(true);return true;
    }
    async function submit(path,payload){const controller=new AbortController();curAC=controller;try{return await display(await settle(await call(path,payload,controller.signal),controller.signal));}catch(e){return display({kind:'action',retry:true,result:{status:'unknown',message:e.name==='AbortError'?'توقف انتظار النتيجة؛ قد يكون طلب الفتح وصل. استعد نتيجة الطلب نفسه قبل تكراره.':e instanceof TypeError?'تعذر الاتصال بالخادم. استعد نتيجة الطلب نفسه؛ لن يُرسل تنفيذ مكرر.':e.message}});}finally{if(curAC===controller)curAC=null;}}
    async function run(path,payload){if(busy)return;ui(true);setSt('thinking');try{await submit(path,payload);}finally{setSt('ready');ui(false);}}
    return submit('/chat/dispatch',body);
  }
  async function executeManual(name,args,{remember=false}={}){
    const id=newRequestId(),grant=await call('/skills/authorize',{name,args,remember});
    const response=await settle(await call('/skills/execute',{name,args,permission_id:grant.permission_id,request_id:id}));
    if(response.kind==='pending')throw Error('ما زال الطلب نفسه قيد التنفيذ؛ انتظر نتيجته قبل طلب جديد.');
    const result=response.result||response;
    if(['error','unavailable','unknown'].includes(result.status))throw Error(result.message);
    return result;
  }
  window.NeuraChat={handleChat,executeManual,newRequestId};
})();
