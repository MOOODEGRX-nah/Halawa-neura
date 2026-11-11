"""Actual Qt composer journeys; fixture and local inference explicitly separated."""
import argparse,json,os,subprocess,time,urllib.request,urllib.parse,hashlib
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--baseline',action='store_true')
p.add_argument('--real-model',action='store_true')
p.add_argument('--workflow',choices=['exact','preserve','plan','proposal','smoke','large','remove','compound','compound-clarify','resource-smoke','web-recipe'],default='exact')
p.add_argument('--seed-project',type=Path,help='Declared existing-project source JSON for large/edit-removal QA')
p.add_argument('--approval',choices=['نعم','فل تبرمج'],default='نعم')
p.add_argument('--login-request',default='أضف زر تسجيل دخول',help='Explicitly declared preservation journey variant')
p.add_argument('--theme-request',default='أضف الوضع الداكن إلى هذا المشروع',help='Explicitly declared preservation journey variant')
p.add_argument('--removed-feature',choices=['login','theme'],default='login',help='Declared expected removed feature for QA only')
p.add_argument('--compound-mode',choices=['add','keep'],default='keep',help='Independent declared compound expectation')
p.add_argument('--compound-request',default='احذف Login ولا تحذف الوضع الداكن')
p.add_argument('--remove-request',default='هل يمكنك إزالة زر تسجيل الدخول؟',help='Explicit removal of an accepted seed feature')
p.add_argument('--resource-config',type=Path,help='Explicit resource protection profile; default Normal for repeatability')
p.add_argument('--gpu',default=None,help='Observed unique device description; no numeric GPU index')
a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
if (out/'composer.json').exists():raise SystemExit('Refusing to overwrite an existing run')
root=Path(__file__).resolve().parents[1]
identity={'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'runtime_hashes':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for base in ('src','web','configs') for p in (root/base).rglob('*') if p.is_file() and '__pycache__' not in str(p)},'started_at':time.time(),'workflow':a.workflow,'preservation_requests':{'login':a.login_request,'theme':a.theme_request},'removal_request':a.remove_request,'removed_feature':a.removed_feature,'compound_mode':a.compound_mode,'compound_request':a.compound_request,'device_requested':a.gpu or 'CPU','inference':'real' if a.real_model else 'fake'}
if a.workflow=='web-recipe':
 from src.tools.web_recipes import manifest
 identity['expected_recipe_manifest']=manifest()
(out/'identity.json').write_text(json.dumps(identity,indent=2))
profile=out/'profile'
os.environ.update(NEURA_SETTINGS_DIR=str(profile/'config'),NEURA_DATA_DIR=str(profile/'data'),NEURA_STATE_DIR=str(profile/'state'),NEURA_TIMEOUT_S='900')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication,QEvent
from src.desktop.paths import DesktopSettings
from src.desktop.app import MainWindow
qt=QApplication(['neura-accuracy-qa']);settings=DesktopSettings()
from src.core.resource_policy import ProtectionConfig,save_config
resource=ProtectionConfig.model_validate_json(a.resource_config.read_text()) if a.resource_config else ProtectionConfig(mode='normal')
save_config(profile/'data',resource)
identity['resource_configuration']=resource.model_dump();(out/'identity.json').write_text(json.dumps(identity,indent=2))
settings.values.update(models_dir='/opt/neura-ai/models',n_gpu_layers=-1 if a.gpu else 0,gpu_device=a.gpu or 'auto',n_ctx=4096,dedicated_coder=True,check_updates=False);settings.save()
seed_id=None
if a.workflow in ('large','remove','compound','compound-clarify'):
 if not a.seed_project:raise ValueError('seeded workflow needs explicit QA seed')
 from src.core.project_store import ProjectStore
 seed=json.loads(a.seed_project.read_text());seed_store=ProjectStore(profile/'data')
 seed_id=seed_store.create('Existing large CV' if a.workflow=='large' else 'Existing saved CV','Synthetic QA existing website' if a.workflow=='large' else 'Declared native-generated QA source')['project_id']
 seed_store.commit(seed_id,seed['files'],0,accepted_requirements=seed['accepted_requirements']);seed_store.close()
w=MainWindow(settings)
if a.real_model:
 from verification.live import foreign_instances
 if foreign_instances():raise RuntimeError('A Neura backend is already running; real QA refused')
 marker={'run_id':out.name};profile.mkdir(parents=True,exist_ok=True);(profile/'.neura-verification-profile').write_text(json.dumps(marker))
 os.environ.update(NEURA_QA_RUN_ROOT=str(out),NEURA_QA_RUN_ID=out.name,NEURA_QA_REAL_TRACE=str(out/'artifacts/model-traces'),NEURA_QA_TARGET_KIND='source checkout')
 fixture=root/'tests/fixtures/real_backend_trace.py'
 w.service.popen=lambda command,**opts:subprocess.Popen([command[0],'-B',str(fixture),'--port',command[-1]],**opts)
else:
 fixture=Path(__file__).resolve().parents[1]/'tests/fixtures/chat_first_backend.py'
 w.service.popen=lambda command,**opts:subprocess.Popen([command[0],'-B',str(fixture),'--port',command[-1]],**opts)
w.resize(1280,900);w.show();turns=[]
def pump():
 qt.processEvents();time.sleep(.005)
def wait(check,seconds=30):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  if check():return
  pump()
 raise TimeoutError('QA condition timed out')
def js(source):
 result=[];w.page.runJavaScript(source,lambda value:result.append(value));wait(lambda:bool(result),5);return result[0]
def api(path):
 req=urllib.request.Request(w.service.url+path,headers={'X-Neura-Token':(profile/'data/.api-token').read_text().strip()})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=5) as r:return json.load(r)
