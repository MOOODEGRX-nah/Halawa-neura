"""N062/N064/N053/N054/N057/N098 component acceptance with packaged Qt and safe fixtures."""
import argparse,json,os,subprocess,time,urllib.request
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
args.data=args.data.resolve();args.output=args.output.resolve();args.output.mkdir(parents=True,exist_ok=True)
os.environ.update(NEURA_SETTINGS_DIR=str(args.data/'config'),NEURA_DATA_DIR=str(args.data/'data'),NEURA_STATE_DIR=str(args.data/'state'),NEURA_QA_SECURITY='1')
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import QCoreApplication,QEvent,Qt,QPoint
from PySide6.QtTest import QTest
from src.desktop import app as desktop
from src.desktop.paths import DesktopSettings,VERSION
from src.runtime import ROOT
class FilePage(desktop.LocalPage):
 def chooseFiles(self,*args):return [str(ROOT/'assets/logo.png')]
desktop.LocalPage=FilePage
qt=QApplication(['neura-milestone-ui']);settings=DesktopSettings();settings.values.update(models_dir='/opt/neura-ai/models',n_gpu_layers=0,check_updates=False);settings.save()
window=desktop.MainWindow(settings);fixture=Path(__file__).resolve().parents[1]/'tests/fixtures/chat_first_backend.py'
window.service.popen=lambda command,**options:subprocess.Popen([command[0],'-B',str(fixture),'--port',command[-1]],**options)
window.show();results=[]
def record(ids,name,passed,**details):
 results.append({'ids':ids.split(','),'name':name,'passed':bool(passed),**details});(args.output/'qt-extra.json').write_text(json.dumps({'version':VERSION,'environment':'actual packaged Qt/API/store/preview with QA model/desktop; file picker and confirmation simulated in test subclass','results':results},ensure_ascii=False,indent=2));print(name,passed,details,flush=True);assert passed,name

def pump(seconds=.03):
 end=time.monotonic()+seconds
 while time.monotonic()<end:qt.processEvents();time.sleep(.003)
def wait(check,seconds=20):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  if check():return
  pump()
 raise AssertionError('timed out')
def js(source,frame=None):
 values=[];(frame or window.page).runJavaScript(source,lambda x:values.append(x));wait(lambda:bool(values),5);return values[0]
def api(path,body=None,method=None):
 headers={'X-Neura-Token':(args.data/'data/.api-token').read_text().strip(),'Content-Type':'application/json'}
 request=urllib.request.Request(window.service.url+path,data=None if body is None else json.dumps(body).encode(),headers=headers,method=method)
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=4) as response:return json.load(response)
def click(selector):js('document.querySelector('+json.dumps(selector)+').click();true;')
def open_project(pid):
 js('window.NeuraWorkspace.openProject('+json.dumps(pid)+');true;');wait(lambda:js('location.hash==="#workspace" && !document.querySelector("#ws-full-button").disabled'))
