#!/usr/bin/env python3
"""Repeatable 109-item verification. Exit 0=selected checks passed, 1=failed,
3=incomplete/blocked. A contract pass never substitutes for real acceptance.

Run with `python tools/verify_neura.py --suite all --target-root /opt/neura-ai/app`.
No installations, releases, messages, downloads or production-data mutations.
"""
import argparse
import ast
from collections import Counter
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import subprocess
import sys
import time
import uuid
import zipfile
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

REPO=Path(__file__).resolve().parents[1]
HERE=Path(__file__).resolve().parent
CATALOG=HERE/'verification/catalog.json'
METHODS={'SOURCE','STATIC','CONTRACT_FAKE','UI_FIXTURE','REAL_MODEL','REAL_DESKTOP','PACKAGE','ADMIN_TRANSACTION','AUDIO_PLAYBACK'}
RESULTS={'PASS','FAIL','BLOCKED','NOT_RUN','NOT_APPLICABLE'}


def now():return datetime.now(ZoneInfo('Asia/Riyadh')).isoformat()
def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()
def command(args,cwd=REPO):
    return subprocess.check_output(args,cwd=cwd,text=True,stderr=subprocess.DEVNULL,timeout=10).strip()


def safe_root(path):
    p=Path(path).expanduser().resolve()
    forbidden=[Path.home()/'.local/share/neura-ai',Path.home()/'.config/neura-ai',Path.home()/'.local/state/neura-ai',Path('/opt/neura-ai')]
    for key,default in [('XDG_DATA_HOME','.local/share'),('XDG_CONFIG_HOME','.config'),('XDG_STATE_HOME','.local/state')]:
        forbidden.append(Path(os.environ.get(key,Path.home()/default)).resolve()/'neura-ai')
    if any(p==x or p.is_relative_to(x) or x.is_relative_to(p) for x in forbidden):
        raise ValueError('QA path overlaps production or installed data: '+str(p))
    return p


def load_catalog():
    rows=json.loads(CATALOG.read_text())
    assert len(rows)==109 and {r['task_id'] for r in rows}=={f'N{i:03}' for i in range(1,110)}
    assert len({r['task_id'] for r in rows})==109
    return rows


def case(identifier,result,method,observed=None,artifacts=(),steps=(),limitation='',required=False):
    if result not in RESULTS or method not in METHODS:raise ValueError('Invalid evidence enum')
    return {'case_id':identifier,'case_result':result,'evidence_method':method,'required':required,
            'command_or_steps':list(steps),'artifacts':list(artifacts),'observed':observed,'limitation':limitation,'recorded_at':now()}


def summarize(requirements):
    features=Counter(r['feature_state'] for r in requirements)
    methods={m:dict(Counter(c['case_result'] for r in requirements for c in r['cases'] if c['evidence_method']==m)) for m in sorted(METHODS)}
    required_methods={m:dict(Counter(c['case_result'] for r in requirements for c in r['cases'] if c['required'] and c['evidence_method']==m)) for m in sorted(METHODS)}
    historical=Counter(c['case_result'] for r in requirements for c in r['cases'] if c.get('historical_attempt'))
    active=[r for r in requirements if r['feature_state'] not in ('DEFERRED','SUPERSEDED')]
    # An absent feature and a missing real trial keep acceptance incomplete.
    failed=any(c['required'] and c['case_result']=='FAIL' for r in active for c in r['cases'])
    incomplete=any(r['feature_state'] in ('PARTIAL','MISSING','UNKNOWN') or not r.get('acceptance_reviewed',False) or any(c['required'] and c['case_result'] not in ('PASS','NOT_APPLICABLE') for c in r['cases']) for r in active)
    complete=[r['task_id'] for r in active if r['feature_state']=='IMPLEMENTED' and r.get('acceptance_reviewed',False) and all(c['case_result']=='PASS' for c in r['cases'] if c['required']) and any(c['required'] for c in r['cases'])]
    return {'requirements':109,'implementation_states':dict(features),'case_results_by_method':methods,
            'current_required_case_results_by_method':required_methods,'retained_historical_case_results':dict(historical),
            'accepted_requirement_ids':complete,'acceptance':'FAILED' if failed else 'INCOMPLETE' if incomplete else 'PASSED',
            'acceptance_exit_code':1 if failed else 3 if incomplete else 0}


