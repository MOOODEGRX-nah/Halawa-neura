"""Deterministic assistant tools: a restricted calculator, clock/calendar and sourced weather.

No tool evaluates arbitrary code. The calculator parses a small arithmetic grammar with `ast`
and rejects everything else; weather comes only from Open-Meteo with a timeout and is reported
with its source and observation time, never invented.
"""
import ast
import math
import operator
import re
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

ARABIC_DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫', '01234567890123456789.')
WEEKDAYS = ['الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت', 'الأحد']
MONTHS = ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر']
HIJRI_MONTHS = ['محرم', 'صفر', 'ربيع الأول', 'ربيع الآخر', 'جمادى الأولى', 'جمادى الآخرة', 'رجب', 'شعبان', 'رمضان', 'شوال', 'ذو القعدة', 'ذو الحجة']


class ToolError(ValueError):
    pass


def ascii_digits(text):
    return str(text).translate(ARABIC_DIGITS)


# Calculator -------------------------------------------------------------------------------
_BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
           ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCTIONS = {'sqrt': math.sqrt, 'abs': abs, 'round': round, 'sin': lambda x: math.sin(math.radians(x)),
              'cos': lambda x: math.cos(math.radians(x)), 'tan': lambda x: math.tan(math.radians(x)),
              'log': math.log10, 'ln': math.log}
_WORDS = [(r'(?:مضروب|مضروبا)\s+في|ضرب|×|\bx\b|\btimes\b', '*'), (r'(?:مقسوم|مقسوما)\s+على|تقسيم|قسمة|÷|\bdivided by\b', '/'),
          (r'زائد|\bplus\b', '+'), (r'ناقص|\bminus\b', '-'), (r'اس|أس|\^|\bto the power of\b', '**'),
          (r'الجذر\s+التربيعي\s+(?:ل|لـ)?|جذر|\bsquare root of\b|√', 'sqrt '), (r'\bmod\b|باقي قسمة', '%')]


def _number_text(expression):
    text = ascii_digits(expression).strip().rstrip('=؟?. ')
    text = re.sub(r'(?<=\d),(?=\d{3}\b)', '', text)      # thousands separators
    text = re.sub(r'(\d+(?:\.\d+)?)\s*[%٪]\s*(?:من|of)\s+', r'(\1/100)*', text)
    text = re.sub(r'(\d+(?:\.\d+)?)\s*[%٪]', r'(\1/100)', text)
    for pattern, replacement in _WORDS:
        text = re.sub(pattern, ' ' + replacement + ' ', text, flags=re.I)
    text = re.sub(r'(?<=\d)\s+في\s+(?=[\d(])', ' * ', text)
    text = re.sub(r'sqrt\s+(\d+(?:\.\d+)?)', r'sqrt(\1)', text)
    return re.sub(r'\s+', ' ', text).strip()


