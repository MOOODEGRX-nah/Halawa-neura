"""Session-scoped project context and one-use proposals, never assistant authority."""
import re
import json
import hashlib
import uuid
import time
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from src.core.application_targets import normalize
from src.core.project_files import Conflict, ProjectError


class ProjectDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    intent: Literal['explanation', 'edit', 'proposal', 'clarification']
    # Classification cannot select a project, expand requests or supply tool args.
    reason: str = Field(max_length=160)


class IntentDecision(BaseModel):
    """Durable user-turn resolution; executable arguments remain separately validated."""
    model_config=ConfigDict(extra='forbid')
    schema_version: Literal[1]=1
    intent: Literal['explanation','project.create','project.edit','project.metadata','project.open','proposal','task.status','desktop.action','clarification','plan','unknown']
    session_id: str|None
    source_turn_id: str
    project_id: str|None=None
    base_revision: int|None=Field(default=None,ge=0)
    job_id: str|None=None
    proposal_id: str|None=None
    resolution_source: Literal['validated_user_dispatch']='validated_user_dispatch'


def edit_command(q):
    return bool(re.match(r'^(?:حسن|تحسن|طور|تطور|جمل|تجمل|حسنلي|طورلي|polish|improve|refine|redesign|enhance)\s+(?:(?:لي|a|an|the|this|current)\s+)*(?:واجه[هة]|الواجه[هة]|تصميم|التصميم|تصميمه|شكله|شكل|الموقع|موقع|المشروع|website|site|ui|interface|design|layout)\b',q) or
        re.match(r'^(?:خل|خلي|خله|اجعل|make)\s+(?:(?:الموقع|المشروع|الواجه[هة]|the site|this website|it)\s+)?(?:احترافي|احترافيا|اجمل|اسرع|professional|beautiful|faster)\b',q) or
        re.match(r'^(?:اضف|تضيف|add)\s+(?:(?:لي|a|some)\s+)?(?:انيميشن|انميشن|حركة|حركات|animation|animations|motion)\b',q))


def followup_kind(text):
    q=normalize(text)
    if re.match(r'^(?:نعم ولكن|نعم لكن|yes but)\b',q):return 'amend'
    if re.fullmatch(r'(?:نعم|اي|ايوه|اجل|موافق|طبقها|نفذها|نفذ التعديلات|ابدا|طبق|نفذ|فل تبرمج|فلتبرمج|yes|apply it|do it|go ahead)',q):return 'accept'
    if re.fullmatch(r'(?:لا|لا تنفذ|لا تطبقها|تراجع|no|reject|do not apply)',q):return 'reject'
    if re.fullmatch(r'(?:لم تفعل شي(?:ء|ئا)? حتى الان|ما سويت شي|وش صار|هل انتهيت|ما حالة (?:المشروع|المهمة)|حالة المهمة|task status|did you finish|nothing changed|what happened|وين التعديل|لم يتغير الموقع)',q):return 'status'
    if re.fullmatch(r'(?:اوقف (?:التوليد|المهمة|التعديل)|الغ (?:المهمة|التعديل)|cancel (?:the )?(?:task|job|edit)|stop generation)',q):return 'cancel'
    return None


