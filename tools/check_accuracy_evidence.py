"""Validate recorded composer acceptance; never infer success from process exit."""
import argparse
import hashlib
import json
from pathlib import Path


def check_run(directory):
    directory=Path(directory)
    identity=json.loads((directory/'identity.json').read_text())
    data=json.loads((directory/'composer.json').read_text())
    workflow=identity['workflow'];turns=data['turns'];errors=[]
    def require(condition,message):
        if not condition:errors.append(message)
    require(identity['inference']=='real','Not real inference evidence')
    require(not (directory/'failure.json').exists(),'Runner recorded an interruption')
    require(len(turns)=={'exact':6,'preserve':4,'plan':1,'proposal':4,'smoke':1}[workflow],'Incomplete conversation')
    project_id=None;seen_jobs=set()
    for index,turn in enumerate(turns):
        label=f'turn {index+1}'
        decisions=turn['dispatch']
        require(len(decisions)==1,label+': expected one dispatch')
        if not decisions:continue
        if workflow=='plan':
            plan=decisions[0].get('planning',{})
            require(decisions[0]['kind']=='plan' and plan.get('accepted'),label+': plan rejected')
            require(plan.get('finish_reason')=='stop',label+': incomplete plan')
            steps=plan.get('plan',{}).get('steps',[])
            require(len(steps)==3 and all(any('\u0600'<=c<='\u06ff' for c in step) for step in steps),label+': not three Arabic steps')
            require(not turn['jobs'] and not turn['after']['projects'],label+': planning wrote projects')
            continue
        projects=turn['after']['projects']
        require(len(projects)==1,label+': project count differs')
        if len(projects)!=1:continue
        project=projects[0];pid=project['project_id']
        if project_id is None:project_id=pid
        require(pid==project_id,label+': wrong project')
        action=(index in (0,2)) if workflow=='proposal' else (workflow=='preserve' or index in (0,1,5))
        require(decisions[0]['kind']==('project' if action else 'proposal' if workflow=='proposal' and index==1 else 'status'),label+': unexpected routing')
        if workflow=='proposal':
            require(turn.get('job_count')==(1 if index<2 else 2),label+': duplicate or missing approval job')
            if index==1:
                require(any(p['state']=='pending' and p['project_id']==pid for p in turn.get('proposals',[])),label+': no real pending proposal')
                require(turn['before']['projects']==projects,label+': proposal mutated source')
            if index==2:
                require(decisions[0].get('proposal_id')==turns[1]['dispatch'][0].get('proposal_id'),label+': wrong accepted proposal')
        jobs=turn['jobs'];require(len(jobs)==1,label+': missing job')
        if len(jobs)!=1:continue
        job=jobs[0];receipt=job.get('execution') or {};rev=project['project_revision']
        if action:
            require(job['job_id'] not in seen_jobs,label+': reused old job')
            seen_jobs.add(job['job_id'])
            planning=[s for s in job.get('stage_results',[]) if s['stage']=='planning' and s.get('result',{}).get('accepted')]
            require(bool(planning),label+': validated planning absent')
            require(job['state']=='completed' and receipt.get('outcome')=='saved',label+': edit not saved')
            require(bool(receipt.get('changed_files')),label+': no changed files')
            require(receipt.get('result_revision')==rev==receipt.get('base_revision',-2)+1,label+': revision mismatch')
        else:
            require(job['job_id'] in seen_jobs,label+': follow-up launched another job')
            require(turn['before']['projects']==projects,label+': status mutated project')
        require(receipt.get('preview_checked_revision')==rev,label+': preview receipt mismatch')
        require(receipt.get('browser',{}).get('status')=='passed',label+': browser checks failed')
        require(str(rev) in turn['after']['preview'],label+': UI preview revision absent')
        hashes={f['path']:f['sha256'] for f in project['files']}
        require(receipt.get('result_hashes')=={name:hashes.get(name) for name in receipt.get('changed_files',[])},label+': committed hashes differ')
        for name,old_hash in receipt.get('base_hashes',{}).items():
            if name not in receipt.get('changed_files',[]):require(hashes.get(name)==old_hash,label+': unrelated file changed '+name)
        for name,source in turn.get('files',{}).get(pid,{}).items():
            if not source.get('binary'):
                require(hashlib.sha256(source['content'].encode()).hexdigest()==hashes.get(name),label+': saved content hash mismatch '+name)
        if workflow=='preserve' and index>=2:
            require(receipt.get('browser',{}).get('theme_changed') is True,label+': theme not demonstrated')
            require(receipt.get('preservation',{}).get('status')=='passed',label+': preservation not checked')
    if workflow!='plan':
        for name in ['cards-before-restart.json','cards-restored.json']:
            path=directory/name
            require(path.exists(),'Missing terminal card evidence '+name)
            if path.exists():
                cards=json.loads(json.loads(path.read_text()).get('cards','[]'))
                require(bool(cards),'No correlated conversation cards')
                require(all(c.get('state') in ('completed','failed','cancelled') for c in cards),'Stale generating card')
        restart_path=directory/'restart.json'
        require(restart_path.exists(),'Restart evidence absent')
        if restart_path.exists():
            restart=json.loads(restart_path.read_text())
            require(restart.get('same_project') and restart.get('same_files'),'Restart lost project/files')
    return {'run':directory.name,'workflow':workflow,'passed':not errors,'errors':errors,
            'environment':data['environment'],'turns':len(turns),'distinct_jobs':len(seen_jobs),
            'limits':['Recorded revision label plus isolated candidate renderer; not native KDE observation',
                      'Sampled contrast and known controls; not full behavioral/aesthetic certification']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('runs',nargs='+',type=Path);p.add_argument('--output',type=Path)
    args=p.parse_args();results=[]
    for run in args.runs:
        try:results.append(check_run(run))
        except (OSError,ValueError,KeyError,TypeError) as error:results.append({'run':run.name,'passed':False,'errors':[str(error)]})
    rendered=json.dumps(results,ensure_ascii=False,indent=2)
    if args.output:args.output.write_text(rendered+'\n')
    print(rendered);raise SystemExit(0 if all(r['passed'] for r in results) else 1)
