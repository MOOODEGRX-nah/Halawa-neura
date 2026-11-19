/* Design studio (P05 UI / P06 graphic). Editable scene nodes, layers, properties, undo/redo,
   revisioned autosave, scoped AI edits, site/PNG/SVG export. Writes only through /designs. */
(()=>{
  const $s=id=>document.getElementById(id);
  const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  async function call(path,method='GET',body){const r=await api(path,{method,...(body===undefined?{}:{body:JSON.stringify(body)})});let j={};try{j=await r.json();}catch(_){}if(!r.ok){const e=Error(j.error?.message||j.detail||'تعذر تنفيذ الطلب');e.status=r.status;throw e;}return j;}
  const NODE_ID=()=>'n_'+crypto.randomUUID().replaceAll('-','').slice(0,12);
  const FRAMES={desktop:[1280,800],tablet:[834,1112],mobile:[390,844],post:[1080,1080],story:[1080,1920],poster:[1240,1754],cv:[1240,1754],banner:[1500,500]};
  const FRAME_LABELS={desktop:'كمبيوتر 1280',tablet:'تابلت 834',mobile:'جوال 390',post:'منشور 1080²',story:'ستوري 1080×1920',poster:'ملصق A4',cv:'سيرة A4',banner:'غلاف 1500×500',custom:'مخصص'};
  const TYPES={text:'نص',rect:'مستطيل',ellipse:'دائرة',button:'زر',image:'صورة'};
  let design=null,doc=null,revision=0,selected=[],past=[],future=[],saveTimer=0,saving=false,dirty=false,scale=1,templates={};

  function status(text,bad){const el=$s('st-status');if(el){el.textContent=text;el.dataset.bad=bad?'1':'';}}
  function snapshot(){return JSON.stringify(doc);}
  function change(mutator,{record=true}={}){if(record){past.push(snapshot());if(past.length>100)past.shift();future=[];}mutator();dirty=true;render();scheduleSave();}
  function scheduleSave(){clearTimeout(saveTimer);status('تغييرات غير محفوظة…');saveTimer=setTimeout(save,1200);}
  async function save(){
    if(!design||!dirty||saving)return;saving=true;const sent=snapshot();
    try{const r=await call('/designs/'+design.id,'PUT',{base_revision:revision,document:doc});revision=r.revision;design=r;if(snapshot()===sent)dirty=false;status('محفوظ · المراجعة '+revision);}
    catch(e){status(e.status===409?'تغير التصميم في مكان آخر؛ أعد فتحه قبل الحفظ.':'لم يُحفظ: '+e.message,1);}
    finally{saving=false;if(dirty)scheduleSave();}
  }
  const nodeById=id=>doc.nodes.find(n=>n.id===id);
  const sel=()=>selected.map(nodeById).filter(Boolean);

  // Rendering --------------------------------------------------------------------------------
  function fit(){const stage=$s('st-stage'),sizer=$s('st-sizer'),canvas=sizer?.parentElement;if(!stage||!doc||!canvas)return;
    const width=canvas.clientWidth-40,height=canvas.clientHeight-40;scale=Math.min(1,width/doc.width,height/doc.height);if(!(scale>0))scale=.25;
    stage.style.width=doc.width+'px';stage.style.height=doc.height+'px';stage.style.transform='scale('+scale+')';
    sizer.style.width=Math.round(doc.width*scale)+'px';sizer.style.height=Math.round(doc.height*scale)+'px';$s('st-zoom').textContent=Math.round(scale*100)+'%';}
  function styleFor(n){const s={left:n.x+'px',top:n.y+'px',width:n.w+'px',height:n.h+'px',opacity:n.opacity,transform:n.rotation?'rotate('+n.rotation+'deg)':'',borderRadius:n.type==='ellipse'?'50%':n.radius+'px',
      background:(n.type==='text'?n.bg:n.bg)||'transparent',border:n.border&&n.borderWidth?n.borderWidth+'px solid '+n.border:'none'};
    if(n.type==='text'||n.type==='button')Object.assign(s,{color:n.color,fontSize:n.fontSize+'px',fontWeight:n.fontWeight,textAlign:n.align,lineHeight:n.lineHeight});return s;}
  function render(){
    if(!doc)return;const stage=$s('st-stage');stage.replaceChildren();stage.style.background=doc.background;
    for(const n of doc.nodes){if(n.hidden)continue;const el=document.createElement('div');el.className='st-node st-'+n.type+(selected.includes(n.id)?' st-selected':'')+(n.locked?' st-locked':'');el.dataset.id=n.id;
      Object.assign(el.style,styleFor(n));
      if(n.type==='text'||n.type==='button'){const t=document.createElement('span');t.dir='auto';t.textContent=n.text;el.append(t);}
      if(n.type==='image'&&n.src){const img=document.createElement('img');img.src=n.src;img.alt=n.name||'صورة';img.draggable=false;el.append(img);}
      if(selected.length===1&&selected[0]===n.id&&!n.locked){const h=document.createElement('i');h.className='st-handle';h.dataset.handle='1';el.append(h);}
      stage.append(el);}
    layers();inspector();fit();
    $s('st-title').value=doc.title;$s('st-frame').value=doc.frame;$s('st-bg').value=doc.background;
    $s('st-undo').disabled=!past.length;$s('st-redo').disabled=!future.length;$s('st-site').hidden=doc.kind!=='ui';
    $s('st-ai-target').textContent=selected.length?('العناصر المحددة: '+sel().map(n=>n.name||TYPES[n.type]).join('، ')):'حدد عنصرًا أو أكثر (Shift للتحديد المتعدد).';
  }
  function layers(){
    const list=$s('st-layers');list.replaceChildren();
    [...doc.nodes].reverse().forEach(n=>{const li=document.createElement('li');li.className='st-layer'+(selected.includes(n.id)?' st-on':'');li.tabIndex=0;
      li.innerHTML='<span class="st-lname" dir="auto"></span><span class="st-lact"></span>';li.querySelector('.st-lname').textContent=(n.hidden?'🚫 ':'')+(n.locked?'🔒 ':'')+(n.name||TYPES[n.type]);
      li.onclick=e=>{if(e.target.closest('button'))return;select(n.id,e.shiftKey);};li.onkeydown=e=>{if(e.key==='Enter')select(n.id,e.shiftKey);};
      const act=li.querySelector('.st-lact');
      for(const [label,title,fn] of [['▲','للأمام',()=>move(n.id,1)],['▼','للخلف',()=>move(n.id,-1)],[n.hidden?'👁':'—',n.hidden?'إظهار':'إخفاء',()=>change(()=>{n.hidden=!n.hidden;})],['🔒','قفل/فتح',()=>change(()=>{n.locked=!n.locked;})],['✕','حذف',()=>remove([n.id])]]){
        const b=document.createElement('button');b.type='button';b.className='st-mini';b.textContent=label;b.title=title;b.setAttribute('aria-label',title+' '+(n.name||''));b.onclick=fn;act.append(b);}
      list.append(li);});
    if(!doc.nodes.length)list.innerHTML='<li class="nx-empty">لا عناصر بعد؛ أضف من شريط الأدوات.</li>';
  }
  const FIELDS=[['name','الاسم','text'],['text','النص','textarea',['text','button']],['x','X','number'],['y','Y','number'],['w','العرض','number'],['h','الارتفاع','number'],['rotation','الدوران','number'],
    ['fontSize','حجم الخط','number',['text','button']],['fontWeight','سماكة الخط','select',['text','button'],[400,500,600,700,800]],['align','المحاذاة','select',['text','button'],['right','center','left']],
    ['lineHeight','تباعد الأسطر','number',['text','button']],['color','لون النص','color',['text','button']],['bg','لون الخلفية','color'],['radius','الزوايا','number'],['border','لون الإطار','color'],['borderWidth','سماكة الإطار','number'],['opacity','الشفافية','number']];
  function inspector(){
    const box=$s('st-props');box.replaceChildren();const items=sel();
    if(items.length!==1){box.innerHTML='<p class="nx-sub">'+(items.length?'حددت '+items.length+' عناصر؛ يمكنك نقلها أو حذفها أو تعديلها بالذكاء الاصطناعي.':'حدد عنصرًا لتعديل خصائصه.')+'</p>';return;}
    const n=items[0];
    for(const [key,label,kind,types,options] of FIELDS){if(types&&!types.includes(n.type))continue;
      const row=document.createElement('label');row.className='st-field';row.append(label);let input;
      if(kind==='textarea'){input=document.createElement('textarea');input.rows=3;input.dir='auto';}
      else if(kind==='select'){input=document.createElement('select');for(const o of options){const op=document.createElement('option');op.value=o;op.textContent={right:'يمين',center:'وسط',left:'يسار'}[o]||o;input.append(op);}}
      else{input=document.createElement('input');input.type=kind==='color'?'color':kind;if(kind==='number'){input.step=key==='opacity'||key==='lineHeight'?'0.05':'1';}}
      input.className='st-input';input.value=n[key]??(kind==='color'?'#ffffff':'');
      input.onchange=()=>{let v=input.value;if(kind==='number')v=Number(v);if(key==='fontWeight')v=Number(v);if(kind==='number'&&!Number.isFinite(v))return;change(()=>{n[key]=v;});};
      row.append(input);
      if(kind==='color'&&key!=='color'){const clear=document.createElement('button');clear.type='button';clear.className='st-mini';clear.textContent='بلا';clear.title='إزالة اللون';clear.onclick=()=>change(()=>{n[key]=null;});row.append(clear);}
      box.append(row);}
    if(n.type==='image'){const row=document.createElement('label');row.className='st-field';row.append('استبدال الصورة');const f=document.createElement('input');f.type='file';f.accept='image/png,image/jpeg,image/webp';f.onchange=()=>readImage(f.files[0],src=>change(()=>{n.src=src;}));row.append(f);box.append(row);}
  }

  // Editing ----------------------------------------------------------------------------------
  function select(id,add){if(!id){selected=[];}else if(add){selected=selected.includes(id)?selected.filter(x=>x!==id):[...selected,id];}else selected=[id];render();}
  function move(id,delta){change(()=>{const i=doc.nodes.findIndex(n=>n.id===id),j=Math.max(0,Math.min(doc.nodes.length-1,i+delta));const [n]=doc.nodes.splice(i,1);doc.nodes.splice(j,0,n);});}
  function remove(ids){change(()=>{doc.nodes=doc.nodes.filter(n=>!ids.includes(n.id));selected=selected.filter(x=>!ids.includes(x));});}
  function duplicate(){const items=sel();if(!items.length)return;change(()=>{const copies=items.map(n=>({...JSON.parse(JSON.stringify(n)),id:NODE_ID(),x:n.x+20,y:n.y+20,name:(n.name||TYPES[n.type])+' (نسخة)'}));doc.nodes.push(...copies);selected=copies.map(c=>c.id);});}
  function add(type,extra={}){
    const w=type==='text'?Math.min(500,doc.width*.6):type==='button'?220:Math.min(300,doc.width*.4),h=type==='text'?80:type==='button'?60:Math.min(200,doc.height*.3);
    const n={id:NODE_ID(),type,name:TYPES[type]+' '+(doc.nodes.length+1),x:Math.round((doc.width-w)/2),y:Math.round((doc.height-h)/2),w:Math.round(w),h:Math.round(h),rotation:0,text:type==='text'?'نص جديد':type==='button'?'زر':'',
      color:type==='button'?'#ffffff':'#1a1a1a',bg:type==='button'?'#0b4f8a':type==='rect'||type==='ellipse'?'#d9e2ec':null,border:null,borderWidth:0,radius:type==='button'?10:0,opacity:1,
      fontSize:type==='button'?22:Math.round(Math.max(18,doc.width/30)),fontWeight:type==='button'?700:400,align:type==='button'?'center':'right',lineHeight:1.5,src:null,hidden:false,locked:false,...extra};
    change(()=>{doc.nodes.push(n);selected=[n.id];});
  }
  function readImage(file,done){if(!file)return;if(file.size>3000000){status('الحد الأقصى للصورة 3 MB',1);return;}const r=new FileReader();r.onload=()=>done(r.result);r.readAsDataURL(file);}
  function undo(){if(!past.length)return;future.push(snapshot());doc=JSON.parse(past.pop());selected=selected.filter(nodeById);dirty=true;render();scheduleSave();}
  function redo(){if(!future.length)return;past.push(snapshot());doc=JSON.parse(future.pop());dirty=true;render();scheduleSave();}

  let drag=null;
  function pointerDown(e){
    const el=e.target.closest('.st-node');if(!el){if(e.target.id==='st-stage')select(null);return;}
    const n=nodeById(el.dataset.id);if(!selected.includes(n.id)||e.shiftKey)select(n.id,e.shiftKey);if(n.locked)return;
    const items=sel().filter(x=>!x.locked);drag={x:e.clientX,y:e.clientY,resize:!!e.target.dataset.handle,start:items.map(x=>({n:x,x:x.x,y:x.y,w:x.w,h:x.h})),before:snapshot(),moved:false};
    e.target.setPointerCapture?.(e.pointerId);e.preventDefault();
  }
  function pointerMove(e){
    if(!drag)return;const dx=(e.clientX-drag.x)/scale,dy=(e.clientY-drag.y)/scale;if(Math.abs(dx)+Math.abs(dy)>1)drag.moved=true;
    for(const s of drag.start){if(drag.resize){s.n.w=Math.max(4,Math.round(s.w+dx));s.n.h=Math.max(4,Math.round(s.h+dy));}else{s.n.x=Math.round(s.x+dx);s.n.y=Math.round(s.y+dy);}}
    for(const s of drag.start){const el=document.querySelector('.st-node[data-id="'+s.n.id+'"]');if(el)Object.assign(el.style,{left:s.n.x+'px',top:s.n.y+'px',width:s.n.w+'px',height:s.n.h+'px'});}
  }
  function pointerUp(){if(!drag)return;const d=drag;drag=null;if(d.moved){past.push(d.before);future=[];dirty=true;render();scheduleSave();}}
  function keys(e){
    if(page!=='studio'||!doc||/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName))return;
    if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();e.shiftKey?redo():undo();return;}
    if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='y'){e.preventDefault();redo();return;}
    if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='d'){e.preventDefault();duplicate();return;}
    if((e.key==='Delete'||e.key==='Backspace')&&selected.length){e.preventDefault();remove([...selected]);return;}
    const step=e.shiftKey?10:1,dir={ArrowLeft:[-step,0],ArrowRight:[step,0],ArrowUp:[0,-step],ArrowDown:[0,step]}[e.key];
    if(dir&&selected.length){e.preventDefault();change(()=>{for(const n of sel())if(!n.locked){n.x+=dir[0];n.y+=dir[1];}});}
    if(e.key==='Escape')select(null);
  }

  // Exports ----------------------------------------------------------------------------------
  function download(blob,name){const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),3000);}
  function safeName(){return (doc.title||'design').replace(/[\\/:*?"<>|]+/g,'-').slice(0,60);}
  function wrap(ctx,text,width){const lines=[];for(const para of String(text).split('\n')){let line='';for(const word of para.split(/\s+/)){const t=line?line+' '+word:word;if(ctx.measureText(t).width>width&&line){lines.push(line);line=word;}else line=t;}lines.push(line);}return lines;}
  function roundRect(ctx,n){ctx.beginPath();if(n.type==='ellipse')ctx.ellipse(n.x+n.w/2,n.y+n.h/2,n.w/2,n.h/2,0,0,Math.PI*2);else ctx.roundRect(n.x,n.y,n.w,n.h,Math.min(n.radius,n.w/2,n.h/2));}
  async function png(){
    const c=document.createElement('canvas');c.width=doc.width;c.height=doc.height;const ctx=c.getContext('2d');ctx.fillStyle=doc.background;ctx.fillRect(0,0,c.width,c.height);
    const family=getComputedStyle(document.body).fontFamily;
    for(const n of doc.nodes){if(n.hidden)continue;ctx.save();ctx.globalAlpha=n.opacity;if(n.rotation){ctx.translate(n.x+n.w/2,n.y+n.h/2);ctx.rotate(n.rotation*Math.PI/180);ctx.translate(-(n.x+n.w/2),-(n.y+n.h/2));}
      if(n.bg){roundRect(ctx,n);ctx.fillStyle=n.bg;ctx.fill();}
      if(n.border&&n.borderWidth){roundRect(ctx,n);ctx.lineWidth=n.borderWidth;ctx.strokeStyle=n.border;ctx.stroke();}
      if(n.type==='image'&&n.src){const img=new Image();img.src=n.src;await img.decode();ctx.save();roundRect(ctx,n);ctx.clip();const r=Math.max(n.w/img.width,n.h/img.height);ctx.drawImage(img,n.x+(n.w-img.width*r)/2,n.y+(n.h-img.height*r)/2,img.width*r,img.height*r);ctx.restore();}
      if((n.type==='text'||n.type==='button')&&n.text){ctx.font=n.fontWeight+' '+n.fontSize+'px '+family;ctx.fillStyle=n.color;ctx.direction=/[؀-ۿ]/.test(n.text)?'rtl':'ltr';ctx.textBaseline='middle';
        const lines=wrap(ctx,n.text,n.w-8),lh=n.fontSize*n.lineHeight,top=n.type==='button'?n.y+(n.h-lines.length*lh)/2:n.y;
        ctx.textAlign=n.align==='center'?'center':n.align==='left'?'left':'right';const x=n.align==='center'?n.x+n.w/2:n.align==='left'?n.x+4:n.x+n.w-4;
        lines.forEach((l,i)=>{if(top+(i+1)*lh<=n.y+n.h+lh*.2)ctx.fillText(l,x,top+i*lh+lh/2);});}
      ctx.restore();}
    c.toBlob(b=>{download(b,safeName()+'.png');status('صُدّرت صورة PNG ('+doc.width+'×'+doc.height+').');},'image/png');
  }
  function svg(){
    const body=doc.nodes.filter(n=>!n.hidden).map(n=>{const st=styleFor(n);const css=Object.entries(st).filter(([,v])=>v!==''&&v!=null).map(([k,v])=>k.replace(/[A-Z]/g,m=>'-'+m.toLowerCase())+':'+v).join(';');
      const inner=n.type==='image'&&n.src?'<img src="'+n.src+'" style="width:100%;height:100%;object-fit:cover"/>':(n.type==='text'||n.type==='button')?'<span dir="auto">'+esc(n.text).replace(/\n/g,'<br/>')+'</span>':'';
      return '<div xmlns="http://www.w3.org/1999/xhtml" style="position:absolute;box-sizing:border-box;overflow:hidden;display:flex;flex-direction:column;justify-content:'+(n.type==='button'?'center':'flex-start')+';'+css+'">'+inner+'</div>';}).join('');
    const out='<svg xmlns="http://www.w3.org/2000/svg" width="'+doc.width+'" height="'+doc.height+'" viewBox="0 0 '+doc.width+' '+doc.height+'"><rect width="100%" height="100%" fill="'+doc.background+'"/><foreignObject width="100%" height="100%"><div xmlns="http://www.w3.org/1999/xhtml" dir="rtl" style="position:relative;width:'+doc.width+'px;height:'+doc.height+'px;font-family:sans-serif">'+body+'</div></foreignObject></svg>';
    download(new Blob([out],{type:'image/svg+xml'}),safeName()+'.svg');status('صُدّر ملف SVG.');
  }
  async function exportSite(newProject){
    await flush();
    try{const r=await call('/designs/'+design.id+'/export-site','POST',{base_revision:revision,new_project:!!newProject});status(r.message);
      if(window.NeuraWorkspace?.openForEdit&&confirm('صُدّر الموقع. هل تريد فتحه في مساحة المبرمج الآن؟'))await window.NeuraWorkspace.openForEdit(r.project_id,'');}
    catch(e){if(e.status===409&&!newProject&&confirm(e.message+'\n\nهل تريد التصدير كمشروع جديد بدلًا من ذلك؟'))return exportSite(true);status(e.message,1);}
  }
  async function flush(){clearTimeout(saveTimer);if(dirty)await save();}
  async function ai(){
    const instruction=$s('st-ai-text').value.trim();if(!instruction||!selected.length){status('حدد عنصرًا واكتب التعديل المطلوب.',1);return;}
    await flush();const button=$s('st-ai-go');button.disabled=true;status('يعدّل النموذج المحلي العناصر المحددة فقط…');
    try{const before=snapshot();const r=await call('/designs/'+design.id+'/ai','POST',{base_revision:revision,node_ids:selected,instruction});
      past.push(before);future=[];design=r;doc=r.document;revision=r.revision;dirty=false;render();status('عُدّل '+r.changed_nodes.length+' عنصر'+(r.note?': '+r.note:'')+' · يمكنك التراجع.');$s('st-ai-text').value='';}
    catch(e){status(e.message,1);}finally{button.disabled=false;}
  }

  // Documents --------------------------------------------------------------------------------
  async function open(id){await flush();const d=await call('/designs/'+id);design=d;doc=d.document;revision=d.revision;past=[];future=[];selected=[];dirty=false;render();status('المراجعة '+revision);try{localStorage.setItem('neura.studio.last',id);}catch(_){}}
  async function refreshList(selectId){
    const data=await call('/designs');templates=data.templates;const pick=$s('st-open');pick.replaceChildren();
    for(const d of data.designs){const o=document.createElement('option');o.value=d.id;o.textContent=d.title+' · '+(d.kind==='ui'?'واجهة':'جرافيك');pick.append(o);}
    const tpl=$s('st-template');if(!tpl.options.length)for(const [k,v] of Object.entries(templates)){const o=document.createElement('option');o.value=k;o.textContent=v;tpl.append(o);}
    let last=selectId;if(!last){try{last=localStorage.getItem('neura.studio.last');}catch(_){}}
    const target=data.designs.find(d=>d.id===last)||data.designs[0];
    if(target){pick.value=target.id;await open(target.id);}else{$s('st-empty').hidden=false;$s('st-editor').hidden=true;return;}
    $s('st-empty').hidden=true;$s('st-editor').hidden=false;
  }
  async function create(){const r=await call('/designs','POST',{template:$s('st-template').value});await refreshList(r.id);}

  function build(){
    const page=$s('pg-studio');if(!page||page.dataset.built)return;page.dataset.built='1';
    page.innerHTML=`<div class="st-wrap">
      <div class="st-bar nx-card">
        <select id="st-open" class="st-input" aria-label="التصاميم المحفوظة"></select>
        <select id="st-template" class="st-input" aria-label="قالب جديد"></select><button type="button" class="as-btn as-primary" id="st-new">تصميم جديد</button>
        <span class="st-sep"></span>
        <button type="button" class="as-btn" id="st-undo" title="تراجع Ctrl+Z">↶ تراجع</button><button type="button" class="as-btn" id="st-redo" title="إعادة Ctrl+Y">↷ إعادة</button>
        <span class="st-sep"></span>
        <button type="button" class="as-btn" id="st-site">تصدير كموقع</button><button type="button" class="as-btn" id="st-png">PNG</button><button type="button" class="as-btn" id="st-svg">SVG</button>
        <button type="button" class="as-btn" id="st-history">المراجعات</button><button type="button" class="as-btn as-danger" id="st-delete">حذف</button>
        <span class="st-status" id="st-status" role="status"></span>
      </div>
      <div id="st-empty" class="nx-card" hidden><p class="nx-p">لا توجد تصاميم بعد. اختر قالبًا ثم «تصميم جديد»: صفحة تعريفية أو شاشة جوال للواجهات، أو منشور وستوري وملصق وسيرة ذاتية للجرافيك.</p></div>
      <div id="st-editor" class="st-editor" hidden>
        <aside class="st-tools nx-card" aria-label="الأدوات">
          <button type="button" class="as-btn" data-add="text">＋ نص</button><button type="button" class="as-btn" data-add="rect">＋ مستطيل</button><button type="button" class="as-btn" data-add="ellipse">＋ دائرة</button>
          <button type="button" class="as-btn" data-add="button">＋ زر</button><label class="as-btn" for="st-image">＋ صورة</label><input id="st-image" type="file" accept="image/png,image/jpeg,image/webp" hidden>
          <button type="button" class="as-btn" id="st-dup" title="Ctrl+D">نسخ</button>
          <label class="st-field">العنوان<input id="st-title" class="st-input" dir="auto" maxlength="120"></label>
          <label class="st-field">المقاس<select id="st-frame" class="st-input"></select></label>
          <label class="st-field">الخلفية<input id="st-bg" class="st-input" type="color"></label>
          <p class="nx-sub">اسحب لتحريك، والمربع الصغير لتغيير الحجم. الأسهم للتحريك الدقيق، Delete للحذف.</p>
        </aside>
        <div class="st-canvas" dir="ltr"><div class="st-zoom" id="st-zoom"></div><div class="st-sizer" id="st-sizer"><div id="st-stage" class="st-stage"></div></div></div>
        <aside class="st-side nx-card">
          <h3 class="nx-h">الطبقات</h3><ul id="st-layers" class="st-layers"></ul>
          <h3 class="nx-h">الخصائص</h3><div id="st-props" class="st-props"></div>
          <h3 class="nx-h">تعديل بالذكاء الاصطناعي</h3><p class="nx-sub" id="st-ai-target"></p>
          <textarea id="st-ai-text" class="st-input" rows="3" dir="auto" maxlength="1000" placeholder="مثال: اكتب عنوانًا جذابًا لمقهى واجعل اللون بنيًا داكنًا"></textarea>
          <button type="button" class="as-btn as-primary" id="st-ai-go">طبّق على المحدد</button>
        </aside>
      </div></div>`;
    for(const [k,v] of Object.entries(FRAME_LABELS)){const o=document.createElement('option');o.value=k;o.textContent=v;$s('st-frame').append(o);}
    $s('st-new').onclick=()=>create().catch(e=>status(e.message,1));
    $s('st-open').onchange=e=>open(e.target.value).catch(err=>status(err.message,1));
    $s('st-undo').onclick=undo;$s('st-redo').onclick=redo;$s('st-dup').onclick=duplicate;
    $s('st-png').onclick=()=>png().catch(e=>status('تعذر التصدير: '+e.message,1));$s('st-svg').onclick=svg;$s('st-site').onclick=()=>exportSite(false);
    $s('st-delete').onclick=async()=>{if(!design||!confirm('حذف التصميم «'+doc.title+'» وكل مراجعاته؟'))return;await call('/designs/'+design.id,'DELETE');design=null;doc=null;try{localStorage.removeItem('neura.studio.last');}catch(_){}refreshList();};
    $s('st-history').onclick=async()=>{await flush();const r=await call('/designs/'+design.id+'/revisions');const list=r.revisions.slice(0,15).map(x=>x.revision+' · '+new Date(x.created*1000).toLocaleString('ar-SA-u-nu-latn')+' · '+x.source).join('\n');
      const pick=prompt('المراجعات المحفوظة:\n'+list+'\n\nاكتب رقم المراجعة لاستعادتها (تُحفظ كمراجعة جديدة):');const n=Number(pick);if(!n)return;
      try{const d=await call('/designs/'+design.id+'/restore','POST',{revision:n,base_revision:revision});past.push(snapshot());design=d;doc=d.document;revision=d.revision;render();status('استُعيدت المراجعة '+n+' كمراجعة '+revision);}catch(e){status(e.message,1);}};
    page.querySelectorAll('[data-add]').forEach(b=>b.onclick=()=>add(b.dataset.add));
    $s('st-image').onchange=e=>{readImage(e.target.files[0],src=>{const img=new Image();img.onload=()=>{const r=Math.min(1,doc.width*.5/img.width,doc.height*.5/img.height);add('image',{src,w:Math.round(img.width*r),h:Math.round(img.height*r)});};img.src=src;});e.target.value='';};
    $s('st-title').onchange=e=>e.target.value.trim()&&change(()=>{doc.title=e.target.value.trim();});
    $s('st-bg').onchange=e=>change(()=>{doc.background=e.target.value;});
    $s('st-frame').onchange=e=>{const f=e.target.value;if(f==='custom'){const w=Number(prompt('العرض بالبكسل',doc.width)),h=Number(prompt('الارتفاع بالبكسل',doc.height));if(!(w>=100&&w<=4000&&h>=100&&h<=6000)){render();return;}change(()=>{doc.frame='custom';doc.width=Math.round(w);doc.height=Math.round(h);});return;}
      change(()=>{doc.frame=f;[doc.width,doc.height]=FRAMES[f];});};
    $s('st-ai-go').onclick=ai;
    const stage=$s('st-stage');stage.addEventListener('pointerdown',pointerDown);addEventListener('pointermove',pointerMove);addEventListener('pointerup',pointerUp);addEventListener('keydown',keys);addEventListener('resize',fit);
    window.addEventListener('beforeunload',()=>{if(dirty)save();});
  }
  async function refresh(){build();try{await refreshList();}catch(e){status(e.message,1);}}
  window.NeuraStudio={refresh,flush};
})();