class Run:
    def __init__(self,args):
        self.args=args;self.target=Path(args.target_root).resolve();self.vendor=Path(args.vendor_dir).resolve() if args.vendor_dir else self.target.parent/'vendor'
        if not (self.target/'src/backend/api.py').is_file():raise ValueError('Selected target is not an application root')
        if args.resume:
            self.out=safe_root(args.resume);self.result=json.loads((self.out/'results.json').read_text())
            if self.result['target_root']!=str(self.target):raise ValueError('Resume target mismatch')
            self.profile=safe_root(self.result['profile_root'])
            if json.loads((self.profile/'.neura-verification-profile').read_text())['run_id']!=self.result['run_id']:raise ValueError('QA marker mismatch')
        else:
            run_id=datetime.now(ZoneInfo('Asia/Riyadh')).strftime('%Y%m%dT%H%M%S')+'_'+uuid.uuid4().hex[:8]
            self.out=safe_root(args.output_root)/run_id;self.out.mkdir(parents=True,exist_ok=False)
            self.profile=safe_root(args.profile_root)/run_id if args.profile_root else self.out/'profile'
            self.profile.mkdir(parents=True,exist_ok=False)
            (self.profile/'.neura-verification-profile').write_text(json.dumps({'run_id':run_id,'created_at':now()}))
            rows=[]
            for item in load_catalog():
                row={**item,'cases':[],'acceptance_reviewed':False}
                for method in item['required_evidence']:
                    row['cases'].append(case('acceptance_'+method.lower(),'NOT_RUN',method,limitation='لم يُنفذ دليل القبول المطلوب في هذه الجولة بعد.',required=True))
                if not item['required_evidence']:row['cases'].append(case('scope','NOT_APPLICABLE','SOURCE',limitation='مؤجل أو ملغى؛ لا يُفعّل أثناء التدقيق.'))
                rows.append(row)
            self.result={'schema_version':1,'run_id':run_id,'started_at':now(),'source':self.git_identity(),
                'target_root':str(self.target),'target_version':(self.target/'VERSION').read_text().strip(),
                'installed_version':self.installed(),'profile_kind':'qa','profile_root':str(self.profile),
                'requirements':rows,'executions':[],'screenshots':[],'deviations':[]}
        for name in ('logs','screenshots','artifacts'): (self.out/name).mkdir(exist_ok=True)
        self.by_id={r['task_id']:r for r in self.result['requirements']}
        self.env={**os.environ,'PYTHONPATH':os.pathsep.join([str(self.target),str(self.vendor)]),
            'NEURA_DATA_DIR':str(self.profile/'data'),'NEURA_SETTINGS_DIR':str(self.profile/'config'),
            'NEURA_STATE_DIR':str(self.profile/'state'),'NEURA_TEST_TARGET_ROOT':str(self.target),
            'NEURA_VERIFY_IMPORT_REPORT':str(self.out/'artifacts/contract-imports.json'),'PYTHONDONTWRITEBYTECODE':'1'}
        for key in ('QTWEBENGINE_DISABLE_SANDBOX','QTWEBENGINE_CHROMIUM_FLAGS','NEURA_TOKEN','NEURA_INSTANCE_ID'):self.env.pop(key,None)
        self.save()

    @staticmethod
    def installed():
        try:return command(['pacman','-Q','neura-ai-bin'])
        except (OSError,subprocess.SubprocessError):return 'unknown'
    @staticmethod
    def git_identity():
        return {'checkout':str(REPO),'branch':command(['git','branch','--show-current']),
                'commit':command(['git','rev-parse','HEAD']),'dirty':bool(command(['git','status','--porcelain'])),
                'changes':command(['git','status','--short']).splitlines()}
    def add(self,ids,c):
        for identifier in ids:
            row=self.by_id[identifier]
            row['cases']=[old for old in row['cases'] if old['case_id']!=c['case_id']]+[dict(c)]
    def gate(self,ids,method,result,observed,artifacts=(),limitation=''):
        for identifier in ids:
            if self.by_id[identifier]['feature_state'] not in ('DEFERRED','SUPERSEDED'):
                row=self.by_id[identifier]
                required=method in row['required_evidence']
                placeholder='acceptance_'+method.lower()
                row['cases']=[c for c in row['cases'] if c['case_id']!=placeholder or c['observed'] is not None]
                if result in ('PASS','FAIL') and artifacts:
                    for old in row['cases']:
                        if old['evidence_method']==method and old['case_result']=='BLOCKED' and not old['artifacts']:
                            old['required']=False;old['historical_attempt']=True
                label=observed.get('name',observed.get('case')) if isinstance(observed,dict) else None
                key=placeholder+'_'+hashlib.sha256(json.dumps([list(artifacts),label]).encode()).hexdigest()[:10]
                self.add([identifier],case(key,result,method,observed,artifacts,limitation=limitation,required=required))
    def save(self):
        self.result['updated_at']=now();self.result['source_after']=self.git_identity();self.result['summary']=summarize(self.result['requirements'])
        (self.out/'results.json').write_text(json.dumps(self.result,ensure_ascii=False,indent=2)+'\n')
        self.report()
    def report(self):
        r=self.result;s=r['summary'];lines=['# تقرير التحقق الحالي — Neura',f"الجولة `{r['run_id']}` · {r['started_at']}",
            f"النتيجة الكاملة: **{s['acceptance']}**. كود قبول الكتالوج: {s['acceptance_exit_code']}. هذا مستقل عن نجاح suite مختارة.",
            f"النسخة المستهدفة `{r['target_version']}` من `{r['target_root']}`؛ المثبتة `{r['installed_version']}`.",
            f"المصدر `{r['source']['branch']}` / `{r['source']['commit']}`؛ dirty عند البدء: {r['source']['dirty']}.",
            f"المصدر الحالي `{r.get('source_after',r['source'])['branch']}` / `{r.get('source_after',r['source'])['commit']}`؛ dirty الآن: {r.get('source_after',r['source'])['dirty']}.",
            'الحالات: `IMPLEMENTED/PARTIAL/MISSING/UNKNOWN` تصف التنفيذ؛ `PASS/FAIL/BLOCKED/NOT_RUN` تصف الأدلة. لا يحول فحص المصدر أو المحاكي إلى قبول حقيقي.',
            '## أعداد التنفيذ',json.dumps(s['implementation_states'],ensure_ascii=False),'## أعداد الأدلة المسجلة، بما فيها المحاولات التاريخية', '```json',json.dumps(s['case_results_by_method'],ensure_ascii=False,indent=2),'```',
            '## الأدلة المطلوبة الحالية فقط','```json',json.dumps(s['current_required_case_results_by_method'],ensure_ascii=False,indent=2),'```',
            '## الفحوص المنفذة']
        for x in r['executions']:lines.append(f"- `{x['name']}`: exit={x['returncode']}, {x['duration_s']}s؛ [log]({x['log']})؛ `{x['command']}`")
        lines+=['## مصفوفة البنود الـ109','| ID | المتطلب | التنفيذ | المسارات | نتيجة القبول المطلوبة | الطريقة / الدليل الحالي | القيد المتبقي |','|---|---|---|---|---|---|---|']
        for row in r['requirements']:
            required=[c for c in row['cases'] if c['required']];status=', '.join(sorted({c['case_result'] for c in required})) or 'NOT_APPLICABLE'
            refs=[]
            for c in row['cases']:
                if c['case_result']=='PASS' or (c['case_result'] in ('FAIL','BLOCKED') and c['required']):
                    refs.append(c['evidence_method']+':'+c['case_result']+' '+', '.join(f'[{Path(p).name}]({p})' for p in c['artifacts']))
            limitations=[c['limitation'] for c in required if c['case_result']!='PASS' and c['limitation']]
            values=[row['task_id'],row.get('title_ar',row['title']),row['feature_state'],'; '.join('`'+p+'`' for p in row['source_paths']),status,'; '.join(refs),row.get('scope_note_ar',row['scope_note'])+' '+ '; '.join(dict.fromkeys(limitations))]
            lines.append('| '+' | '.join(str(v).replace('|','/').replace('\n',' ') for v in values)+' |')
        lines+=['## الصور الحالية']
        for img in r['screenshots']:lines += [img['caption'],f"![{img['task_id']}]({img['artifact']})"]
        lines+=['## حدود القبول والعمل التالي','لا تنفذ هذه الجولة تثبيتًا إداريًا أو نشرًا أو إرسال رسائل أو برامج مولّدة على المضيف. البنود المؤجلة تبقى منفصلة. Missing/blocked/not-run لا تُحذف لتحسين النسبة.','النتائج التفصيلية والخطوات التالية في ACCEPTANCE_AR.md؛ افتح حالات FAIL وBLOCKED وNOT_RUN المطلوبة قبل إغلاق أي بند. قبول GIO مختلف عن رصد النافذة، ونجاح parsing مختلف عن صحة السلوك.']
        blocks=[];table=[]
        for line in lines:
            if line.startswith('|'):table.append(line);continue
            if table:blocks.append('\n'.join(table));table=[]
            blocks.append(line)
        if table:blocks.append('\n'.join(table))
        (self.out/'REPORT_AR.md').write_text('\n\n'.join(blocks)+'\n')

    def execute(self,name,args,timeout,env=None,cwd=None):
        import shlex
        suffix=sum(x['name']==name for x in self.result['executions'])
        log=self.out/'logs'/f'{name}{"-attempt"+str(suffix+1) if suffix else ""}.txt';started=time.monotonic();timed=False
        def bounded_files():resource.setrlimit(resource.RLIMIT_FSIZE,(16*1024*1024,16*1024*1024))
        with log.open('wb') as f:
            process=subprocess.Popen(args,cwd=cwd or self.out,env=env or self.env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=bounded_files)
            try:code=process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed=True;os.killpg(process.pid,signal.SIGTERM)
                try:code=process.wait(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);code=process.wait(timeout=5)
                f.write(b'\nVERIFICATION DEADLINE EXCEEDED; stopped owned static/fake process group only.\n')
        entry={'name':name,'command':shlex.join(args),'cwd':str(cwd or self.out),'log':str(log.relative_to(self.out)),
               'returncode':code,'timed_out':timed,'output_file_limit_bytes':16*1024*1024,'duration_s':round(time.monotonic()-started,3)}
        self.result['executions'].append(entry);self.save();return entry

    def source_review(self):
        observations=[]
        current={r['task_id']:r for r in load_catalog()}
        for row in self.result['requirements']:
            needed=current[row['task_id']]['required_evidence']
            for previous in row['cases']:
                if previous['required'] and previous['case_id'].startswith('acceptance_') and previous['evidence_method'] not in needed:
                    previous['required']=False;previous['scope_revision']='Evidence method refined; retained for provenance.'
            for method in needed:
                if not any(c['required'] and c['evidence_method']==method for c in row['cases']):
                    row['cases'].append(case('acceptance_'+method.lower(),'NOT_RUN',method,limitation='مستوى الدليل المطلوب لم ينفذ بعد.',required=True))
            row['required_evidence']=needed
            for key in ('feature_state','scope_note','source_paths','title_ar','scope_note_ar'):
                if key not in current[row['task_id']]:continue
                row[key]=current[row['task_id']][key]
            refs=[]
            for rel in row['source_paths']:
                p=self.target/rel
                # Tooling/docs/CI live in the checkout; never masquerade as installed imports.
                if not p.is_file() and (REPO/rel).is_file():p=REPO/rel
                refs.append({'path':str(p),'exists':p.is_file(),'sha256':digest(p) if p.is_file() else None})
            observations.append({'task_id':row['task_id'],'feature_state':row['feature_state'],'files':refs,'scope':row['scope_note']})
            self.add([row['task_id']],case('current_source_review','PASS','SOURCE',observations[-1],['artifacts/source-review.json'],limitation='فحص التنفيذ فقط؛ ليس إثبات رحلة القبول.'))
        (self.out/'artifacts/source-review.json').write_text(json.dumps(observations,ensure_ascii=False,indent=2))
        self.save()

    def static(self):
        e=self.execute('static',[sys.executable,str(HERE/'verification/worker.py'),'static','--target',str(self.target),'--output',str(self.out/'artifacts/static.json')],120)
        data=json.loads((self.out/'artifacts/static.json').read_text()) if (self.out/'artifacts/static.json').exists() else {}
        self.result['baseline']=data
        ids='N001 N002 N007 N023 N029 N031 N032 N099'.split()
        for identifier in ids:
            checks=data.get('checks',{});key={'N001':'imports','N002':'imports','N007':'model_metadata','N023':'package_match','N029':'local_assets','N031':'diagnostic_scope','N032':'syntax','N099':'ci_config'}[identifier]
            item=checks.get(key,{'passed':False,'reason':'Static worker did not produce the check'})
            self.gate([identifier],'STATIC','NOT_RUN' if item['passed'] is None else 'PASS' if item['passed'] else 'FAIL',item,['artifacts/static.json'],item.get('limitation',''))
        self.save();return e['returncode']

    def contract(self):
        xml=self.out/'artifacts/contract.xml'
        e=self.execute('contract',[sys.executable,'-m','pytest',str(REPO/'tests'),'-q','-o','faulthandler_timeout=25','--junitxml='+str(xml)],180)
        if not xml.exists():
            self.gate([r['task_id'] for r in self.result['requirements']],'CONTRACT_FAKE','FAIL',e,[e['log']],limitation='Dependency/import/deadline failure; no testcase results available.');self.save();return e['returncode'] or 1
        tree=ET.parse(xml);counts=Counter();mapped={}
        mapping={
            'test_api':'N003 N004 N005 N006 N012 N013 N015 N033 N093 N098 N108',
            'test_application_followups':'N065 N066 N071 N073 N097',
            'test_chat_dispatch':'N041 N049 N059 N065 N066 N068 N069 N070 N071 N072 N073 N098',
            'test_cv_request_flow':'N041 N043 N044 N049 N050 N052 N058 N059',
            'test_backend':'N005 N006','test_core_loop':'N010 N011 N012 N013 N017 N018',
            'test_desktop':'N019 N020 N021 N023 N025 N026',
            'test_entrypoints':'N001 N002 N032','test_game_mode':'N016',
            'test_installer':'N024','test_integration':'N003 N004 N010 N011',
            'test_milestone_contracts':'N041 N044 N045 N065 N069',
            'test_project_jobs':'N041 N042 N043 N044 N045 N050 N052',
            'test_project_store':'N050 N054 N055 N058 N059',
            'test_projects':'N041 N042 N043 N044 N045','test_residency':'N007 N008 N010 N011 N018',
            'test_router':'N004','test_safe_tools':'N068 N104','test_telegram_gateway':'N103',
            'test_workspace_acceptance':'N041 N043 N044 N049 N050 N052 N055',
            'test_workspace_api':'N050 N053 N054 N055 N056 N057 N058 N059 N060 N098',
            'test_workspace_navigation_client':'N049 N051 N060','test_workspace_save_client':'N054',
            'test_workspace_recovery':'N010 N012 N018 N050 N052 N054 N055 N059',
            'test_desktop_skills':'N065 N067 N068 N069 N070 N071 N072 N073 N098',
            'test_markdown_renderer':'N063 N098','test_safety':'N098','test_vault':'N033',
            'test_verification_runner':'N014 N097'}
        mapping['test_review_046']='N041 N042 N049 N050 N054 N055 N056 N066'
        mapping['test_update_lifecycle']='N026 N010 N013 N098'
        for tc in tree.iter('testcase'):
            status='FAIL' if tc.find('failure') is not None or tc.find('error') is not None else 'NOT_RUN' if tc.find('skipped') is not None else 'PASS'
            counts[status]+=1;module=tc.get('classname','').split('.')[-1];name=tc.get('name')
            for identifier in mapping.get(module,'').split():
                mapped.setdefault(identifier,[]).append({'name':module+'::'+name,'result':status})
        self.result['contract_counts']=dict(counts)
        for identifier,items in mapped.items():
            status='FAIL' if any(x['result']=='FAIL' for x in items) else 'NOT_RUN' if any(x['result']=='NOT_RUN' for x in items) else 'PASS'
            self.gate([identifier],'CONTRACT_FAKE',status,{'mapped_testcases':items},['artifacts/contract.xml','artifacts/contract-imports.json'],limitation='نماذج/محولات/حساسات وهمية؛ اختبارات renderer تقرأ أصول checkout المعلنة، وAPI imports من target المسجل.')
        self.add(['N014'],case('fresh_pytest','PASS' if e['returncode']==0 else 'FAIL','CONTRACT_FAKE',dict(counts),['artifacts/contract.xml'],required=True))
        self.save();return e['returncode']

    def ui(self):
        suites=[('qa_targets_workspace_qt.py','journeys.json','N049 N050 N051 N052 N053 N055 N056 N059 N060 N066 N071 N073'),
                ('qa_chat_first_qt.py','qt-journeys.json','N029 N033 N049 N051 N052 N053 N054 N055 N056 N060 N061 N062 N063 N064 N066 N073'),
                ('qa_milestone_ui.py','qt-extra.json','N053 N054 N056 N057 N062 N064 N098'),
                ('qa_review_update_qt.py','update-qt.json','N026 N054 N098')]
        codes=[]
        for script,record,ids in suites:
            name=Path(script).stem;folder=self.out/'artifacts'/name
            env={**self.env,'QT_QPA_PLATFORM':'offscreen'}
            e=self.execute(name,[sys.executable,str(HERE/script),'--data',str(self.profile/name),'--output',str(folder)],150,env=env)
            logfile=(self.out/e['log']).read_text(errors='replace');file=folder/record
            blocked=any(text in logfile.lower() for text in ('no usable sandbox','failed to move to new namespace','operation not permitted','running as root without --no-sandbox','failed to initialize graphics','could not connect to display'))
            if file.exists():
                value=json.loads(file.read_text());items=value['results'];status='PASS' if e['returncode']==0 and all(x['passed'] for x in items) else 'FAIL';observed={'checks':items,'sandbox_disabled':False,'qt_surface':'offscreen','model':'fake','desktop':'fake'}
            else:status='BLOCKED' if blocked else 'FAIL';observed={'exit':e['returncode'],'reason':'Normal Qt sandbox/display unavailable' if blocked else 'Qt tool did not produce results'}
            self.gate(ids.split(),'UI_FIXTURE',status,observed,[str(file.relative_to(self.out))] if file.exists() else [e['log']],limitation='Qt offscreen؛ لا native visible KDE ولا تعطيل sandbox. قبول النموذج/سطح المكتب منفصل.')
            codes.append(3 if status=='BLOCKED' else 1 if status=='FAIL' else 0)
            self.save()
        return 1 if 1 in codes else 3 if 3 in codes else 0

    def observations(self,path):
        data=json.loads(Path(path).read_text())
        if data['run_id']!=self.result['run_id']:raise ValueError('Cannot import historical evidence from another run')
        for entry in data.get('cases',[]):
            for artifact in entry.get('artifacts',[]):
                resolved=(self.out/artifact).resolve()
                if not resolved.is_relative_to(self.out) or not resolved.is_file():raise ValueError('Evidence artifact must exist inside this run')
            if entry.get('required',False):
                for identifier in entry['task_ids']:
                    row=self.by_id[identifier]
                    placeholder='acceptance_'+entry['evidence_method'].lower()
                    row['cases']=[old for old in row['cases'] if old['case_id']!=placeholder or old['observed'] is not None]
            self.add(entry['task_ids'],case(entry['case_id'],entry['case_result'],entry['evidence_method'],entry.get('observed'),entry.get('artifacts',[]),entry.get('command_or_steps',[]),entry.get('limitation',''),entry.get('required',False)))
        for entry in data.get('screenshots',[]):
            p=(self.out/entry['artifact']).resolve()
            if not p.is_relative_to(self.out) or not p.is_file():raise ValueError('Missing/confined screenshot required')
            self.result['screenshots']=[old for old in self.result['screenshots'] if old['artifact']!=entry['artifact']]+[entry]
        for identifier in data.get('reviewed_requirements',[]):
            row=self.by_id[identifier]
            if row['feature_state']!='IMPLEMENTED' or any(c['required'] and c['case_result']!='PASS' for c in row['cases']):
                raise ValueError('Cannot close an incomplete requirement: '+identifier)
            row['acceptance_reviewed']=True
        self.save()

    def archive(self):
        """Export evidence, never profile secrets/caches/model files."""
        target=self.out/'verification-evidence.zip'
        secret=self.profile/'data/.api-token';token=secret.read_bytes().strip() if secret.is_file() else b''
        sources=[p for folder in ('logs','screenshots','artifacts') for p in (self.out/folder).rglob('*') if p.is_file()]
        sources += [self.out/'REPORT_AR.md',self.out/'results.json']
        sources += [self.out/name for name in ('ACCEPTANCE_AR.md','MATRIX.csv') if (self.out/name).is_file()]
        with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
            for path in sorted(sources):
                if path.is_symlink() or path.stat().st_size>16*1024*1024:raise ValueError('Evidence export file refused: '+str(path))
                raw=path.read_bytes()
                if token and token in raw:raise ValueError('QA credential detected; export refused: '+str(path.relative_to(self.out)))
                z.writestr(str(path.relative_to(self.out)),raw)
        with zipfile.ZipFile(target) as z:
            if z.testzip() is not None:raise ValueError('Evidence ZIP integrity failure')
        (self.out/'SHA256SUMS.txt').write_text(digest(target)+'  '+target.name+'\n')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--suite',choices=['static','contract','ui','model','desktop','all','report'],default='static')
    p.add_argument('--target-root',default=str(REPO));p.add_argument('--vendor-dir')
    p.add_argument('--output-root',default=str(REPO/'verification-runs'));p.add_argument('--profile-root');p.add_argument('--resume')
    p.add_argument('--allow-real-model',action='store_true');p.add_argument('--allow-desktop',action='store_true')
    p.add_argument('--trace-real-model',action='store_true',help='QA-only observer of actual model input/options; never production data')
    p.add_argument('--model-case',choices=['all','history','budget','transport'],default='all')
    p.add_argument('--serve',choices=['fixture','real']);p.add_argument('--observations')
    p.add_argument('--archive',action='store_true')
    args=p.parse_args(argv);run=Run(args)
    import shlex
    run.result.setdefault('invocations',[]).append({'at':now(),'executable':sys.executable,
        'command':shlex.join([sys.executable,str(Path(__file__).resolve()),*(argv if argv is not None else sys.argv[1:])]),
        'cwd':str(Path.cwd()),'suite':args.suite,'serve':args.serve})
    print(json.dumps({'run_id':run.result['run_id'],'source':str(REPO),'target':str(run.target),'profile':str(run.profile),'suite':args.suite,
        'side_effects':{'static':'QA files/imports only','contract':'fake inference/desktop/sensors','ui':'owned offscreen Qt fixture windows, sandbox enabled','model':args.allow_real_model,'trace_real_model':args.trace_real_model,'desktop_launch':args.allow_desktop,'serve':args.serve,'admin_or_publish':False},'output':str(run.out)},ensure_ascii=False,indent=2),flush=True)
    run.source_review();codes=[]
    if args.observations:run.observations(args.observations)
    if args.serve:
        from verification.live import serve
        return serve(run,args.serve)
    if args.suite=='report':
        run.save()
        if args.archive:run.archive()
        return run.result['summary']['acceptance_exit_code']
    for suite in ['static','contract','ui','model','desktop'] if args.suite=='all' else [args.suite]:
        if suite in ('model','desktop'):
            from verification.live import execute_live
            codes.append(execute_live(run,suite))
        else:codes.append(getattr(run,suite)())
    run.save()
    if args.archive:run.archive()
    selected=1 if any(c not in (0,3) for c in codes) else 3 if 3 in codes else 0
    # all must expose incomplete catalog acceptance even when selected suites pass.
    return run.result['summary']['acceptance_exit_code'] if args.suite=='all' else selected


if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError,subprocess.SubprocessError) as exc:
        print('Verification failed safely: '+str(exc),file=sys.stderr);raise SystemExit(1)
