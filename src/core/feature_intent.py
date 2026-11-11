"""Shared bounded user-origin feature grammar with exact source evidence.

Interpretation alone never authorizes a job or device action. Unsupported or
contradictory coordinated units are explicit, never a weaker partial contract.
"""
import re
import unicodedata
from dataclasses import dataclass,asdict,field
from src.core.user_commands import command_text
from src.core.project_files import ProjectError

FEATURES={
 'theme':r'(?:dark(?:\s+mode)?|theme|الوضع\s+الداكن|وضع\s+داكن|الوضع\s+الليلي|وضع\s+ليلي|الثيم\s+الداكن|المظهر\s+الداكن|النمط\s+الداكن|الوضع\s+المظلم)',
 'login':r'(?:login|log\s+in|sign[ -]in|ل?تسجيل\s+(?:الدخول|دخول))'}
OPS={
 'remove':r'(?:احذف|تحذف|ازل|تزيل|ازالة|حذف|remove|delete|disable)',
 'keep':r'(?:حافظ(?:\s+على)?|ابق|keep|preserve)',
 'add':r'(?:اضف|ضيف|حط|تضف|تضيف(?:لي)?|اضافة|فعل|تفعيل|خل|خلي|اجعل|يكون|احتاج|نحتاج|يحتاج|اريد|ابغى|ابي|وفر|توفير|يدعم|بدي|add|enable|implement|include|want|need|provide|support)'}
NEG=r'(?:لا|لن|ليس|مو|مش|ما\s+ابي|ما\s+ابغى|بدون|do\s+not|don[’\x27]t|never|without)'
OP=re.compile(r'(?<!\w)(?:(?P<neg>'+NEG+r')\s+)?(?P<verb>'+'|'.join(OPS.values())+r')(?!\w)')
TARGET=re.compile('|'.join(r'(?P<'+k+r'>(?<!\w)'+v+r'(?!\w))' for k,v in FEATURES.items()))
START='|'.join(list(OPS.values())+[NEG]+list(FEATURES.values())+[r'هل\s+يمكنك',r'لو\s+سمحت',r'من\s+فضلك',r'ممكن',r'please'])
COORD=re.compile(r'(?<!\w)(?:and|but|then|لكن|ثم)(?!\w)|(?<!\w)و(?=\s|(?:'+START+r')(?!\w))')
EXPLAIN=re.compile(r'(?<!\w)(?:كيف|كيفية|اشرح|فسر|مثال|افترض|لو\s+قلت|ما\s+معنى|how|explain|example|suppose)(?!\w)')


@dataclass(frozen=True)
class FeatureIntent:
    feature:str
    operation:str
    evidence:str
    provenance:str='validated_user_request'
    source_span:tuple[int,int]|None=None
    operation_span:tuple[int,int]|None=None
    feature_span:tuple[int,int]|None=None
    polarity:str='positive'


@dataclass
class FeatureInterpretation:
    changes:list[FeatureIntent]=field(default_factory=list)
    issues:list[str]=field(default_factory=list)
    non_actions:list[dict]=field(default_factory=list)

    @property
    def requests_edit(self):return any(i.operation in ('add','remove') for i in self.changes)


def mapped_text(text):
    """Keep a map to original Unicode character offsets; never guess raw spans."""
    chars=[];offsets=[]
    for i,c in enumerate(text):
        for n in unicodedata.normalize('NFKC',c).casefold().translate(str.maketrans('أإآٱ','اااا')):
            if not re.match(r'[\u064b-\u065f\u0670\u0640]',n):chars.append(n);offsets.append((i,i+1))
    return ''.join(chars),offsets