def frames():return [frame for frame in window.page.mainFrame().children() if '/p/' in frame.url().toString()]
try:
 wait(lambda:window.loaded,35);wait(lambda:js('!!window.NeuraWorkspace'))
 pid=api('/qa/state')['security_project'];open_project(pid);wait(lambda:bool(frames()))
 frame=frames()[0];wait(lambda:js('document.querySelector("#checks").textContent!=="pending"',frame))
 checks=json.loads(js('document.querySelector("#checks").textContent',frame));frame=None
 expected={'parent':'blocked','storage':'blocked','bridge':True,'tool':'blocked','api':'blocked','vault':'blocked','unrelated':'blocked'}
 state=api('/qa/state');record('N057,N098','qt-preview-privilege-boundary',checks==expected and not state['desktop'] and state['grants']==0 and state['unrelated_requests']==0,checks=checks)
 click('#ws-full-button');wait(lambda:len(frames())==2)
 full=frames()[-1];wait(lambda:js('document.querySelector("#checks").textContent!=="pending"',full));full_checks=json.loads(js('document.querySelector("#checks").textContent',full));full=None
 record('N056,N057,N098','qt-full-page-same-boundary',full_checks==expected and js('document.querySelector("#ws-full iframe").src===document.querySelector("#ws-preview-content iframe").src && document.querySelector("#ws-full iframe").getAttribute("sandbox")==="allow-scripts"'))
 click('#ws-full-close')
 # Swapping a dirty selected file is a view operation, then save it explicitly before restart.
 js('Array.from(document.querySelectorAll("#ws-file-list button")).find(b=>b.textContent==="checks.js").click();true;');wait(lambda:js('document.querySelector("#ws-path").textContent==="checks.js"'))
 draft=js('document.querySelector("#ws-editor").value')+'\n// swap fixture edit\n'
 js('document.querySelector("#ws-editor").value='+json.dumps(draft)+';document.querySelector("#ws-editor").dispatchEvent(new Event("input"));true;');click('#ws-swap')
 record('N053,N054','swap-keeps-selected-file-and-draft',js('document.querySelector("#ws-path").textContent')=='checks.js' and js('document.querySelector("#ws-editor").value')==draft and js('window.NeuraWorkspace.dirty'))
 old_question=QMessageBox.question;QMessageBox.question=lambda *a,**k:QMessageBox.No
 before=window.service.process.pid;window.restart();wait(lambda:not window.checking_close);QMessageBox.question=old_question
 record('N054','declined-restart-keeps-draft',window.service.process.pid==before and js('document.querySelector("#ws-editor").value')==draft)
 click('#ws-save');wait(lambda:not js('window.NeuraWorkspace.dirty'));wait(lambda:api('/workspace/preferences')['swapped'])
 window._restart_backend();wait(lambda:window.loaded,35);wait(lambda:js('!!window.NeuraWorkspace'));open_project(pid)
 record('N053','pane-preference-and-saved-edit-survive-restart',js('document.querySelector("#ws-split").dataset.swapped')=='true' and api('/projects/'+pid+'/file?path=checks.js')['content']==draft)
 click('#ws-swap');click('#ws-return')
 api('/vault/save',{'session':'qa_toolbar_session','messages':[{'role':'user','content':'افتح يوتيوب'},{'role':'assistant','content':'**جلسة محفوظة**'}]})
 before=api('/qa/state');click('#saved-sessions');wait(lambda:js('Array.from(document.querySelectorAll("#log button")).some(b=>b.textContent.startsWith("qa_toolbar_session"))'))
 js('Array.from(document.querySelectorAll("#log button")).find(b=>b.textContent.startsWith("qa_toolbar_session")).click();true;');wait(lambda:js('document.querySelector("#log strong")?.textContent==="جلسة محفوظة"'))
 record('N062,N063,N073','saved-session-handler-no-replayed-action',api('/qa/state')['desktop']==before['desktop'])
 window.view.setFocus();js('document.querySelector("#chat-actions [role=button]").focus();true;');QTest.keyClick(window.view.focusProxy() or window.view,Qt.Key_Return);wait(lambda:js('document.querySelector("#image-label").textContent.includes("logo.png")'))
 record('N062,N064','attachment-keyboard-handler-file-reader',js('document.querySelector("#image-input").files.length')==1 and api('/qa/state')['model_calls']==0)
 js('document.querySelector("#tab-chat").focus();true;');QTest.keyClick(window.view.focusProxy() or window.view,Qt.Key_Right);wait(lambda:js('document.activeElement.id==="tab-about"'))
 record('N064','rtl-keyboard-tab-navigation',js('document.querySelector("#tab-about").getAttribute("aria-selected")')=='true')
 click('#tab-chat')
 for width in (1200,600,360):
  window.resize(width,850);pump(.15)
  # The retained entrance animation briefly scales the composer to .98.
  wait(lambda:js('Math.abs(document.querySelector("#chat-actions").getBoundingClientRect().width-document.querySelector("#ctl").getBoundingClientRect().width)<2'))
  geometry=json.loads(js('JSON.stringify({width:innerWidth,toolbar:document.querySelector("#chat-actions").getBoundingClientRect().width,composer:document.querySelector("#ctl").getBoundingClientRect().width,clipped:Array.from(document.querySelectorAll("#nav button,#chat-actions>*")).filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&(r.left<-.5||r.right>innerWidth+.5)}).map(e=>e.id)})'))
  record('N062,N064','toolbar-controls-'+str(width),not geometry['clipped'] and abs(geometry['toolbar']-geometry['composer'])<2,geometry=geometry)
  open_project(pid)
  clipped=json.loads(js('JSON.stringify(Array.from(document.querySelectorAll("#ws-return,#ws-work-view button,#ws-edit-request")).filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&(r.left<-.5||r.right>innerWidth+.5)}).map(e=>e.id))'))
  record('N064','workspace-controls-'+str(width),not clipped,clipped=clipped)
  click('#ws-return')
 window.resize(1200,850);open_project(pid)
 # A second writer commits first. The editor must show a conflict while keeping its local text.
 opened=api('/projects/'+pid+'/file?path=index.html');local=opened['content']+'<!-- local unsaved -->';remote=opened['content']+'<!-- external saved -->'
 js('document.querySelector("#ws-editor").value='+json.dumps(local)+';document.querySelector("#ws-editor").dispatchEvent(new Event("input"));true;')
 api('/projects/'+pid+'/file',{'path':'index.html','content':remote,'expected_revision':opened['project_revision'],'expected_sha256':opened['sha256']},'PUT')
 click('#ws-save');wait(lambda:js('!document.querySelector("#ws-conflict").classList.contains("ws-hidden")'))
 record('N054,N059','real-api-conflict-is-reviewable',js('document.querySelector("#ws-editor").value')==local and js('window.NeuraWorkspace.dirty') and js('document.querySelector("#ws-conflict-content").textContent')==remote and api('/projects/'+pid+'/file?path=index.html')['content']==remote)
 pump(.2);window.grab().save(str(args.output/'qt-conflict.png'))
finally:
 window.close_checked=True;window.close();pump(.1);wait(lambda:not window.tasks,20);window.service.stop();pump(.3)
 QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);qt.processEvents()
