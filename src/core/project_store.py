"""Durable projects. SQLite is canonical; project.json/summary.md are derived views."""
import hashlib
import base64
import io
import json
import re
import sqlite3
import threading
import unicodedata
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from src.core.project_files import SafeTree, ProjectError, Conflict, bounded_files, safe_path, MAX_FILE
from src.core.project_validation import inspect_files, LANGUAGES


class InvalidIndex(ProjectError):
    status=409


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(text):
    return hashlib.sha256(text.encode('utf-8') if isinstance(text,str) else text).hexdigest()


def redact(text):
    text=re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----','[محذوف: مفتاح خاص]',text)
    text=re.sub(r'(?i)((?:api[_ -]?key|access[_ -]?token|token|password|secret|كلمة المرور)\s*[:=]\s*)[^\s,;]+',r'\1[محذوف]',text)
    text=re.sub(r'(?i)(bearer\s+)[A-Za-z0-9_.-]+',r'\1[محذوف]',text)
    return re.sub(r'\bsk-[A-Za-z0-9_-]{16,}\b','[محذوف: مفتاح]',text)


def snapshot_json(files):
    return json.dumps({'files':{p:({'binary_base64':base64.b64encode(value).decode()} if isinstance(value,bytes) else value) for p,value in files.items()}},ensure_ascii=False)


def snapshot_files(data):
    return {p:(base64.b64decode(value['binary_base64'],validate=True) if isinstance(value,dict) else value) for p,value in json.loads(data)['files'].items()}