def _evaluate(node):
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        left, right = _evaluate(node.left), _evaluate(node.right)
        if isinstance(node.op, ast.Pow) and (abs(right) > 100 or abs(left) > 1e6):
            raise ToolError('الأس كبير جدًا')
        try:
            value = _BINARY[type(node.op)](left, right)
        except ZeroDivisionError as exc:
            raise ToolError('لا يمكن القسمة على صفر') from exc
        if isinstance(value, complex) or abs(value) > 1e100:
            raise ToolError('الناتج خارج النطاق المدعوم')
        return value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_evaluate(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCTIONS and len(node.args) == 1 and not node.keywords:
        try:
            return _FUNCTIONS[node.func.id](_evaluate(node.args[0]))
        except ValueError as exc:
            raise ToolError('قيمة غير صالحة للدالة ' + node.func.id) from exc
    raise ToolError('صيغة حسابية غير مدعومة')


def calculate(expression):
    text = _number_text(expression)
    if not text or len(text) > 200 or not re.fullmatch(r'[\d\s+\-*/%().a-z]+', text):
        raise ToolError('صيغة حسابية غير مدعومة')
    try:
        tree = ast.parse(text, mode='eval')
    except SyntaxError as exc:
        raise ToolError('صيغة حسابية غير مكتملة') from exc
    operators = [n for n in ast.walk(tree) if isinstance(n, (ast.BinOp, ast.Call))]
    if not operators:
        raise ToolError('لا توجد عملية حسابية')
    value = _evaluate(tree)
    return {'expression': text, 'value': value, 'display': format_number(value)}


def is_expression(text):
    try:
        calculate(text)
        return True
    except ToolError:
        return False


def format_number(value):
    if isinstance(value, float):
        if value.is_integer() and abs(value) < 1e15:
            return f'{int(value):,}'
        return f'{value:,.6f}'.rstrip('0').rstrip('.')
    return f'{value:,}'


# Clock and calendar -----------------------------------------------------------------------
def hijri(day):
    """Tabular (arithmetical) Islamic calendar. May differ by a day from Umm al-Qura/sighting."""
    jd = day.toordinal() + 1721425 - 1948440 + 10632
    n = (jd - 1) // 10631
    jd = jd - 10631 * n + 354
    j = ((10985 - jd) // 5316) * ((50 * jd) // 17719) + (jd // 5670) * ((43 * jd) // 15238)
    jd = jd - ((30 - j) // 15) * ((17719 * j) // 50) - (j // 16) * ((15238 * j) // 43) + 29
    month = (24 * jd) // 709
    return {'day': jd - (709 * month) // 24, 'month': month, 'year': 30 * n + j - 30}


def time_of_day(hour):
    return 'صباحًا' if hour < 12 else 'ظهرًا' if hour < 15 else 'عصرًا' if hour < 18 else 'مساءً'


def clock_text(moment):
    hour = moment.hour % 12 or 12
    return f'{hour}:{moment.minute:02d} {time_of_day(moment.hour)}'


def date_text(moment):
    return f'{WEEKDAYS[moment.weekday()]} {moment.day} {MONTHS[moment.month - 1]} {moment.year}'


def hijri_text(moment):
    h = hijri(moment.date() if isinstance(moment, datetime) else moment)
    return f'{h["day"]} {HIJRI_MONTHS[h["month"] - 1]} {h["year"]} هـ'


CITY_ZONES = {'الرياض': 'Asia/Riyadh', 'جده': 'Asia/Riyadh', 'جدة': 'Asia/Riyadh', 'مكه': 'Asia/Riyadh', 'مكة': 'Asia/Riyadh',
              'دبي': 'Asia/Dubai', 'ابوظبي': 'Asia/Dubai', 'ابو ظبي': 'Asia/Dubai', 'الدوحه': 'Asia/Qatar', 'الدوحة': 'Asia/Qatar',
              'الكويت': 'Asia/Kuwait', 'المنامه': 'Asia/Bahrain', 'المنامة': 'Asia/Bahrain', 'مسقط': 'Asia/Muscat',
              'القاهره': 'Africa/Cairo', 'القاهرة': 'Africa/Cairo', 'عمان': 'Asia/Amman', 'بيروت': 'Asia/Beirut', 'بغداد': 'Asia/Baghdad',
              'دمشق': 'Asia/Damascus', 'الدار البيضاء': 'Africa/Casablanca', 'تونس': 'Africa/Tunis', 'الجزائر': 'Africa/Algiers',
              'اسطنبول': 'Europe/Istanbul', 'لندن': 'Europe/London', 'باريس': 'Europe/Paris', 'برلين': 'Europe/Berlin',
              'مدريد': 'Europe/Madrid', 'روما': 'Europe/Rome', 'موسكو': 'Europe/Moscow', 'نيويورك': 'America/New_York',
              'واشنطن': 'America/New_York', 'لوس انجلوس': 'America/Los_Angeles', 'تورنتو': 'America/Toronto',
              'طوكيو': 'Asia/Tokyo', 'بكين': 'Asia/Shanghai', 'سيول': 'Asia/Seoul', 'دلهي': 'Asia/Kolkata', 'نيودلهي': 'Asia/Kolkata',
              'سيدني': 'Australia/Sydney', 'كوالالمبور': 'Asia/Kuala_Lumpur', 'جاكرتا': 'Asia/Jakarta',
              'london': 'Europe/London', 'paris': 'Europe/Paris', 'new york': 'America/New_York', 'tokyo': 'Asia/Tokyo',
              'dubai': 'Asia/Dubai', 'riyadh': 'Asia/Riyadh', 'cairo': 'Africa/Cairo', 'berlin': 'Europe/Berlin'}


def zone_for_city(city):
    from src.core.application_targets import normalize
    name = re.sub(r'^(?:مدينه|مدينة|ال(?=القاهره))\s*', '', normalize(city))
    return CITY_ZONES.get(name) or CITY_ZONES.get(name.removeprefix('ال')) or CITY_ZONES.get('ال' + name)


# Weather ----------------------------------------------------------------------------------
WMO = {0: 'صافٍ', 1: 'صافٍ غالبًا', 2: 'غائم جزئيًا', 3: 'غائم', 45: 'ضباب', 48: 'ضباب متجمد', 51: 'رذاذ خفيف', 53: 'رذاذ', 55: 'رذاذ كثيف',
       56: 'رذاذ متجمد', 57: 'رذاذ متجمد كثيف', 61: 'مطر خفيف', 63: 'مطر', 65: 'مطر غزير', 66: 'مطر متجمد', 67: 'مطر متجمد غزير',
       71: 'ثلج خفيف', 73: 'ثلج', 75: 'ثلج كثيف', 77: 'حبيبات ثلج', 80: 'زخات مطر خفيفة', 81: 'زخات مطر', 82: 'زخات مطر عنيفة',
       85: 'زخات ثلج', 86: 'زخات ثلج كثيفة', 95: 'عاصفة رعدية', 96: 'عاصفة رعدية مع برد', 99: 'عاصفة رعدية قوية مع برد'}
KNOWN_PLACES = {'الرياض': (24.7136, 46.6753), 'جده': (21.4858, 39.1925), 'جدة': (21.4858, 39.1925), 'مكه': (21.3891, 39.8579),
                'مكة': (21.3891, 39.8579), 'المدينه': (24.5247, 39.5692), 'المدينة': (24.5247, 39.5692), 'المدينه المنوره': (24.5247, 39.5692),
                'المدينة المنورة': (24.5247, 39.5692), 'الدمام': (26.4207, 50.0888), 'الخبر': (26.2172, 50.1971), 'الظهران': (26.2361, 50.0393),
                'الطائف': (21.2703, 40.4158), 'تبوك': (28.3835, 36.5662), 'ابها': (18.2164, 42.5053), 'خميس مشيط': (18.3, 42.7333),
                'بريده': (26.326, 43.975), 'بريدة': (26.326, 43.975), 'القصيم': (26.326, 43.975), 'حائل': (27.5114, 41.7208),
                'جازان': (16.8892, 42.5511), 'نجران': (17.4917, 44.1322), 'الاحساء': (25.3833, 49.5833), 'الهفوف': (25.3833, 49.5833),
                'ينبع': (24.0895, 38.0618), 'الجبيل': (27.0174, 49.6225), 'الباحه': (20.0129, 41.4677), 'الباحة': (20.0129, 41.4677),
                'سكاكا': (29.9697, 40.2064), 'عرعر': (30.9753, 41.0381), 'العلا': (26.6085, 37.9232), 'نيوم': (28.0, 35.2),
                'الكويت': (29.3759, 47.9774), 'دبي': (25.2048, 55.2708), 'ابوظبي': (24.4539, 54.3773), 'ابو ظبي': (24.4539, 54.3773),
                'الدوحه': (25.2854, 51.531), 'الدوحة': (25.2854, 51.531), 'المنامه': (26.2285, 50.586), 'المنامة': (26.2285, 50.586),
                'مسقط': (23.588, 58.3829), 'القاهره': (30.0444, 31.2357), 'القاهرة': (30.0444, 31.2357), 'عمان': (31.9454, 35.9284)}


class Weather:
    """Open-Meteo client (no API key). Results are cached briefly and always carry their source."""
    SOURCE = 'Open-Meteo'

    def __init__(self, fetch=None, ttl=600):
        self._fetch = fetch or self._http
        self.ttl = ttl
        self._cache = {}

    @staticmethod
    def _http(url, params):
        import httpx
        response = httpx.get(url, params=params, timeout=8.0, follow_redirects=False, headers={'User-Agent': 'NeuraAI-desktop'})
        response.raise_for_status()
        return response.json()

    def locate(self, city):
        from src.core.application_targets import normalize
        name = normalize(city)
        name = re.sub(r'^(?:مدينه|مدينة)\s+', '', name)
        for candidate in (name, name.removeprefix('ال'), 'ال' + name):
            if candidate in KNOWN_PLACES:
                lat, lon = KNOWN_PLACES[candidate]
                return {'name': city.strip(), 'latitude': lat, 'longitude': lon, 'country': None}
        try:
            data = self._fetch('https://geocoding-api.open-meteo.com/v1/search', {'name': city.strip()[:80], 'count': 1, 'language': 'ar', 'format': 'json'})
        except Exception as exc:
            raise ToolError('تعذر الاتصال بخدمة تحديد المدن (Open-Meteo). تحقق من الإنترنت.') from exc
        results = (data or {}).get('results') or []
        if not results:
            raise ToolError('لم أجد مدينة باسم «' + city.strip()[:60] + '».')
        top = results[0]
        return {'name': top.get('name') or city.strip(), 'latitude': top['latitude'], 'longitude': top['longitude'], 'country': top.get('country')}

    def forecast(self, city, day_offset=0):
        place = self.locate(city)
        cache_key = (round(place['latitude'], 3), round(place['longitude'], 3))
        cached = self._cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < self.ttl:
            data = cached[1]
        else:
            try:
                data = self._fetch('https://api.open-meteo.com/v1/forecast', {
                    'latitude': place['latitude'], 'longitude': place['longitude'], 'timezone': 'auto', 'forecast_days': 3,
                    'current': 'temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m',
                    'daily': 'weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max'})
            except Exception as exc:
                raise ToolError('تعذر جلب الطقس من Open-Meteo الآن. تحقق من الإنترنت ثم أعد المحاولة.') from exc
            self._cache[cache_key] = (time.monotonic(), data)
        try:
            daily = data['daily']
            index = min(day_offset, len(daily['time']) - 1)
            day = {'date': daily['time'][index], 'condition': WMO.get(daily['weather_code'][index], 'غير معروف'),
                   'max': daily['temperature_2m_max'][index], 'min': daily['temperature_2m_min'][index],
                   'rain_chance': daily.get('precipitation_probability_max', [None] * (index + 1))[index]}
            current = data.get('current') or {}
            now = None if day_offset else {'time': current.get('time'), 'temperature': current.get('temperature_2m'),
                                           'feels_like': current.get('apparent_temperature'), 'humidity': current.get('relative_humidity_2m'),
                                           'wind': current.get('wind_speed_10m'), 'condition': WMO.get(current.get('weather_code'), 'غير معروف')}
        except (KeyError, IndexError, TypeError) as exc:
            raise ToolError('استجابة خدمة الطقس غير مكتملة؛ لم أعرض أرقامًا غير مؤكدة.') from exc
        return {'place': place, 'day': day, 'now': now, 'source': self.SOURCE, 'day_offset': day_offset}

    @staticmethod
    def describe(result):
        place = result['place']['name']
        day, now = result['day'], result['now']
        if now and now['temperature'] is not None:
            text = (f'الطقس في {place} الآن: {now["condition"]}، {round(now["temperature"])}° '
                    f'(الإحساس {round(now["feels_like"])}°)، الرطوبة {now["humidity"]}%، الرياح {round(now["wind"])} كم/س.')
            text += f'\nاليوم: العظمى {round(day["max"])}° والصغرى {round(day["min"])}°'
        else:
            label = 'غدًا' if result['day_offset'] == 1 else 'بعد غد' if result['day_offset'] == 2 else 'اليوم'
            text = f'الطقس في {place} {label}: {day["condition"]}، العظمى {round(day["max"])}° والصغرى {round(day["min"])}°'
        if day['rain_chance'] is not None:
            text += f'، احتمال المطر {day["rain_chance"]}%'
        stamp = (now or {}).get('time') or day['date']
        return text + f'.\nالمصدر: {result["source"]} ({stamp} بالتوقيت المحلي).'


def local_now(timezone='Asia/Riyadh', now=None):
    return datetime.fromtimestamp(time.time() if now is None else now, ZoneInfo(timezone))


def relative_day_label(target, today):
    delta = (target.date() - today.date()).days
    return {0: 'اليوم', 1: 'غدًا', 2: 'بعد غد'}.get(delta, 'يوم ' + WEEKDAYS[target.weekday()] + ' ' + str(target.day) + ' ' + MONTHS[target.month - 1])


def due_text(due, timezone, now=None):
    moment = local_now(timezone, due)
    return relative_day_label(moment, local_now(timezone, now)) + ' الساعة ' + clock_text(moment)


__all__ = ['calculate', 'is_expression', 'Weather', 'ToolError', 'clock_text', 'date_text', 'hijri_text', 'hijri',
           'zone_for_city', 'local_now', 'due_text', 'ascii_digits', 'timedelta', 'date']
