"""Server-owned candidate coordinates; model text never selects a source anchor."""
from dataclasses import dataclass
import hashlib
import json
from src.core.project_files import ProjectError, bounded_files, safe_path
from src.core.project_store import digest


@dataclass(frozen=True)
class RepairTarget:
    target_id: str
    path: str
    start: int
    end: int
    sha256: str


class RepairTargets:
    """One immutable candidate snapshot, including unchanged/binary file hashes.

    Every text byte is supplied once as bounded contiguous line groups. Coordinates refer to the
    original candidate, never to intermediate replacements. No fuzzy matching.
    """
    def __init__(self, files, revision=None, binding=None, ranges=None):
        self.hashes={p:digest(v) for p,v in files.items()}
        self.revision=revision
        self.binding=dict(binding or {})
        self.snapshot=hashlib.sha256(json.dumps({'revision':revision,'files':self.hashes,'binding':self.binding,'ranges':ranges},sort_keys=True).encode()).hexdigest()
        self.targets={};self.source=[]
        for path,value in files.items():
            safe_path(path)
            if not isinstance(value,str):continue
            parts=[];segments=[]
            if ranges is not None:
                cursor=0
                for start,end in sorted(ranges.get(path,[])):
                    if not 0<=cursor<=start<end<=len(value):raise ProjectError('نطاقات دلالية متداخلة أو غير صالحة')
                    if start>cursor:segments.append((cursor,start,False))
                    segments.append((start,end,True));cursor=end
                if cursor<len(value):segments.append((cursor,len(value),False))
            else:
                groups=[];group=''
                for line in value.splitlines(keepends=True):
                    if group and len(group)+len(line)>512:groups.append(group);group=''
                    group+=line
                if group:groups.append(group)
                cursor=0
                for group in groups:
                    if len(group)>4000:raise ProjectError('سطر المرشح أكبر من نطاق الإصلاح المحدود؛ لم يُقتطع المصدر')
                    segments.append((cursor,cursor+len(group),True));cursor+=len(group)
            for start,end,editable in segments:
                key=None
                if editable:
                    key='t_'+hashlib.sha256(f'{self.snapshot}:{path}:{start}:{end}'.encode()).hexdigest()[:16]
                    self.targets[key]=RepairTarget(key,path,start,end,digest(value[start:end]))
                parts.append({'target_id':key,'source':value[start:end]})
            self.source.append({'path':path,'spans':parts})
        if len(self.targets)>512:raise ProjectError('عدد نطاقات الإصلاح يتجاوز الحد الآمن')

    def apply(self, files, edits, revision=None, binding=None):
        if dict(binding or {})!=self.binding or revision!=self.revision or {p:digest(v) for p,v in files.items()}!=self.hashes:
            raise ProjectError('تغيرت مراجعة المرشح أو بصمته؛ رُفض الإصلاح القديم')
        scheduled={}
        for edit in edits:
            key=edit.target_id if hasattr(edit,'target_id') else edit['target_id']
            after=edit.after if hasattr(edit,'after') else edit['after']
            target=self.targets.get(key)
            if target is None:raise ProjectError('معرّف هدف الإصلاح غير صادر لهذا المرشح')
            source=files[target.path]
            if digest(source[target.start:target.end])!=target.sha256:raise ProjectError('بصمة نطاق الإصلاح لا تطابق المرشح')
            scheduled.setdefault(target.path,[]).append((target.start,target.end,after))
        return apply_spans(files,scheduled)

    def manifest(self):
        return {'candidate_sha256':self.snapshot,'base_revision':self.revision,'source_hashes':self.hashes,'binding':self.binding,
                'targets':[vars(t) for t in self.targets.values()]}


def apply_spans(files, scheduled):
    """Validate the entire set before building any candidate replacement."""
    for path,edits in scheduled.items():
        safe_path(path)
        if path not in files or not isinstance(files[path],str):raise ProjectError('ملف نطاق الإصلاح غير صالح')
        last=-1
        for start,end,after in sorted(edits):
            if not isinstance(after,str) or not 0<=start<end<=len(files[path]) or start<last:
                raise ProjectError('نطاقات الإصلاح متداخلة أو مكررة أو غير صالحة؛ لم يُطبّق أي تعديل')
            last=end
    result=dict(files)
    for path,edits in scheduled.items():
        for start,end,after in sorted(edits,reverse=True):result[path]=result[path][:start]+after+result[path][end:]
    bounded_files(result)
    return result
