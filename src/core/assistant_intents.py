"""Recognize explicit personal-assistant requests in the user's own message.

Classification is conservative: only clear imperative/question forms match, negations and
quoted/explanatory text never do, and an unresolvable time asks instead of guessing.
The returned intent never executes anything by itself.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from src.core.application_targets import normalize
from src.core.assistant_tools import ascii_digits

NUMBER_WORDS = {'واحد': 1, 'واحده': 1, 'واحدة': 1, 'اثنين': 2, 'اثنتين': 2, 'ثنتين': 2, 'ثلاث': 3, 'ثلاثه': 3, 'ثلاثة': 3, 'اربع': 4, 'اربعه': 4,
                'اربعة': 4, 'خمس': 5, 'خمسه': 5, 'خمسة': 5, 'ست': 6, 'سته': 6, 'ستة': 6, 'سبع': 7, 'سبعه': 7, 'سبعة': 7, 'ثمان': 8,
                'ثمانيه': 8, 'ثمانية': 8, 'ثماني': 8, 'تسع': 9, 'تسعه': 9, 'تسعة': 9, 'عشر': 10, 'عشره': 10, 'عشرة': 10,
                'عشرين': 20, 'ثلاثين': 30, 'اربعين': 40, 'خمسين': 50, 'ستين': 60,
                'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
                'fifteen': 15, 'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50, 'an': 1, 'a': 1}
UNIT_SECONDS = [(r'ثانيتين', 2, 1), (r'ثواني|ثوان|ثانيه|ثانية|seconds?|secs?', 1, None), (r'دقيقتين', 120, 1),
                (r'دقائق|دقايق|دقيقه|دقيقة|minutes?|mins?', 60, None), (r'ساعتين', 7200, 1), (r'ساعات|ساعه|ساعة|hours?|hrs?', 3600, None),
                (r'يومين', 172800, 1), (r'ايام|يوم|days?', 86400, None), (r'اسبوعين', 1209600, 1), (r'اسابيع|اسبوع|weeks?', 604800, None)]
UNIT = '|'.join(p for p, _, _ in UNIT_SECONDS)
NUM = r'\d+(?:\.\d+)?|' + '|'.join(sorted(NUMBER_WORDS, key=len, reverse=True))
WEEKDAY_NAMES = {'الاثنين': 0, 'اثنين': 0, 'الثلاثاء': 1, 'ثلاثاء': 1, 'الاربعاء': 2, 'اربعاء': 2, 'الخميس': 3, 'خميس': 3,
                 'الجمعه': 4, 'الجمعة': 4, 'جمعه': 4, 'السبت': 5, 'سبت': 5, 'الاحد': 6, 'احد': 6,
                 'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3, 'friday': 4, 'saturday': 5, 'sunday': 6}
PERIODS = {'صباحا': 'am', 'صباح': 'am', 'ص': 'am', 'الصبح': 'am', 'الصباح': 'am', 'صبحا': 'am', 'فجرا': 'am', 'الفجر': 'am', 'am': 'am',
           'ظهرا': 'noon', 'الظهر': 'noon', 'عصرا': 'pm', 'العصر': 'pm', 'مساء': 'pm', 'مساءا': 'pm', 'المساء': 'pm', 'م': 'pm',
           'المغرب': 'pm', 'ليلا': 'night', 'الليل': 'night', 'بالليل': 'night', 'pm': 'pm'}
DAY_WORDS = {'اليوم': 0, 'الليله': 0, 'الليلة': 0, 'today': 0, 'tonight': 0, 'غدا': 1, 'غدوه': 1, 'بكره': 1, 'بكرة': 1, 'باكر': 1,
             'tomorrow': 1, 'بعد غد': 2, 'بعد بكره': 2, 'بعد بكرة': 2}


@dataclass
class Intent:
    name: str
    args: dict = field(default_factory=dict)


def clean(text):
    q = normalize(ascii_digits(text))
    for _ in range(3):
        before = q
        q = re.sub(r'^(?:يا\s+)?(?:نيورا|neura|جارفس|jarvis)[,،]?\s+', '', q)
        q = re.sub(r'^(?:لو سمحت|من فضلك|ارجوك|رجاء|ممكن|please|hey|يا)\s+', '', q)
        q = re.sub(r'^(?:هل\s+(?:يمكنك|تستطيع|تقدر|بامكانك)|تقدر|تستطيع|يمكنك|بامكانك|اريد(?:ك)?(?:\s+منك)?|ابيك|ابي|ابغاك|ابغى|ودي|can you|could you|would you|i want you to|please)\s+(?:ان\s+)?', '', q)
        q = re.sub(r'\s+(?:من فضلك|لو سمحت|please)$', '', q)
        if q == before:
            break
    return q


def _number(token):
    token = token.strip()
    if token in NUMBER_WORDS:
        return NUMBER_WORDS[token]
    return float(token)


def _unit_seconds(unit):
    for pattern, seconds, fixed in UNIT_SECONDS:
        if re.fullmatch(pattern, unit):
            return seconds, fixed
    raise ValueError(unit)


REL = re.compile(r'(?:(?<=\s)|^)(?:بعد|خلال|في غضون|in|after)\s+(?:(' + NUM + r')\s+)?(?:(نص|نصف|ربع)\s+)?(' + UNIT + r')(?:\s+(?:و\s*)?(نص|النص|نصف|ربع|الا ربع))?(?=\s|$)')
CLOCK = re.compile(r'(?:(?<=\s)|^)(?:(?:على|عند|في|at)\s+)?(?:(?:ال)?ساعه|(?:ال)?ساعة)?\s*(\d{1,2})(?:[:.](\d{2}))?(?:\s+(?:و\s*)?(نص|النص|ربع|الا ربع))?'
                   r'(?:\s+(' + '|'.join(sorted(PERIODS, key=len, reverse=True)) + r'))?(?=\s|$)')
DAYS = re.compile(r'(?:(?<=\s)|^)(' + '|'.join(sorted(DAY_WORDS, key=len, reverse=True)) + r'|(?:يوم\s+)?(?:' + '|'.join(sorted(WEEKDAY_NAMES, key=len, reverse=True)) + r')'
                  r'|(?:on\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))(?=\s|$)')
STANDALONE_PERIOD = re.compile(r'(?:(?<=\s)|^)(?:في\s+)?(الصبح|الصباح|الظهر|العصر|المغرب|المساء|الليل)(?=\s|$)')


class TimeParse:
    """Resolve a reminder time in `tz` from normalized text; returns (due datetime, consumed spans) or an error."""

    def __init__(self, text, now):
        self.text, self.now, self.spans = text, now, []

    def _take(self, match):
        self.spans.append(match.span())

    def resolve(self):
        rel = REL.search(self.text)
        if rel:
            self._take(rel)
            count = _number(rel[1]) if rel[1] else 1
            seconds, fixed = _unit_seconds(rel[3])
            amount = seconds if fixed else seconds * count
            if rel[2] in ('نص', 'نصف'):
                amount = seconds / 2
            elif rel[2] == 'ربع':
                amount = seconds / 4
            extra = rel[4]
            if extra in ('نص', 'النص', 'نصف'):
                amount += seconds / 2
            elif extra == 'ربع':
                amount += seconds / 4
            elif extra == 'الا ربع':
                amount -= seconds / 4
            if amount < 5 or amount > 366 * 86400:
                return None, 'المدة خارج النطاق المدعوم (من 5 ثوانٍ إلى سنة).'
            return self.now + timedelta(seconds=amount), None
        day_match = DAYS.search(self.text)
        clock_match = None
        for candidate in CLOCK.finditer(self.text):
            prefixed = re.match(r'(?:(?:على|عند|في|at)\s+)?(?:(?:ال)?ساع)', candidate[0].strip())
            if prefixed or candidate[2] or candidate[4] or candidate[3]:
                clock_match = candidate
                break
        period_match = None if clock_match and clock_match[4] else STANDALONE_PERIOD.search(self.text)
        if not day_match and not clock_match and not period_match:
            return None, None
        base = self.now
        explicit_day = None
        if day_match:
            self._take(day_match)
            word = re.sub(r'^(?:يوم|on)\s+', '', day_match[1])
            if word in DAY_WORDS:
                explicit_day = DAY_WORDS[word]
                base = self.now + timedelta(days=explicit_day)
            else:
                ahead = (WEEKDAY_NAMES[word] - self.now.weekday()) % 7 or 7
                explicit_day = ahead
                base = self.now + timedelta(days=ahead)
        period = None
        if clock_match:
            self._take(clock_match)
            hour, minute = int(clock_match[1]), int(clock_match[2] or 0)
            if clock_match[3] in ('نص', 'النص'):
                minute = 30
            elif clock_match[3] == 'ربع':
                minute = 15
            elif clock_match[3] == 'الا ربع':
                hour, minute = hour - 1, 45
            period = PERIODS.get(clock_match[4]) if clock_match[4] else None
            if hour > 23 or minute > 59:
                return None, 'الوقت غير صالح.'
        else:
            if period_match:
                self._take(period_match)
                period = PERIODS.get(period_match[1])
            hour, minute = {'am': 8, 'noon': 12, 'pm': 17, 'night': 21, None: 9}[period], 0
            if day_match and day_match[1] in ('الليله', 'الليلة', 'tonight'):
                hour = 21
        if period in ('pm', 'night') and hour < 12:
            hour = hour + 12 if not (period == 'night' and hour == 12) else 0
        elif period == 'noon' and hour < 11:
            hour += 12
        elif period == 'am' and hour == 12:
            hour = 0
        candidate = base.replace(hour=hour % 24, minute=minute, second=0, microsecond=0)
        if clock_match and period is None and hour <= 12:
            # A bare «الساعة 5»: choose the nearest future of 5:00/17:00 on the chosen day.
            options = [candidate, candidate + timedelta(hours=12)] if hour < 12 else [candidate]
            future = [o for o in options if o > self.now]
            if explicit_day:
                candidate = options[-1] if 1 <= hour <= 6 and len(options) > 1 else options[0]
            elif future:
                candidate = future[0]
        if candidate <= self.now:
            if explicit_day is not None:
                return None, 'هذا الوقت مضى بالفعل؛ اذكر وقتًا قادمًا.'
            candidate += timedelta(days=1)
        return candidate, None

    def remainder(self):
        text = self.text
        for start, end in sorted(self.spans, reverse=True):
            text = text[:start] + ' ' + text[end:]
        return re.sub(r'\s+', ' ', text).strip()


def strip_connectors(text):
    text = re.sub(r'^(?:و\s+)?(?:[اأإ]ن\s+|[اأإ]نه\s+|[اأإ]نني\s+|[اأإ]ني\s+|عن\s+|ب\s+|ب[اأ]ن\s+|ب[اأ]نه\s+|لكي\s+|كي\s+|to\s+|that\s+|about\s+|of\s+)+', '', text.strip(), flags=re.I)
    text = re.sub(r'^ب(?=ال)', '', text)
    return re.sub(r'\s+(?:و|ان|عن|ب|to|that)$', '', text).strip(' ,،.')


def original_span(original, normalized_target):
    """Return the user's original wording (keeping hamza and diacritics) for a normalized fragment."""
    if not normalized_target:
        return ''
    words = original.split()
    for size in range(len(words), 0, -1):
        for start in range(0, len(words) - size + 1):
            fragment = ' '.join(words[start:start + size])
            if normalize(ascii_digits(fragment)) == normalized_target:
                return fragment.strip(' ؟?!.،,')
    return normalized_target


