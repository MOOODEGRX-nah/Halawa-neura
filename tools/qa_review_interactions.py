"""Actual renderer replay of recorded rejected candidates and compiled contracts."""
import argparse,json,threading,time
from pathlib import Path
from src.core.candidate_browser import check_candidate
from src.core.required_interactions import compile_theme,theme_contract
from src.core.project_validation import inspect_files
from src.core.project_files import ProjectError
from src.core.contrast_repair import repair_contrast
from src.core.feature_intent import build_contract,contract_features
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
results=[]
def run(name,files,expected,contract=False,repair=False,removed=False):
    history=[{'origin':'user_request','text':'أضف زر تسجيل دخول'}]
    if removed:history.append({'origin':'user_request','text':'أضف الوضع الداكن'})
    feature_contract=build_contract('احذف الوضع الداكن' if removed else 'هل يمكنك أن تضيف الوضع الداكن؟',history,{'intent':'project.edit','resolution_source':'controlled renderer fixture'})
    required={**contract_features(feature_contract),'feature_contract':feature_contract,'removed_features':['theme'] if removed else []}
    if contract:required['interaction']=theme_contract()
    reports=[];actual=False
    for attempt in range(2 if repair else 1):
        try:
            report=check_candidate(files,inspect_files(files)[1],threading.Event(),time.monotonic()+35,required=required);actual=True
            assert report['required_feature_contract']==feature_contract
            reports.append(report);break
        except ProjectError as exc:
            report=getattr(exc,'browser_report',{'errors':[str(exc)]});reports.append(report)
            if attempt==0 and repair:
                fixed=repair_contrast(files,'index.html',report,'Preserve dark mode')
                if fixed:
                    files,receipt=fixed;reports.append({'repair':receipt});continue
            break
    result={'case':name,'accepted':actual,'expected':expected,'passed':actual==expected,'reports':reports,'files':files}
    results.append(result);(a.output/'results.json').write_text(json.dumps({'environment':'Actual Qt offscreen; recorded source fixtures; no model inference','results':results},ensure_ascii=False,indent=2));print(name,result['passed'],flush=True)
for fixture in sorted((Path(__file__).parents[1]/'tests/fixtures/ax07_review').glob('*.json')):
    data=json.loads(fixture.read_text())
    run(fixture.stem+'-original-failure',data['rejected'],False)
    compiled,_=compile_theme(data['base'],'index.html')
    run(fixture.stem+'-compiled',compiled,True,True,True)
    disconnected={p:s.replace('root.setAttribute(state,dark?"dark":"light")','root.setAttribute("unrelated-state",dark?"dark":"light")') for p,s in compiled.items()}
    run(fixture.stem+'-disconnected-state',disconnected,False,True)
    for mode,extra in [('hidden-control','display:none!important'),('pointer-blocked-control','pointer-events:none!important')]:
        blocked={p:s.replace('</head>','<style>#neura-theme-toggle{'+extra+'}</style></head>') for p,s in compiled.items()}
        run(fixture.stem+'-'+mode,blocked,False,True,True)
    disabled={p:s.replace('id="neura-theme-toggle"','disabled id="neura-theme-toggle"') for p,s in compiled.items()}
    run(fixture.stem+'-disabled-control',disabled,False,True,True)
    run(fixture.stem+'-removed-but-visible',compiled,False,False,False,True)
    run(fixture.stem+'-removed',data['base'],True,False,False,True)
raise SystemExit(0 if all(r['passed'] for r in results) else 1)
