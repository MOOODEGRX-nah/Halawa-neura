"""Actual isolated Qt renderer checks with synthetic, non-model candidate fixtures."""
import argparse,json,threading,time
from pathlib import Path
from src.core.candidate_browser import check_candidate
from src.core.project_validation import inspect_files
from src.core.project_files import ProjectError
from src.core.contrast_repair import repair_contrast
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
body='<h1>QA CV</h1><p>Original content</p><a href="#" id="login">Login</a>'
base='<html><body style="color:#111;background:white">'+body+'</body></html>'
cases=[('readable',base,True),
 ('uppercase_visible',base.replace('color:#111;background:white','color:#111;background:white;text-transform:uppercase'),True),
 ('uppercase_hidden',base.replace('color:#111;background:white','color:#111;background:white;text-transform:uppercase').replace('id="login"','id="login" style="display:none"'),False),
 ('required_theme_absent',base,False),
 ('required_login_absent',base.replace('<a href="#" id="login">Login</a>',''),False),
 ('black_on_dark',base.replace('color:#111;background:white','color:black;background:#222'),False),
 ('hidden_login',base.replace('id="login"','id="login" style="display:none"'),False),
 ('overflow',base.replace('<h1>','<h1 style="width:1500px">'),False),
 ('noop_theme',base.replace('</body>','<button id="theme">Dark mode</button></body>'),False),
 ('complex_background',base.replace('background:white','background:linear-gradient(white,black)'),False),
 ('dark_white_surface',base.replace('color:#111;background:white','color:#111;background:white').replace('<h1>','<div style="background:white"><h1>').replace('</body>',"</div><style>body.dark{color:#eee!important}</style><button id='theme'>Dark mode</button><script>document.querySelector('#theme').onclick=()=>document.body.classList.toggle('dark')</script></body>"),False),
 ('working_theme',base.replace('</body>',"<button id='theme'>Toggle theme</button><script>document.querySelector('#theme').onclick=()=>{document.body.style.color='white';document.body.style.background='#111';document.querySelector('#login').style.color='#aaf'}</script></body>"),True)]
results=[]
for name,html,accepted in cases:
 files={'index.html':html};preview=inspect_files(files)[1]
 try:
  report=check_candidate(files,preview,threading.Event(),time.monotonic()+35,required={'controls':[] if name=='required_login_absent' else [{'tag':'a','href':'#','id':'login','label':'Login'}],'text':['Original content'],'theme':name=='required_theme_absent','login':name=='required_login_absent'})
  actual=True
 except ProjectError as exc:
  report={'error':str(exc)};actual=False
  corrected=repair_contrast(files,'index.html',getattr(exc,'browser_report',None),'Improve readability and preserve dark mode')
  if corrected:
   fixed,receipt=corrected
   report['repair']=receipt
   report['rechecked']=check_candidate(fixed,inspect_files(fixed)[1],threading.Event(),time.monotonic()+35,required={'controls':[] if name=='required_login_absent' else [{'tag':'a','href':'#','id':'login','label':'Login'}],'text':['Original content'],'theme':name=='required_theme_absent','login':name=='required_login_absent'})
 if name=='dark_white_surface':assert report.get('rechecked',{}).get('status')=='passed' and report['rechecked'].get('theme_changed'),report
 results.append({'case':name,'expected_accepted':accepted,'accepted':actual,'passed':actual==accepted,'report':report})
 (a.output/'results.json').write_text(json.dumps({'environment':'actual Qt offscreen, sandboxed static JavaScript; synthetic source; no inference','results':results},ensure_ascii=False,indent=2))
 print(name,actual==accepted,flush=True)
raise SystemExit(0 if all(x['passed'] for x in results) else 1)
