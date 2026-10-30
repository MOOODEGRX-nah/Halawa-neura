"""Review follow-ups using one existing actual QA backend; never starts another."""
import argparse,json,re,sys,time,unicodedata,urllib.request
from argparse import Namespace
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_neura import Run
from verification.live import Client,require_actual

def colors(text):
    text=''.join(c for c in unicodedata.normalize('NFKD',text).casefold() if not unicodedata.combining(c))
    names={'red':['احمر','red'],'blue':['ازرق','blue'],'green':['اخضر','green'],'yellow':['اصفر','yellow'],'black':['اسود','black'],'white':['ابيض','white']}
    return {name for name,terms in names.items() if any(term in text for term in terms)}

def matched_native_inputs(left,right):
    fields=['model_id','model_path','projector','device','n_ctx','chat_template_sha256','messages_sha256','options_sha256','image_sha256']
    return {key:left[key]==right[key] for key in fields}

def vision_pair(run,client,ui_trace,ui_output,expected):
    path=Path(ui_trace).resolve();assert path.is_relative_to(run.out/'artifacts/model-traces')
    trace=json.loads(path.read_text());assert trace['environment'].startswith('actual packaged')
    assert [m['role'] for m in trace['messages']]==['system','user'],'Fresh UI history is required for this matched pair'
    options=trace['effective_options'];assert options['stream'] is True
    payload={'messages':trace['messages'][1:],'neura':{'tier':'vision','deep':False},'stream':True,
        **{k:options[k] for k in ('max_tokens','temperature','top_p')}}
    before={p.name for p in path.parent.glob('*.json')}
    request=urllib.request.Request(client.info['url']+'/v1/chat/completions',data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json','X-Neura-Token':client.token})
    pieces=[];finish=None;done=False;error=None;started=time.monotonic()
    with client.opener.open(request,timeout=930) as response:
        for raw in response:
            if not raw.startswith(b'data: '):continue
            if raw[6:].strip()==b'[DONE]':done=True;break
            value=json.loads(raw[6:]);error=value.get('error') or error
            for choice in value.get('choices',[]):
                pieces.append(choice.get('delta',{}).get('content') or '')
                finish=choice.get('finish_reason') or finish
    assert client.idle(900)
    after=[p for p in path.parent.glob('*.json') if p.name not in before];assert len(after)==1
    api=json.loads(after[0].read_text());answer=''.join(pieces)
    equality=matched_native_inputs(trace,api);matched=all(equality.values())
    ui_pass=colors(ui_output)==set(expected);api_pass=colors(answer)==set(expected) and finish=='stop' and done and not error
    evidence={'case':'vision_pair_'+path.stem,'request':payload,'expected_colors':expected,'ui_output':ui_output,'api_output':answer,
        'ui_colors':sorted(colors(ui_output)),'api_colors':sorted(colors(answer)),'ui_passed':ui_pass,'api_passed':api_pass,
        'native_input_equality':equality,'all_matched':matched,'ui_trace':str(path.relative_to(run.out)),
        'api_trace':str(after[0].relative_to(run.out)),'finish_reason':finish,'error':error,'api_duration_s':time.monotonic()-started,
        'sampling_note':'Same effective sampling configuration and no fixed seed in either path; stochastic outputs need not be identical. No retry of failed images.',
        'passed':matched and ui_pass and api_pass}
    dest=run.out/'artifacts'/('vision-pair-'+path.stem+'.json');dest.write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
    run.gate(['N093'],'REAL_MODEL','PASS' if evidence['passed'] else 'FAIL',evidence,[str(dest.relative_to(run.out)),str(path.relative_to(run.out)),str(after[0].relative_to(run.out))]);run.save()
    print(json.dumps({k:evidence[k] for k in ('passed','all_matched','ui_output','api_output','native_input_equality')},ensure_ascii=False,indent=2))
    return int(not evidence['passed'])

def required_plan(run,client):
    created=client.call('/projects',{'user_request':'اكتب برنامج Python بسيطًا يجمع رقمين في main.py مع خطة تنفيذ مختصرة. لا تنفّذ البرنامج.',
        'requirements':['A complete compact plan','main.py with add(a,b) returning a+b'],'required_files':['main.py'],'required_python_symbols':['add'],
        'background':True,'plan':True,'max_tokens':768})
    jid=created['job']['job_id'];end=time.monotonic()+930
    while time.monotonic()<end:
        job=client.call('/project-jobs/'+jid)
        if job['state'] in ('completed','failed','cancelled'):break
        time.sleep(.15)
    else:client.call('/project-jobs/'+jid+'/cancel',{});assert client.idle(900);raise TimeoutError('Required plan deadline')
    planning=next(s for s in job['stage_results'] if s['stage']=='planning')
    result=planning.get('result',{});accepted=result.get('accepted',False);generated=any(s['stage']=='generating' for s in job['stage_results'])
    completed=accepted and planning['status']=='completed' and result.get('finish_reason')=='stop'
    policy=(completed and generated) or (not accepted and planning['status']=='failed' and job['state']=='failed' and not job['saved_files'] and not generated)
    value={'case':'required_compact_plan','job':job,'policy_passed':bool(policy),'model_completed_plan':bool(completed),'job_artifacts_completed':job['state']=='completed','max_tokens':768,'automatic_plan_retries':0,'generated_program_executed':False}
    dest=run.out/'artifacts/required-plan.json';dest.write_text(json.dumps(value,ensure_ascii=False,indent=2))
    run.gate(['N041'],'REAL_MODEL','PASS' if policy else 'FAIL',value,['artifacts/required-plan.json'])
    run.gate(['N042'],'REAL_MODEL','PASS' if completed else 'FAIL',value,['artifacts/required-plan.json'])
    run.gate(['N006'],'REAL_MODEL','PASS' if completed and job['state']=='completed' else 'FAIL',value,['artifacts/required-plan.json']);run.save();print(json.dumps(value,ensure_ascii=False,indent=2))
    return int(not(completed and job['state']=='completed'))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True);p.add_argument('--target-root',required=True);p.add_argument('--case',choices=['required-plan','vision-pair'],required=True);p.add_argument('--ui-trace');p.add_argument('--ui-output');p.add_argument('--expected',nargs='+');p.add_argument('--allow-real-model',action='store_true');a=p.parse_args()
    if not a.allow_real_model:raise SystemExit('Real inference requires explicit --allow-real-model')
    run=Run(Namespace(target_root=a.target_root,vendor_dir=None,resume=a.run,profile_root=None,output_root=None));client=Client(run,json.loads((run.out/'artifacts/backend.json').read_text()));require_actual(client.info,'model')
    assert client.idle(900)
    raise SystemExit(required_plan(run,client) if a.case=='required-plan' else vision_pair(run,client,a.ui_trace,a.ui_output,a.expected))