def save():
 (out/'composer.json').write_text(json.dumps({'environment':'Qt offscreen; '+('actual local inference; requested '+(a.gpu or 'CPU') if a.real_model else 'fake inference and desktop adapters')+'; actual composer/API/jobs/storage/preview','baseline':a.baseline,'turns':turns},ensure_ascii=False,indent=2))
def state():
 projects=api('/projects')['projects']
 return {'session':js('sid'),'projects':[{k:v for k,v in item.items() if k in ('project_id','project_revision','files','latest_job_id','generation_status','accepted_requirements','generation_recipe')} for item in projects],
  'preview':js('document.querySelector("#ws-preview-rev").textContent'),'active_project':js('window.NeuraWorkspace.projectId||null'),
  'cards':js('JSON.stringify(Array.from(document.querySelectorAll("[data-project-job-id]")).map(e=>({job_id:e.dataset.projectJobId,state:e.dataset.jobState,text:e.textContent})))')}
def send(text):
 wait(lambda:not js('busy'),930)
 if js('location.hash==="#workspace"'):js('document.querySelector("#ws-return").click();true;')
 started=time.monotonic();before=state();stats_before=api('/stats');offset=js('(window.__qaDispatch||[]).length')
 js('document.querySelector("#in").value='+json.dumps(text)+';document.querySelector("#go").click();true;')
 wait(lambda:not js('busy'),930)
 wait(lambda:all(x['generation_status'] in ('idle','completed','failed','cancelled') for x in api('/projects')['projects']),930)
 # Event rendering can finish after the worker commits.
 end=time.monotonic()+1
 while time.monotonic()<end:pump()
 after=state();record={'text':text,'before':before,'after':after,'dispatch':json.loads(js('JSON.stringify((window.__qaDispatch||[]).slice('+str(offset)+'))')),
  'visible_result':js('document.querySelector("#log").textContent'),'workspace_result':js('document.querySelector("#ws-message").textContent')}
 record['jobs']=[api('/project-jobs/'+x['latest_job_id']) for x in after['projects'] if x.get('latest_job_id')]
 import sqlite3
 catalog=next((profile/'data').rglob('catalog.sqlite3'))
 with sqlite3.connect('file:'+str(catalog)+'?mode=ro',uri=True) as db:
  record['job_count']=db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]
  record['proposals']=[dict(zip(['session','project_id','revision','state','details'],row)) for row in db.execute('SELECT session,project_id,revision,state,details FROM project_proposals')]
 record['duration_s']=time.monotonic()-started;record['stats_before']=stats_before;record['stats_after']=api('/stats')
 record['files']={item['project_id']:{f['path']:api('/projects/'+item['project_id']+'/file?path='+urllib.parse.quote(f['path'])) for f in item['files']} for item in after['projects']}
 turns.append(record);save();w.grab().save(str(out/('turn-'+str(len(turns))+'.png')))
 print(json.dumps({'turn':len(turns),'text':text,'decision':[d['kind'] for d in record['dispatch']], 'jobs':[(j['state'],j['error']) for j in record['jobs']],'revisions':[x['project_revision'] for x in after['projects']]},ensure_ascii=False),flush=True)
