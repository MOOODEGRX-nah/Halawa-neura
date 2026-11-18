"""Guard against ordinary chat replies that claim completed file/project actions.

`/v1/chat/completions` never creates jobs, edits files or saves revisions. Prompt instructions
already forbid such claims, but a local model can still write «تم تحديث الكود في index.html».
This module detects completed-action claims about files, code or projects in the generated text,
so the server can append a fixed, truthful notice to the same reply. It never edits or hides model
text and never changes a project; job receipts and project cards remain the source of truth.
"""
import re

_TASHKEEL = re.compile(r'[ً-ْٰـ]')

# Completed-action phrasing only (past tense / status), not advice such as «يمكنك تحديث الملف».
_CLAIM = re.compile(
    r'(?:'
    r'\bتم(?:ت)?\s+(?:بنجاح\s+)?(?:ال)?(?:تحديث|تعديل|حفظ|اضاف[ةه]|انشاء|تنفيذ|تطبيق|ازال[ةه]|حذف|دمج|اصلاح)'
    r'|\bلقد\s+(?:قمت|عدلت|اضفت|حدثت|حفظت|انشات|حذفت|ازلت|اصلحت|نفذت)'
    r'|\bقمت\s+ب(?:تعديل|تحديث|اضاف[ةه]|حفظ|انشاء|حذف|ازال[ةه]|اصلاح|تنفيذ)'
    r'|(?<!\w)(?:اضيفت|اضيف|عدلت|حدثت|حفظت|حذفت)\s+(?:ال)?(?:فئ[ةه]|ملف|ملفات|الكود|كود|زر|قسم|خدم[ةه]|بطاق[ةه]|صفح[ةه]|ميز[ةه]|التعديلات|البيانات)'
    r'|\bملفات\s+محدث[ةه]'
    r'|\bالحال[ةه]\s*:\s*تم'
    r'|\bI(?:\'ve|\s+have)?\s+(?:now\s+)?(?:updated|modified|added|saved|created|implemented|edited|removed|applied|fixed)\b'
    r'|\b(?:has|have)\s+(?:now\s+)?been\s+(?:updated|modified|added|saved|created|applied|edited|removed|implemented|fixed)\b'
    r'|\b(?:changes|files)\s+(?:were|are)\s+(?:saved|applied|updated)\b'
    r')', re.I)
_CONTEXT = re.compile(r'\.(?:html?|css|js|py|json|md)\b|ملف|الملفات|الكود|كود|المشروع|مشروع|الموقع|الصفح[ةه]|\b(?:file|files|code|project|website|page|repo)\b', re.I)

NOTICE = ('\n\n— تنبيه من Neura: هذا رد محادثة فقط؛ لم يُعدِّل هذا الرد أي ملف ولم يحفظ مراجعة ولم ينشئ مهمة. '
          'حالة المشروع الفعلية تظهر في بطاقات المهام ومساحة المبرمج. لتنفيذ تعديل اكتب طلبًا صريحًا مثل «عدّل هذا المشروع: …».')


def normalize(text):
    text = _TASHKEEL.sub('', text or '')
    return text.translate(str.maketrans({'أ': 'ا', 'إ': 'ا', 'آ': 'ا', 'ى': 'ي'}))


def unsupported_action_claim(text):
    """Return the first completed file/project action claim in `text`, or None."""
    value = normalize(text)
    if not _CONTEXT.search(value): return None
    match = _CLAIM.search(value)
    return match.group(0) if match else None


def guard_receipt(text):
    claim = unsupported_action_claim(text)
    return None if claim is None else {'unsupported_action_claim': claim, 'notice_appended': True,
                                       'scope': 'Ordinary chat cannot edit files; only job receipts prove changes'}
