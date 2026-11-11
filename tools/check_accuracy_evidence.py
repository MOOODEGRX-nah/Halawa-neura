"""Validate recorded composer acceptance; never infer success from process exit."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def check_run(directory):
    directory=Path(directory)
    identity=json.loads((directory/'identity.json').read_text())
    data=json.loads((directory/'composer.json').read_text())
    workflow=identity['workflow'];turns=data['turns'];errors=[]
    def require(condition,message):
        if not condition:errors.append(message)
    require(identity['inference']=='real','Not real inference evidence')
    require(not any((directory/name).exists() for name in ('failure.json','interruption.json')),'Runner recorded an interruption')
    require(len(turns)=={'exact':6,'preserve':4,'plan':1,'proposal':4,'smoke':1,'large':1,'remove':1}[workflow],'Incomplete conversation')
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
            contract=(job.get('invoice') or {}).get('required_feature_contract')
            if contract:
                from src.core.feature_intent import validate_contract
                try:validate_contract(contract)
                except Exception as error:require(False,label+': invalid feature contract '+str(error))
                require(contract==receipt.get('required_feature_contract'),label+': receipt feature contract mismatch')
                require(contract==(job.get('validation') or {}).get('required_feature_contract'),label+': source-validation feature contract mismatch')
                require(contract==receipt.get('browser',{}).get('required_feature_contract'),label+': independent browser feature contract mismatch')
                require(contract==decisions[0].get('decision',{}).get('required_feature_contract'),label+': conversational feature contract mismatch')
                for stage in job.get('stage_results',[]):
                    if stage['stage'] in ('planning','generating'):
                        require(contract==stage.get('result',{}).get('required_feature_contract'),label+': stage feature contract mismatch '+stage['stage'])
                if workflow=='remove':
                    require(contract['prior_required'].get('login') and contract['prior_required'].get('theme'),label+': removal seed requirements absent')
                    require(contract['required']=={'theme':True},label+': removal did not retain only the accepted theme')
                    require(any(c['feature']=='login' and c['operation']=='remove' for c in contract['changes']),label+': explicit removal absent from contract')
                    require(turn.get('job_count')==1,label+': removal duplicated jobs')
                    samples=[sample for attempt in job.get('attempts',[]) if attempt.get('status')=='accepted' for sample in (attempt.get('browser') or {}).get('samples',[])]
                    require(bool(samples) and all(not any(re.search(r'login|sign.?in|دخول',c.get('label',''),re.I) for c in sample.get('controls',[])) for sample in samples),label+': removed Login still visible')
                    require(receipt.get('browser',{}).get('theme_changed'),label+': removal broke the remaining theme')
                if workflow=='preserve' and index>=1:require(contract['required'].get('login'),label+': accepted Login requirement lost')
                if workflow=='preserve' and index>=2:require(contract['required'].get('theme'),label+': accepted theme requirement lost')
                require(any(r.get('job_id')==job['job_id'] and r.get('feature_contract')==contract for r in project.get('accepted_requirements',[])),label+': persisted feature contract mismatch')

            if receipt.get('base_revision',0)>0 and 'src/core/bounded_edits.py' in identity.get('runtime_hashes',{}):
                operations=[o for stage in job.get('stage_results',[]) for o in stage.get('result',{}).get('operations',[])]
                require(bool(operations),label+': bounded edit operations absent')
                require(sum(o.get('output_tokens_charged',o['output_limit']) for o in operations)<=3072,label+': operation budget overflow')
                scopes={}
                for op in operations:
                    native=op.get('token_metrics') or {};usage=op.get('usage') or {};pre=op.get('preflight') or {}
                    require(op.get('finish_reason')=='stop',label+': incomplete patch accepted')
                    require(native.get('prompt_tokens')==pre.get('prompt_tokens')==usage.get('prompt_tokens'),label+': prompt metrics mismatch')
                    require(native.get('completion_tokens')==usage.get('completion_tokens'),label+': completion metrics mismatch')
                    require(native.get('effective_output_limit')==op['output_limit'],label+': output silently clipped')
                    require(native.get('prompt_tokens',99999)+op['output_limit']<=native.get('context_size',0),label+': context overflow')
                    table=op.get('scope_targets')
                    if table:
                        binding=table['binding']
                        require(binding.get('project_id')==pid and binding.get('job_id')==job['job_id'],label+': scoped IDs belong to another job/project')
                        require(binding.get('base_file_sha256')==op['source_sha256']==receipt.get('base_hashes',{}).get(op['path']),label+': scoped IDs base hash mismatch')
                        require(binding.get('scope_start_char')==op['source_start_char'] and binding.get('scope_end_char')==op['source_end_char'],label+': scoped IDs range mismatch')
                        require(table['source_hashes'].get(op['path'])==op['source_scope_sha256'],label+': scoped IDs source hash mismatch')
                        try:
                            patch=json.loads(op['output']);ids=[e['target_id'] for e in patch.get('target_edits',[])]
                            require(len(ids)==len(set(ids)) and set(ids)<=set(t['target_id'] for t in table['targets']),label+': duplicate or unissued scoped edit')
                            require(not patch.get('edits'),label+': legacy anchors accepted for scoped removal')
                        except (ValueError,KeyError,TypeError):require(False,label+': invalid scoped edit record')
                    scopes.setdefault(op['path'],[]).append(op)
                for path,parts in scopes.items():
                    cursor=0
                    for op in sorted(parts,key=lambda o:o['source_start_char']):
                        require(op['source_start_char']==cursor,label+': skipped/overlapping source segment '+path)
                        cursor=op['source_end_char']
                    require(cursor==parts[0]['source_size_chars'],label+': incomplete source coverage '+path)

            require(receipt.get('result_revision')==rev==receipt.get('base_revision',-2)+1,label+': revision mismatch')
        else:
            require(job['job_id'] in seen_jobs,label+': follow-up launched another job')
            require(turn['before']['projects']==projects,label+': status mutated project')
        require(receipt.get('preview_checked_revision')==rev,label+': preview receipt mismatch')
        require(receipt.get('browser',{}).get('status')=='passed',label+': browser checks failed')
        require(receipt.get('browser',{}).get('color_schemes')==['light','dark'],label+': light/dark embedding schemes not verified')
        require(str(rev) in turn['after']['preview'],label+': UI preview revision absent')
        hashes={f['path']:f['sha256'] for f in project['files']}
        require(receipt.get('result_hashes')=={name:hashes.get(name) for name in receipt.get('changed_files',[])},label+': committed hashes differ')
        for name,old_hash in receipt.get('base_hashes',{}).items():
            if name not in receipt.get('changed_files',[]):require(hashes.get(name)==old_hash,label+': unrelated file changed '+name)
        for name,source in turn.get('files',{}).get(pid,{}).items():
            if not source.get('binary'):
                require(hashlib.sha256(source['content'].encode()).hexdigest()==hashes.get(name),label+': saved content hash mismatch '+name)
        if workflow=='preserve' and index>=1:
            samples=[sample for attempt in job.get('attempts',[]) if attempt.get('status')=='accepted' for sample in (attempt.get('browser') or {}).get('samples',[])]
            require(bool(samples) and all(any(re.search(r'login|sign.?in|دخول',c.get('label',''),re.I) for c in sample.get('controls',[])) for sample in samples),label+': Login placeholder not visibly demonstrated')
        if workflow=='preserve' and index==3:
            css=[]
            for stage in job.get('stage_results',[]):
                for operation in stage.get('result',{}).get('operations',[]):
                    try:patch=json.loads(operation.get('output','{}'))
                    except ValueError:continue
                    rules=patch.get('css_rules') or ''
                    if isinstance(rules,list):css.extend(rule['selector']+'{'+''.join(p['name']+':'+p['value']+';' for p in rule['declarations'])+'}' for rule in rules)
                    else:css.append(rules)
                    if operation.get('path','').endswith('.css'):css.extend(e.get('after','') for e in patch.get('edits',[]))
            text='\n'.join(css)
            properties=set(re.findall(r'(?:^|[;{])\s*([a-zA-Z-]+)\s*:',text))
            selectors=re.findall(r'([^{}]+)\{',text)
            require(len(properties)>=5 and len(selectors)>=3,label+': substantial CSS redesign not demonstrated (5 properties / 3 selectors)')
        if workflow=='preserve' and index>=2:
            require(receipt.get('browser',{}).get('theme_changed') is True,label+': theme not demonstrated')
            samples=[sample for attempt in job.get('attempts',[]) if attempt.get('status')=='accepted' for sample in (attempt.get('browser') or {}).get('samples',[])]
            for scheme in ('light','dark'):
                initial={c['selector']:c['background'] for sample in samples if sample.get('color_scheme')==scheme and sample.get('width')==1280 and sample.get('mode')=='initial' for c in sample.get('checks',[])}
                toggled={c['selector']:c['background'] for sample in samples if sample.get('color_scheme')==scheme and sample.get('width')==1280 and sample.get('mode')=='toggled' for c in sample.get('checks',[])}
                require(any(initial[p]!=toggled[p] for p in initial.keys()&toggled.keys()),label+': actual theme surface change not demonstrated in '+scheme+' scheme')

            require(receipt.get('preservation',{}).get('status')=='passed',label+': preservation not checked')
    if workflow!='plan':
        durable={job['job_id']:job['state'] for turn in turns for job in turn.get('jobs',[])}
        for name in ['cards-before-restart.json','cards-restored.json']:
            path=directory/name
            require(path.exists(),'Missing terminal card evidence '+name)
            if path.exists():
                cards=json.loads(json.loads(path.read_text()).get('cards','[]'))
                require(bool(cards),'No correlated conversation cards')
                require(all(c.get('state') in ('completed','failed','cancelled') for c in cards),'Stale generating card')
                require(all(c.get('state')==durable.get(c.get('job_id')) for c in cards),'Card differs from durable job state')
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
