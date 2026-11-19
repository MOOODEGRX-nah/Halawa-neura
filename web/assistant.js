/* Assistant page (memory, reminders, preferences) and in-chat reminder delivery.
   Every write goes to the authenticated /assistant API; nothing here is driven by model output. */
(()=>{
  const $a=id=>document.getElementById(id);
  const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  async function call(path,options={}){
    const r=await api(path,options);let body={};try{body=await r.json();}catch(_){}
    if(!r.ok)throw Error(body.error?.message||body.detail||'تعذر تنفيذ الطلب');return body;
  }
  const send=(path,method,body)=>call(path,{method,...(body===undefined?{}:{body:JSON.stringify(body)})});
  let prefs={speak_reminders:true};
  const fmt=new Intl.DateTimeFormat('ar-SA-u-nu-latn',{weekday:'long',day:'numeric',month:'long',hour:'numeric',minute:'2-digit',timeZone:'Asia/Riyadh'});
  function when(ts,tz){try{return new Intl.DateTimeFormat('ar-SA-u-nu-latn',{weekday:'long',day:'numeric',month:'long',hour:'numeric',minute:'2-digit',timeZone:tz||'Asia/Riyadh'}).format(new Date(ts*1000));}catch(_){return fmt.format(new Date(ts*1000));}}
  function status(id,text,bad){const el=$a(id);if(!el)return;el.textContent=text||'';el.dataset.bad=bad?'1':'';if(text)setTimeout(()=>{if(el.textContent===text)el.textContent='';},6000);}

  function row(text,meta,buttons){
    const li=document.createElement('li');li.className='as-item';
    const body=document.createElement('div');body.className='as-body';
    const t=document.createElement('span');t.className='as-text';t.dir='auto';t.textContent=text;body.append(t);
    if(meta){const m=document.createElement('span');m.className='as-meta';m.textContent=meta;body.append(m);}
    const actions=document.createElement('div');actions.className='as-actions';
    for(const [label,handler,danger] of buttons){const b=document.createElement('button');b.type='button';b.className='as-btn'+(danger?' as-danger':'');b.textContent=label;b.onclick=handler;actions.append(b);}
    li.append(body,actions);return li;
  }

  async function loadReminders(){
    const list=$a('as-reminders');if(!list)return;
    try{
      const data=await call('/assistant/reminders');list.replaceChildren();
      $a('as-notify-state').textContent=data.notifications?'إشعارات سطح المكتب: متاحة':'إشعارات سطح المكتب غير متاحة؛ تظهر التذكيرات داخل Neura فقط';
      if(!data.reminders.length){list.innerHTML='<li class="nx-empty">لا توجد تذكيرات قادمة.</li>';return;}
      for(const r of data.reminders)list.append(row(r.text,when(r.due,r.timezone),[['إلغاء',async()=>{try{await send('/assistant/reminders/'+r.id,'DELETE');loadReminders();status('as-rem-status','أُلغي التذكير.');}catch(e){status('as-rem-status',e.message,1);}},true]]));
    }catch(e){list.innerHTML='<li class="nx-empty">'+esc(e.message)+'</li>';}
  }

  async function loadMemories(){
    const list=$a('as-memories');if(!list)return;
    try{
      const data=await call('/assistant/memories');list.replaceChildren();
      $a('as-mem-count').textContent=data.memories.length?String(data.memories.length):'';
      if(!data.memories.length){list.innerHTML='<li class="nx-empty">لا شيء محفوظ بعد. اكتب في المحادثة «تذكر أن…» أو أضف معلومة هنا.</li>';return;}
      for(const m of data.memories){
        const item=row(m.text,null,[
          ['تعديل',()=>{const input=document.createElement('input');input.className='as-input';input.value=m.text;input.dir='auto';input.maxLength=500;
            const save=document.createElement('button');save.type='button';save.className='as-btn as-primary';save.textContent='حفظ';
            save.onclick=async()=>{try{await send('/assistant/memories/'+m.id,'PUT',{text:input.value});loadMemories();}catch(e){status('as-mem-status',e.message,1);}};
            item.querySelector('.as-body').replaceChildren(input);item.querySelector('.as-actions').replaceChildren(save);input.focus();}],
          ['حذف',async()=>{try{await send('/assistant/memories/'+m.id,'DELETE');loadMemories();status('as-mem-status','حُذفت المعلومة.');}catch(e){status('as-mem-status',e.message,1);}},true]]);
        list.append(item);
      }
    }catch(e){list.innerHTML='<li class="nx-empty">'+esc(e.message)+'</li>';}
  }

  async function loadPrefs(){
    try{prefs=await call('/assistant/preferences');}catch(_){return;}
    if(!$a('as-city'))return;
    $a('as-city').value=prefs.city||'';if($a('as-persona'))$a('as-persona').value=prefs.persona||'';
    for(const key of ['desktop_notifications','speak_reminders','use_memory_in_chat']){const box=$a('as-'+key);if(box)box.checked=!!prefs[key];}
  }

  async function quick(text,statusId,after){
    // Natural-language input goes through the same authenticated dispatcher as the chat.
    if(!text.trim())return;
    try{
      const result=await send('/chat/dispatch','POST',{text,request_id:window.NeuraChat.newRequestId(),session_id:sid});
      if(result.kind==='chat'){status(statusId,'لم أفهم هذا كأمر للمساعد. جرّب: «ذكرني بعد 10 دقائق أن…».',1);return false;}
      status(statusId,result.message||result.result?.message||'تم.',['error','unavailable','clarification'].includes(result.result?.status)||result.kind==='clarification');
      after&&after();return true;
    }catch(e){status(statusId,e.message,1);return false;}
  }

  function build(){
    const page=$a('pg-assistant');if(!page||page.dataset.built)return;page.dataset.built='1';
    page.innerHTML=`<div class="nx-wrap">
      <div class="nx-card as-hero">
        <div class="as-hero-top"><b>المساعد الشخصي</b><span class="nx-tag ok">يعمل دون تحميل نموذج</span></div>
        <p class="nx-p">اكتب طلبك في المحادثة بلغتك العادية، أو جرّب أحد هذه الأمثلة:</p>
        <div class="as-examples" id="as-examples"></div>
      </div>
      <div class="nx-grid">
        <div class="nx-card">
          <h3 class="nx-h"><i class="nx-dot" style="background:#FFCA28"></i>التذكيرات القادمة</h3>
          <form class="as-form" id="as-rem-form"><input class="as-input" id="as-rem-input" dir="auto" maxlength="300" placeholder="مثال: ذكرني غدًا الساعة 9 صباحًا بالاجتماع" aria-label="تذكير جديد"><button class="as-btn as-primary" type="submit">إضافة</button></form>
          <p class="as-status" id="as-rem-status" role="status"></p>
          <ul class="as-list" id="as-reminders"></ul>
          <div class="as-row"><button type="button" class="as-btn" id="as-ics-export">تصدير للتقويم (.ics)</button><label class="as-btn" for="as-ics-import">استيراد من تقويم</label><input type="file" id="as-ics-import" accept=".ics,text/calendar" hidden></div>
          <p class="nx-sub" id="as-notify-state"></p>
        </div>
        <div class="nx-card">
          <h3 class="nx-h"><i class="nx-dot" style="background:#CE93D8"></i>ما أتذكره عنك <span class="nx-tag" id="as-mem-count"></span></h3>
          <form class="as-form" id="as-mem-form"><input class="as-input" id="as-mem-input" dir="auto" maxlength="500" placeholder="مثال: أفضّل الردود المختصرة" aria-label="معلومة جديدة"><button class="as-btn as-primary" type="submit">حفظ</button></form>
          <p class="as-status" id="as-mem-status" role="status"></p>
          <ul class="as-list" id="as-memories"></ul>
          <div class="as-row"><button type="button" class="as-btn" id="as-export">تصدير</button><label class="as-btn" for="as-import">استيراد</label><input type="file" id="as-import" accept="application/json,.json" hidden><button type="button" class="as-btn as-danger" id="as-clear">حذف الكل</button></div>
          <p class="nx-sub">لا أحفظ إلا ما تطلب حفظه صراحةً. المعلومات تبقى على جهازك فقط.</p>
        </div>
      </div>
      <div class="nx-card">
        <h3 class="nx-h"><i class="nx-dot" style="background:#66BB6A"></i>المعرفة — ملفاتك <span class="nx-tag" id="as-kb-count"></span></h3>
        <p class="nx-sub">أضف ملفات نصية (txt، md، csv، html، كود) ثم اسأل في المحادثة: «من ملفاتي: …». تبقى على جهازك وتُفهرس محليًا.</p>
        <div class="as-row"><label class="as-btn as-primary" for="as-kb-file">إضافة ملفات</label><input type="file" id="as-kb-file" multiple accept=".txt,.md,.markdown,.csv,.json,.html,.htm,.py,.js,.ts,.css,.yaml,.yml,.toml,.log,.srt,.vtt,.xml,.tex,.rst" hidden></div>
        <p class="as-status" id="as-kb-status" role="status"></p>
        <ul class="as-list" id="as-kb"></ul>
      </div>
      <div class="nx-card">
        <h3 class="nx-h"><i class="nx-dot" style="background:#42A5F5"></i>تفضيلات المساعد</h3>
        <div class="as-prefs">
          <label class="as-field">المدينة الافتراضية للطقس<input class="as-input" id="as-city" dir="auto" maxlength="80"></label>
          <label class="as-check"><input type="checkbox" id="as-desktop_notifications"> إشعارات سطح المكتب للتذكيرات</label>
          <label class="as-check"><input type="checkbox" id="as-speak_reminders"> قراءة التذكير بصوت عند توفر النطق</label>
          <label class="as-check"><input type="checkbox" id="as-use_memory_in_chat"> استخدام ما أتذكره في المحادثة</label>
        </div>
        <label class="as-field as-wide">أسلوب Neura في الرد (اختياري)<textarea class="as-input" id="as-persona" dir="auto" rows="2" maxlength="600" placeholder="مثال: رد باختصار وبلهجة سعودية ودودة، واذكر الخطوات مرقمة."></textarea></label>
        <p class="as-status" id="as-pref-status" role="status"></p>
      </div>
      <div class="nx-card">
        <h3 class="nx-h"><i class="nx-dot" style="background:#26C6DA"></i>الصوت — مقارنة الأصوات واختيارها</h3>
        <p class="nx-sub">نفس الجملة العربية (أسماء وأرقام وعلامات ترقيم) تُقرأ بكل صوت محلي، مع قياس زمن التوليد الفعلي. الحكم على الجودة سماعي يعود لك.</p>
        <label class="as-field as-wide">جملة المقارنة<textarea class="as-input" id="as-voice-text" dir="auto" rows="2" maxlength="600"></textarea></label>
        <p class="as-status" id="as-voice-status" role="status"></p>
        <ul class="as-list" id="as-voices"></ul>
      </div>
      <div class="nx-card">
        <h3 class="nx-h"><i class="nx-dot" style="background:#AB47BC"></i>أدوات MCP الخارجية <span class="nx-tag" id="as-mcp-count"></span></h3>
        <p class="as-warn">أضف فقط خادم MCP تثق به: يعمل ببرنامج على جهازك وبصلاحيات حسابك. كل أداة تبدأ معطلة ولا تعمل حتى تفعّلها بنفسك.</p>
        <form class="as-form" id="as-mcp-form"><input class="as-input as-mono" id="as-mcp-name" maxlength="32" placeholder="name" aria-label="اسم الخادم" style="max-width:130px"><input class="as-input as-mono" id="as-mcp-command" placeholder="npx -y @modelcontextprotocol/server-filesystem /home/me/Documents" aria-label="أمر تشغيل الخادم"><button class="as-btn as-primary" type="submit">إضافة</button></form>
        <p class="as-status" id="as-mcp-status" role="status"></p>
        <div id="as-mcp"></div>
      </div>
    </div>`;
    const examples=[['ما الطقس اليوم؟'],['ذكرني بعد 10 دقائق أن أشرب الماء'],['اضبط مؤقت 25 دقيقة'],['كم الساعة في لندن؟'],['ما تاريخ اليوم؟'],['احسب 15% من 2400'],['ما الأعمال غير المكتملة؟'],['تذكر أنني أفضّل الردود المختصرة'],['ماذا تتذكر عني؟'],['افتح يوتيوب'],['برمج لي موقع سيرة ذاتية عربي']];
    for(const [text] of examples){const b=document.createElement('button');b.type='button';b.className='as-chip';b.dir='auto';b.textContent=text;b.onclick=()=>{showPage('chat');setTimeout(()=>window.NeuraAssistant.ask(text),60);};$a('as-examples').append(b);}
    $a('as-rem-form').onsubmit=async e=>{e.preventDefault();const input=$a('as-rem-input');let text=input.value.trim();if(!text)return;
      if(!/^(?:ذكرني|ذكّرني|نبهني|فكرني|اضبط|مؤقت|remind|set)/i.test(text))text='ذكرني '+text;
      if(await quick(text,'as-rem-status',loadReminders))input.value='';};
    $a('as-mem-form').onsubmit=async e=>{e.preventDefault();const input=$a('as-mem-input');if(!input.value.trim())return;
      try{const saved=await send('/assistant/memories','POST',{text:input.value});status('as-mem-status',saved.duplicate?'محفوظة مسبقًا.':'حُفظت.');input.value='';loadMemories();}catch(e){status('as-mem-status',e.message,1);}};
    $a('as-export').onclick=async()=>{try{const data=await call('/assistant/memories/export');const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));
      const a=document.createElement('a');a.href=url;a.download='neura-memories.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);}catch(e){status('as-mem-status',e.message,1);}};
    $a('as-import').onchange=async e=>{const file=e.target.files[0];e.target.value='';if(!file)return;
      try{const result=await send('/assistant/memories/import','POST',JSON.parse(await file.text()));status('as-mem-status','أُضيفت '+result.added+'، وتُجوهلت '+result.skipped+' مكررة.');loadMemories();}catch(err){status('as-mem-status',err instanceof SyntaxError?'الملف ليس JSON صالحًا.':err.message,1);}};
    $a('as-kb-file').onchange=async e=>{const files=[...e.target.files];e.target.value='';let ok=0;
      for(const f of files){if(f.size>2000000){status('as-kb-status',f.name+': أكبر من 2 MB',1);continue;}status('as-kb-status','أفهرس '+f.name+'…');
        try{const r=await send('/assistant/knowledge','POST',{filename:f.name,text:await f.text()});ok++;status('as-kb-status',r.duplicate?f.name+' موجود مسبقًا.':'أُضيف '+f.name+' ('+r.chunks+' مقطع).');}catch(err){status('as-kb-status',f.name+': '+err.message,1);}}
      loadKnowledge();};
    $a('as-ics-export').onclick=async()=>{try{const r=await api('/assistant/reminders.ics');if(!r.ok)throw Error('تعذر التصدير');const url=URL.createObjectURL(await r.blob());
      const a=document.createElement('a');a.href=url;a.download='neura-reminders.ics';a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);status('as-rem-status','صُدّرت التذكيرات؛ استيرادها مرة أخرى في تطبيق التقويم يحدّث نفس المواعيد ولا يكررها.');}catch(e){status('as-rem-status',e.message,1);}};
    $a('as-ics-import').onchange=async e=>{const file=e.target.files[0];e.target.value='';if(!file)return;
      try{const r=await send('/assistant/calendar/import','POST',{ics:await file.text()});const s=r.skipped;
        status('as-rem-status','أُضيف '+r.created.length+' تذكير'+(r.already_imported?'، و'+r.already_imported+' مستورد سابقًا':'')+(r.past?'، وتُجوهل '+r.past+' موعد فات':'')+(s.recurring?'، و'+s.recurring+' متكرر لم أوسّعه':'')+(s.all_day?'، و'+s.all_day+' ليوم كامل بلا وقت':'')+'.');loadReminders();}
      catch(err){status('as-rem-status',err.message,1);}};
    $a('as-clear').onclick=async()=>{if(!confirm('حذف كل ما يتذكره Neura عنك؟ لا يمكن التراجع.'))return;try{await send('/assistant/memories','DELETE');loadMemories();status('as-mem-status','حُذفت كل الذاكرة.');}catch(e){status('as-mem-status',e.message,1);}};
    const savePref=async values=>{try{prefs=await send('/assistant/preferences','PUT',values);status('as-pref-status','حُفظ الإعداد.');}catch(e){status('as-pref-status',e.message,1);loadPrefs();}};
    $a('as-city').onchange=e=>e.target.value.trim()&&savePref({city:e.target.value.trim()});
    $a('as-persona').onchange=e=>savePref({persona:e.target.value});
    for(const key of ['desktop_notifications','speak_reminders','use_memory_in_chat'])$a('as-'+key).onchange=e=>savePref({[key]:e.target.checked});
  }

  async function loadKnowledge(){
    const list=$a('as-kb');if(!list)return;
    try{const data=await call('/assistant/knowledge');list.replaceChildren();$a('as-kb-count').textContent=data.documents.length?String(data.documents.length):'';
      if(!data.available)status('as-kb-status','نموذج التضمين غير موجود في مجلد النماذج؛ المعرفة غير متاحة.',1);
      if(!data.documents.length){list.innerHTML='<li class="nx-empty">لا مستندات بعد.</li>';return;}
      for(const d of data.documents)list.append(row(d.title,d.chunks+' مقطع · '+Math.round(d.chars/1000)+' ألف حرف',[['حذف',async()=>{try{await send('/assistant/knowledge/'+d.id,'DELETE');loadKnowledge();}catch(e){status('as-kb-status',e.message,1);}},true]]));}
    catch(e){list.innerHTML='<li class="nx-empty">'+esc(e.message)+'</li>';}
  }
  /* N089: compare local voices with the same sentence and measured synthesis time; keep the chosen one. */
  async function loadVoices(){
    const list=$a('as-voices');if(!list)return;
    try{const data=await call('/voice/voices');const text=$a('as-voice-text');if(!text.value)text.value=data.sample_text;list.replaceChildren();
      if(!data.engine_available||!data.voices.length){list.innerHTML='<li class="nx-empty">لا يوجد محرك Piper أو أصوات محلية في ~/.local/share/neura-ai/voice؛ النطق يستخدم صوت النظام المحلي إن وجد.</li>';return;}
      for(const v of data.voices){const lang=v.language.startsWith('ar')?'ar':v.language.startsWith('en')?'en':'';
        const item=row(v.id,(v.selected?'✓ المستخدم الآن · ':'')+(v.language||'لغة غير معلنة')+' · جودة '+(v.quality||'؟')+' · '+v.size_mb+' MB',[
          ['استمع',async()=>{if(!lang){status('as-voice-status','لغة الصوت غير مدعومة للمعاينة.',1);return;}status('as-voice-status','أولّد العينة بصوت '+v.id+'…');const t=performance.now();
            try{const r=await api('/tts',{method:'POST',body:JSON.stringify({text:$a('as-voice-text').value||data.sample_text,lang,voice:v.id})});
              if(!r.ok){let m='';try{m=(await r.json()).error.message}catch(_){}throw Error(m||'تعذر توليد العينة');}
              const total=Math.round(performance.now()-t),synth=r.headers.get('X-Neura-Synth-Ms'),url=URL.createObjectURL(await r.blob()),audio=new Audio(url);
              audio.onloadedmetadata=()=>{item.querySelector('.as-meta').textContent+=' · توليد '+(synth||total)+' ms · مدة '+audio.duration.toFixed(1)+' ث';};
              audio.onended=()=>URL.revokeObjectURL(url);await audio.play();status('as-voice-status','زمن التوليد المقاس: '+(synth||total)+' ms (الإجمالي مع النقل '+total+' ms).');}
            catch(e){status('as-voice-status',e.message,1);}}],
          ...(v.selected?[]:[['اختيار',async()=>{try{await send('/voice/select','POST',{voice:v.id});status('as-voice-status','اخترت '+v.id+' لصوت Neura.');loadVoices();}catch(e){status('as-voice-status',e.message,1);}}]])]);
        list.append(item);}
    }catch(e){list.innerHTML='<li class="nx-empty">'+esc(e.message)+'</li>';}
  }

  /* N079: user-configured MCP servers; tools are enabled one by one and run only on an explicit click. */
  function words(command){return (command.match(/"[^"]*"|'[^']*'|\S+/g)||[]).map(w=>w.replace(/^["']|["']$/g,''));}
  async function loadMcp(){
    const box=$a('as-mcp');if(!box)return;
    try{const data=await call('/mcp');box.replaceChildren();$a('as-mcp-count').textContent=data.servers.length?String(data.servers.length):'';
      if(!data.servers.length){box.innerHTML='<p class="nx-empty">لا خوادم MCP. لا يُضاف خادم إلا منك من هنا.</p>';return;}
      for(const server of data.servers){
        const card=document.createElement('div');card.className='as-tool';
        card.innerHTML='<div class="as-row" style="align-items:center;justify-content:space-between;margin:0"><b class="as-mono">'+esc(server.name)+'</b><span class="as-meta">'+(server.running?'متصل':'غير متصل')+' · مهلة '+server.timeout_s+' ث</span></div><p class="as-mono">'+esc(server.command.join(' '))+'</p>';
        const actions=document.createElement('div');actions.className='as-row';actions.style.marginTop='6px';
        const connect=document.createElement('button');connect.type='button';connect.className='as-btn';connect.textContent=server.running?'إعادة الاتصال':'اتصال وعرض الأدوات';
        connect.onclick=async()=>{status('as-mcp-status','أتصل بـ '+server.name+'…');try{await send('/mcp/servers/'+server.name+'/connect','POST');status('as-mcp-status','اتصلت بـ '+server.name+'.');loadMcp();}catch(e){status('as-mcp-status',e.message,1);}};
        const remove=document.createElement('button');remove.type='button';remove.className='as-btn as-danger';remove.textContent='حذف الخادم';
        remove.onclick=async()=>{if(!confirm('حذف خادم MCP «'+server.name+'»؟'))return;try{await send('/mcp/servers/'+server.name,'DELETE');loadMcp();}catch(e){status('as-mcp-status',e.message,1);}};
        actions.append(connect,remove);card.append(actions);
        const tools=document.createElement('div');tools.className='as-tools';
        if(!server.tools.length&&server.enabled_tools.length)tools.innerHTML='<p class="nx-sub">مفعّل: '+esc(server.enabled_tools.join('، '))+' — اتصل لعرض التفاصيل.</p>';
        for(const tool of server.tools){
          const t=document.createElement('div');t.className='as-tool';
          t.innerHTML='<label class="as-check"><input type="checkbox"'+(tool.enabled?' checked':'')+'> <span class="as-mono">'+esc(tool.name)+'</span></label><p>'+esc(tool.description)+'</p>';
          t.querySelector('input').onchange=async e=>{try{await send('/mcp/servers/'+server.name+'/tools/'+encodeURIComponent(tool.name),'POST',{enabled:e.target.checked});loadMcp();}catch(err){status('as-mcp-status',err.message,1);}};
          if(tool.enabled){
            const args=document.createElement('textarea');args.className='as-input as-mono';args.rows=2;args.value='{}';args.setAttribute('aria-label','معاملات '+tool.name+' (JSON)');
            const run=document.createElement('button');run.type='button';run.className='as-btn as-primary';run.textContent='تشغيل';
            const out=document.createElement('pre');out.className='as-pre';out.hidden=true;
            run.onclick=async()=>{let parsed;try{parsed=JSON.parse(args.value||'{}');}catch(_){status('as-mcp-status','المعاملات ليست JSON صالحًا.',1);return;}
              run.disabled=true;try{const r=await send('/mcp/servers/'+server.name+'/call','POST',{tool:tool.name,arguments:parsed});out.hidden=false;out.textContent=(r.is_error?'⚠ الخادم أبلغ عن خطأ:\n':'')+r.text+(r.truncated?'\n… (اقتُطع)':'');}
              catch(e){out.hidden=false;out.textContent=e.message;}finally{run.disabled=false;}};
            t.append(args,run,out);}
          tools.append(t);}
        card.append(tools);box.append(card);}
    }catch(e){box.innerHTML='<p class="nx-empty">'+esc(e.message)+'</p>';}
  }
  function bindExtras(){
    const form=$a('as-mcp-form');if(!form||form.dataset.bound)return;form.dataset.bound='1';
    form.onsubmit=async e=>{e.preventDefault();const name=$a('as-mcp-name').value.trim(),command=words($a('as-mcp-command').value.trim());if(!name||!command.length)return;
      try{await send('/mcp/servers','POST',{name,command});$a('as-mcp-name').value='';$a('as-mcp-command').value='';status('as-mcp-status','أُضيف الخادم. اضغط «اتصال وعرض الأدوات» ثم فعّل ما تثق به.');loadMcp();}catch(err){status('as-mcp-status',err.message,1);}};
  }
  function refresh(){build();bindExtras();loadReminders();loadMemories();loadPrefs();loadKnowledge();loadVoices();loadMcp();}

  // In-chat reminder delivery --------------------------------------------------------------
  const KEY='neura.assistant.lastEvent';
  let last=null,polling=false;
  function stored(){try{const v=localStorage.getItem(KEY);return v===null?null:Number(v);}catch(_){return null;}}
  function remember(seq){last=seq;try{localStorage.setItem(KEY,String(seq));}catch(_){}}
  async function deliver(event){
    if(event.kind!=='reminder')return;
    if(typeof setHas==='function'&&!document.body.classList.contains('has'))setHas(true);
    const text='⏰ '+event.text+(event.late?'\n(فات موعده أثناء إغلاق Neura: '+when(event.due,event.timezone)+')':'');
    const card=bubble('n','Neura [تذكير]','#FFCA28','zap',text);card.d.dataset.reminderId=event.id;sc(true);
    if(typeof hist!=='undefined'){hist.push({role:'assistant',content:'تذكير: '+event.text});}
    if(prefs.speak_reminders&&typeof speak==='function'&&!busy){try{await speak('تذكير: '+event.text,true);}catch(_){}}
    if(page==='assistant')loadReminders();
  }
  async function poll(){
    if(polling||!TOKEN)return;polling=true;
    try{
      if(last===null){
        const saved=stored();
        if(saved===null){
          // First run on this profile: show only reminders fired in the last 15 minutes.
          const all=await call('/assistant/events?after=0');const cutoff=Date.now()/1000-900;
          for(const e of all.events)if((e.fired||0)>=cutoff)await deliver(e);
          remember(all.last);return;
        }
        last=saved;
      }
      const data=await call('/assistant/events?after='+last);
      for(const e of data.events){await deliver(e);remember(e.seq);}
      if(data.last<last)remember(data.last);   // a reset data directory
    }catch(_){/* offline: retry on next tick */}
    finally{polling=false;}
  }
  async function ask(text){$a('in').value='';await window.sendMessage?.(text);}
  loadPrefs();setTimeout(poll,1500);setInterval(poll,10000);
  window.NeuraAssistant={refresh,poll,ask};
})();
