"""QA dependency injection only. This file is never included in the app package."""
import argparse,os,time,json,asyncio
from pathlib import Path
import uvicorn
from src.runtime import Settings
from src.core.neura_loop import NeuraLoop
from src.backend.api import create_app
# The fixture backend has no native inference or live sensor dependency.
import src.backend.api as api_module
import src.backends.residency as residency_module
from types import SimpleNamespace
import psutil
api_module.gpu_memory=lambda:None
residency_module.gpu_memory=lambda:None
psutil.cpu_percent=lambda *a,**k:0.0
psutil.virtual_memory=lambda:SimpleNamespace(total=32_000_000_000,used=8_000_000_000,available=24_000_000_000,free=24_000_000_000,percent=25.0)
parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,required=True);args=parser.parse_args()
WEB='```html index.html\n<html lang="ar" dir="rtl"><link rel="stylesheet" href="style.css"><h1>سيرة Qt</h1><button id="hello">تجربة</button><p id="result"></p><script src="script.js"></script></html>\n```\n```css style.css\nbody{background:#e8f4ee;color:#24523e;font-family:sans-serif;padding:30px}\n```\n```javascript script.js\ndocument.querySelector("#hello").onclick=()=>document.querySelector("#result").textContent="مرحبا";\n```'
MARKDOWN='فقرة **غامقة** و*مائلة* و`inline`.\n\n- واحد\n- two\n\n[رابط](https://example.com/)\n\n```python\nprint("code")\n```\n\n<script>fetch("/skills/authorize",{method:"POST"})</script><img src=x onerror="fetch(\'/skills/authorize\',{method:\'POST\'})">\n[bad](javascript:alert(1))'
class Backend:
 def __init__(self):self.model=None;self.calls=0;self.loads=0;self.selected_device={'description':'CPU'}
 def load(self,*args,**kwargs):self.loads+=1;self.model=object()
 def unload(self):self.model=None
 def health_check(self):return {'status':'loaded' if self.model else 'unloaded'}
 def measure_messages(self,messages,max_tokens=1024,**options):
  return {'prompt_tokens':200,'context_size':4096,'effective_output_limit':min(max_tokens,3896),'measurement':'controlled Qt token fixture, not native'}
 def generate(self,*,messages,stream=False,**options):
  self.calls+=1;text=WEB if 'complete named files' in messages[0]['content'] else os.environ.get('NEURA_QA_CHAT_TEXT') or MARKDOWN
  if messages[0]['content'].startswith('Return ONLY a compact JSON implementation plan'):
   invoice=json.loads(messages[1]['content'])
   text=json.dumps({'steps':['Inspect requirements and source.','Implement the requested files.','Check syntax and preserved behavior.'],
                    'files':invoice['expected_files'] or invoice['filename_hints'] or ['index.html','style.css','script.js']})
  if 'complete named files' in messages[0]['content']:
   invoice=json.loads(messages[1]['content'].split('\nValidated implementation plan:')[0])
   if invoice.get('context_summary'):text='```css style.css\nbody{background:blue;color:white;font-family:sans-serif}\n```'
  if messages[0]['content'].startswith('Return a bounded file patch'):
   packet=json.loads(messages[1]['content']);path=packet['path'];scope=packet['source_scope']
   edits=[{'before':scope,'after':'body{background:blue;color:white;font-family:sans-serif}'}] if path.endswith('.css') else []
   text=json.dumps({'base_revision':packet['base_revision'],'path':path,'source_sha256':packet['source_sha256'],'edits':edits,'new_content':None})
  if not stream:return {'choices':[{'message':{'content':text},'finish_reason':'stop'}]}
  def chunks():
   for offset in range(0,len(text),13):
    stop=options.get('stopping_criteria')
    if stop and stop(None,None):return
    time.sleep(.06)
    yield {'choices':[{'delta':{'content':text[offset:offset+13]},'finish_reason':None}]}
   yield {'choices':[{'delta':{},'finish_reason':'stop'}]}
  return chunks()
class Desktop:
 def __init__(self):self.calls=[]
 def configuration(self):
  from src.desktop.paths import DesktopSettings
  return DesktopSettings().values
 def status(self):return {'desktop_available':True,'brave_available':True,'reason':'','text_viewer_available':True,'folder_viewer_available':True,'locations':[],'applications':[{'id':'brave-browser.desktop','name':'Brave'},{'id':'calc.desktop','name':'الحاسبة'},{'id':'discord.desktop','name':'Discord'},{'id':'cmake.desktop','name':'CMake'}]}
 def browser(self,url):self.calls.append(['browser',url]);return {'status':'launched','message':'أُرسل طلب الفتح في اختبار Qt؛ لا ادعاء تحميل الصفحة.','application_id':'brave-browser.desktop'}
 def launch(self,application_id,uris=()):self.calls.append(['app',application_id]);return {'status':'launched','message':'طلب فتح تطبيق QA','application_id':application_id}
 def open_file(self,args):self.calls.append(['file',args]);return {'status':'launched','message':'طلب عرض ملف QA'}
 def open_folder(self,args):self.calls.append(['folder',args]);return {'status':'launched','message':'طلب فتح مجلد QA'}
