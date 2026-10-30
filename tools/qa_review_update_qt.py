"""F4 Qt offscreen component checks. Fake model/desktop and installer; real gate API.

Never downloads a package or invokes pkexec/pacman. Normal Chromium sandbox.
"""
import argparse,json,os,subprocess,time,threading
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
a.data=a.data.resolve();a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=True)
os.environ.update(NEURA_DATA_DIR=str(a.data/'data'),NEURA_SETTINGS_DIR=str(a.data/'config'),NEURA_STATE_DIR=str(a.data/'state'))
os.environ.pop('QTWEBENGINE_DISABLE_SANDBOX',None);os.environ.pop('QTWEBENGINE_CHROMIUM_FLAGS',None)
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication,QEvent
from src.desktop import app as desktop
from src.desktop.paths import DesktopSettings,VERSION
from urllib.request import Request,build_opener,ProxyHandler
desktop.fetch_release=lambda:SimpleNamespace(version='999.0.0',notes='QA only; installer never runs')
qt=QApplication(['neura-update-qa']);settings=DesktopSettings();settings.values.update(n_gpu_layers=0,check_updates=False);settings.save()
window=desktop.MainWindow(settings);fixture=Path(__file__).resolve().parents[1]/'tests/fixtures/chat_first_backend.py'
window.service.popen=lambda command,**options:subprocess.Popen([command[0],'-B',str(fixture),'--port',command[-1]],**options)
window.show();results=[]
def pump():qt.processEvents();time.sleep(.003)
def wait(check,seconds=15):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  if check():return
  pump()
 raise AssertionError('Qt update QA deadline')
def js(source):
 values=[];window.page.runJavaScript(source,lambda v:values.append(v));wait(lambda:bool(values),5);return values[0]
def api(path,body=None,method=None):
 token=(a.data/'data/.api-token').read_text().strip();request=Request(window.service.url+path,data=json.dumps(body).encode() if body is not None else None,headers={'X-Neura-Token':token,'Content-Type':'application/json'},method=method)
 with build_opener(ProxyHandler({})).open(request,timeout=5) as response:return json.load(response)
def record(name,passed,**details):
 results.append({'name':name,'passed':bool(passed),**details});(a.output/'update-qt.json').write_text(json.dumps({'version':VERSION,'scope':'Real Qt offscreen and API/store; fake model, desktop and administrative result; sandbox enabled','results':results},ensure_ascii=False,indent=2));print(name,passed,flush=True);assert passed,name
