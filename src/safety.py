"""
نظام الأمان — مواقع موثوقة + فلترة الروابط الخطرة
مبدأ: Neura مرشد آمن، لا ينفذ أوامر مدمرة أبداً
"""
import re
from urllib.parse import quote_plus, urlparse

KNOWN_SITES = {
    "يوتيوب": "https://www.youtube.com",
    "youtube": "https://www.youtube.com",
    "جوجل": "https://www.google.com",
    "google": "https://www.google.com",
    "ويكيبيديا": "https://ar.wikipedia.org",
    "wikipedia": "https://en.wikipedia.org",
    "جيتهب": "https://github.com",
    "github": "https://github.com",
    "تويتر": "https://x.com",
    "اكس": "https://x.com",
}

TRUSTED_DOMAINS = [
    "youtube.com", "youtu.be", "google.com", "wikipedia.org", "github.com",
    "x.com", "twitter.com", "reddit.com", "stackoverflow.com",
    "microsoft.com", "python.org", "huggingface.co",
]

BLOCKED_PATTERNS = [
    r"\.exe\b", r"\.bat\b", r"\.scr\b", r"bit\.ly", r"tinyurl",
    r"crack", r"keygen", r"malware", r"phishing",
]

DANGEROUS_COMMANDS = ["format", "del /f", "rmdir /s", "rd /s", "shutdown", "diskpart"]


def find_known_site(text, extra_channels=None):
    """يبحث عن موقع معروف في نص المستخدم"""
    tl = text.lower()
    all_sites = dict(KNOWN_SITES)
    if extra_channels:
        for name, url in extra_channels.items():
            all_sites[name.lower()] = url
    for name, url in all_sites.items():
        if name in tl:
            return name, url
    return None


def build_search_url(query):
    return f"https://www.google.com/search?q={quote_plus(query)}"


def is_safe_url(url):
    """يفحص الرابط قبل فتحه"""
    for p in BLOCKED_PATTERNS:
        if re.search(p, url, re.IGNORECASE):
            return False, "الرابط يحتوي نمطاً مشبوهاً"
    domain = urlparse(url).netloc.lower()
    if any(d in domain for d in TRUSTED_DOMAINS):
        return True, "نطاق موثوق"
    return False, "نطاق غير معروف"


def is_dangerous_command(cmd):
    return any(d in cmd.lower() for d in DANGEROUS_COMMANDS)
