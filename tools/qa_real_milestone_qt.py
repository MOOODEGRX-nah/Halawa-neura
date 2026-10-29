"""Opt-in packaged Qt/CPU model acceptance using isolated data and existing local weights.

No fake inference or desktop adapter. --launch-youtube explicitly includes a real
Brave launch. Generated Python is statically inspected, never executed.
"""
import argparse,hashlib,json,os,time,urllib.request,urllib.parse
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--data',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--launch-youtube',action='store_true');args=parser.parse_args()
args.data=args.data.resolve();args.output=args.output.resolve();args.output.mkdir(parents=True,exist_ok=True)
os.environ.update(NEURA_SETTINGS_DIR=str(args.data/'config'),NEURA_DATA_DIR=str(args.data/'data'),NEURA_STATE_DIR=str(args.data/'state'),NEURA_TIMEOUT_S='240')
from PySide6.QtCore import QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication
from src.desktop.paths import DesktopSettings,VERSION
from src.desktop.app import MainWindow
qt=QApplication(['neura-real-milestone-qa']);settings=DesktopSettings()
settings.values.update(models_dir='/opt/neura-ai/models',n_gpu_layers=0,n_ctx=2048,dedicated_coder=True,check_updates=False);settings.save()
window=MainWindow(settings);window.show();results=[]
def record(name,passed,**details):
 results.append({'name':name,'passed':bool(passed),**details});(args.output/'real-qt.json').write_text(json.dumps({'version':VERSION,'inference':'actual llama.cpp and local Qwen2.5 Coder14B on explicit CPU','desktop':'actual default GIO adapter','qt':'offscreen MainWindow, unmodified BackendService child','results':results},ensure_ascii=False,indent=2));print(name,passed,details,flush=True);assert passed,name

def pump(seconds=.04):
 deadline=time.monotonic()+seconds
 while time.monotonic()<deadline:qt.processEvents();time.sleep(.004)
def wait(predicate,seconds=20):
 deadline=time.monotonic()+seconds
 while time.monotonic()<deadline:
  if predicate():return
  pump()
 raise AssertionError('timed out')
def js(source,frame=None):
 values=[];(frame or window.page).runJavaScript(source,lambda value:values.append(value));wait(lambda:bool(values),5);return values[0]
def api(path,raw=False):
 req=urllib.request.Request(window.service.url+path,headers={'X-Neura-Token':(args.data/'data/.api-token').read_text().strip()})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=5) as response:return response.read().decode() if raw else json.load(response)
