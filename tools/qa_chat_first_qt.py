"""Opt-in Qt journey test. Injected model/desktop; real window, API, state and preview.

Run with the application/vendor PYTHONPATH, --data and --output in a QA directory.
No installed application or personal data is modified.
"""
import argparse,json,os,subprocess,time,traceback,urllib.request
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--data',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();args.data=args.data.resolve();args.output=args.output.resolve()
args.data.mkdir(parents=True,exist_ok=True);args.output.mkdir(parents=True,exist_ok=True)
os.environ.update(NEURA_SETTINGS_DIR=str(args.data/'config'),NEURA_DATA_DIR=str(args.data/'data'),NEURA_STATE_DIR=str(args.data/'state'))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer,QCoreApplication,QEvent
from src.desktop.paths import DesktopSettings,VERSION
from src.desktop.app import MainWindow,SettingsDialog
qt=QApplication(['neura-chat-first-qa']);settings=DesktopSettings()
settings.values.update(models_dir='/opt/neura-ai/models',check_updates=False,n_gpu_layers=0);settings.save()
window=MainWindow(settings)
fixture=Path(__file__).resolve().parents[1]/'tests/fixtures/chat_first_backend.py'
window.service.popen=lambda command,**kwargs:subprocess.Popen([command[0],'-B',str(fixture),'--port',command[-1]],**kwargs)
results=[]
def record(name,passed,**details):
 results.append({'name':name,'passed':bool(passed),**details})
 (args.output/'qt-journeys.json').write_text(json.dumps({'version':VERSION,'adapters':'fake model and desktop; actual Qt/UI/API/store/events/preview','results':results},ensure_ascii=False,indent=2))
 print(name,passed,details,flush=True);assert passed,name
window.show()
def pump(seconds=.03):
 deadline=time.monotonic()+seconds
 while time.monotonic()<deadline:qt.processEvents();time.sleep(.004)
def wait(predicate,seconds=15):
 deadline=time.monotonic()+seconds
 while time.monotonic()<deadline:
  if predicate():return
  pump()
 raise AssertionError('timed out')
def js(source,frame=None):
 result=[];(frame or window.page).runJavaScript(source,lambda v:result.append(v));wait(lambda:bool(result),5);return result[0]
