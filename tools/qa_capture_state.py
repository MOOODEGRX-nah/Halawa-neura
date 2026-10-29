"""Read-only evidence capture for an explicitly selected disposable QA profile.

Never copies API tokens; API reads and immutable revision reads only.
"""
import argparse,hashlib,json,sqlite3,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlencode

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--info',type=Path,required=True);p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
info=json.loads(a.info.read_text());root=a.data.resolve();token=(root/'data/.api-token').read_text().strip()
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def get(path,raw=False):
    req=urllib.request.Request(info['url']+path,headers={'X-Neura-Token':token})
    with opener.open(req,timeout=10) as response:
        value=response.read()
    return value.decode() if raw else json.loads(value)
workspace=root/'data/workspace'
with sqlite3.connect('file:'+str(workspace/'catalog.sqlite3')+'?mode=ro',uri=True) as db:
    jobs=[r[0] for r in db.execute('SELECT id FROM jobs ORDER BY created')]
    directories=dict(db.execute('SELECT id,directory FROM projects'))
projects=[get('/projects/'+item['project_id']) for item in get('/projects')['projects']]
report={'captured_at':datetime.now(timezone.utc).isoformat(),'environment':info,
        'health':get('/health'),'stats':get('/stats'),'projects':projects,
        'jobs':[],'files':{},'history':get('/skills/history')}
for project in report['projects']:
    pid=project['project_id'];report['files'][pid]={entry['path']:get('/projects/'+pid+'/file?'+urlencode({'path':entry['path']})) for entry in project['files']}
for jid in jobs:
    job=get('/project-jobs/'+jid)
    if job['state'] in ('completed','failed','cancelled'):
        events=[json.loads(line[6:]) for line in get('/project-jobs/'+jid+'/events',raw=True).splitlines() if line.startswith('data: ')]
        job['captured_events']=events
        seq=[event['seq'] for event in events]
        job['events_contiguous']=bool(seq) and seq==list(range(seq[0],seq[-1]+1))
    refs=[]
    for saved in job.get('saved_files',[]):
        directory=(workspace/directories[saved['project_id']]).resolve()
        assert directory.is_relative_to(workspace)
        snapshot=json.loads((directory/'.neura/revisions'/str(saved['revision'])).with_suffix('.json').read_text())
        content=snapshot['files'][saved['path']]
        if isinstance(content,str):refs.append(hashlib.sha256(content.encode()).hexdigest()==saved['sha256'])
    job['saved_refs_match_immutable_revisions']=all(refs) if refs else None
    report['jobs'].append(job)
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({'projects':[(p['project_id'],p['project_revision'],p['source_freshness']) for p in report['projects']],
 'jobs':[(j['job_id'],j['state'],j.get('events_contiguous'),j['saved_refs_match_immutable_revisions']) for j in report['jobs']],
 'model':report['stats']['current_model'],'requests':report['stats']['totals']['requests']},ensure_ascii=False))