try:
 wait(lambda:w.loaded,40);wait(lambda:js('!!window.NeuraChat'))
 js('window.__qaDispatch=[];window.__qaFetch=window.fetch;window.fetch=async(...args)=>{const r=await window.__qaFetch(...args);if(String(args[0]).includes("/chat/dispatch")){window.__qaDispatch.push(await r.clone().json());}return r;};true;')
 if a.workflow in ('large','remove','compound','compound-clarify'):
  js('document.querySelector("#coding-workspace").click();true;')
  wait(lambda:js('document.querySelector("#ws-project-list button")!==null'))
  js('document.querySelector("#ws-project-list button").click();true;')
  wait(lambda:js('window.NeuraWorkspace.projectId==='+json.dumps(seed_id)))
 if a.workflow=='compound-clarify':send(a.compound_request)
 elif a.workflow=='plan':
  send('خطط لموقع سيرة ذاتية ثابت بثلاث خطوات مرقمة. بدون cloud وبدون تثبيت أي شيء.')
 else:
  if a.workflow=='web-recipe':send('برمج لي موقع سيرة ذاتية عربي محلي يعمل بدون إنترنت مع بيانات تجريبية واضحة')
  elif a.workflow=='resource-smoke':send('برمج سكربت Python بسيط باسم main.py يطبع مرحبا دون أي اعتماد خارجي')
  elif a.workflow=='compound':send(a.compound_request)
  elif a.workflow=='remove':send(a.remove_request)
  elif a.workflow=='large':send('هل يمكنك ان تحسن الواجهه الموقع بجودة عالي و مبهر جدا')
  else:send('برمج لي موقع صفحة واحدة فيها عنوان مرحبا فقط' if a.workflow=='smoke' else 'برمج لي موقع للcv')
  texts=['هل يمكنك ان تحسن الواجهه الموقع بجودة عالي و مبهر جدا','نعم','لم تفعل شي حتى الان؟','فل تبرمج','هل يمكنك أن تحسن واجهة الموقع بجودة عالية ومبهرة جدًا'] if a.workflow=='exact' else [a.login_request,a.theme_request,'هل يمكنك ان تحسن الواجهه الموقع بجودة عالي و مبهر جدا']
  if a.workflow=='web-recipe':texts=['أضف الوضع الداكن إلى هذا المشروع','هل يمكنك ان تحسن الواجهه الموقع بجودة عالي و مبهر جدا']
  if a.workflow=='proposal':texts=['واجهة مميزة تناسب العرض',a.approval,a.approval]
  if a.workflow in ('smoke','resource-smoke','large','remove','compound'):texts=[]
  for text in texts:
   if a.workflow=='web-recipe' and any(j['state']!='completed' for j in turns[-1]['jobs']):break
   send(text)
  js('document.querySelector("#ws-return").click();true;')
  wait(lambda:js('Array.from(document.querySelectorAll("[data-project-job-id]")).every(e=>["completed","failed","cancelled"].includes(e.dataset.jobState))'))
  (out/'cards-before-restart.json').write_text(json.dumps(state(),ensure_ascii=False,indent=2))
  w.grab().save(str(out/'cards-before-restart.png'))
  # Restore the SAME conversation and reopen from the saved project drawer.
  prior=state();session=prior['session'];pid=prior['active_project'];w._restart_backend()
  wait(lambda:w.loaded,40);wait(lambda:js('!!window.NeuraChat'))
  js('sessionButton.click();true;')
  wait(lambda:js('Array.from(document.querySelectorAll("#log button")).some(e=>e.textContent.startsWith('+json.dumps(session)+'))'))
  js('Array.from(document.querySelectorAll("#log button")).find(e=>e.textContent.startsWith('+json.dumps(session)+')).click();true;')
  wait(lambda:js('sid==='+json.dumps(session)))
  wait(lambda:js('document.querySelector("[data-project-job-id]")!==null'))
  end=time.monotonic()+2
  while time.monotonic()<end:pump()
  (out/'cards-restored.json').write_text(json.dumps(state(),ensure_ascii=False,indent=2))
  w.grab().save(str(out/'cards-restored.png'))
  js('document.querySelector("#coding-workspace").click();true;')
  wait(lambda:js('document.querySelector("#ws-project-list button")!==null'))
  js('document.querySelector("#ws-project-list button").click();true;')
  wait(lambda:js('window.NeuraWorkspace.projectId==='+json.dumps(pid)))
  end=time.monotonic()+2
  while time.monotonic()<end:pump()
  after=state();(out/'restart.json').write_text(json.dumps({'before':prior,'after':after,'same_project':pid==after['active_project'],'same_files':[(x['project_id'],x['files']) for x in prior['projects']]==[(x['project_id'],x['files']) for x in after['projects']]},ensure_ascii=False,indent=2))
  w.grab().save(str(out/'reopened.png'))
except BaseException as error:
 (out/'failure.json').write_text(json.dumps({'completed_turns':len(turns),'type':type(error).__name__,'error':str(error),'time':time.time()},ensure_ascii=False,indent=2))
 raise
finally:
 save();w.close_checked=True;w.close();wait(lambda:not w.tasks,25);w.service.stop()
 QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);w.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);qt.processEvents()
