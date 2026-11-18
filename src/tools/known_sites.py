"""Curated well-known websites and site search engines, by Arabic and English name.

Only fixed HTTPS addresses written here are ever opened; a user's words select an entry by exact
normalized name (no fuzzy guessing), and a search query is only URL-encoded into a fixed engine.
"""
from urllib.parse import quote_plus
import re

# (canonical name, fixed URL, names a user may say)
SITES = [
    ('YouTube', 'https://www.youtube.com/', ('youtube', 'you tube', 'يوتيوب', 'يوتوب', 'يو تيوب')),
    ('Google', 'https://www.google.com/', ('google', 'جوجل', 'قوقل', 'غوغل', 'جوجل سيرش')),
    ('Gmail', 'https://mail.google.com/', ('gmail', 'جيميل', 'جي ميل', 'بريد جوجل', 'بريد قوقل')),
    ('Google Maps', 'https://www.google.com/maps', ('google maps', 'خرائط جوجل', 'خرائط قوقل', 'جوجل ماب', 'قوقل ماب', 'الخرائط')),
    ('Google Translate', 'https://translate.google.com/', ('google translate', 'مترجم جوجل', 'مترجم قوقل', 'ترجمة جوجل', 'ترجمة قوقل', 'المترجم')),
    ('Google Drive', 'https://drive.google.com/', ('google drive', 'جوجل درايف', 'قوقل درايف')),
    ('Gemini', 'https://gemini.google.com/', ('gemini', 'جيميني', 'جيمناي')),
    ('Facebook', 'https://www.facebook.com/', ('facebook', 'فيسبوك', 'فيس بوك', 'الفيس')),
    ('Instagram', 'https://www.instagram.com/', ('instagram', 'انستقرام', 'انستغرام', 'انستجرام', 'انستا')),
    ('X', 'https://x.com/', ('x', 'twitter', 'تويتر', 'اكس', 'منصة اكس')),
    ('TikTok', 'https://www.tiktok.com/', ('tiktok', 'tik tok', 'تيك توك', 'تيكتوك')),
    ('Snapchat', 'https://web.snapchat.com/', ('snapchat', 'سناب', 'سناب شات', 'سنابشات')),
    ('WhatsApp Web', 'https://web.whatsapp.com/', ('whatsapp', 'whatsapp web', 'واتساب', 'واتساب ويب', 'واتس اب', 'الواتس')),
    ('Telegram Web', 'https://web.telegram.org/', ('telegram', 'telegram web', 'تيليجرام', 'تلغرام', 'تليجرام', 'تيليقرام')),
    ('Discord', 'https://discord.com/app', ('discord', 'ديسكورد', 'دسكورد')),
    ('Reddit', 'https://www.reddit.com/', ('reddit', 'ريديت', 'رديت')),
    ('Wikipedia', 'https://www.wikipedia.org/', ('wikipedia', 'ويكيبيديا', 'ويكيبيديا العربية', 'ويكي')),
    ('Amazon', 'https://www.amazon.com/', ('amazon', 'امازون')),
    ('Amazon Saudi', 'https://www.amazon.sa/', ('amazon sa', 'امازون السعودية', 'امازون السعودي')),
    ('Noon', 'https://www.noon.com/', ('noon', 'موقع نون')),
    ('Netflix', 'https://www.netflix.com/', ('netflix', 'نتفلكس', 'نتفليكس')),
    ('Spotify', 'https://open.spotify.com/', ('spotify', 'سبوتيفاي', 'سبوتفاي')),
    ('Twitch', 'https://www.twitch.tv/', ('twitch', 'تويتش')),
    ('Kick', 'https://kick.com/', ('kick', 'كيك')),
    ('LinkedIn', 'https://www.linkedin.com/', ('linkedin', 'لينكد ان', 'لينكدان')),
    ('Pinterest', 'https://www.pinterest.com/', ('pinterest', 'بنترست', 'بينترست')),
    ('GitHub', 'https://github.com/', ('github', 'جيت هب', 'جيتهاب', 'قيت هب')),
    ('GitLab', 'https://gitlab.com/', ('gitlab', 'جيت لاب')),
    ('Stack Overflow', 'https://stackoverflow.com/', ('stack overflow', 'stackoverflow', 'ستاك اوفرفلو', 'ستاك اوفر فلو')),
    ('Hugging Face', 'https://huggingface.co/', ('hugging face', 'huggingface', 'هقنق فيس', 'هاجينج فيس')),
    ('ChatGPT', 'https://chatgpt.com/', ('chatgpt', 'chat gpt', 'شات جي بي تي', 'تشات جي بي تي', 'شات جبت')),
    ('Claude', 'https://claude.ai/', ('claude', 'كلود')),
    ('Outlook', 'https://outlook.live.com/', ('outlook', 'hotmail', 'اوتلوك', 'هوتميل')),
    ('Al Jazeera', 'https://www.aljazeera.net/', ('aljazeera', 'al jazeera', 'الجزيرة', 'الجزيرة نت', 'قناة الجزيرة')),
    ('Al Arabiya', 'https://www.alarabiya.net/', ('alarabiya', 'al arabiya', 'قناة العربية', 'العربية نت')),
    ('BBC Arabic', 'https://www.bbc.com/arabic', ('bbc arabic', 'بي بي سي عربي', 'بي بي سي العربية')),
    ('BBC', 'https://www.bbc.com/', ('bbc', 'بي بي سي')),
    ('Steam', 'https://store.steampowered.com/', ('steam', 'ستيم', 'متجر ستيم')),
    ('Epic Games', 'https://store.epicgames.com/', ('epic games', 'epic', 'ايبك', 'ايبك جيمز')),
    ('ProtonDB', 'https://www.protondb.com/', ('protondb', 'بروتون دي بي')),
    ('Arch Wiki', 'https://wiki.archlinux.org/', ('arch wiki', 'archwiki', 'ارش ويكي', 'ويكي ارش')),
    ('CachyOS', 'https://cachyos.org/', ('cachyos', 'كاشي', 'كاشي او اس')),
    ('Speedtest', 'https://www.speedtest.net/', ('speedtest', 'سبيد تست', 'اختبار سرعة الانترنت', 'قياس سرعة النت')),
    ('DuckDuckGo', 'https://duckduckgo.com/', ('duckduckgo', 'داك داك جو')),
    ('Bing', 'https://www.bing.com/', ('bing', 'بينج', 'بنج')),
]

