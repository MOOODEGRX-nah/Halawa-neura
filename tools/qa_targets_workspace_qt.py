"""Controlled Qt component journeys: fake model/desktop, real packaged UI/API.

No actual desktop launch or real inference; CUA provides the separate visible
acceptance run against the real-model QA backend.
"""
import argparse,json,os,subprocess,time,urllib.request
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
a.data=a.data.resolve();a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=True)
os.environ.update(NEURA_SETTINGS_DIR=str(a.data/'config'),NEURA_DATA_DIR=str(a.data/'data'),NEURA_STATE_DIR=str(a.data/'state'))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication,QEvent
from src.desktop.paths import DesktopSettings,VERSION
from src.desktop.app import MainWindow
q=QApplication(['neura-targets-qa']);s=DesktopSettings();s.values.update(models_dir='/opt/neura-ai/models',n_gpu_layers=0,check_updates=False);s.save()
w=MainWindow(s);fixture=Path(__file__).resolve().parents[1]/'tests/fixtures/chat_first_backend.py'
w.service.popen=lambda command,**opts:subprocess.Popen([command[0],'-B',str(fixture),'--port',command[-1]],**opts)
w.show();results=[]
def pump(seconds=.03):
 end=time.monotonic()+seconds
 while time.monotonic()<end:q.processEvents();time.sleep(.003)
def wait(check,seconds=20):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  if check():return
  pump()
 raise AssertionError('bounded QA wait expired')
def js(source,frame=None):
 values=[];(frame or w.page).runJavaScript(source,lambda value:values.append(value));wait(lambda:bool(values),5);return values[0]
def api(path):
 req=urllib.request.Request(w.service.url+path,headers={'X-Neura-Token':(a.data/'data/.api-token').read_text().strip()})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=4) as response:return json.load(response)
def send(text):
 wait(lambda:not js('busy'));js('document.querySelector("#in").value='+json.dumps(text)+';document.querySelector("#go").click();true;')
def click(selector):js('document.querySelector('+json.dumps(selector)+').click();true;')
def preview():return next((f for f in w.page.mainFrame().children() if '/p/' in f.url().toString()),None)
def record(name,passed,**data):
 if not passed:w.grab().save(str(a.output/'failure.png'))
 results.append({'name':name,'passed':bool(passed),**data});(a.output/'journeys.json').write_text(json.dumps({'version':VERSION,'environment':'offscreen Qt, fake model and desktop; real packaged UI/API/jobs/store/events/preview','results':results},ensure_ascii=False,indent=2));print(name,passed,data,flush=True);assert passed,name
