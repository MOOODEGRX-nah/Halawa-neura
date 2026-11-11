"""Actual isolated Qt replay of the recorded native legacy-theme regression."""
import argparse,json,threading,time
from pathlib import Path
from src.core.candidate_browser import check_candidate
from src.core.contrast_repair import repair_contrast
from src.core.project_validation import inspect_files
from src.core.project_files import ProjectError
from src.core.edit_preservation import require_preserved
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
f=json.loads((Path(__file__).parents[1]/'tests/fixtures/compound_review/large-lost-theme-surface.json').read_text());rows=[]
required={'login':True,'theme':True,'feature_contract':f['contract']}
def run(name,files,expected):
    try:
        report=check_candidate(files,inspect_files(files)[1],threading.Event(),time.monotonic()+35,required=required);accepted=True
    except ProjectError as exc:report=getattr(exc,'browser_report',{'errors':[str(exc)]});accepted=False
    rows.append({'case':name,'accepted':accepted,'expected':expected,'passed':accepted==expected,'report':report});(a.output/'results.json').write_text(json.dumps({'environment':'Actual isolated Qt, recorded native source; no new model inference','results':rows},ensure_ascii=False,indent=2));print(name,accepted==expected,flush=True)
    return report
report=run('original-native-failure',f['candidate'],False)
fixed,receipt=repair_contrast(f['candidate'],'index.html',report,'Preserve dark mode')
assert require_preserved(f['before'],fixed,f['request'],f['contract'])['status']=='passed'
(a.output/'repair.json').write_text(json.dumps({'files':fixed,'receipt':receipt},ensure_ascii=False,indent=2))
run('measured-surface-repair',fixed,True)
blocked={**fixed,'index.html':fixed['index.html'].replace('<button>Login</button>','<button style="display:none">Login</button>')}
run('hidden-login-still-rejected',blocked,False)
raise SystemExit(0 if all(r['passed'] for r in rows) else 1)