class ProjectStore:
    def __init__(self, data_dir):
        self.root = Path(data_dir) / 'workspace'
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.is_symlink() or (self.root / 'catalog.sqlite3').is_symlink():
            raise ProjectError('مجلد المشاريع أو فهرسه لا يجوز أن يكون رابطًا')
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.root / 'catalog.sqlite3', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, directory TEXT UNIQUE, metadata TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS workspace_preferences(id INTEGER PRIMARY KEY CHECK(id=1),value TEXT)')
        self.db.commit()
        for row in self.db.execute('SELECT id FROM projects').fetchall():
            self._recover(row['id'])

    def close(self):
        with self.lock:
            self.db.close()

    def preferences(self, values=None):
        with self.lock:
            row = self.db.execute('SELECT value FROM workspace_preferences WHERE id=1').fetchone()
            current = json.loads(row['value']) if row else {'swapped':False,'ratio':50,'last_project':None}
            if values is not None:
                current.update(values)
                self.db.execute('INSERT OR REPLACE INTO workspace_preferences VALUES(1,?)', (json.dumps(current),))
                self.db.commit()
            return current

    def _row(self, project_id):
        if not re.fullmatch(r'p_[a-f0-9]{32}', project_id):
            raise ProjectError('معرّف المشروع غير صالح')
        row = self.db.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
        if not row:
            error = ProjectError('المشروع غير موجود'); error.status = 404
            raise error
        return row

    def directory(self, project_id):
        with self.lock:
            name = self._row(project_id)['directory']
            if '/' in name or name.startswith('.'):
                raise ProjectError('فهرس مجلد المشروع غير صالح')
            path = self.root / name
            with SafeTree(path):
                return path

    def create(self, title, purpose, project_type='auto', *, legacy_id=None, project_id=None):
        title = redact(str(title).strip())[:100] or 'مشروع جديد'
        purpose = redact(str(purpose).strip())[:1000]
        if project_type not in ('auto', 'static_web', 'python', 'other'):
            raise ProjectError('نوع المشروع غير معروف')
        project_id = project_id or 'p_' + uuid.uuid4().hex
        if not re.fullmatch(r'p_[a-f0-9]{32}',project_id):raise ProjectError('معرّف المشروع غير صالح')
        slug = re.sub(r'[^\w-]+', '-', unicodedata.normalize('NFKC', title), flags=re.UNICODE).strip('-_')[:48] or 'project'
        folder = slug + '-' + project_id[-8:]
        meta = {'schema_version': 1, 'project_id': project_id, 'display_name': title,
                'type': project_type, 'purpose': purpose, 'languages': [], 'entry_point': None,
                'project_revision': 0, 'summary_revision': 0, 'files': [],
                'preview': {'supported': False, 'reason': 'لم تُحفظ ملفات نهائية بعد.'},
                'validation': {'static_checks': 'not_run', 'behavioral_tests': 'not_run', 'executed': False},
                'generation_status': 'idle', 'created_at': now(), 'updated_at': now(),
                'source_fingerprint': digest(''), 'legacy_id': legacy_id}
        with self.lock:
            with SafeTree(self.root) as tree:
                import os
                os.mkdir(folder, mode=0o700, dir_fd=tree.fd)
            self.db.execute('INSERT INTO projects VALUES(?,?,?)', (project_id, folder, json.dumps(meta, ensure_ascii=False)))
            self.db.commit()
            self._derived(project_id, meta)
        return self.get(project_id)

    def list(self):
        with self.lock:
            result=[]
            for row in self.db.execute('SELECT * FROM projects ORDER BY rowid DESC LIMIT 300'):
                try:result.append(self._decode(row['metadata'],row['id']))
                except InvalidIndex:result.append(self._fallback(row['id'],row['directory']))
            return result

    @staticmethod
    def _decode(raw,project_id):
        try:
            meta=json.loads(raw)
            assert meta['project_id']==project_id and meta['schema_version']==1
            assert isinstance(meta['display_name'],str) and isinstance(meta['purpose'],str)
            assert type(meta['project_revision']) is int and meta['project_revision']>=0
            assert isinstance(meta['files'],list) and (meta['files'] or not meta['project_revision'])
            assert isinstance(meta['preview']['supported'],bool)
            assert meta['validation']['static_checks'] in ('not_run','passed','failed')
            for entry in meta['files']:
                safe_path(entry['path'])
                assert re.fullmatch(r'[a-f0-9]{64}',entry['sha256']) and entry['size']>=0 and entry['mtime_ns']>=0
            return meta
        except (ValueError,TypeError,KeyError,AssertionError) as exc:
            raise InvalidIndex('الفهرس غير صالح؛ افتح المشروع واستخدم «مراجعة الملفات وتحديث الفهرس».') from exc

    @staticmethod
    def _fallback(project_id,directory):
        return {'schema_version':1,'project_id':project_id,'display_name':directory.rsplit('-',1)[0],
            'purpose':'الوصف السابق غير متاح؛ أعد بناء الفهرس من الملفات الفعلية.',
            'type':'other','languages':[],'entry_point':None,'project_revision':0,'summary_revision':0,
            'files':[],'preview':{'supported':False,'reason':'الفهرس يحتاج إلى إعادة بناء.'},
            'validation':{'static_checks':'not_run','behavioral_tests':'not_run','executed':False},
            'generation_status':'failed','source_freshness':'invalid','index_valid':False,
            'summary':'الفهرس غير صالح. إعادة بنائه لا تُشغّل الملفات ولا تنشئ طلب توليد.'}

    def _canonical(self, project_id):
        return self._decode(self._row(project_id)['metadata'],project_id)

    def get(self, project_id, *, freshness=True):
        with self.lock:
            try:meta = self._canonical(project_id)
            except InvalidIndex:return self._fallback(project_id,self._row(project_id)['directory'])
            if freshness:
                try:
                    with SafeTree(self.directory(project_id)) as tree:
                        actual = tree.inventory()
                        indexed = {x['path']: x for x in meta['files']}
                        changed = set(actual) != set(indexed)
                        for path, entry in actual.items():
                            old = indexed.get(path)
                            if old and (entry['size'], entry['mtime_ns']) != (old['size'], old['mtime_ns']):
                                if hashlib.sha256(tree.read(path)).hexdigest() != old['sha256']:
                                    changed = True
                        meta['source_freshness'] = 'stale' if changed else 'current'
                except ProjectError as exc:
                    meta['source_freshness'] = 'unsafe'
                    meta['freshness_error'] = str(exc)
            meta['summary'] = self.summary(meta)
            return meta

    @staticmethod
    def summary(meta):
        # Purpose is a user description, never an instruction or a claim of tests.
        lines = [f"Project {meta['project_id']} / revision {meta['project_revision']}",
                 'Title: ' + meta['display_name'], 'Requested purpose: ' + meta['purpose'][:600],
                 'Type: ' + meta['type'], 'Languages: ' + ', '.join(meta['languages']),
                 'Entry point: ' + str(meta['entry_point']),
                 'Preview available: ' + str(meta['preview']['supported']),
                 'Static checks: ' + meta['validation']['static_checks'] + '; behavioral tests: not_run',
                 'Source freshness: ' + meta.get('source_freshness', 'current')]
        for entry in meta['files'][:12]:
            if re.search(r'secret|credential|token|password|private',entry['path'],re.I):continue
            item = entry['path'] + ' — ' + entry['role']
            if sum(map(len, lines)) + len(item) > 3000:
                break
            lines.append(item)
        if len(meta['files']) > 12:
            lines.append(f"Full file index available separately: {len(meta['files'])} files")
        return '\n'.join(lines)

    def _derived(self, project_id, meta):
        with SafeTree(self.directory(project_id)) as tree:
            tree.write('.neura/project.json', json.dumps(meta, ensure_ascii=False, indent=2), internal=True)
            tree.write('.neura/summary.md', self.summary(meta), internal=True)

    def set_generation(self, project_id, state, job_id=None):
        with self.lock:
            meta = self._canonical(project_id)
            meta['generation_status'] = state
            if job_id is not None:
                meta['latest_job_id'] = job_id
            self.db.execute('UPDATE projects SET metadata=? WHERE id=?', (json.dumps(meta, ensure_ascii=False), project_id))
            self.db.commit()
            if state in ('completed','failed','cancelled'):
                try:self._derived(project_id,meta)
                except ProjectError:pass  # SQLite remains authoritative if a derived view cannot be refreshed.

    def read(self, project_id, path):
        safe_path(path)
        with self.lock, SafeTree(self.directory(project_id)) as tree:
            meta = self.get(project_id)
            data = tree.read(path)
            try:
                text = data.decode('utf-8')
                binary=False
            except UnicodeError:
                text=None;binary=True
            return {'path': path, 'content': text, 'sha256': hashlib.sha256(data).hexdigest(),
                    'binary':binary,'project_revision': meta['project_revision'], 'source_freshness': meta['source_freshness']}

    def committed_files(self, project_id):
        with self.lock:
            meta = self._canonical(project_id)
            if not meta['project_revision']:
                return {}
            with SafeTree(self.directory(project_id)) as tree:
                snapshot = tree.read(f".neura/revisions/{meta['project_revision']}.json", internal=True, limit=6_000_000)
            return snapshot_files(snapshot)

    def commit(self, project_id, files, expected_revision):
        bounded_files(files)
        languages, preview, validation = inspect_files(files)
        if validation['errors']:
            raise ProjectError('فشل الفحص الساكن: ' + '; '.join(validation['errors'])[:1000])
        with self.lock:
            old = self.get(project_id)
            if old['project_revision'] != expected_revision or old['source_freshness'] != 'current':
                raise Conflict('تغير المشروع؛ أعد تحميل الملفات أو راجع التغييرات الخارجية أولًا')
            # Recheck actual source hashes at a write boundary, including edits that
            # preserved file size/mtime. Metadata questions do not perform this scan.
            with SafeTree(self.directory(project_id)) as checked:
                if any(hashlib.sha256(checked.read(item['path'])).hexdigest() != item['sha256'] for item in old['files']):
                    raise Conflict('تغير محتوى ملف خارج التطبيق؛ راجع الفهرس أولًا')
            meta = self._canonical(project_id)
            revision = expected_revision + 1
            meta.update(project_revision=revision, summary_revision=revision, languages=languages,
                        preview=preview, validation=validation, entry_point=preview['entry_point'], updated_at=now())
            meta['type'] = 'static_web' if preview['supported'] else 'python' if 'Python' in languages else 'other'
            with SafeTree(self.directory(project_id)) as tree:
                tree.write(f'.neura/revisions/{revision}.json', snapshot_json(files), internal=True)
                journal = {'old_revision': expected_revision, 'new_revision': revision, 'paths': sorted(set(files) | {x['path'] for x in old['files']})}
                tree.write('.neura/transaction.json', json.dumps(journal), internal=True)
                try:
                    for path, text in files.items():
                        tree.write(path, text)
                    for entry in old['files']:
                        if entry['path'] not in files:
                            tree.remove(entry['path'])
                    inventory = {path: tree.info(path) for path in files}
                    if not inventory or any(hashlib.sha256(tree.read(path)).hexdigest() != digest(text) for path, text in files.items()):
                        raise ProjectError('لم ينجح التحقق من الملفات المحفوظة؛ أُبقيت آخر مراجعة سليمة')
                    meta['files'] = [{'path': path, 'role': LANGUAGES.get(Path(path).suffix.lower(), 'Text') + ' source',
                                      'size': info['size'], 'mtime_ns': info['mtime_ns'], 'sha256': digest(files[path])}
                                     for path, info in inventory.items()]
                    meta['source_fingerprint'] = digest(json.dumps([(x['path'], x['sha256']) for x in meta['files']]))
                    self.db.execute('UPDATE projects SET metadata=? WHERE id=?', (json.dumps(meta, ensure_ascii=False), project_id))
                    self.db.commit()
                    tree.remove('.neura/transaction.json', internal=True)
                except BaseException:
                    self.db.rollback()
                    self._recover(project_id)
                    raise
            self._derived(project_id, meta)
            return self.get(project_id)

    def _recover(self, project_id):
        with self.lock, SafeTree(self.directory(project_id)) as tree:
            try:
                journal = json.loads(tree.read('.neura/transaction.json', internal=True))
            except (ProjectError, FileNotFoundError):
                return
            meta = self._canonical(project_id)
            if meta['project_revision'] != journal['new_revision']:
                files = self.committed_files(project_id)
                # Retain a recoverable record of any partially written text.
                partial = {}
                for path in journal['paths']:
                    try:
                        partial[path] = tree.read(path).decode('utf-8')
                    except (ProjectError, UnicodeError):
                        pass
                tree.write('.neura/recovery-' + uuid.uuid4().hex + '.json', json.dumps(partial, ensure_ascii=False), internal=True)
                for path in journal['paths']:
                    if path in files:
                        tree.write(path, files[path])
                    else:
                        tree.remove(path)
                # Restored source has new mtimes; update stats without inventing a revision.
                inventory = tree.inventory()
                for item in meta['files']:
                    if item['path'] in inventory:
                        item['mtime_ns'] = inventory[item['path']]['mtime_ns']
                self.db.execute('UPDATE projects SET metadata=? WHERE id=?', (json.dumps(meta, ensure_ascii=False), project_id))
                self.db.commit()
            tree.remove('.neura/transaction.json', internal=True)

    def save_file(self, project_id, path, content, revision, expected_sha256):
        with self.lock:
            current = self.read(project_id, path)
            if current['binary']:raise ProjectError('الأصل الثنائي يُعرض ولا يُحرر كنص')
            if current['sha256'] != expected_sha256:
                raise Conflict('تغير الملف منذ فتحه؛ لم يُستبدل محتواه')
            files = self.committed_files(project_id)
            files[path] = content
            return self.commit(project_id, files, revision)

    def rebuild(self, project_id, expected_revision):
        with self.lock, SafeTree(self.directory(project_id)) as tree:
            broken=False
            try:meta=self._canonical(project_id)
            except InvalidIndex:
                broken=True
                meta=self._fallback(project_id,self._row(project_id)['directory'])
                try:meta=self._decode(tree.read('.neura/project.json',internal=True).decode(),project_id)
                except (ProjectError,UnicodeError):pass
            if not broken and meta['project_revision'] != expected_revision:
                raise Conflict('تغيرت مراجعة المشروع')
            files={}
            from src.core.project_files import BINARY_ASSETS
            inventory=tree.inventory()
            for path in inventory:
                data=tree.read(path)
                try:files[path]=data if Path(path).suffix.lower() in BINARY_ASSETS else data.decode('utf-8')
                except UnicodeError as exc:raise ProjectError('ملف غير نصي غير مدعوم: '+path) from exc
            bounded_files(files)
            languages,preview,validation = inspect_files(files)
            if validation['errors']:
                raise ProjectError('لم يُعتمد الفهرس: ' + '; '.join(validation['errors'])[:1000])
            if tree.inventory()!=inventory:raise Conflict('تغيرت الملفات أثناء فحص الفهرس')
            revision=meta['project_revision']+1
            if broken:
                tree.write('.neura/invalid-index-'+uuid.uuid4().hex+'.txt',self._row(project_id)['metadata'],internal=True)
                try:
                    import os
                    fd,_=tree.parent('.neura/revisions/sentinel',internal=True)
                    try:revision=max([int(name[:-5]) for name in os.listdir(fd) if re.fullmatch(r'\d{1,9}\.json',name)]+[0])+1
                    finally:os.close(fd)
                except ProjectError:pass
            meta.update(project_revision=revision,summary_revision=revision,languages=languages,
                preview=preview,validation=validation,entry_point=preview['entry_point'],updated_at=now(),index_valid=True)
            meta.pop('source_freshness',None);meta.pop('summary',None)
            meta['type']='static_web' if preview['supported'] else 'python' if 'Python' in languages else 'other'
            meta['files']=[{'path':p,'role':LANGUAGES.get(Path(p).suffix.lower(),'Asset')+' source',**info,'sha256':digest(files[p])} for p,info in inventory.items()]
            meta['source_fingerprint']=digest(json.dumps([(x['path'],x['sha256']) for x in meta['files']]))
            # Reindex never overwrites source: it snapshots the reviewed current files.
            tree.write(f'.neura/revisions/{revision}.json',snapshot_json(files),internal=True)
            self.db.execute('UPDATE projects SET metadata=? WHERE id=?',(json.dumps(meta,ensure_ascii=False),project_id));self.db.commit()
            self._derived(project_id,meta)
            return self.get(project_id)

    def answer(self, project_id, question):
        meta = self.get(project_id)
        if meta['source_freshness'] != 'current':
            return {'answer': 'تغيرت ملفات المشروع خارج التطبيق؛ راجعها ثم حدّث الفهرس.', 'source': 'metadata', 'model_called': False, 'stale': True}
        if re.search(r'لغة|لغات|language', question, re.I):
            answer = 'اللغات الموجودة: ' + (', '.join(meta['languages']) or 'لم تُحفظ ملفات بعد')
        elif re.search(r'ما (?:هو|هذا|هي).*المشروع|ماهذا المشروع|غرض|purpose|what is (?:this|the) project|which project|لماذا.*(?:أنش|انش|صُنع)|why.*(?:created|built)', question, re.I):
            answer = meta['display_name'] + '\nالغرض المطلوب: ' + meta['purpose'] + '\nالمعاينة: ' + ('متاحة' if meta['preview']['supported'] else 'غير متاحة')
        else:
            return {'answer': 'هذا السؤال يحتاج فحص ملفات فعلية؛ اختر الملفات ذات الصلة أولًا.',
                    'source': 'source_required', 'model_called': False, 'files': meta['files']}
        return {'answer': answer, 'source': 'metadata', 'model_called': False,
                'project_revision': meta['project_revision'], 'summary': meta['summary']}

    def export(self, project_id):
        with self.lock, SafeTree(self.directory(project_id)) as tree:
            meta = self.get(project_id)
            if meta['source_freshness'] != 'current':
                raise Conflict('راجع التغييرات الخارجية قبل التصدير')
            output = io.BytesIO()
            with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
                for entry in meta['files']:
                    archive.writestr(entry['path'], tree.read(entry['path']))
                archive.writestr('.neura/project.json', json.dumps(meta, ensure_ascii=False, indent=2))
            return output.getvalue()