settings=Settings();backend=Backend();desktop=Desktop();loop=NeuraLoop(settings=settings,backend=backend);app=create_app(settings,loop,desktop_adapter=desktop)
if os.environ.get('NEURA_QA_REAL_DESKTOP')=='1':
 from src.desktop.actions import DesktopAdapter
 import subprocess
 class RecordedDesktop(DesktopAdapter):
  def __init__(self):
   self.calls=[]
   super().__init__(app.state.project_store,runner=self.recorded_launch)
  def recorded_launch(self,command,**options):
   result=subprocess.run(command,**options)
   self.calls.append({'argv':command,'shell':options.get('shell'),'returncode':result.returncode,'time':time.time()})
   return result
 desktop=RecordedDesktop();app.state.desktop_skills.adapter=desktop
save_requests=0
@app.middleware('http')
async def save_delay(request,call_next):
 global save_requests
 saving=request.method=='PUT' and request.url.path.endswith('/file')
 if saving:save_requests+=1
 response=await call_next(request)
 if saving:await asyncio.sleep(float(os.environ.get('NEURA_QA_SAVE_DELAY_S','0')))
 return response
@app.get('/qa/state')
async def state():
 from src.runtime import ROOT
 return {'target_root':str(ROOT),'model_adapter':'fake','desktop_adapter':'actual trusted GIO' if os.environ.get('NEURA_QA_REAL_DESKTOP')=='1' else 'fake','unrelated_requests':unrelated_requests,'security_project':security_project,'save_requests':save_requests,'desktop':desktop.calls,'model_calls':backend.calls,'model_loads':backend.loads,'projects':len(app.state.project_store.list()),'grants':app.state.project_store.db.execute('SELECT COUNT(*) FROM skill_grants').fetchone()[0]}
security_project=None;unrelated_requests=0;unrelated_server=None
if os.environ.get('NEURA_QA_SECURITY')=='1':
 from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
 import threading
 class Beacon(BaseHTTPRequestHandler):
  def do_GET(self):
   global unrelated_requests
   unrelated_requests+=1;self.send_response(200);self.end_headers();self.wfile.write(b'QA only')
  def log_message(self,*args):pass
 unrelated_server=ThreadingHTTPServer(('127.0.0.1',0),Beacon)
 threading.Thread(target=unrelated_server.serve_forever,daemon=True).start()
 security_project=app.state.project_store.create('فحص عزل N057','Controlled adversarial preview fixture')['project_id']
 payload="""const checks={};
try{checks.parent=parent.document.title}catch(e){checks.parent='blocked'};
try{localStorage.setItem('qa','x');checks.storage='allowed'}catch(e){checks.storage='blocked'};
checks.bridge=typeof qt==='undefined'&&typeof QWebChannel==='undefined';
try{parent.NeuraSkills.perform('open_website',{destination:'https://example.com/'});checks.tool='allowed'}catch(e){checks.tool='blocked'};
const targets=[['api',APP+'/skills/authorize'],['vault',APP+'/vault/sessions'],['unrelated',UNRELATED+'/beacon']];
Promise.all(targets.map(async([name,url])=>{try{await fetch(url,{method:name==='api'?'POST':'GET',headers:{'Content-Type':'application/json'},...(name==='api'?{body:JSON.stringify({name:'open_website',args:{destination:'https://example.com/'}})}:{})});checks[name]='allowed'}catch(e){checks[name]='blocked'}})).then(()=>document.querySelector('#checks').textContent=JSON.stringify(checks));""".replace('APP',json.dumps('http://127.0.0.1:'+str(args.port))).replace('UNRELATED',json.dumps('http://127.0.0.1:'+str(unrelated_server.server_port)))
 app.state.project_store.commit(security_project,{'index.html':'<html dir="rtl"><h1>فحص العزل</h1><pre id="checks">pending</pre><script src="checks.js"></script></html>','checks.js':payload,'private.txt':'QA private content'},0)
try:
 uvicorn.run(app,host='127.0.0.1',port=args.port,log_level='warning',proxy_headers=False)
finally:
 if unrelated_server:unrelated_server.shutdown();unrelated_server.server_close()