QUESTION = re.compile(r'[?؟]')


def parse(text, now: datetime):
    """Return an Intent for explicit assistant requests, else None."""
    original = text.strip()
    if not original or original.startswith(('"', "'", '«', '“', '`', '>')) or '```' in original or len(original) > 600:
        return None
    q = clean(original)
    if not q or re.match(r'^(?:لا|لاتذكرني|ما تذكرني|don.?t|do not|never|كيف(?!\s+(?:الجو|الطقس|حال|الحال)\b)|اشرح|explain|how(?!.?s the weather))\b', q):
        return None

    # Reading the web (explicit link or Wikipedia) -------------------------------------------
    link = re.search(r'https?://[^\s<>"«»]+', original)
    if link and re.match(r'^(?:لخص|لخصي|تلخيص|اقرا|اقرأ|ملخص|summari[sz]e|tl;?dr|read)\b', q):
        url = link[0].rstrip('.,،؛)!?؟')
        from src.core.web_reader import youtube_id
        return Intent('web.youtube' if youtube_id(url) else 'web.summary', {'url': url})
    match = re.match(r'^(?:ابحث|بحث|اعمل بحث|سو بحث|research)\s+(?:لي\s+)?(?:بعمق|بحثا\s+(?:موسعا|معمقا)|موسع|معمق|deeply|in depth)\s+(?:عن\s+|في\s+|about\s+|on\s+)?(.+)$'
                     r'|^(?:بحث|تقرير)\s+(?:موسع|معمق|شامل)\s+(?:عن|حول)\s+(.+)$|^deep research\s+(?:on\s+|about\s+)?(.+)$', q)
    if match:
        topic = next(g for g in match.groups() if g)
        return Intent('web.research', {'topic': original_span(original, topic.strip())})
    match = re.fullmatch(r'(?:(?:ماذا|ما|وش|ايش|شو)\s+(?:تقول|يقول|تقوله|يقوله)\s+(?:ال)?ويكيبيديا\s+(?:عن|في)\s+(.+)'
                         r'|(?:لخص(?:\s+لي)?|اعطني\s+ملخص(?:ا)?|ملخص)\s+(?:من\s+)?(?:ال)?ويكيبيديا\s+(?:عن\s+|ل)?(.+)'
                         r'|(?:عرفني|عرفنا)\s+(?:ب|على)\s*(.+?)\s+من\s+(?:ال)?ويكيبيديا'
                         r'|what does wikipedia say about\s+(.+)|wikipedia summary (?:of|for)\s+(.+))', q)
    if match:
        topic = next(g for g in match.groups() if g)
        return Intent('web.wikipedia', {'topic': original_span(original, topic.strip()), 'language': 'en' if re.match(r'^(?:what|wikipedia)', q) else 'ar'})

    # Video bookmarks (N082) -----------------------------------------------------------------
    from src.core.web_reader import youtube_id
    if link and youtube_id(link[0]) and re.match(r'^(?:احفظ|سجل|save|bookmark)\b', q):
        stamp = re.search(r'(?:عند|من|في|at)\s+(?:الدقيق[ةه]\s+|الثاني[ةه]\s+|minute\s+)?(\d{1,2}(?::\d{2}){1,2}|\d{1,3})', ascii_digits(original))
        seconds = None
        if stamp:
            parts = [int(x) for x in stamp.group(1).split(':')]
            seconds = parts[0] * 60 if len(parts) == 1 else parts[0] * 60 + parts[1] if len(parts) == 2 else parts[0] * 3600 + parts[1] * 60 + parts[2]
        return Intent('video.save', {'url': link[0].rstrip('.,،؛)!?؟'), 'seconds': seconds})
    if re.fullmatch(r'(?:افتح|شغل|كمل|اكمل|أكمل|resume|open)\s+(?:لي\s+)?(?:اخر|آخر)?\s*(?:ال)?فيديو\s+(?:ال)?محفوظ|(?:كمل|اكمل)\s+(?:ال)?فيديو|resume (?:the )?(?:last )?video', q):
        return Intent('video.open')
    if re.fullmatch(r'(?:ما|اعرض|وش)\s+(?:هي\s+)?(?:ال)?فيديوهات\s+(?:ال)?محفوظ[ةه]|(?:my )?saved videos', q):
        return Intent('video.list')

    # Lasting reply preferences (N039) -------------------------------------------------------
    match = re.match(r'^(?:من\s+الان\s+(?:و)?(?:فصاعدا|فصاعدًا)?|من\s+اليوم\s+و?رايح|دائما|دايما|كل\s+مر[ةه]|from now on|always)\s*[،,]?\s*(?:رد|اجب|أجب|اكتب|تكلم|خاطبني|استخدم|reply|answer|write|use|talk)\b(.*)$', q)
    if match and not QUESTION.search(original):
        return Intent('persona.suggest', {'text': original.strip()[:300]})

    # Knowledge base (N038) ------------------------------------------------------------------
    match = re.match(r'^(?:من\s+(?:ملفاتي|معرفتي|مستنداتي)|ابحث\s+في\s+(?:ملفاتي|معرفتي|مستنداتي)(?:\s+عن)?|اسال\s+(?:ملفاتي|معرفتي)|حسب\s+(?:ملفاتي|مستنداتي)|ask my (?:files|documents|notes))\s*[:،,]?\s*(.+)$', q)
    if match:
        return Intent('knowledge.ask', {'question': original_span(original, match[1].strip())})
    if re.fullmatch(r'(?:ما|ماذا|وش|ايش)\s+(?:الملفات|المستندات)\s+(?:في|ب)\s*(?:معرفتك|المعرفه|المعرفة)|(?:اعرض|عرض)\s+(?:ال)?معرف[ةه]|list (?:my )?knowledge', q):
        return Intent('knowledge.list')
    match = re.match(r'^(?:اضف|احفظ|ادخل)\s+(?:ال)?(?:ملف\s+)?(.+?)\s+(?:الى|إلى|في|ل)\s*(?:ال)?(?:معرف[ةه]|معرفتك|قاعده المعرفه|قاعدة المعرفة)$', q)
    if match:
        return Intent('knowledge.add', {'target': original_span(original, match[1].strip())})

    # Files (N076) ---------------------------------------------------------------------------
    if re.fullmatch(r'(?:تراجع|ارجع|الغ|الغي|undo)\s+(?:عن\s+)?(?:اخر\s+|آخر\s+)?(?:عمليه\s+|عملية\s+)?(?:ال)?تنظيم(?:\s+(?:ال)?ملفات)?|undo (?:the )?last organi[sz]e', q):
        return Intent('files.undo')
    match = re.match(r'^(?:نظم|رتب|نظف|organi[sz]e|sort|tidy)\s+(?:لي\s+)?(?:(?:ملفات\s+(?:مجلد\s+)?)|(?:مجلد\s+)|(?:the\s+)?folder\s+|files in\s+)(.+)$', q)
    if match:
        return Intent('files.organize', {'target': original_span(original, match[1].strip())})

    # Memory --------------------------------------------------------------------------------
    if re.fullmatch(r'(?:(?:ماذا|ما الذي|ما|وش|ايش|شو|شنو|what)\s+(?:تتذكر|تذكر|تعرف|تعرفه|تتذكره|حفظت|حفظته|do you (?:remember|know))\s+(?:عني|about me)'
                    r'|(?:اعرض|عرض|show|list)\s+(?:لي\s+)?(?:ذاكرتك|ذكرياتي|الذاكره|الذاكرة|محتوى ذاكرتك|your memory|memories|my memories)'
                    r'|(?:ماذا|ما|وش|ايش)\s+(?:في|ب)\s*ذاكرتك|what(?:.s| is) in your memory)', q):
        return Intent('memory.list')
    if re.fullmatch(r'(?:انس|انسى|امسح|احذف)\s+(?:كل\s+(?:شي|شيء|ما تعرفه عني|ذكرياتي|الذكريات)|ذاكرتك(?:\s+كلها)?|كل\s+ذاكرتك)|forget everything|clear (?:your )?memory', q):
        return Intent('memory.forget_all')
    match = re.match(r'^(?:انس|انسى|forget)\s+(?:ان\s+|انني\s+|اني\s+|that\s+)?(.+)$|^(?:احذف|امسح|شيل)\s+(?:من\s+(?:ذاكرتك|الذاكره|الذاكرة))\s+(?:ان\s+|انني\s+)?(.+)$', q)
    if match:
        return Intent('memory.forget', {'query': (match[1] or match[2]).strip()})
    match = re.match(r'^(?:تذكر|احفظ|سجل|خزن|remember)(?:\s+(?:في|ب|على)?\s*(?:ذاكرتك|الذاكره|الذاكرة|عندك))?\s+(?:دائما\s+)?(?:ان\s+|انه\s+|انني\s+|اني\s+|انا\s+|that\s+)?(.+)$', q)
    if match and not QUESTION.search(original) and not re.match(r'^(?:هل|متى|كيف)\b', q):
        fact = match[1].strip()
        if re.match(r'^(?:هذا|هذه|ذلك|ذا|it|this|that)$', fact):
            return Intent('clarify', {'message': 'ما المعلومة التي تريدني أن أتذكرها؟ اكتبها بعد «تذكر أن…».'})
        wording = original_span(original, fact)
        if re.match(r'^(?:تذكر|احفظ|remember)\s+(?:انني|اني|انا)\b', normalize(original)) and not wording.startswith(('أنا', 'انا')):
            wording = 'أنا ' + wording
        return Intent('memory.save', {'text': wording})

    # Reminders -------------------------------------------------------------------------------
    if re.fullmatch(r'(?:(?:ما|ماهي|ما هي|وش|ايش|شو|اعرض|عرض|show|list|what are)\s+(?:هي\s+)?(?:لي\s+)?(?:تذكيراتي|التذكيرات|مواعيدي|منبهاتي|my reminders|reminders|(?:ال)?تذكيرات القادمه|(?:ال)?تذكيرات القادمة)'
                    r'|(?:هل\s+)?(?:عندي|لدي|لي)\s+(?:اي\s+)?(?:تذكيرات|تذكير|مواعيد)(?:\s+(?:اليوم|قادمه|قادمة))?|do i have (?:any )?reminders)', q):
        return Intent('reminder.list')
    if re.fullmatch(r'(?:الغ|الغي|احذف|امسح|cancel|delete|clear)\s+(?:كل|جميع|all)\s+(?:ال)?(?:تذكيرات|reminders)', q):
        return Intent('reminder.cancel_all')
    match = re.match(r'^(?:الغ|الغي|احذف|امسح|شيل|cancel|delete|remove)\s+(?:ال)?(?:تذكير|reminder)(?:\s+(?:ب|عن|about|for)?\s*(.+))?$', q)
    if match:
        return Intent('reminder.cancel', {'query': (match[1] or '').strip()})
    match = re.match(r'^(?:ذكرني|ذكرنا|نبهني|فكرني|remind me|(?:اضبط|ضع|حط|سو|سوي|اعمل|set|create|add)\s+(?:لي\s+)?(?:a\s+)?(?:تذكير|منبه|مؤقت|مؤقتا|reminder|timer|alarm))(?:\s+(.*))?$', q)
    if not match:
        match = re.match(r'^(?:مؤقت|timer)\s+(.+)$', q)
    if match:
        timer = bool(re.search(r'مؤقت|timer', q.split(' ', 2)[0] + ' ' + (q.split(' ', 2)[1] if ' ' in q else '')))
        rest = (match[1] or '').strip()
        if timer and re.match(r'^(?:(?:لمده|لمدة|ل|for)\s+)?(?:' + NUM + r')?\s*(?:نص\s+|نصف\s+|ربع\s+)?(?:' + UNIT + r')\b', rest):
            rest = 'بعد ' + re.sub(r'^(?:لمده|لمدة|ل|for)\s+', '', rest)
        parser = TimeParse(rest, now)
        due, error = parser.resolve()
        if error:
            return Intent('clarify', {'message': error + ' لم أنشئ تذكيرًا.'})
        if due is None:
            return Intent('clarify', {'message': 'متى أذكرك؟ اكتب مثلًا: «ذكرني بعد 20 دقيقة أن أشرب الماء» أو «ذكرني غدًا الساعة 9 صباحًا بالاجتماع». لم أنشئ تذكيرًا.'})
        remainder = re.sub(r'^(?:و\s+)?(?:ان|انه|انني|اني|عن|بان|بانه|لكي|كي|to|that|about|of)\s+', '', parser.remainder().strip())
        wording = original_span(original, remainder) if remainder else ''
        wording = re.sub(r'^ب(?=\S{3,})', '', strip_connectors(wording))
        if not wording:
            wording = 'انتهى المؤقت' if timer else 'تذكير من Neura'
        return Intent('reminder.create', {'text': wording, 'due': due.timestamp()})

    # Clock, calendar, calculator, weather ---------------------------------------------------
    match = re.fullmatch(r'(?:كم\s+(?:الساعه|الساعة|الوقت)|(?:ما|وش|ايش|شو)\s+(?:هو\s+|هي\s+)?(?:الوقت|الساعه|الساعة)|what time is it|what.?s the time|the time|الوقت|الساعه|الساعة)'
                         r'(?:\s+(?:الان|الحين|هلا|now))?(?:\s+(?:في|ب|in)\s*(.+?))?(?:\s+(?:الان|الحين|now))?', q)
    if match:
        return Intent('clock.time', {'place': (match[1] or '').strip()})
    if re.fullmatch(r'(?:(?:ما|وش|ايش|شو|كم)\s+(?:هو\s+)?(?:تاريخ(?:\s+(?:اليوم|اليوم الهجري|اليوم الميلادي))?|التاريخ(?:\s+(?:الهجري|الميلادي))?(?:\s+اليوم)?|اليوم)'
                    r'|(?:اي|أي|وش)\s+يوم\s+(?:اليوم|هذا)|اليوم\s+(?:ايش|وش|ما)|what(?:.s| is) (?:the )?(?:date|day)(?: today)?|what day is (?:it|today)|today.?s date)(?:\s+(?:اليوم|الان|today))?', q):
        return Intent('clock.date', {'hijri_only': 'هجري' in q})
    match = re.fullmatch(r'(?:احسب(?:\s+لي)?|حساب|كم\s+(?:يساوي|تساوي|ناتج|حاصل|يطلع)|(?:ما|وش)\s+(?:هو\s+)?(?:ناتج|حاصل)|calculate|compute|what is|what.?s|how much is)\s+(.+?)', q)
    if match:
        from src.core.assistant_tools import is_expression
        if is_expression(match[1]):
            return Intent('calc', {'expression': match[1]})
    if re.fullmatch(r'\d+(?:[.,]\d+)?\s*[%٪]\s*(?:من|of)\s+\d+(?:[.,]\d+)?', q):
        return Intent('calc', {'expression': original})
    if re.fullmatch(r'[\d\s+\-*/×÷^().,%٪=]+', ascii_digits(original)) and re.search(r'\d\s*[+\-*/×÷^%]\s*[\d(]', ascii_digits(original)):
        return Intent('calc', {'expression': original})
    match = re.fullmatch(r'(?:(?:ما|كيف|وش|ايش|شو|شلون|how.?s|what.?s|what is)\s+)?(?:هو\s+|هي\s+)?(?:(?:حاله|حالة)\s+)?(?:the\s+)?(الطقس|الجو|درجه الحراره|درجة الحرارة|الحراره|الحرارة|weather|temperature)'
                         r'(?:\s+(اليوم|الان|الحين|غدا|بكره|بكرة|بعد غد|today|now|tomorrow))?(?:\s+(?:في|ب|in|at)\s*|\s+ب(?=\S))?(.*?)(?:\s+(اليوم|الان|الحين|غدا|بكره|بكرة|بعد غد|today|now|tomorrow))?', q)
    if match and (match[1] in ('الطقس', 'weather') or match[3] or match[2] or match[4] or q.startswith(('ما', 'كيف', 'وش', 'ايش', 'شو', 'شلون', 'how', 'what'))):
        when = match[2] or match[4] or ''
        offset = 2 if when == 'بعد غد' else 1 if when in ('غدا', 'بكره', 'بكرة', 'tomorrow') else 0
        city = (match[3] or '').strip()
        return Intent('weather', {'city': original_span(original, city) if city else '', 'day_offset': offset})
    return None
