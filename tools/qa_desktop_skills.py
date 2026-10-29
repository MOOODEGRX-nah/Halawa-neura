"""Opt-in real N066-N073 GIO trials with disposable files and no inference.

Launch acceptance is not page loading, reading, or video understanding.
"""
import argparse,asyncio,json,os,subprocess,time,uuid
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args();args.data=args.data.resolve();args.data.mkdir(parents=True,exist_ok=True)
os.environ.update(NEURA_DATA_DIR=str(args.data/'data'),NEURA_SETTINGS_DIR=str(args.data/'config'))
from src.desktop.paths import DesktopSettings,VERSION
from src.runtime import Settings
from src.backend.api import create_app
from src.core.project_store import ProjectStore
from src.tools.desktop_skills import DesktopSkills
from urllib.parse import parse_qs,urlsplit
import httpx
file=args.data/'عرض-Neura.txt';file.write_text('ملف اختبار مهارات Neura. لا معلومات شخصية ولا شيفرة تنفيذية.\n')
selection='l_'+uuid.uuid4().hex;config=DesktopSettings();config.values.update(models_dir='/opt/neura-ai/models',approved_locations={selection:{'path':str(file),'kind':'file'}},check_updates=False);config.save()
app=create_app(Settings(models_dir=Path('/opt/neura-ai/models'),data_dir=args.data/'data',n_gpu_layers=0));adapter=app.state.desktop_skills.adapter;launches=[]
def runner(command,**options):
 launches.append({'argv':command,'shell':options.get('shell'),'timeout_s':options.get('timeout')});return subprocess.run(command,**options)
adapter.runner=runner
project=app.state.project_store.create('فحص المهارات N','مجلد QA معتمد')['project_id'];app.state.project_store.commit(project,{'README.md':'# QA\n'},0)
def rid():return 'r_'+str(int(time.time()*1000))+'_'+uuid.uuid4().hex
async def main():
 results=[]
 async with app.router.lifespan_context(app):
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8000',headers={'X-Neura-Token':app.state.token}) as client:
   for text in ['هل يمكنك ان تفتح لي موقع youtube','ابحث في الويب عن تعلم Python بالعربي','ابحث في يوتيوب عن تعلم Python بالعربي','افتح Brave','افتح الحاسبة','افتح ملف عرض-Neura.txt','افتح مجلد مشروع فحص المهارات N']:
    count=len(launches);payload={'text':text,'request_id':rid()};response=await client.post('/chat/dispatch',json=payload);response.raise_for_status();result=response.json()
    assert result['result']['status']=='launched',result
    assert len(launches)==count+1
    assert (await client.post('/chat/dispatch',json=payload)).json()==result and len(launches)==count+1
    if text.startswith('ابحث'):
     url=launches[-1]['argv'][-1];query=parse_qs(urlsplit(url).query);assert ('تعلم Python بالعربي' in query.get('q',[]) or 'تعلم Python بالعربي' in query.get('search_query',[]))
    results.append({'text':text,'result':result,'launch':launches[-1],'retry_cached':True})
   for text in ['لا تفتح يوتيوب','"افتح يوتيوب"','كيف أفتح يوتيوب بنفسي؟','```text\nافتح يوتيوب\n```']:
    count=len(launches);assert (await client.post('/chat/dispatch',json={'text':text,'request_id':rid()})).json()['kind']=='chat';assert len(launches)==count
   assert app.state.coordinator.current_model_id is None
   before=app.state.desktop_skills.recent();assert any('brave' in item['application_id'].lower() for item in before)
 store=ProjectStore(args.data/'data');restored=DesktopSkills(store);after=restored.recent();assert after==before
 report={'version':VERSION,'ids':['N066','N067','N068','N069','N070','N071','N072','N073'],'adapter':'actual trusted catalog and actual GIO subprocess runner; argv captured before real execution','results':results,'negation_quotation_explanation_code_launches':0,'model_loaded':None,'recent_neura_history_survives_reopen':True,'recent_scope':'Only launches through Neura; not complete KDE/Brave history','history_count':len(after),'success_means':'real desktop accepted launch; no page load/read claim'}
 store.close();args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({'real_launches':len(results),'cached_retries':True,'history_persisted':True,'model_loaded':None}))
asyncio.run(main())