def interpret_features(text):
    result=FeatureInterpretation()
    if not isinstance(text,str) or not text.strip() or text.lstrip().startswith(('"',"'",'«','“','`','>','<','~~~')) or '```' in text:return result
    if len(text)>30000:result.issues.append('الطلب أكبر من حد تفسير الميزات؛ قسّمه إلى طلب محدد.');return result
    q,offsets=mapped_text(text)
    # Mask, do not erase: all provenance coordinates stay in the original text.
    q=re.sub(r'"[^"\n]*"|«[^»]*»|“[^”]*”|`[^`]*`',lambda m:' '*len(m[0]),q)
    if EXPLAIN.search(q):
        if command_text(text):result.issues.append('هل تطلب تغيير الميزات أم شرحها؟ افصل طلب التنفيذ عن المثال أو الشرح.')
        return result
    boundaries=sorted([(m.start(),m.end(),True) for m in COORD.finditer(q)]+[(m.start(),m.end(),m[0] in ',،') for m in re.finditer(r'[.!?؟؛;\n,،]',q)])
    units=[];cursor=0;inherit=False
    for a,b,next_inherit in boundaries:
        if a<cursor:continue
        units.append((cursor,a,inherit));cursor=b;inherit=next_inherit
    units.append((cursor,len(q),inherit));previous=None;positive=False
    def raw_span(a,b):return (offsets[a][0],offsets[b-1][1])
    for a,b,can_inherit in units:
        while a<b and q[a].isspace():a+=1
        while b>a and q[b-1].isspace():b-=1
        if a==b:continue
        unit=q[a:b];targets=list(TARGET.finditer(unit));actions=list(OP.finditer(unit))
        if not targets:
            if (can_inherit and previous is not None) or (actions and TARGET.search(q)):
                result.issues.append('يوجد جزء من الطلب المركب دون ميزة مدعومة واضحة: «'+text[slice(*raw_span(a,b))]+'». حدّد الفعل والميزة المقصودة.')
            previous=None;continue
        if len(targets)>1 and actions:
            result.issues.append('يوجد أكثر من هدف دون رابط عمليات مدعوم؛ حدّد فعل كل ميزة بدل تعميم الفعل الأول.');previous=None;continue
        if actions:
            # Two actions without a coordinating boundary cannot share a target.
            if any(m.start()>=targets[0].start() for m in actions):result.issues.append('افصل أفعال الطلب المركب واربط كل فعل بميزة واضحة.');previous=None;continue
            first=actions[0];prefix=command_text(unit[:first.end()])
            # Questions/mentions cannot gain authority from a verb buried in text.
            lead=bool(prefix and (OP.match(prefix) or re.fullmatch(r'(?:i|we)\s+(?:want|need)',prefix) or re.match(r'^(?:برمج|انشئ|اصنع|صمم|ابن|اكتب|create|build|design|make|write)\b',prefix)))
            if not lead and first.group('neg') is None:previous=None;continue
            meanings=[]
            for match in actions:
                operation=next(k for k,v in OPS.items() if re.fullmatch(v,match['verb']))
                if match['neg']:operation='keep' if operation=='remove' else 'not_add' if operation=='add' else 'ambiguous'
                meanings.append(operation)
            if len(set(meanings))!=1 or 'ambiguous' in meanings:result.issues.append('نفي أو أفعال متعارضة للميزة نفسها؛ ما التغيير المطلوب تحديدًا؟');previous=None;continue
            operation=meanings[0];op_span=raw_span(a+first.start(),a+actions[-1].end());polarity='negated' if first['neg'] else 'positive'
        elif can_inherit and previous is not None:
            prelude=unit[:targets[0].start()].strip()
            if prelude and not re.fullmatch(r'(?:زرا?|الزر|button|a\s+button|the\s+button|ميزة|الميزة)',prelude):
                result.issues.append('الفعل أو الهدف في الجزء المنسق غير واضح؛ لم تُورث له عملية الميزة السابقة.');previous=None;continue
            operation,op_span,polarity=previous
        else:
            # A mention is not an action; it cannot inherit across sentences.
            previous=None;continue
        previous=(operation,op_span,polarity)
        for target in targets:
            feature=target.lastgroup;feature_span=raw_span(a+target.start(),a+target.end());span=(min(op_span[0],feature_span[0]),max(op_span[1],feature_span[1]))
            record=FeatureIntent(feature,operation,text[slice(*span)],source_span=span,operation_span=op_span,feature_span=feature_span,polarity=polarity)
            if operation=='not_add':result.non_actions.append(asdict(record))
            else:result.changes.append(record);positive|=operation in ('add','remove')
        tail=unit[targets[-1].end():]
        if re.match(r'\s+و\S+',tail):result.issues.append('جزء من الطلب بعد الميزة غير محدد؛ وضح الهدف التالي دون توسيع نطاق الحذف.')
    for feature in FEATURES:
        ops={i.operation for i in result.changes if i.feature==feature}
        if 'remove' in ops and len(ops)>1:result.issues.append('الطلب يطلب إزالة وإبقاء/إضافة '+feature+' معًا؛ أيهما تقصد؟')
    if result.non_actions and positive:result.issues.append('يتضمن الطلب شرط عدم إضافة ميزة؛ حدّد التغيير الإيجابي في طلب مستقل كي لا يُتجاهل الشرط.')
    return result


def execution_issue(interpreted):
    if interpreted.issues:return interpreted.issues[0]
    if interpreted.non_actions:return 'شرط عدم الإضافة لا يجيز توليد ميزة أو حذفها؛ حدّد التغيير المطلوب في طلب مستقل.'
    adds={i.feature for i in interpreted.changes if i.operation=='add'}
    removes={i.feature for i in interpreted.changes if i.operation=='remove'}
    if adds and removes and not (adds<={'theme'} and removes<={'login'}):
        return 'هذا الجمع بين الإزالة والإضافة غير مدعوم بأمان في مهمة واحدة؛ أي ميزة تريد تعديلها أولًا؟'
    return None


def feature_intents(text):
    interpreted=interpret_features(text)
    if interpreted.issues:raise ProjectError(interpreted.issues[0])
    return interpreted.changes