class ProjectConversation:
    def __init__(self,store):
        self.store=store
        with store.lock:
            store.db.execute('CREATE TABLE IF NOT EXISTS conversation_projects(session TEXT PRIMARY KEY, project_id TEXT, job_id TEXT, updated REAL)')
            store.db.execute('CREATE TABLE IF NOT EXISTS project_proposals(session TEXT PRIMARY KEY, project_id TEXT, revision INTEGER, request TEXT, expires REAL, state TEXT)')
            columns={row['name'] for row in store.db.execute('PRAGMA table_info(project_proposals)')}
            if 'details' not in columns:store.db.execute("ALTER TABLE project_proposals ADD COLUMN details TEXT NOT NULL DEFAULT '{}'")
            store.db.execute("UPDATE project_proposals SET state='interrupted' WHERE state='pending'")
            store.db.commit()

    def bind(self,session,project_id,job_id=None):
        if not session:return
        self.store.get(project_id)
        with self.store.lock:
            old=self.get(session)
            if old and old['project_id']!=project_id:self.invalidate(session)
            if job_id is None and old and old['project_id']==project_id:job_id=old['job_id']
            self.store.db.execute('INSERT OR REPLACE INTO conversation_projects VALUES(?,?,?,?)',(session,project_id,job_id,time.time()))
            self.store.db.commit()

    def get(self,session):
        if not session:return None
        with self.store.lock:
            row=self.store.db.execute('SELECT * FROM conversation_projects WHERE session=?',(session,)).fetchone()
            return dict(row) if row else None

    def invalidate(self,session):
        if not session:return
        with self.store.lock:
            self.store.db.execute("UPDATE project_proposals SET state='rejected' WHERE session=? AND state='pending'",(session,))
            self.store.db.commit()

    def propose(self,session,project_id,request,source_turn_id=None):
        if not session:raise ProjectError('افتح محادثة قبل حفظ اقتراح تعديل')
        project=self.store.get(project_id)
        details={'proposal_id':'pp_'+uuid.uuid4().hex,'session_id':session,'source_turn_id':source_turn_id,
            'project_id':project_id,'base_revision':project['project_revision'],'scope':request,
            'source_hashes':{f['path']:f['sha256'] for f in project['files']},'permissions':['project.edit'],
            'preserved_requirements':project.get('accepted_requirements',[])}
        details['digest']=hashlib.sha256(json.dumps(details,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        with self.store.lock:
            self.store.db.execute('INSERT OR REPLACE INTO project_proposals(session,project_id,revision,request,expires,state,details) VALUES(?,?,?,?,?,?,?)',
                (session,project_id,project['project_revision'],request,time.time()+300,'pending',json.dumps(details,ensure_ascii=False)))
            self.store.db.commit()
        return {'kind':'proposal','project_id':project_id,'base_revision':project['project_revision'],'proposal_id':details['proposal_id'],'proposal_digest':details['digest'],
                'message':'هل تريد تطبيق هذا الطلب على «'+project['display_name']+'»؟ '+request[:220]+' — لم تتغير الملفات بعد. أجب نعم للتنفيذ أو لا للإلغاء.'}

    def consume(self,session,project_id):
        with self.store.lock:
            row=self.store.db.execute('SELECT * FROM project_proposals WHERE session=?',(session,)).fetchone()
            if not row or row['state']!='pending':return None
            project=self.store.get(row['project_id'])
            valid=(row['expires']>=time.time() and row['project_id']==project_id and
                   row['revision']==project['project_revision'] and project['source_freshness']=='current' and
                   json.loads(row['details']).get('source_hashes')=={f['path']:f['sha256'] for f in project['files']})
            self.store.db.execute('UPDATE project_proposals SET state=? WHERE session=?',('consumed' if valid else 'conflict',session));self.store.db.commit()
            if not valid:raise Conflict('انتهت صلاحية الاقتراح أو تغير مشروعه/مراجعته؛ لم ينفذ شيء. أرسل طلب التعديل من جديد.')
            return dict(row)

    def status(self,session,jobs,cancel=False):
        context=self.get(session)
        if not context or not context['job_id']:
            return {'kind':'status','message':'لا توجد مهمة تنفيذ مرتبطة بهذه المحادثة. لم أؤكد أي تعديل؛ اكتب طلبًا محددًا واختر مشروعه.'}
        job=jobs.cancel(context['job_id']) if cancel else jobs.get(context['job_id'])
        receipt=job.get('execution') or {}
        states={'queued':'في الانتظار','planning':'قيد التخطيط','generating':'يجري توليد مرشح للتعديل','validating':'قيد فحص المرشح','completed':'انتهت المهمة','failed':'فشلت المهمة؛ راجع الخطأ','cancelled':'ألغيت المهمة مع إبقاء آخر مراجعة محفوظة'}
        message=states.get(job['state'],'لم تتأكد النتيجة')+' — '+job['job_id']
        if cancel and job['state'] not in ('completed','failed','cancelled'):message='أُرسل طلب الإلغاء؛ قد يظل المحرك يعمل حتى نقطة توقف آمنة.'
        if receipt.get('outcome')=='saved':message+='؛ حُفظت مراجعة '+str(receipt['result_revision'])+' بدل '+str(receipt['base_revision'])+'، الملفات المتغيرة: '+', '.join(receipt['changed_files'])+'. الفحص الساكن فقط لا يثبت صحة السلوك.'
        elif receipt.get('outcome')=='no_change':message+='؛ لم يتغير محتوى الملفات ولم تُنشأ مراجعة جديدة.'
        if job.get('error'):message+='؛ '+job['error']
        current=self.store.get(job['project_id'])
        if receipt and current['project_revision']!=receipt.get('result_revision'):message+='؛ توجد مراجعة أحدث للمشروع: '+str(current['project_revision'])
        if current['source_freshness']!='current':message+='؛ تغير المصدر خارج التطبيق أو يحتاج مراجعة؛ لا أؤكد أن المعاينة الحالية تطابق آخر مهمة.'
        return {'kind':'status','message':message,'project_id':job['project_id'],'job_id':job['job_id'],'state':job['state'],'execution':receipt,'current_revision':current['project_revision'],'source_freshness':current['source_freshness']}
