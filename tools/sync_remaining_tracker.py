"""Import the user-supplied plan without closing tasks or promoting deferred work."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PLAN=ROOT/'docs/Neura_Remaining_Tasks_Implementation_EN_2026-10-29.md'
OUT=ROOT/'docs/REMAINING_TRACKER.json'
text=PLAN.read_text();previous=json.loads(OUT.read_text()) if OUT.exists() else {}
old={item['id']:item for item in previous.get('active',[])}
active=[]
for match in re.finditer(r'^## (N\d{3}) — (.+)\n([\s\S]*?)(?=^## N\d|^# |\Z)',text,re.M):
 identifier,title,body=match.groups()
 phase=re.findall(r'^# (P\d+) —',text[:match.start()],re.M)[-1]
 approach,acceptance=body.split('Acceptance:',1)
 item={'id':identifier,'phase':phase,'title':title,'approach':approach.strip(),'acceptance':acceptance.strip(),
       'status':'verification_pending' if int(phase[1:])<=4 else 'backlog_verify_first',
       'code_paths':[],'evidence':[],'remaining_limitation':'Acceptance not yet mapped to current evidence.', 'next_action':'Verify and reuse existing implementation before editing.'}
 prior=old.get(identifier,{})
 if all(prior.get(key)==item[key] for key in ('phase','title','approach','acceptance')):
  item.update({key:value for key,value in prior.items() if key not in ('id','phase','title','approach','acceptance')})
 active.append(item)
def extensions(section):
 data=text.split(section,1)[1].split('\n# ',1)[0]
 return [{'id':m[0],'description':m[1],'status':'deferred' if 'DEFERRED' in section else 'superseded'} for m in re.findall(r'^- (N\d{3}): (.+)$',data,re.M)]
deferred=extensions('# DEFERRED EXTENSIONS');superseded=extensions('# SUPERSEDED ITEMS')
assert len(active)==len({x['id'] for x in active})==80
assert len(deferred)==10 and len(superseded)==2
result={**previous,'schema_version':1,'source_plan':str(PLAN.relative_to(ROOT)),'source_sha256':hashlib.sha256(PLAN.read_bytes()).hexdigest(),
        'first_delivery_ids':[x['id'] for x in active if int(x['phase'][1:])<=4], 'active':active,'deferred':deferred,'superseded':superseded}
OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'active':len(active),'first_delivery':len(result['first_delivery_ids']),'deferred':len(deferred),'superseded':len(superseded)}))