def terminal(jid):return api('/project-jobs/'+jid)['state'] in ('completed','failed','cancelled')
try:
 wait(lambda:window.loaded,35);wait(lambda:js('!!window.NeuraWorkspace'))
 created=api('/projects',{'user_request':'QA web','requirements':['QA'],'background':True});pid=created['project']['project_id'];wait(lambda:terminal(created['job']['job_id']))
 js('window.NeuraWorkspace.openProject('+json.dumps(pid)+').then(()=>document.body.dataset.qaOpened="yes");true;');wait(lambda:js('document.body.dataset.qaOpened==="yes"'))
 dialog=desktop.UpdateDialog(window);window.update_dialog=dialog;dialog.show();wait(lambda:dialog.package is not None)
 saved=js('document.querySelector("#ws-editor").value');draft=saved+'\n<!-- unsaved update fixture -->'
 js('document.querySelector("#ws-editor").value='+json.dumps(draft)+';document.querySelector("#ws-editor").dispatchEvent(new Event("input"));true;')
 old_pid=window.service.process.pid;dialog.downloaded(Path('/qa-only-package'))
 wait(lambda:dialog.status.text().startswith('تعذّر'));wait(lambda:not window.update_pending)
 details={'pid_same':window.service.process.pid==old_pid,'draft_same':js('document.querySelector("#ws-editor").value')==draft,'dirty':js('window.NeuraWorkspace.dirty'),'inert':js('document.body.inert'),'status':dialog.status.text()}
 record('dirty-update-deferred-with-text-and-backend-intact',details['pid_same'] and details['draft_same'] and details['dirty'] and not details['inert'] and 'احفظ' in details['status'],**details)
 dialog.grab().save(str(a.output/'update-dirty-deferred.png'))
 js('document.querySelector("#ws-save").click();true;');wait(lambda:not js('window.NeuraWorkspace.dirty'))
 running=api('/projects',{'user_request':'QA active job','requirements':['QA'],'background':True});dialog.downloaded(Path('/qa-only-package'))
 wait(lambda:'مهام' in dialog.status.text() or 'الاستدلال' in dialog.status.text());wait(lambda:not window.update_pending)
 record('backend-job-outside-selected-workspace-blocks-update',window.service.process.pid==old_pid and not js('document.body.inert'))
 dialog.grab().save(str(a.output/'update-active-job-deferred.png'));wait(lambda:terminal(running['job']['job_id']))
 # Cancel during an in-flight prepare: release must happen after prepare returns.
 original=window.service.prepare_update;entered=threading.Event();release=threading.Event()
 def delayed():entered.set();assert release.wait(5);return original()
 window.service.prepare_update=delayed
 dialog.downloaded(Path('/qa-only-package'));wait(entered.is_set);dialog.reject();release.set()
 wait(lambda:not window.update_pending and not window.tasks)
 window.service.prepare_update=original
 record('cancel-during-prepare-does-not-leak-admission-reservation',window.service.process.pid==old_pid and window.service.update_reservation is None and not js('document.body.inert'))
 dialog=desktop.UpdateDialog(window);window.update_dialog=dialog;dialog.show();wait(lambda:dialog.package is not None)
 # Simulate a late editor callback after admission reservation, before stop.
 real_js=window.page.runJavaScript;injected=[False]
 def late_editor(source,*args):
  if 'checkUpdate' in source and not injected[0]:
   injected[0]=True;real_js('document.querySelector("#ws-editor").value+="\\n<!-- late edit -->";document.querySelector("#ws-editor").dispatchEvent(new Event("input"));')
  return real_js(source,*args)
 window.page.runJavaScript=late_editor;dialog.downloaded(Path('/qa-only-package'))
 wait(lambda:injected[0] and not window.update_pending);window.page.runJavaScript=real_js
 record('final-state-recheck-prevents-stop-after-late-edit',window.service.process.pid==old_pid and js('document.querySelector("#ws-editor").value.includes("late edit")') and js('window.NeuraWorkspace.dirty'))
 js('document.querySelector("#ws-save").click();true;');wait(lambda:not js('window.NeuraWorkspace.dirty'))
 # Allowed idle transition; authorization itself remains a stub.
 authorized=[];dialog.authorize=lambda path:authorized.append(str(path));dialog.downloaded(Path('/qa-only-package'));wait(lambda:bool(authorized))
 record('idle-only-stop-after-editor-and-backend-reservation',window.service.process is None and dialog.backend_stopped and js('document.body.inert'))
 dialog.installed(SimpleNamespace(returncode=1,stderr='QA simulated authorization cancellation'))
 wait(lambda:window.loaded,35);wait(lambda:not window.update_pending and js('!!window.NeuraWorkspace'))
 record('authorization-failure-restarts-owned-backend-and-preserves-files',window.service.process.pid!=old_pid and api('/projects/'+pid)['project_revision']==3 and not js('document.body.inert'))
 dialog.grab().save(str(a.output/'update-cancel-recovered.png'))
except Exception:
 window.grab().save(str(a.output/'update-failure.png'))
 if 'dialog' in locals():
  dialog.grab().save(str(a.output/'update-dialog-failure.png'))
  (a.output/'failure-state.json').write_text(json.dumps({'phase':dialog.phase,'cancelled':dialog.cancelled,'status':dialog.status.text(),'update_pending':window.update_pending,'preparing':window.update_preparing,'release_requested':window.update_release_requested,'releasing':window.releasing_update,'workspace':js('JSON.stringify(window.NeuraWorkspace.checkUpdate())')},ensure_ascii=False,indent=2))
 raise
finally:
 if 'release' in locals():release.set()
 window.close_checked=True;window.close();wait(lambda:not window.tasks,25);window.service.stop()
 QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);qt.processEvents()
