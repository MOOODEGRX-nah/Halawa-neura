"""Shared user-command normalization; classification is never authorization."""
import re
from src.core.application_targets import normalize


def command_text(text):
    original=text.strip()
    if not original or original.startswith(('"',"'",'«','“','`','>','<','~~~')) or '```' in original:
        return ''
    q=normalize(text)
    for _ in range(4):
        before=q
        q=re.sub(r'^(?:لو سمحت|من فضلك|ارجوك|رجاء|رجاءا|ممكن|please)\s+','',q)
        q=re.sub(r'^(?:هل\s+(?:يمكنك|تستطيع|تقدر|بامكانك)|تقدر|تستطيع|يمكنك|بامكانك|اريد(?:\s+منك)?|ابي|ابغى|can you|could you|would you|i want you to|i want)\s+(?:ان\s+)?','',q)
        if q==before:break
    if q!=normalize(text):
        q=re.sub(r'^فتح\s+','افتح ',q)
        q=re.sub(r'^(?:البحث|بحث)\s+','ابحث ',q)
        q=re.sub(r'^انشاء\s+','انشئ ',q)
        q=re.sub(r'^(?:اضافة|تضيف(?:لي)?)\s+','اضف ',q)
        if re.match(r'^(?:زرا?|button)\b',q):q='اضف '+q
        q=re.sub(r'^(?:يدعم|تدعم)\s+(الموقع|المشروع|الصفحة)\s+',r'اجعل \1 يدعم ',q)
        q=re.sub(r'^(this website|the site|it)\s+to\s+(support|include)\s+',r'make \1 \2 ',q)
    q=re.sub(r'^(?:ضيف|حط)\s+','اضف ',q)
    q=re.sub(r'^(?:ازالة|حذف|تحذف|تزيل)\s+','احذف ',q)
    q=re.sub(r'^delete\s+','remove ',q)
    if re.match(r'^(?:لا\b|لاتفتح|ما تفتح|ماتفتح|ليس\b|لم\b|ماذا\b|لو قلت\b|افترض\b|كيف\b|كيفية\b|اشرح\b|فسر\b|معنى\b|مثال\b|how\b|explain\b|do not\b|don.t\b|never\b)',q):return ''
    return q