def click(selector):js('document.querySelector('+json.dumps(selector)+').click();true;')
def send(text):wait(lambda:not js('busy'));js('send('+json.dumps(text)+');true;')
def preview_frame():return next((f for f in window.page.mainFrame().children() if '/p/' in f.url().toString()),None)
try:
 wait(lambda:window.loaded,35)
 wait(lambda:js('!!window.NeuraChat && document.querySelectorAll("#nav [role=tab]").length===3'))
 record('native-startup-and-navigation',js('Array.from(document.querySelectorAll("#nav [role=tab]")).map(e=>e.id).join(",")')=='tab-chat,tab-monitor,tab-about')
 prompt='أنشئ لي موقع سيرة ذاتية باستخدام HTML وCSS وJavaScript. Keep exactly index.html, style.css, script.js, short local files. Heading Sami, developer text, button id hello setting p id result to مرحبا. No external assets.'
 send(prompt);wait(lambda:js('location.hash==="#workspace"'),30)
 project=js('window.NeuraWorkspace.projectId')
 wait(lambda:js('document.querySelector("#ws-editor").value.length>0'),120)
 meta=api('/projects/'+project);job=meta['latest_job_id']
 record('actual-stream-before-completion',api('/project-jobs/'+job)['state'] not in ('completed','failed'),partial_characters=js('document.querySelector("#ws-editor").value.length'))
 pump(.15);window.grab().save(str(args.output/'real-stream.png'))
 wait(lambda:api('/project-jobs/'+job)['state'] in ('completed','failed'),240)
 snapshot=api('/project-jobs/'+job);assert snapshot['state']=='completed',snapshot
 wait(lambda:js('!document.querySelector("#ws-full-button").disabled'))
 meta=api('/projects/'+project);events=[json.loads(line[6:]) for line in api('/project-jobs/'+job+'/events',True).splitlines() if line.startswith('data: ')]
 files={f['path']:api('/projects/'+project+'/file?path='+urllib.parse.quote(f['path'])) for f in meta['files']}
 record('actual-chat-creation-and-files',len(api('/projects')['projects'])==1 and set(files)=={'index.html','style.css','script.js'} and meta['purpose']==prompt and all(f['content']==snapshot['draft_files'][path]['content'] for path,f in files.items()),event_count=len(events),file_deltas=sum(e['type']=='file_delta' for e in events),ordered=[e['seq'] for e in events]==list(range(1,len(events)+1)))
 record('code-left-preview-right',js('document.querySelector(".ws-code").getBoundingClientRect().x<document.querySelector(".ws-preview").getBoundingClientRect().x'))
 wait(lambda:preview_frame() is not None);frame=preview_frame();wait(lambda:js('!!document.querySelector("#hello")',frame))
 js('document.querySelector("#hello").click();true;',frame);record('real-generated-preview-interaction',js('document.querySelector("#result").textContent',frame)=='مرحبا');frame=None
 click('#ws-full-button');record('full-preview-boundary',js('document.querySelector("#ws-full iframe").src===document.querySelector("#ws-preview-content iframe").src && document.querySelector("#ws-full iframe").getAttribute("sandbox")==="allow-scripts"'));click('#ws-full-close')
 pump(.15);window.grab().save(str(args.output/'real-site.png'))
 click('#ws-swap');record('pane-swapping',js('document.querySelector(".ws-code").getBoundingClientRect().x>document.querySelector(".ws-preview").getBoundingClientRect().x'));click('#ws-swap')
 js('Array.from(document.querySelectorAll("#ws-file-list button")).find(b=>b.textContent==="style.css").click();true;');wait(lambda:js('document.querySelector("#ws-path").textContent==="style.css"'))
 css=js('document.querySelector("#ws-editor").value')+'\n/* explicit QA edit */'
 js('document.querySelector("#ws-editor").value='+json.dumps(css)+';document.querySelector("#ws-editor").dispatchEvent(new Event("input"));document.querySelector("#ws-save").click();true;')
 wait(lambda:not js('window.NeuraWorkspace.dirty'))
 meta=api('/projects/'+project);record('actual-edit-save-current-metadata',meta['project_revision']==2 and meta['summary_revision']==2 and meta['source_freshness']=='current' and api('/projects/'+project+'/file?path=style.css')['content']==css)
 before=api('/stats');click('#ws-return');send('ما هي لغات هذا المشروع؟');wait(lambda:js('document.querySelector("#log").textContent.includes("دون استدعاء نموذج")'))
 after=api('/stats');record('metadata-keeps-model-resident-without-call',after['totals']['requests']==before['totals']['requests'] and after['current_model']==before['current_model'],model=after['current_model'])
 if args.launch_youtube:
  send('هل يمكنك ان تفتح لي موقع youtube');wait(lambda:js('document.querySelector("#log").textContent.includes("أُرسل طلب الفتح")'))
  after=api('/stats');record('actual-chat-brave-no-model-swap',after['totals']['requests']==before['totals']['requests'] and after['current_model']==before['current_model'])
 second='أنشئ مشروع Python صغير بملف main.py فقط، يحتوي دالة add(a, b) تعيد a + b. لا تشغل الملف.'
 send(second);wait(lambda:js('location.hash==="#workspace" && window.NeuraWorkspace.projectId!=='+json.dumps(project)),30)
 python_project=js('window.NeuraWorkspace.projectId');python_job=api('/projects/'+python_project)['latest_job_id'];wait(lambda:api('/project-jobs/'+python_job)['state'] in ('completed','failed'),240)
 py_meta=api('/projects/'+python_project);assert api('/project-jobs/'+python_job)['state']=='completed'
 record('separate-python-project-not-executed',len(api('/projects')['projects'])==2 and not py_meta['preview']['supported'] and py_meta['validation']['executed'] is False and any(f['path']=='main.py' for f in py_meta['files']))
 directories={}
 for path in (args.data/'data/workspace').glob('*/.neura/project.json'):
  data=json.loads(path.read_text());directories[data['project_id']]=str(path.parent.parent)
 record('distinct-project-directories',project in directories and python_project in directories and directories[project]!=directories[python_project],directories=directories)
 hashes={f['path']:f['sha256'] for f in api('/projects/'+project)['files']}
 window._restart_backend();wait(lambda:window.loaded,35);wait(lambda:js('!!window.NeuraWorkspace && !!document.querySelector("#coding-workspace")'))
 click('#coding-workspace');wait(lambda:js('document.querySelectorAll("#ws-project-list button").length===2'))
 js('Array.from(document.querySelectorAll("#ws-project-list .ws-project")).find(c=>c.querySelector("h3").textContent.includes("السيرة")).querySelector("button").click();true;')
 wait(lambda:js('location.hash==="#workspace" && !document.querySelector("#ws-full-button").disabled'))
 record('restart-and-reopen-without-generation',js('window.NeuraWorkspace.projectId')==project and {f['path']:f['sha256'] for f in api('/projects/'+project)['files']}==hashes and api('/stats')['current_model'] is None)
 pump(.2);window.grab().save(str(args.output/'real-reopened.png'))
finally:
 window.close_checked=True;window.close();pump(.1);wait(lambda:not window.tasks,25);window.service.stop();pump(.3)
 QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);qt.processEvents()