# engine: (names, fixed search URL prefix); the query is URL-encoded and appended
ENGINES = {
    'Google': (('google', 'جوجل', 'قوقل', 'غوغل'), 'https://www.google.com/search?q='),
    'Bing': (('bing', 'بينج', 'بنج'), 'https://www.bing.com/search?q='),
    'DuckDuckGo': (('duckduckgo', 'داك داك جو'), 'https://duckduckgo.com/?q='),
    'Wikipedia': (('wikipedia', 'ويكيبيديا', 'ويكي'), None),
    'Amazon': (('amazon', 'امازون'), 'https://www.amazon.com/s?k='),
    'GitHub': (('github', 'جيت هب', 'جيتهاب'), 'https://github.com/search?q='),
    'Reddit': (('reddit', 'ريديت', 'رديت'), 'https://www.reddit.com/search/?q='),
    'Stack Overflow': (('stack overflow', 'stackoverflow', 'ستاك اوفرفلو'), 'https://stackoverflow.com/search?q='),
}


def _key(text):
    from src.core.application_targets import key
    return key(text)


_SITE_INDEX = {_key(alias): (name, url) for name, url, aliases in SITES for alias in aliases + (name,)}
_ENGINE_INDEX = {_key(alias): name for name, (aliases, _) in ENGINES.items() for alias in aliases + (name,)}


def site_for(target):
    """Exact normalized name -> {'name','url'}; None when the name is not a known site."""
    found = _SITE_INDEX.get(_key(target or ''))
    if not found: return None
    aliases = next(a for n, u, a in SITES if n == found[0])
    # Latin names double as the desktop app's catalog name (Steam, Discord, Telegram...).
    return {'name': found[0], 'url': found[1], 'app_names': [found[0]] + [a for a in aliases if re.fullmatch(r'[a-z ]+', a)]}


def engine_for(name):
    return _ENGINE_INDEX.get(_key(name or ''))


def engine_names_pattern():
    """Normalized engine names for a dispatcher regex, longest first."""
    names = sorted({a for aliases, _ in ENGINES.values() for a in aliases}, key=len, reverse=True)
    return '|'.join(re.escape(n) for n in names)


def search_url(engine, query):
    aliases, prefix = ENGINES[engine]
    if engine == 'Wikipedia':
        lang = 'ar' if re.search(r'[؀-ۿ]', query) else 'en'
        return 'https://' + lang + '.wikipedia.org/w/index.php?search=' + quote_plus(query)
    return prefix + quote_plus(query)
