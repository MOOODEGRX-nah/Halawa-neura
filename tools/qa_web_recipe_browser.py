"""Actual isolated Qt checks of positive/negative offline CV recipe fixtures."""
import json,time,threading,argparse
from pathlib import Path
from src.core.project_validation import inspect_files
from src.core.candidate_browser import check_candidate
from src.core.project_files import ProjectError
from src.tools.web_recipes import ID
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
source=json.loads((Path(__file__).resolve().parents[1]/'tests/fixtures/web_cv.json').read_text());rows=[]
for case,change,expected in [('working',{},True),('empty-script',{'script.js':''},False),('fake-state-only',{'script.js':"const b=document.getElementById('cv-font-toggle');b.addEventListener('click',()=>b.setAttribute('aria-pressed',String(b.getAttribute('aria-pressed')!=='true')));"},False),('missing-css-state',{'style.css':source['style.css'].replace('body.cv-large-text main p {font-size:1.25rem}','')},False)]:
 files={**source,**change};preview=inspect_files(files)[1];report=None
 try:report=check_candidate(files,preview,threading.Event(),time.monotonic()+45,required={'web_recipe':ID});passed=True
 except ProjectError as e:passed=False;report=getattr(e,'browser_report',{'error':str(e)})
 (a.output/(case+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2));rows.append({'case':case,'browser_accepted':passed,'expected':expected,'passed':passed==expected,'environment':'actual isolated Qt renderer; fixed fixture, NO model inference'})
(a.output/'results.json').write_text(json.dumps(rows,indent=2));assert all(r['passed'] for r in rows),rows
print(json.dumps(rows,indent=2))
