"""N058/N059: current metadata vs full-source token counts; no generation or code execution.

Real generated QA projects and deterministic larger fixtures are measured separately.
Summary-token counts are hypothetical context costs, not actual metadata-answer input.
"""
import argparse,json,time
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--projects-data',type=Path,required=True);p.add_argument('--fixture-data',type=Path,required=True);p.add_argument('--gguf',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
from src.core.project_store import ProjectStore
from src.desktop.paths import VERSION
from llama_cpp import Llama
actual=ProjectStore(args.projects_data);fixtures=ProjectStore(args.fixture_data)
web=fixtures.create('Large static fixture','موقع لعرض المهارات والمعلومات المهنية','static_web')['project_id']
fixtures.commit(web,{'index.html':'<link rel="stylesheet" href="style.css"><script src="script.js"></script>'+''.join('<section id="s'+str(i)+'"><h2>مهارة '+str(i)+'</h2><p>مثال على بيانات السيرة الذاتية</p></section>\n' for i in range(300)),
 'style.css':'body{font-family:sans-serif}'+''.join('.skill-'+str(i)+'{padding:'+str(i%30)+'px}\n' for i in range(200)),
 'script.js':'\n'.join('function value'+str(i)+'(){return '+str(i)+';}' for i in range(120))},0)
python=fixtures.create('Large Python fixture','دوال حسابية ثابتة للاختبار','python')['project_id']
fixtures.commit(python,{'main.py':'\n'.join('def value_'+str(i)+'():\n    return '+str(i)+'\n' for i in range(300))},0)
started=time.monotonic();tokenizer=Llama(model_path=str(args.gguf),vocab_only=True,n_gpu_layers=0,n_ctx=512,verbose=False)
report={'version':VERSION,'ids':['N058','N059'],'tokenizer':args.gguf.name,'mode':'vocab_only, CPU; no model generation','tokenizer_setup_s':round(time.monotonic()-started,3),'actual_metadata_generation_calls':0,'cases':[],'notes':['Summary/full-source counts are hypothetical input sizes for these fixtures; full-source contexts were not sent to a model.','Basic metadata answers and maintenance bypass generation. See the separately recorded actual API/model-residency trial.']}
try:
 for source,store,projects in [('actual_generated',actual,actual.list()),('deterministic_large_fixture',fixtures,fixtures.list())]:
  for meta in projects:
   if meta['generation_status'] not in ('completed','idle'):continue
   meta=store.get(meta['project_id']);files=store.committed_files(meta['project_id']);summary=meta['summary']
   full='\n'.join('FILE '+path+'\n'+body for path,body in files.items() if isinstance(body,str))
   assert len(summary)<=3500
   for question in ('ما هو هذا المشروع؟','ما هي لغات المشروع؟','لماذا أنشئ هذا المشروع؟'):
    answer=store.answer(meta['project_id'],question);assert not answer['model_called'] and not answer.get('stale')
    source_tokens=len(tokenizer.tokenize((full+'\n'+question).encode(),add_bos=False));summary_tokens=len(tokenizer.tokenize((summary+'\n'+question).encode(),add_bos=False))
    report['cases'].append({'fixture_source':source,'project_type':meta['type'],'project_id':meta['project_id'],'question':question,'files':len(files),'summary_characters':len(summary),'full_source_context_tokens':source_tokens,'summary_context_tokens_if_used':summary_tokens,'actual_metadata_question_model_input_tokens':0,'deterministic_summary_maintenance_model_tokens':0})
 args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
 print(json.dumps({'cases':len(report['cases']),'full_token_range':[min(x['full_source_context_tokens'] for x in report['cases']),max(x['full_source_context_tokens'] for x in report['cases'])],'summary_token_range':[min(x['summary_context_tokens_if_used'] for x in report['cases']),max(x['summary_context_tokens_if_used'] for x in report['cases'])],'generation_calls':0}))
finally:tokenizer.close();actual.close();fixtures.close()
