"""Validated user-language feature intents, never model/project authorizations.

This intentionally bounded vocabulary is shared by routing and validation.
Unsupported/ambiguous requests remain outside this feature contract.
"""
import re
from dataclasses import dataclass,asdict
from src.core.application_targets import normalize


@dataclass(frozen=True)
class FeatureIntent:
    feature: str
    operation: str
    evidence: str
    provenance: str = 'validated_user_request'


def feature_intents(text):
    if not isinstance(text,str) or len(text)>30000:return []
    q=normalize(text).strip()
    if not q or q.startswith(('"',"'",'«','“','`','>','<','~~~')) or '```' in q:return []
    # Quoted examples and source snippets cannot request a feature.
    q=re.sub(r'"[^"\n]*"|«[^»]*»|“[^”]*”|`[^`]*`', ' ',q)
    result=[]
    for clause in re.split(r'[.!?؟؛;\n]|\bbut\b|\bلكن\b',q):
        clause=clause.strip()
        if not clause:continue
        if re.search(r'\b(?:كيف|كيفية|اشرح|فسر|مثال|افترض|لو قلت|ما معنى|how|explain|example|suppose)\b',clause):continue
        features=[]
        if re.search(r'\b(?:dark(?: mode)?|theme|الوضع الداكن|وضع داكن|الوضع الليلي|وضع ليلي|الثيم الداكن|المظهر الداكن|النمط الداكن|الوضع المظلم)\b',clause):features.append('theme')
        if re.search(r'\b(?:login|log in|sign in|sign-in|ل?تسجيل دخول|ل?تسجيل الدخول)\b',clause):features.append('login')
        if not features:continue
        remove=bool(re.search(r'\b(?:احذف|تحذف|ازل|تزيل|ازالة|حذف|remove|delete|disable)\b',clause))
        negated=bool(re.search(r'\b(?:لا|لن|ليس|مو|مش|ما ابي|ما ابغى|بدون|do not|don.t|never|without)\b',clause))
        if negated:
            if remove:operation='keep'
            else:continue
        elif remove:operation='remove'
        elif re.search(r'\b(?:اضف|ضيف|حط|تضيف|تضيفلي|اضافة|فعل|تفعيل|خل|خلي|اجعل|يكون|احتاج|نحتاج|يحتاج|اريد|ابغى|ابي|وفر|توفير|ممكن|يدعم|بدي|add|enable|implement|include|want|need|provide|support)\b',clause):operation='add'
        elif re.search(r'\b(?:حافظ|ابق|keep|preserve)\b',clause):operation='keep'
        else:continue
        for feature in features:result.append(FeatureIntent(feature,operation,clause))
    return result


def required_features(requirements,current_request):
    result={}
    # Never trust feature flags supplied by generated content or a stored summary.
    texts=[r.get('text','') for r in requirements if r.get('origin')=='user_request']+[current_request]
    for text in texts:
        for item in feature_intents(text):
            if item.operation=='remove':result.pop(item.feature,None)
            else:result[item.feature]=True
    return result


def intent_evidence(text):return [asdict(item) for item in feature_intents(text)]


def _fingerprint(value):
    import hashlib,json
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def validate_contract(contract):
    from src.core.project_files import ProjectError
    if not contract:return {}
    content={k:v for k,v in contract.items() if k!='sha256'}
    if contract.get('version')!=1 or contract.get('sha256')!=_fingerprint(content):raise ProjectError('بصمة عقد متطلبات المستخدم غير مطابقة')
    if contract.get('provenance',{}).get('intent') not in ('project.create','project.edit'):raise ProjectError('عقد الميزات ليس قرار مشروع معتمدًا')
    for states in (contract.get('required',{}),contract.get('prior_required',{})):
        if not isinstance(states,dict) or any(k not in ('theme','login') or v is not True for k,v in states.items()):raise ProjectError('حالة ميزة غير مدعومة في العقد')
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
    prior={};start=0;legacy=[]
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
    changes=intent_evidence(text);required=dict(prior)
    for item in changes:
        if item['operation']=='remove':required.pop(item['feature'],None)
        else:required[item['feature']]=True
    contract={'version':1,'source_request_sha256':digest(text),'provenance':dict(decision),
              'prior_required':prior,'changes':changes,'required':required,'legacy_migration':legacy}
    contract['sha256']=_fingerprint(contract)
    return validate_contract(contract)


def contract_features(contract):return dict(validate_contract(contract).get('required',{}))
