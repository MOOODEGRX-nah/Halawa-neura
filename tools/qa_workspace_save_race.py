"""Reproduce/save-regress editor typing while an actual API save reply is delayed.

Model and desktop are fixtures; Qt, the API commit and editor are real. The
fixture-only delay runs after the commit, never inside the production package.
"""
import argparse,json,os,subprocess,time
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--data',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--expect-bug',action='store_true');args=parser.parse_args()
args.data=args.data.resolve();args.output=args.output.resolve();args.output.parent.mkdir(parents=True,exist_ok=True)
os.environ.update(NEURA_SETTINGS_DIR=str(args.data/'config'),NEURA_DATA_DIR=str(args.data/'data'),NEURA_STATE_DIR=str(args.data/'state'),NEURA_QA_SAVE_DELAY_S='0.8')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication,QEvent
from src.desktop.paths import DesktopSettings,VERSION
from src.desktop.app import MainWindow
import urllib.request
qt=QApplication(['neura-save-race-qa']);settings=DesktopSettings();settings.values.update(models_dir='/opt/neura-ai/models',n_gpu_layers=0,check_updates=False);settings.save()
window=MainWindow(settings);fixture=Path(__file__).resolve().parents[1]/'tests/fixtures/chat_first_backend.py'
window.service.popen=lambda command,**options:subprocess.Popen([command[0],'-B',str(fixture),'--port',command[-1]],**options)
window.show();evidence={'version':VERSION,'model_and_desktop':'QA fakes','save':'actual backend commit and delayed response; actual Qt editor','expect_before_fix_bug':args.expect_bug}
def pump(seconds=.03):
 deadline=time.monotonic()+seconds
 while time.monotonic()<deadline:qt.processEvents();time.sleep(.003)
def wait(predicate,seconds=15):
 deadline=time.monotonic()+seconds
 while time.monotonic()<deadline:
  if predicate():return
  pump()
 raise AssertionError('timed out')
def js(source):
 result=[];window.page.runJavaScript(source,lambda value:result.append(value));wait(lambda:bool(result),5);return result[0]
def api(path,body=None):
 headers={'X-Neura-Token':(args.data/'data/.api-token').read_text().strip(),'Content-Type':'application/json'}
 req=urllib.request.Request(window.service.url+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=3) as response:return json.load(response)
def edit(text):js('document.querySelector("#ws-editor").value='+json.dumps(text)+';document.querySelector("#ws-editor").dispatchEvent(new Event("input"));true;')
try:
 wait(lambda:window.loaded,35)
 result=api('/projects',{'title':'Save race QA','user_request':'Create a tiny static CV','requirements':['Create a tiny static CV'],'background':True,'max_tokens':2048})
 pid=result['project']['project_id'];job=result['job']['job_id']
 wait(lambda:api('/project-jobs/'+job)['state']=='completed')
 js('window.NeuraWorkspace.openProject('+json.dumps(pid)+');true;')
 wait(lambda:js('location.hash==="#workspace" && document.querySelector("#ws-editor").value.includes("<html")'))
 original=js('document.querySelector("#ws-editor").value');first=original+'\n<!-- sent save -->';newest=first+'\n<!-- typed while waiting -->'
 edit(first);js('document.querySelector("#ws-save").click();true;')
 wait(lambda:api('/projects/'+pid)['project_revision']==2)
 edit(newest)
 js('document.querySelector("#ws-editor").dispatchEvent(new KeyboardEvent("keydown",{key:"s",ctrlKey:true,bubbles:true}));true;')
 if not args.expect_bug:
  # Selecting a different file during a pending save must not change its target.
  js('Array.from(document.querySelectorAll("#ws-file-list button")).find(b=>b.textContent==="style.css").click();true;')
 pump(1.3)
 snapshot={'editor_keeps_new_text':js('document.querySelector("#ws-editor").value')==newest,'dirty':js('window.NeuraWorkspace.dirty'),'saved_content_is_sent_version':api('/projects/'+pid+'/file?path=index.html')['content']==first,'save_requests':api('/qa/state')['save_requests'],'selected_file':js('document.querySelector("#ws-path").textContent')}
 evidence['during_reply']=snapshot
 if args.expect_bug:
  evidence['bug_demonstrated']=snapshot['editor_keeps_new_text'] and not snapshot['dirty'] and snapshot['saved_content_is_sent_version']
  assert evidence['bug_demonstrated'],snapshot
 else:
  assert snapshot['editor_keeps_new_text'] and snapshot['dirty'] and snapshot['saved_content_is_sent_version'] and snapshot['save_requests']==1 and snapshot['selected_file']=='index.html',snapshot
  js('document.querySelector("#ws-save").click();true;')
  wait(lambda:api('/projects/'+pid)['project_revision']==3);wait(lambda:not js('window.NeuraWorkspace.dirty'))
  assert api('/projects/'+pid+'/file?path=index.html')['content']==newest
  meta=api('/projects/'+pid);assert meta['summary_revision']==3 and meta['source_freshness']=='current'
  evidence['second_save']={'new_text_saved':True,'project_revision':3,'summary_revision':3,'source_freshness':'current'}
  evidence['passed']=True
 args.output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2));print(json.dumps(evidence,ensure_ascii=False,indent=2))
finally:
 window.close_checked=True;window.close();pump(.1);wait(lambda:not window.tasks,20);window.service.stop();pump(.3)
 QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);qt.processEvents()
