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
    def __init__(self, files, revision=None, binding=None, ranges=None, focus=None):
        """`focus` (path -> line-aligned regions) supplies ONLY those regions as editable line
        groups; every other span is omitted from the prompt yet stays hash-bound and verbatim."""
        if ranges is not None and focus is not None:raise ProjectError('نطاقات الإصلاح الدلالية والمركزة لا تجتمع')
        self.hashes={p:digest(v) for p,v in files.items()}
        self.revision=revision
        self.binding=dict(binding or {})
        identity={'revision':revision,'files':self.hashes,'binding':self.binding,'ranges':ranges}
        if focus is not None:identity['focus']={p:[list(r) for r in sorted(v)] for p,v in focus.items()}
        self.snapshot=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
        self.targets={};self.source=[]
        for path,value in files.items():
            safe_path(path)
            if not isinstance(value,str):continue
            parts=[];segments=[]
            if focus is not None:
                cursor=0
                for start,end in sorted(focus.get(path,[])):
                    if not 0<=cursor<=start<end<=len(value):raise ProjectError('نطاقات الإصلاح المركزة متداخلة أو غير صالحة')
                    if start>cursor:segments.append((cursor,start,False))
                    segments.extend((s,e,True) for s,e in line_groups(value,start,end));cursor=end
                if cursor<len(value):segments.append((cursor,len(value),False))
                if not any(editable for *_,editable in segments):continue
            elif ranges is not None:
                cursor=0
                for start,end in sorted(ranges.get(path,[])):
                    if not 0<=cursor<=start<end<=len(value):raise ProjectError('نطاقات دلالية متداخلة أو غير صالحة')
                    if start>cursor:segments.append((cursor,start,False))
                    segments.append((start,end,True));cursor=end
                if cursor<len(value):segments.append((cursor,len(value),False))
            else:
                segments.extend((s,e,True) for s,e in line_groups(value,0,len(value)))
            for start,end,editable in segments:
                key=None
                if editable:
                    key='t_'+hashlib.sha256(f'{self.snapshot}:{path}:{start}:{end}'.encode()).hexdigest()[:16]
                    self.targets[key]=RepairTarget(key,path,start,end,digest(value[start:end]))
                if focus is not None and not editable:
                    parts.append({'target_id':None,'omitted_unchanged_chars':end-start,'sha256':digest(value[start:end])})
                else:parts.append({'target_id':key,'source':value[start:end]})
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


def line_groups(value, start, end):
    """Contiguous <=512-char line groups covering value[start:end] exactly."""
    groups=[];cursor=start;group=''
    for line in value[start:end].splitlines(keepends=True):
        if group and len(group)+len(line)>512:groups.append((cursor,cursor+len(group)));cursor+=len(group);group=''
        group+=line
    if group:groups.append((cursor,cursor+len(group)))
    if any(e-s>4000 for s,e in groups):raise ProjectError('سطر المرشح أكبر من نطاق الإصلاح المحدود؛ لم يُقتطع المصدر')
    return groups


def changed_regions(before, files, context_lines=2):
    """Line-aligned regions of each candidate file that differ from the saved revision.

    Returns (focus, replaced): focus maps path -> merged [start,end) character regions
    (changed lines plus `context_lines` unchanged lines on each side); replaced lists the
    saved-revision text that the candidate removed or replaced, so a repair can restore it.
    New text files are wholly in focus. Unchanged files are absent.
    """
    import difflib
    focus={};replaced=[]
    for path,value in files.items():
        if not isinstance(value,str) or not value:continue
        base=before.get(path)
        if not isinstance(base,str):focus[path]=[(0,len(value))];continue
        if base==value:continue
        old=base.splitlines(keepends=True);new=value.splitlines(keepends=True)
        offsets=[0]
        for line in new:offsets.append(offsets[-1]+len(line))
        spans=[]
        for tag,i1,i2,j1,j2 in difflib.SequenceMatcher(None,old,new,autojunk=False).get_opcodes():
            if tag=='equal':continue
            if i2>i1:replaced.append({'path':path,'candidate_line':j1+1,'saved_source':''.join(old[i1:i2])})
            lo=max(0,j1-context_lines);hi=min(len(new),max(j2,j1+1)+context_lines)
            if spans and lo<=spans[-1][1]:spans[-1][1]=max(spans[-1][1],hi)
            else:spans.append([lo,hi])
        regions=[(offsets[lo],offsets[hi]) for lo,hi in spans if offsets[hi]>offsets[lo]]
        if regions:focus[path]=regions
    return focus,replaced


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
