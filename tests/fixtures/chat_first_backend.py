"""QA dependency injection only. This file is never included in the app package."""
import argparse,os,time,json,asyncio
from pathlib import Path
import uvicorn
from src.runtime import Settings
from src.core.neura_loop import NeuraLoop
from src.backend.api import create_app
parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,required=True);args=parser.parse_args()
WEB='```html index.html\n<html lang="ar" dir="rtl"><link rel="stylesheet" href="style.css"><h1>سيرة Qt</h1><button id="hello">تجربة</button><p id="result"></p><script src="script.js"></script></html>\n```\n```css style.css\nbody{background:#e8f4ee;color:#24523e;font-family:sans-serif;padding:30px}\n```\n```javascript script.js\ndocument.querySelector("#hello").onclick=()=>document.querySelector("#result").textContent="مرحبا";\n```'
MARKDOWN='فقرة **غامقة** و*مائلة* و`inline`.\n\n- واحد\n- two\n\n[رابط](https://example.com/)\n\n```python\nprint("code")\n```\n\n<script>fetch("/skills/authorize",{method:"POST"})</script><img src=x onerror="fetch(\'/skills/authorize\',{method:\'POST\'})">\n[bad](javascript:alert(1))'
class Backend:
 def __init__(self):self.model=None;self.calls=0;self.loads=0;self.selected_device={'description':'CPU'}
 def load(self,*args,**kwargs):self.loads+=1;self.model=object()
 def unload(self):self.model=None
 def health_check(self):return {'status':'loaded' if self.model else 'unloaded'}
 def generate(self,*,messages,stream=False,**options):
  self.calls+=1;text=WEB if 'complete named files' in messages[0]['content'] else MARKDOWN
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
 def status(self):return {'desktop_available':True,'brave_available':True,'reason':'','text_viewer_available':True,'folder_viewer_available':True,'locations':[],'applications':[{'id':'brave-browser.desktop','name':'Brave'},{'id':'calc.desktop','name':'الحاسبة'}]}
 def browser(self,url):self.calls.append(['browser',url]);return {'status':'launched','message':'أُرسل طلب الفتح في اختبار Qt؛ لا ادعاء تحميل الصفحة.','application_id':'brave-browser.desktop'}
 def launch(self,application_id,uris=()):self.calls.append(['app',application_id]);return {'status':'launched','message':'طلب فتح تطبيق QA','application_id':application_id}
 def open_file(self,args):self.calls.append(['file',args]);return {'status':'launched','message':'طلب عرض ملف QA'}
 def open_folder(self,args):self.calls.append(['folder',args]);return {'status':'launched','message':'طلب فتح مجلد QA'}
settings=Settings();backend=Backend();desktop=Desktop();loop=NeuraLoop(settings=settings,backend=backend);app=create_app(settings,loop,desktop_adapter=desktop)
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
async def state():return {'save_requests':save_requests,'desktop':desktop.calls,'model_calls':backend.calls,'model_loads':backend.loads,'projects':len(app.state.project_store.list()),'grants':app.state.project_store.db.execute('SELECT COUNT(*) FROM skill_grants').fetchone()[0]}
uvicorn.run(app,host='127.0.0.1',port=args.port,log_level='warning',proxy_headers=False)
