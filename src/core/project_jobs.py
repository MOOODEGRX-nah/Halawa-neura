"""One bounded worker, durable ordered events, and recovery without replaying inference."""
import json
import queue
import re
import threading
import time
import uuid
from pathlib import PurePosixPath
from contextlib import closing
from pydantic import ConfigDict, Field
from src.core.invoice_orchestrator import InvoiceOrchestrator, ProjectRequest
from src.core.neura_loop import InferenceError
from src.core.project_files import ProjectError, Conflict
from src.core.project_store import now, digest
from src.core.project_stream import FileStream
from src.core.project_contracts import JobEvent
from src.core.project_validation import inspect_files
from src.core.edit_preservation import require_preserved, html_contract, contract_summary, requested_web_features
from src.core.candidate_browser import check_candidate
from src.core.contrast_repair import repair_contrast

TERMINAL = {'completed', 'failed', 'cancelled'}


class WorkspaceRequest(ProjectRequest):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    background: bool = False
    title: str = Field(default='', max_length=100)
    project_type: str = Field(default='auto', pattern=r'^(auto|static_web|python|other)$')
    project_id: str | None = None
    expected_revision: int | None = Field(default=None, ge=0)
    context_files: list[str] = Field(default_factory=list, max_length=8)
    source_hashes: dict[str,str] = Field(default_factory=dict)

    def legacy(self):
        return ProjectRequest.model_validate({key: getattr(self, key) for key in ProjectRequest.model_fields})