def required_features(requirements,current_request):
    result={}
    texts=[r.get('text','') for r in requirements if r.get('origin')=='user_request']+[current_request]
    for text in texts:
        for item in feature_intents(text):
            if item.operation=='remove':result.pop(item.feature,None)
            else:result[item.feature]=True
    return result


def evidence_record(item):
    record=asdict(item)
    for key in ('source_span','operation_span','feature_span'):
        if record[key] is not None:record[key]=list(record[key])
    return record


def intent_evidence(text):return [evidence_record(item) for item in feature_intents(text)]

def _fingerprint(value):
    import hashlib,json
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def validate_contract(contract):
    from src.core.project_files import ProjectError
    if not contract:return {}
    content={k:v for k,v in contract.items() if k!='sha256'}
    if contract.get('version')!=1 or contract.get('sha256')!=_fingerprint(content):raise ProjectError('بصمة عقد متطلبات المستخدم غير مطابقة')
    if contract.get('provenance',{}).get('intent') not in ('project.create','project.edit'):raise ProjectError('عقد الميزات ليس قرار مشروع معتمدًا')
    for states in (contract.get('required',{}),contract.get('prior_required',{}),contract.get('excluded',{}),contract.get('prior_excluded',{})):
        if not isinstance(states,dict) or any(k not in ('theme','login') or v is not True for k,v in states.items()):raise ProjectError('حالة ميزة غير مدعومة في العقد')
    if set(contract.get('required',{})) & set(contract.get('excluded',{})):raise ProjectError('ميزة مطلوبة ومستبعدة في العقد نفسه')
    for change in contract.get('changes',[]):
        if change.get('feature') not in ('theme','login') or change.get('operation') not in ('add','remove','keep') or change.get('provenance')!='validated_user_request':raise ProjectError('تغيير ميزة غير معتمد')
    return contract


def build_contract(text,accepted,decision):
    """Called ONCE at validated job admission, not by downstream validators.

    A decision can only come from the server's authenticated workspace admission
    or conversational/project-selection/one-use-approval path. It is not a tool
    permission. Old accepted user records are migrated at this boundary only.
    """
    from src.core.project_files import ProjectError
    from src.core.project_store import digest
    if decision.get('intent') not in ('project.create','project.edit'):raise ProjectError('لا يُشتق عقد تنفيذ من ذكر ميزة أو رد نموذج')
    interpreted=interpret_features(text)
    issue=execution_issue(interpreted)
    if issue:raise ProjectError(issue)
    prior={};start=0;legacy=[];excluded={}
    # Explicit removals remain exclusions until the user explicitly adds the
    # feature again. Read accepted contracts, never generated source summaries.
    for record in accepted:
        if record.get('origin')!='user_request':continue
        saved=record.get('feature_contract')
        changes=validate_contract(saved).get('changes',[]) if saved else intent_evidence(record.get('text',''))
        if saved and 'excluded' in saved:
            # The latest accepted state survives bounded history retention.
            excluded=dict(saved['excluded'])
            continue
        for item in changes:
            if item['operation']=='remove':excluded[item['feature']]=True
            elif item['operation']=='add':excluded.pop(item['feature'],None)
    for i in range(len(accepted)-1,-1,-1):
        record=accepted[i]
        if record.get('origin')!='user_request' or not record.get('feature_contract'):continue
        saved=validate_contract(record['feature_contract'])
        if saved['source_request_sha256']!=digest(record['text']):raise ProjectError('مصدر متطلبات المشروع لا يطابق العقد المحفوظ')
        prior=dict(saved['required']);start=i+1;break
    for record in accepted[start:]:
        if record.get('origin')!='user_request':continue
        legacy.append({'job_id':record.get('job_id'),'text_sha256':digest(record.get('text',''))})
        for item in feature_intents(record.get('text','')):
            if item.operation=='remove':prior.pop(item.feature,None)
            else:prior[item.feature]=True
    changes=[evidence_record(item) for item in interpreted.changes];required=dict(prior);prior_excluded=dict(excluded)
    for item in changes:
        if item['operation']=='remove':required.pop(item['feature'],None);excluded[item['feature']]=True
        elif item['operation']=='add':required[item['feature']]=True;excluded.pop(item['feature'],None)
        elif item['feature'] in excluded:raise ProjectError('الميزة '+item['feature']+' أزيلت سابقًا؛ طلب إبقائها لا يجيز إضافتها من جديد.')
        else:required[item['feature']]=True
    contract={'version':1,'intent_grammar_version':2,'source_request_sha256':digest(text),'provenance':dict(decision),
              'prior_required':prior,'prior_excluded':prior_excluded,'changes':changes,'required':required,'excluded':excluded,'legacy_migration':legacy}
    contract['sha256']=_fingerprint(contract)
    return validate_contract(contract)


def contract_features(contract):return dict(validate_contract(contract).get('required',{}))