try:
 wait(lambda:w.loaded and w.stack.currentIndex()==1,35);wait(lambda:js('!!window.NeuraChat'))
 send('هل يمكنك ان تفتح ديسكورد');wait(lambda:not js('busy'))
 record('arabic-discord-composer',api('/qa/state')['desktop']==[['app','discord.desktop']] and api('/qa/state')['model_calls']==0)
 send('هل تعرف الديسكورد بالإنجليزي');wait(lambda:not js('busy'))
 record('knowledge-not-launch',len(api('/qa/state')['desktop'])==1 and api('/qa/state')['model_calls']==0)
 send('هذا هوا افتحه');wait(lambda:not js('busy'))
 record('followup-resolved-no-refusal',api('/qa/state')['desktop'][-1]==['app','discord.desktop'] and len(api('/qa/state')['desktop'])==2 and api('/qa/state')['model_calls']==0 and js('document.querySelector("#log").textContent.includes("أرسلت طلب فتح Discord")'))
 send('افتح تطبيق discord');wait(lambda:not js('busy'))
 record('english-same-target',api('/qa/state')['desktop'][-1]==['app','discord.desktop'] and len(api('/qa/state')['desktop'])==3 and api('/qa/state')['model_calls']==0)
 click('#clr');send('افتحه');wait(lambda:not js('busy'))
 record('new-conversation-no-target',len(api('/qa/state')['desktop'])==3 and js('document.querySelector("#log").textContent.includes("أي تطبيق تقصد")'))
 request='برمج لي موقع للcv';send(request)
 wait(lambda:js('location.hash==="#workspace" && document.querySelector("#ws-editor").value.length>0'))
 pid=js('window.NeuraWorkspace.projectId');job=api('/projects/'+pid)['latest_job_id']
 record('exact-cv-opens-workspace-during-generation',api('/project-jobs/'+job)['state'] not in ('completed','failed') and api('/qa/state')['projects']==1 and api('/projects/'+pid)['purpose']==request)
 click('#ws-return');click('#coding-workspace');wait(lambda:js('document.querySelector("#ws-project-list button")!==null'));click('#ws-project-list button')
 wait(lambda:js('!document.querySelector("#ws-full-button").disabled'))
 record('generation-survives-reopen',api('/qa/state')['projects']==1 and api('/project-jobs/'+job)['state']=='completed')
 record('physical-code-left',js('document.querySelector(".ws-code").getBoundingClientRect().x<document.querySelector(".ws-preview").getBoundingClientRect().x'))
 code=js('document.querySelector("#ws-editor").value');selected=js('document.querySelector("#ws-path").textContent');click('#ws-swap')
 record('swap-preserves-editor-selection',js('document.querySelector("#ws-editor").value')==code and js('document.querySelector("#ws-path").textContent')==selected);click('#ws-swap')
 click('#ws-return');send('غيّر لون الخلفية إلى الأزرق')
 wait(lambda:api('/projects/'+pid)['latest_job_id']!=job);edit=api('/projects/'+pid)['latest_job_id'];wait(lambda:api('/project-jobs/'+edit)['state'] in ('completed','failed'))
 assert api('/project-jobs/'+edit)['state']=='completed',api('/project-jobs/'+edit)
 wait(lambda:js('document.querySelector("#ws-preview-rev").textContent.includes("2")'))
 wait(lambda:preview() is not None);f=preview();wait(lambda:js('getComputedStyle(document.body).backgroundColor',f)=='rgb(0, 0, 255)');f=None
 record('same-project-blue-edit-preview',api('/qa/state')['projects']==1 and api('/projects/'+pid)['project_revision']==2 and api('/project-jobs/'+edit)['invoice']['context_summary'].find('Actual relevant source:')>=0)
 # Change source without changing file size/mtime, then ask through the real UI.
 # The answer and freshness label must agree while a dirty editor stays intact.
 metadata=next(p for p in (a.data/'data/workspace').glob('*/.neura/project.json') if json.loads(p.read_text())['project_id']==pid)
 css=metadata.parent.parent/'style.css';before=css.read_bytes();stamp=css.stat()
 assert b'blue' in before
 css.write_bytes(before.replace(b'blue',b'aqua'));os.utime(css,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
 click('#ws-file-list button[data-path="style.css"]') if js('!!document.querySelector("#ws-file-list button[data-path=\\"style.css\\"]")') else None
 editor=js('document.querySelector("#ws-editor").value')+'\n/* QA unsaved */'
 js('document.querySelector("#ws-editor").value='+json.dumps(editor)+';document.querySelector("#ws-editor").dispatchEvent(new Event("input"));document.querySelector(".ws-info").open=true;true;')
 calls=api('/qa/state')['model_calls'];js('document.querySelector("#ws-question-input").value="ما هي لغات المشروع؟";document.querySelector("#ws-meta-question").click();true;')
 wait(lambda:js('document.querySelector("#ws-freshness").textContent.includes("تغيرت")'))
 record('same-stat-question-refreshes-stale-ui-preserves-dirty-editor',api('/projects/'+pid)['source_freshness']=='stale' and api('/qa/state')['model_calls']==calls and js('document.querySelector("#ws-editor").value')==editor and js('document.querySelector("#ws-save-state").textContent.includes("غير محفوظ")'))
 css.write_bytes(before);os.utime(css,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
 # Discard only this disposable fixture's dirty editor before the restart test.
 js('window.confirm=()=>true;true;')
 click('#ws-full-button');record('full-preview-same-isolation',js('document.querySelector("#ws-full iframe").src===document.querySelector("#ws-preview-content iframe").src && document.querySelector("#ws-full iframe").getAttribute("sandbox")==="allow-scripts"'));click('#ws-full-close')
 hashes={f['path']:f['sha256'] for f in api('/projects/'+pid)['files']}
 w._restart_backend();wait(lambda:w.loaded and w.stack.currentIndex()==1,35);wait(lambda:js('!!window.NeuraWorkspace'));click('#coding-workspace');wait(lambda:js('document.querySelector("#ws-project-list button")!==null'));click('#ws-project-list button');wait(lambda:js('!document.querySelector("#ws-full-button").disabled'))
 record('restart-project-hashes-and-summary-current',{f['path']:f['sha256'] for f in api('/projects/'+pid)['files']}==hashes and api('/projects/'+pid)['source_freshness']=='current')
 click('#ws-return');send('اشرح هذا الكود');wait(lambda:not js('busy'))
 count=api('/qa/state')['projects'];location=js('location.hash')
 record('explanation-kept-in-chat',count==1 and location!='#workspace',projects=count,location=location,chat=js('document.querySelector("#log").textContent'))
finally:
 w.close_checked=True;w.close();pump(.1);wait(lambda:not w.tasks,20);w.service.stop();pump(.2)
 QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);w.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);q.processEvents()