def api(path,body=None):
 token=(args.data/'data/.api-token').read_text().strip()
 request=urllib.request.Request(window.service.url+path,data=None if body is None else json.dumps(body).encode(),headers={'X-Neura-Token':token,'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=3) as response:return json.load(response)
def state():return api('/qa/state')
def send(text):
 wait(lambda:not js('busy'));js('send('+json.dumps(text)+');true;')
def click(selector):js('document.querySelector('+json.dumps(selector)+').click();true;')
def reopen():
 click('#coding-workspace');wait(lambda:js('document.querySelector("#ws-projects").open && document.querySelector("#ws-project-list button")!==null'))
 click('#ws-project-list button');wait(lambda:js('location.hash==="#workspace" && !document.querySelector("#ws-projects").open'))
def frame():return next((f for f in window.page.mainFrame().children() if '/p/' in f.url().toString()),None)
try:
 wait(lambda:window.loaded and window.stack.currentIndex()==1,35)
 tabs=json.loads(js('JSON.stringify(Array.from(document.querySelectorAll("#nav [role=tab]")).map(e=>e.id))'))
 record('navigation-only-chat-monitor-about',tabs==['tab-chat','tab-monitor','tab-about'] and js('!document.querySelector("#pg-skills,#pg-projects,#ws-new,#sk-browser-form")'),tabs=tabs)
 send('افتح يوتيوب');wait(lambda:len(state()['desktop'])==1)
 record('website-chat-no-model',state()['model_calls']==0 and state()['model_loads']==0)
 send('افتح تطبيق Brave');wait(lambda:len(state()['desktop'])==2)
 record('application-chat',state()['desktop'][-1]==['app','brave-browser.desktop'])
 send('اشرح كيف أكتب دالة Python');wait(lambda:js('document.querySelector("#log .neura-md strong")!==null'))
 record('explanation-remains-chat',state()['projects']==0 and js('location.hash!=="#workspace"'))
 wait(lambda:not js('busy'));pump(.2);window.grab().save(str(args.output/'chat-wide.png'))
 send('أنشئ لي موقع سيرة ذاتية باستخدام HTML وCSS وJavaScript')
 wait(lambda:js('location.hash==="#workspace" && document.querySelector("#ws-editor").value.length>0'))
 project=js('window.NeuraWorkspace.projectId');partial=js('document.querySelector("#ws-editor").value.length')
 click('#ws-return');reopen()
 record('active-generation-survives-chat-and-drawer',js('window.NeuraWorkspace.projectId')==project and state()['projects']==1,partial_characters=partial)
 wait(lambda:js('!document.querySelector("#ws-full-button").disabled'))
 files=json.loads(js('JSON.stringify(Array.from(document.querySelectorAll("#ws-file-list button")).map(e=>e.textContent))'))
 record('workspace-input-style',js('getComputedStyle(document.querySelector("#ws-edit-request")).backgroundColor')=='rgb(17, 26, 32)')
 record('single-project-files-and-panes',set(files)=={'index.html','style.css','script.js'} and js('document.querySelector(".ws-code").getBoundingClientRect().x<document.querySelector(".ws-preview").getBoundingClientRect().x'))
 wait(lambda:frame() is not None);preview=frame();wait(lambda:js('!!document.querySelector("#hello")',preview))
 js('document.querySelector("#hello").click();true;',preview)
 record('isolated-preview-interaction',js('document.querySelector("#result").textContent',preview)=='مرحبا');preview=None
 click('#ws-full-button');record('full-preview',js('document.querySelector("#ws-full").open && document.querySelector("#ws-full iframe").getAttribute("sandbox")==="allow-scripts" && document.querySelector("#ws-full iframe").src===document.querySelector("#ws-preview-content iframe").src'));click('#ws-full-close')
 click('#ws-folder');wait(lambda:state()['desktop'][-1][0]=='folder' and js('document.querySelector("#ws-message").textContent.includes("QA")'));record('workspace-folder-callback',js('document.querySelector("#ws-message").textContent.includes("QA")'));click('#ws-open-file');wait(lambda:state()['desktop'][-1][0]=='file' and js('document.querySelector("#ws-message").textContent.includes("QA")'));record('workspace-file-callback',js('document.querySelector("#ws-message").textContent.includes("QA")'));pump(.2);window.grab().save(str(args.output/'workspace-wide.png'))
 click('#ws-swap');click('#ws-return');reopen()
 record('swap-kept-across-views',js('document.querySelector(".ws-code").getBoundingClientRect().x>document.querySelector(".ws-preview").getBoundingClientRect().x'))
 click('#ws-swap')
 original=js('document.querySelector("#ws-editor").value');draft=original+'\n<!-- unsaved view-switch QA -->'
 js('document.querySelector("#ws-editor").value='+json.dumps(draft)+';document.querySelector("#ws-editor").dispatchEvent(new Event("input"));true;')
 click('#ws-return');click('#tab-monitor');click('#tab-chat');reopen()
 record('unsaved-edit-survives-view-changes',js('window.NeuraWorkspace.dirty') and js('document.querySelector("#ws-editor").value')==draft)
 click('#ws-return');send('عدل هذا المشروع واجعل العنوان أزرق')
 wait(lambda:js('location.hash==="#workspace" && document.querySelector("#ws-edit-request").value.includes("أزرق")'))
 record('chat-edit-opens-same-workspace-with-draft',js('document.querySelector("#ws-editor").value')==draft and state()['projects']==1)
 # Revoke a specific remembered permission from the actual native Settings dialog.
 grant=api('/skills/authorize',{'name':'open_website','args':{'destination':'https://www.youtube.com/'},'remember':True})
 dialog=SettingsDialog(settings,window);dialog.resize(700,700);dialog.show()
 wait(lambda:dialog.grants.count()==1)
 record('native-settings-availability-and-grants',len(dialog.skill_checks)==7 and dialog.skill_checks['open_website'].isChecked())
 dialog.grants.setCurrentRow(0);dialog.revoke_skill_grant();wait(lambda:dialog.grants.count()==0 and dialog.revoke_grant.isEnabled())
 record('native-settings-revokes-grant',api('/skills/grants')['grants']==[])
 from PySide6.QtWidgets import QScrollArea
 dialog.findChild(QScrollArea).ensureWidgetVisible(dialog.grants);pump(.15);record('settings-permissions-reachable-by-scroll',dialog.grants.visibleRegion().isEmpty()==False);dialog.grab().save(str(args.output/'settings-permissions.png'));dialog.reject()
 # Actual Settings entry point: a permission-only save must not restart the engine or erase the editor.
 process=window.service.process.pid
 def disable_in_modal():
  active=qt.activeModalWidget();assert isinstance(active,SettingsDialog)
  active.skill_checks['open_website'].setChecked(False);active.save()
 QTimer.singleShot(150,disable_in_modal);window.settings_dialog()
 record('permission-save-preserves-service-and-unsaved-editor',window.service.process.pid==process and js('window.NeuraWorkspace.dirty') and js('document.querySelector("#ws-editor").value')==draft)
 click('#ws-return');before=len(state()['desktop']);send('افتح يوتيوب')
 wait(lambda:js('document.querySelector("#log").textContent.includes("معطلة")'))
 record('settings-disable-enforced-by-chat-backend',len(state()['desktop'])==before and 'open_website' in settings.values['disabled_skills'])
 reopen();click('#ws-save');wait(lambda:not js('window.NeuraWorkspace.dirty'))
 record('saved-files-preserved',api('/projects/'+project)['project_revision']==2 and api('/projects/'+project+'/file?path=index.html')['content']==draft)
 for width in (1200,600,360):
  window.resize(width,850);pump(.15);click('#ws-return');click('#coding-workspace');wait(lambda:js('document.querySelector("#ws-projects").open'))
  geometry=json.loads(js('JSON.stringify({viewport:innerWidth,drawer:document.querySelector("#ws-projects").getBoundingClientRect().width,folder:document.querySelector("#coding-workspace").getBoundingClientRect().width})'))
  record('drawer-responsive-'+str(width),geometry['drawer']<=geometry['viewport']+1 and geometry['folder']<60,geometry=geometry)
  if width==360:window.grab().save(str(args.output/'drawer-narrow.png'))
  click('#ws-drawer-close');reopen()
  if width<900:click('#ws-mobile-preview');record('narrow-preview-'+str(width),js('getComputedStyle(document.querySelector(".ws-preview")).display!=="none"'));click('#ws-mobile-code')
 window.resize(1200,850);pump(.1)
 for old in ('projects','skills'):
  js('location.hash='+json.dumps('#'+old)+';true;');wait(lambda:js('location.hash==="#chat"'))
  record('obsolete-link-'+old,js('!document.querySelector("#pg-chat").classList.contains("nx-off")'))
 window._restart_backend();wait(lambda:window.loaded and window.stack.currentIndex()==1,35)
 reopen()
 record('restart-reopen-saved-project',js('window.NeuraWorkspace.projectId')==project and js('document.querySelector("#ws-editor").value')==draft and state()['projects']==1 and state()['model_calls']==0)
 window.grab().save(str(args.output/'workspace-reopened.png'));(args.output/'failure.txt').unlink(missing_ok=True)
except BaseException as error:
 (args.output/'failure.txt').write_text(traceback.format_exc());raise
finally:
 window.close_checked=True;window.close();pump(.1);wait(lambda:not window.tasks,20);window.service.stop();pump(.3)
 # processEvents alone does not flush deferred QObject deletion in this manual test loop.
 QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);qt.processEvents()
