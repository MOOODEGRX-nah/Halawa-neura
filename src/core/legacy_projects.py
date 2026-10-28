"""Explicit copy-only import; old directories and identifiers are preserved."""
import json
import re
from src.core.project_files import SafeTree,ProjectError,Conflict,bounded_files


class LegacyProjects:
    def __init__(self,store):
        self.store=store
        self.root=store.root.parent/'projects'

    def list(self):
        if not self.root.exists():return []
        imported={p.get('legacy_id'):p['project_id'] for p in self.store.list() if p.get('legacy_id')}
        result=[]
        with SafeTree(self.root) as tree:
            import os
            for name in sorted(os.listdir(tree.fd))[:300]:
                if not re.fullmatch(r'proj_[a-f0-9]{32}',name):continue
                try:
                    with SafeTree(self.root/name) as old:
                        invoice=json.loads(old.read('invoice.json').decode())
                        title=str(invoice.get('user_request',name))[:100]
                    with SafeTree(self.root/name/'files'):pass
                    result.append({'legacy_id':name,'title':title,'imported_project_id':imported.get(name)})
                except (OSError,ProjectError,ValueError):continue
        return result

    def copy(self,legacy_id):
        if not re.fullmatch(r'proj_[a-f0-9]{32}',legacy_id):raise ProjectError('معرّف المخرج القديم غير صالح')
        with self.store.lock:
            existing=None
            for record in self.store.list():
                if record.get('legacy_id')==legacy_id:
                    if record['project_revision']>0:return {'project':self.store.get(record['project_id']),'original_preserved':True,'already_imported':True}
                    existing=record
            if legacy_id not in {entry['legacy_id'] for entry in self.list()}:raise ProjectError('المشروع القديم غير متاح للاستيراد')
            with SafeTree(self.root/legacy_id) as old:
                invoice=json.loads(old.read('invoice.json').decode())
            with SafeTree(self.root/legacy_id/'files') as tree:
                before=tree.inventory();files={p:tree.read(p).decode('utf-8') for p in before}
                bounded_files(files)
                if before!=tree.inventory():raise Conflict('تغيرت الملفات الأصلية أثناء الاستيراد')
            purpose=str(invoice.get('user_request','مشروع مستورد'))
            from src.core.project_validation import inspect_files
            _,_,validation=inspect_files(files)
            if validation['errors']:raise ProjectError('تعذر استيراد الملفات: '+'; '.join(validation['errors'])[:1000])
            identifier='p_'+legacy_id.removeprefix('proj_')
            if self.store.db.execute('SELECT 1 FROM projects WHERE id=?',(identifier,)).fetchone():identifier=None
            project=existing or self.store.create(purpose[:100],purpose,legacy_id=legacy_id,project_id=identifier)
            project=self.store.commit(project['project_id'],files,0)
            return {'project':project,'original_preserved':True,'already_imported':False}