class ProjectJobs:
    def __init__(self, store, coordinator):
        self.store, self.coordinator = store, coordinator
        self.invoice = InvoiceOrchestrator(coordinator)
        self.queue = queue.Queue(maxsize=4)
        self.cancel_flags = {}
        self.stopping = threading.Event()
        self.worker = None
        self.update_reservation = None
        with store.lock:
            store.db.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,project_id TEXT,state TEXT,request TEXT,draft TEXT,seq INTEGER,cancel INTEGER,error TEXT,created TEXT,updated TEXT)')
            store.db.execute('CREATE TABLE IF NOT EXISTS project_events(job_id TEXT,seq INTEGER,payload TEXT,PRIMARY KEY(job_id,seq))')
            store.db.execute('CREATE TABLE IF NOT EXISTS job_contracts(job_id TEXT PRIMARY KEY,invoice TEXT NOT NULL,stages TEXT NOT NULL,result TEXT NOT NULL)')
            interrupted = store.db.execute("SELECT id FROM jobs WHERE state NOT IN ('completed','failed','cancelled')").fetchall()
            store.db.commit()
        for row in interrupted:
            job=self._row(row['id']);meta=self.store.get(job['project_id']);receipt=meta.get('last_execution')
            if receipt and receipt['job_id']==row['id'] and receipt['result_revision']==meta['project_revision'] and meta['source_freshness']=='current':
                result={'execution':receipt,'validation':meta['validation'],'saved_files':[{'project_id':job['project_id'],'path':path,'revision':receipt['result_revision'],'sha256':sha} for path,sha in receipt['result_hashes'].items()]}
                store.db.execute('UPDATE job_contracts SET result=? WHERE job_id=?',(json.dumps(result,ensure_ascii=False),row['id']));store.db.commit()
                self._state(row['id'],'completed');self._emit(row['id'],'job_completed',{'execution':receipt,'recovered_committed_receipt':True});continue
            self._state(row['id'], 'failed', error='interrupted: توقف التطبيق؛ لم يُستأنف التوليد تلقائيًا')
            self._emit(row['id'], 'job_failed', {'code': 'interrupted'})

    def _row(self, job_id):
        with self.store.lock:
            if not re.fullmatch(r'j_[a-f0-9]{32}', job_id):
                raise ProjectError('معرّف المهمة غير صالح')
            row = self.store.db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
            if not row:
                error=ProjectError('المهمة غير موجودة');error.status=404;raise error
            return row

    def get(self, job_id):
        with self.store.lock:
            row = self._row(job_id)
            contract=self.store.db.execute('SELECT * FROM job_contracts WHERE job_id=?',(job_id,)).fetchone()
            result=json.loads(contract['result']) if contract else {}
            return {'job_id': row['id'], 'project_id': row['project_id'], 'state': row['state'],
                    'last_seq': row['seq'], 'cancellation_requested': bool(row['cancel']),
                    'draft_files': json.loads(row['draft']), 'error': row['error'],
                    'created_at': row['created'], 'updated_at': row['updated'],
                    'invoice':json.loads(contract['invoice']) if contract else None,
                    'invoice_provenance':'recorded' if contract else 'unavailable_legacy',
                    'stage_results':json.loads(contract['stages']) if contract else [],
                    'saved_files':result.get('saved_files',[]),'validation':result.get('validation'),'execution':result.get('execution'),'attempts':result.get('attempts',[])}

    def _stage_result(self, job_id, stage, result):
        with self.store.lock:
            row=self.store.db.execute('SELECT stages FROM job_contracts WHERE job_id=?',(job_id,)).fetchone()
            if not row:return
            stages=json.loads(row['stages'])
            for entry in reversed(stages):
                if entry['stage']==stage:
                    entry['result']=result;break
            self.store.db.execute('UPDATE job_contracts SET stages=? WHERE job_id=?',(json.dumps(stages,ensure_ascii=False),job_id))
            self.store.db.commit()

    def _state(self, job_id, state, *, error=None):
        with self.store.lock:
            row = self._row(job_id)
            self.store.db.execute('UPDATE jobs SET state=?,error=?,updated=? WHERE id=?', (state, error, now(), job_id))
            contract=self.store.db.execute('SELECT stages FROM job_contracts WHERE job_id=?',(job_id,)).fetchone()
            if contract:
                stages=json.loads(contract['stages']);stamp=now()
                if stages and stages[-1]['status']=='running' and stages[-1]['stage']!=state:
                    stages[-1].update(status=state if state in ('failed','cancelled') else 'completed',completed_at=stamp)
                    if error:stages[-1]['error']=error
                if state not in TERMINAL and (not stages or stages[-1]['stage']!=state):
                    stages.append({'stage':state,'status':'running','started_at':stamp})
                self.store.db.execute('UPDATE job_contracts SET stages=? WHERE job_id=?',(json.dumps(stages,ensure_ascii=False),job_id))
            self.store.db.commit()
            self.store.set_generation(row['project_id'], state)

    def _emit(self, job_id, kind, data, *, drafts=None):
        with self.store.lock:
            row = self._row(job_id)
            seq = row['seq'] + 1
            project = self.store.get(row['project_id'], freshness=False)
            event = {'job_id': job_id, 'project_id': row['project_id'], 'seq': seq,
                     'type': kind, 'revision': project['project_revision'], 'data': data}
            JobEvent.model_validate(event)
            self.store.db.execute('INSERT INTO project_events VALUES(?,?,?)', (job_id, seq, json.dumps(event, ensure_ascii=False)))
            if drafts is not None:
                self.store.db.execute('UPDATE jobs SET seq=?,draft=?,updated=? WHERE id=?', (seq, json.dumps(drafts, ensure_ascii=False), now(), job_id))
            else:
                self.store.db.execute('UPDATE jobs SET seq=?,updated=? WHERE id=?', (seq, now(), job_id))
            self.store.db.execute('DELETE FROM project_events WHERE job_id=? AND seq<?', (job_id, seq - 4095))
            self.store.db.commit()
            return event

    def events(self, job_id, after):
        with self.store.lock:
            row = self._row(job_id)
            first = self.store.db.execute('SELECT MIN(seq) FROM project_events WHERE job_id=?', (job_id,)).fetchone()[0]
            if after > row['seq'] or after < 0:
                raise ProjectError('مؤشر أحداث غير صالح')
            if first and after < first - 1:
                return [{'job_id':job_id,'project_id':row['project_id'],'seq':row['seq'],
                         'type':'snapshot','revision':self.store.get(row['project_id'],freshness=False)['project_revision'],
                         'data': self.get(job_id)}]
            return [json.loads(x['payload']) for x in self.store.db.execute('SELECT payload FROM project_events WHERE job_id=? AND seq>? ORDER BY seq LIMIT 128', (job_id, after))]

    def prepare_update(self,reservation_id):
        # Same ordering as admission: store lock serializes queued jobs, and a
        # nonblocking coordinator lock refuses active native work, never kills it.
        with self.store.lock:
            if self.update_reservation==reservation_id:return {'reservation_id':reservation_id,'ready':True}
            if self.update_reservation:raise Conflict('توجد تهيئة تحديث أخرى؛ لم يُوقف المحرك.')
            active=self.store.db.execute("SELECT COUNT(*) FROM jobs WHERE state NOT IN ('completed','failed','cancelled')").fetchone()[0]
            if active:raise Conflict('توجد مهام توليد نشطة أو منتظرة؛ انتظر اكتمالها أو ألغها من مساحة العمل ثم أعد التحديث.')
            if not self.coordinator.lock.acquire(blocking=False):raise Conflict('الاستدلال ما زال يعمل؛ أُجّل التحديث دون إيقافه.')
            try:
                if self.stopping.is_set() or getattr(self.coordinator,'_closed',False):raise Conflict('المحرك غير جاهز لتهيئة التحديث')
                self.coordinator._maintenance=True
                self.update_reservation=reservation_id
            finally:self.coordinator.lock.release()
            return {'reservation_id':reservation_id,'ready':True}

    def release_update(self,reservation_id):
        with self.store.lock:
            if self.update_reservation and self.update_reservation!=reservation_id:raise Conflict('هوية تهيئة التحديث غير مطابقة')
            self.coordinator._maintenance=False;self.update_reservation=None
            return {'status':'released'}

    def create(self, request):
        request = WorkspaceRequest.model_validate(request)
        with self.store.lock:
            if self.update_reservation:raise Conflict('التحديث قيد التهيئة؛ لم تُنشأ مهمة جديدة.')
            if self.stopping.is_set() or self.queue.full():
                raise Conflict('قائمة التوليد ممتلئة؛ انتظر انتهاء مهمة')
            if request.project_id:
                active=self.store.db.execute("SELECT COUNT(*) FROM jobs WHERE project_id=? AND state NOT IN ('completed','failed','cancelled')",(request.project_id,)).fetchone()[0]
                if active:raise Conflict('توجد مهمة نشطة لهذا المشروع؛ انتظر أو ألغها قبل إنشاء تعديل جديد')
                project = self.store.get(request.project_id)
                if request.expected_revision != project['project_revision'] or project['source_freshness'] != 'current':
                    raise Conflict('راجع مراجعة المشروع قبل تعديله')
                if not request.context_files:
                    raise ProjectError('يجب تحديد ملفات فعلية ذات صلة للتعديل؛ الملخص وحده لا يكفي')
                for path in request.context_files:
                    self.store.read(request.project_id, path)
                captured={p:digest(v) for p,v in self.store.committed_files(request.project_id).items()}
                if request.source_hashes and request.source_hashes!=captured:raise Conflict('بصمات مصدر التعديل قديمة')
                request.source_hashes=captured
            else:
                title = request.title or request.user_request.split('\n')[0][:80]
                project = self.store.create(title, request.user_request, request.project_type)
            job_id = 'j_' + uuid.uuid4().hex
            self.store.db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)',
                (job_id, project['project_id'], 'queued', request.model_dump_json(), '{}', 0, 0, None, now(), now()))
            invoice=self.invoice.make_invoice(request.legacy(),project_id=project['project_id'],task_id=job_id)
            self.store.db.execute('INSERT INTO job_contracts VALUES(?,?,?,?)',(job_id,invoice.model_dump_json(),
                json.dumps([{'stage':'queued','status':'running','started_at':now()}]),'{}'))
            self.store.db.commit()
            self.cancel_flags[job_id] = threading.Event()
            self._emit(job_id, 'job_started', {'state': 'queued'})
            self.store.set_generation(project['project_id'], 'queued', job_id)
            self.queue.put_nowait(job_id)
            if self.worker is None or not self.worker.is_alive():
                self.worker = threading.Thread(target=self._run, name='neura-project-worker', daemon=True)
                self.worker.start()
            return {'project': self.store.get(project['project_id']), 'job': self.get(job_id)}

    def cancel(self, job_id):
        with self.store.lock:
            row = self._row(job_id)
            if row['state'] not in TERMINAL:
                self.cancel_flags[job_id].set()
                self.store.db.execute('UPDATE jobs SET cancel=1 WHERE id=?', (job_id,))
                self.store.db.commit()
            return self.get(job_id)

    def _run(self):
        while not self.stopping.is_set():
            try:
                job_id = self.queue.get(timeout=.2)
            except queue.Empty:
                continue
            try:
                self._generate(job_id)
            finally:
                self.queue.task_done()

    def _generate(self, job_id):
        cancel = self.cancel_flags[job_id]
        deadline = time.monotonic() + self.coordinator.settings.timeout_s
        acquired = False
        parser = FileStream(lambda kind, data: self._emit(job_id, kind, data, drafts=parser.files))
        try:
            while not acquired:
                self.coordinator._check(cancel, deadline)
                acquired = self.coordinator.lock.acquire(timeout=.1)
            row = self._row(job_id)
            request = WorkspaceRequest.model_validate_json(row['request'])
            parser=FileStream(lambda kind,data:self._emit(job_id,kind,data,drafts=parser.files),
                              expected_files=request.required_files,filename_hints=request.filename_hints or request.context_files)
            project_id = row['project_id']
            project = self.store.get(project_id)
            expected = request.expected_revision if request.project_id else 0
            if project['project_revision'] != expected or project['source_freshness'] != 'current':
                raise Conflict('تغير المشروع أثناء الانتظار')
            if request.project_id and {p:digest(v) for p,v in self.store.committed_files(project_id).items()}!=request.source_hashes:raise Conflict('تغيرت بصمات المصدر أثناء الانتظار')
            context = ''
            if request.project_id:
                context = project['summary'] + '\nActual relevant source:\n'
                for path in request.context_files:
                    actual = self.store.read(project_id, path)
                    if actual['binary']:raise ProjectError('اختر ملف مصدر نصيًا للسياق')
                    context += '\nFILE ' + path + '\n' + actual['content']
                # Full source remains available to bounded per-file operations.
            actual_invoice=self.invoice.make_invoice(request.legacy(),project_id=project_id,task_id=job_id,context=context)
            with self.store.lock:
                self.store.db.execute('UPDATE job_contracts SET invoice=? WHERE job_id=?',(actual_invoice.model_dump_json(),job_id));self.store.db.commit()
            before = self.store.committed_files(project_id) if request.project_id else {}
            accepted=project.get('accepted_requirements',[])
            if request.project_id:
                context+='\nPreserve ALL existing visible content, control labels, IDs, links and behavior. Keep Login as a placeholder, not authentication. Dark mode must have readable foreground and background colors. Use local resources only.\n'
                requirements_context=json.dumps(accepted,ensure_ascii=False)
                if len(requirements_context)>8000:raise ProjectError('سجل متطلبات المشروع يتجاوز حد السياق؛ يلزم مراجعته قبل تعديل جديد')
                context+='Accepted user requirements: '+requirements_context
            attempts=[];browser={'status':'not_run'};preserved={'status':'not_applicable'}
            repair='';generated={};files={};browser_failure=None
            # One model correction and at most two corrective validation passes.
            # Measured CSS correction spends no model output; deadline is shared.
            remaining_tokens=request.max_tokens//4
            model_repairs=0
            for attempt in range(3):
                parser=FileStream(lambda kind,data:self._emit(job_id,kind,data,drafts=parser.files),
                                  expected_files=request.required_files,filename_hints=request.filename_hints or request.context_files)
                if attempt:
                    self._state(job_id,'generating');self._emit(job_id,'stage_changed',{'stage':'generating','attempt':attempt,'mode':'candidate_patch'})
                    try:
                        corrected=repair_contrast(generated,preview.get('entry_point'),browser_failure,request.user_request+' '+json.dumps(accepted,ensure_ascii=False))
                        if corrected:generated,repair_result=corrected
                        else:
                            if model_repairs:raise ProjectError('استُنفدت محاولة الإصلاح بالنموذج؛ بقيت المراجعة السابقة')
                            model_repairs+=1
                            generated,repair_result=self.invoice.repair_candidate(generated,request,repair,contract_summary(before),
                                cancel=cancel,deadline=deadline,max_tokens=remaining_tokens)
                        self._stage_result(job_id,'generating',repair_result)
                        for path,content in generated.items():
                            parser.files[path]={'content':'','complete':False};self._emit(job_id,'file_started',{'path':path},drafts=parser.files)
                            parser.files[path]['content']=content
                            self._emit(job_id,'file_delta',{'path':path,'delta':content,'offset':0},drafts=parser.files)
                            parser.files[path]['complete']=True;self._emit(job_id,'file_draft_complete',{'path':path},drafts=parser.files)
                    except (ProjectError,InferenceError) as error:
                        attempts.append({'attempt':attempt,'status':'rejected','error':str(error),'mode':'candidate_patch'})
                        with self.store.lock:
                            self.store.db.execute('UPDATE job_contracts SET result=? WHERE job_id=?',(json.dumps({'attempts':attempts},ensure_ascii=False),job_id));self.store.db.commit()
                        raise
                else:
                    candidate_request=request.legacy()
                    candidate_request.max_tokens=max(64,request.max_tokens-remaining_tokens)
                    if request.project_id:
                        from src.core.bounded_edits import BoundedEditor
                        iterator=BoundedEditor(self.invoice).generate(candidate_request,before,request.context_files,expected,
                            context+repair,project_id,job_id,cancel,deadline,accepted=accepted)
                    else:iterator=self.invoice.stream_files(candidate_request,context=context+repair,project_id=project_id,task_id=job_id,cancel=cancel,deadline=deadline)
                    with closing(iterator) as stream:
                        for item in stream:
                            if item['kind']=='stage':
                                self._state(job_id,item['stage']);self._emit(job_id,'stage_changed',{'stage':item['stage'],'attempt':attempt})
                            elif item['kind']=='delta':parser.feed(item['text'])
                            elif item['kind']=='candidate_file':
                                path,content=item['path'],item['content']
                                parser.files[path]={'content':'','complete':False}
                                self._emit(job_id,'file_started',{'path':path,'mode':'applied_candidate_patch'},drafts=parser.files)
                                parser.files[path]={'content':content,'complete':False}
                                self._emit(job_id,'file_delta',{'path':path,'delta':content,'offset':0},drafts=parser.files)
                                parser.files[path]['complete']=True
                                self._emit(job_id,'file_draft_complete',{'path':path},drafts=parser.files)
                            elif item['kind'] in ('stage_result','finished'):
                                result={key:value for key,value in item.items() if key not in ('kind','stage')}
                                if item['kind']=='finished':result['filename_resolutions']=parser.resolutions
                                self._stage_result(job_id,item.get('stage','generating'),result)
                    generated={p:v['content'] for p,v in parser.files.items()} if request.project_id else parser.finish()
                self.coordinator._check(cancel,deadline)
                self._state(job_id,'validating');self._emit(job_id,'stage_changed',{'stage':'validating','attempt':attempt})
                files={**before,**generated}
                unseen=set(generated).intersection(before).difference(request.context_files) if request.project_id else set()
                if unseen:raise ProjectError('لم يُرسل المصدر الفعلي لهذه الملفات: '+', '.join(sorted(unseen)))
                try:
                    missing=set(request.required_files)-files.keys()
                    if missing:raise ProjectError('ملفات مطلوبة مفقودة: '+', '.join(sorted(missing)))
                    if request.required_python_symbols:
                        import ast
                        symbols={node.name for path,text in files.items() if path.endswith('.py') for node in ast.walk(ast.parse(text)) if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))}
                        if set(request.required_python_symbols)-symbols:raise ProjectError('رموز Python المطلوبة مفقودة')
                    languages,preview,validation=inspect_files(files)
                    if validation['errors']:raise ProjectError('; '.join(validation['errors']))
                    if before:preserved=require_preserved(before,files,request.user_request)
                    def meaningful(value):
                        if not isinstance(value,str):return value
                        return value.replace('\r\n','\n').rstrip('\n')
                    changed=[path for path in generated if meaningful(before.get(path))!=meaningful(generated[path])]
                    # Ignore only trailing line terminators, never whitespace within code strings.
                    for path in set(generated)-set(changed):
                        if path in before:files[path]=before[path]
                    if changed:
                        required=html_contract(before).get(preview.get('entry_point'),{})
                        resulting=html_contract(files).get(preview.get('entry_point'),{})
                        required={'controls':[c for c in required.get('controls',[]) if c in resulting.get('controls',[])],
                                  'text':[t for t in required.get('text',[]) if t in ' '.join(resulting.get('text',[]))],
                                  **requested_web_features(accepted,request.user_request)}
                        browser=check_candidate(files,preview,cancel,deadline,required=required)
                    attempts.append({'attempt':attempt,'status':'accepted' if changed else 'no_change','preservation':preserved,'browser':browser})
                    break
                except ProjectError as error:
                    browser_failure=getattr(error,'browser_report',None)
                    attempts.append({'attempt':attempt,'status':'rejected','error':str(error),'draft_files':dict(generated),'browser':browser_failure})
                    with self.store.lock:
                        self.store.db.execute('UPDATE job_contracts SET result=? WHERE job_id=?',(json.dumps({'attempts':attempts},ensure_ascii=False),job_id));self.store.db.commit()
                    if attempt>=2 or remaining_tokens<256:raise
                    repair=str(error)[:1800]
            self.coordinator._check(cancel,deadline)
            # Receipt and project metadata share the SAME durable SQLite commit.
            execution={'outcome':'saved' if changed else 'no_change','project_id':project_id,'job_id':job_id,
                'base_revision':expected,'result_revision':expected+1 if changed else expected,'changed_files':changed,
                'base_hashes':{path:digest(value) for path,value in before.items()},
                'result_hashes':{path:digest(files[path]) for path in changed},
                'preservation':preserved,'browser':{key:value for key,value in browser.items() if key!='samples'},'preview_checked_revision':expected+1 if changed and browser['status']=='passed' else None}
            if request.project_id and {p:digest(v) for p,v in self.store.committed_files(project_id).items()}!=request.source_hashes:raise Conflict('تغير المصدر قبل ترقية المرشح؛ لم يُحفظ تعديل جزئي')
            if changed:
                project=self.store.commit(project_id,files,expected,execution_receipt=execution,
                    accepted_requirements=[*accepted,{'origin':'user_request','job_id':job_id,'text':request.user_request}][-30:])
            else:
                project=self.store.get(project_id)
                if project['project_revision']!=expected or project['source_freshness']!='current':raise Conflict('تغير المشروع قبل تأكيد عدم وجود تغييرات')
            saved=[{'project_id':project_id,'path':path,'revision':project['project_revision'],
                    'sha256':execution['result_hashes'][path]} for path in changed]
            with self.store.lock:
                self.store.db.execute('UPDATE job_contracts SET result=? WHERE job_id=?',
                    (json.dumps({'saved_files':saved,'validation':project['validation'],'execution':execution,'attempts':attempts},ensure_ascii=False),job_id));self.store.db.commit()
            self._emit(job_id, 'validation_result', project['validation'])
            for path in changed:
                self._emit(job_id, 'file_saved', {'path': path, 'revision': project['project_revision']})
            self.coordinator.lock.release()
            acquired = False
            with self.store.lock:
                self._state(job_id, 'completed')
                self._emit(job_id, 'job_completed', {'revision': project['project_revision'], 'preview': project['preview'],'execution':execution}, drafts=parser.files)
        except BaseException as exc:
            if acquired:
                self.coordinator.lock.release()
                acquired = False
            state = 'cancelled' if cancel.is_set() else 'failed'
            with self.store.lock:
                self._state(job_id, state, error=str(exc)[:1000])
                self._emit(job_id, 'job_cancelled' if state == 'cancelled' else 'job_failed',
                           {'message': str(exc)[:1000], 'code': getattr(exc, 'code', 'project_failed')}, drafts=parser.files)
        finally:
            if acquired:
                self.coordinator.lock.release()
            self.cancel_flags.pop(job_id, None)

    def shutdown(self):
        self.stopping.set()
        with self.store.lock:
            for flag in self.cancel_flags.values():
                flag.set()
        if self.worker and self.worker.is_alive():
            self.worker.join()
