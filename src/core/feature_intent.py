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
    if not isinstance(text,str) or len(text)>16000:return []
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
        elif re.search(r'\b(?:اضف|تضيف|اضافة|فعل|تفعيل|خل|خلي|اجعل|يكون|احتاج|نحتاج|يحتاج|اريد|ابغى|ابي|وفر|توفير|ممكن|يدعم|بدي|add|enable|implement|include|want|need|provide|support)\b',clause):operation='add'
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
