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
from src.core.project_store import now
from src.core.project_stream import FileStream
from src.core.project_contracts import JobEvent

TERMINAL = {'completed', 'failed', 'cancelled'}


class WorkspaceRequest(ProjectRequest):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    background: bool = False
    title: str = Field(default='', max_length=100)
    project_type: str = Field(default='auto', pattern=r'^(auto|static_web|python|other)$')
    project_id: str | None = None
    expected_revision: int | None = Field(default=None, ge=0)
    context_files: list[str] = Field(default_factory=list, max_length=8)

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
        with store.lock:
            store.db.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,project_id TEXT,state TEXT,request TEXT,draft TEXT,seq INTEGER,cancel INTEGER,error TEXT,created TEXT,updated TEXT)')
            store.db.execute('CREATE TABLE IF NOT EXISTS project_events(job_id TEXT,seq INTEGER,payload TEXT,PRIMARY KEY(job_id,seq))')
            interrupted = store.db.execute("SELECT id FROM jobs WHERE state NOT IN ('completed','failed','cancelled')").fetchall()
            store.db.commit()
        for row in interrupted:
            self._state(row['id'], 'failed', error='interrupted: توقف التطبيق؛ لم يُستأنف التوليد تلقائيًا')
            self._emit(row['id'], 'job_failed', {'code': 'interrupted'})

    def _row(self, job_id):
        if not re.fullmatch(r'j_[a-f0-9]{32}', job_id):
            raise ProjectError('معرّف المهمة غير صالح')
        row = self.store.db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
        if not row:
            error=ProjectError('المهمة غير موجودة');error.status=404;raise error
        return row

    def get(self, job_id):
        with self.store.lock:
            row = self._row(job_id)
            return {'job_id': row['id'], 'project_id': row['project_id'], 'state': row['state'],
                    'last_seq': row['seq'], 'cancellation_requested': bool(row['cancel']),
                    'draft_files': json.loads(row['draft']), 'error': row['error'],
                    'created_at': row['created'], 'updated_at': row['updated']}

    def _state(self, job_id, state, *, error=None):
        with self.store.lock:
            row = self._row(job_id)
            self.store.db.execute('UPDATE jobs SET state=?,error=?,updated=? WHERE id=?', (state, error, now(), job_id))
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

    def create(self, request):
        request = WorkspaceRequest.model_validate(request)
        with self.store.lock:
            if self.stopping.is_set() or self.queue.full():
                raise Conflict('قائمة التوليد ممتلئة؛ انتظر انتهاء مهمة')
            if request.project_id:
                project = self.store.get(request.project_id)
                if request.expected_revision != project['project_revision'] or project['source_freshness'] != 'current':
                    raise Conflict('راجع مراجعة المشروع قبل تعديله')
                if not request.context_files:
                    raise ProjectError('يجب تحديد ملفات فعلية ذات صلة للتعديل؛ الملخص وحده لا يكفي')
                for path in request.context_files:
                    self.store.read(request.project_id, path)
            else:
                title = request.title or request.user_request.split('\n')[0][:80]
                project = self.store.create(title, request.user_request, request.project_type)
            job_id = 'j_' + uuid.uuid4().hex
            self.store.db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)',
                (job_id, project['project_id'], 'queued', request.model_dump_json(), '{}', 0, 0, None, now(), now()))
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
            project_id = row['project_id']
            project = self.store.get(project_id)
            expected = request.expected_revision if request.project_id else 0
            if project['project_revision'] != expected or project['source_freshness'] != 'current':
                raise Conflict('تغير المشروع أثناء الانتظار')
            context = ''
            if request.project_id:
                context = project['summary'] + '\nActual relevant source:\n'
                for path in request.context_files:
                    actual = self.store.read(project_id, path)
                    if actual['binary']:raise ProjectError('اختر ملف مصدر نصيًا للسياق')
                    context += '\nFILE ' + path + '\n' + actual['content']
                if len(context) > 60_000:
                    raise ProjectError('الملفات المختارة تتجاوز حد السياق؛ اختر ملفات أقل')
            with closing(self.invoice.stream_files(request.legacy(), context=context, cancel=cancel, deadline=deadline)) as stream:
                for item in stream:
                    if item['kind'] == 'stage':
                        self._state(job_id, item['stage'])
                        self._emit(job_id, 'stage_changed', {'stage': item['stage']})
                    elif item['kind'] == 'delta':
                        parser.feed(item['text'])
            generated = parser.finish()
            self.coordinator._check(cancel, deadline)
            self._state(job_id, 'validating')
            self._emit(job_id, 'stage_changed', {'stage': 'validating'})
            files = self.store.committed_files(project_id) if request.project_id else {}
            unseen=set(generated).intersection(files).difference(request.context_files) if request.project_id else set()
            if unseen:
                raise ProjectError('لم يُرسل المصدر الفعلي لهذه الملفات؛ اخترها قبل تعديلها: '+', '.join(sorted(unseen)))
            files.update(generated)
            # Reuse the existing deterministic required-file/symbol acceptance checks.
            missing = set(request.required_files) - files.keys()
            if missing:
                raise ProjectError('ملفات مطلوبة مفقودة: ' + ', '.join(sorted(missing)))
            if request.required_python_symbols:
                import ast
                symbols = {node.name for p, text in files.items() if PurePosixPath(p).suffix.lower()=='.py' for node in ast.walk(ast.parse(text))
                           if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
                if set(request.required_python_symbols) - symbols:
                    raise ProjectError('رموز Python المطلوبة مفقودة')
            self.coordinator._check(cancel, deadline)
            project = self.store.commit(project_id, files, expected)
            self._emit(job_id, 'validation_result', project['validation'])
            for path in generated:
                self._emit(job_id, 'file_saved', {'path': path, 'revision': project['project_revision']})
            self.coordinator.lock.release()
            acquired = False
            with self.store.lock:
                self._state(job_id, 'completed')
                self._emit(job_id, 'job_completed', {'revision': project['project_revision'], 'preview': project['preview']}, drafts=parser.files)
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
