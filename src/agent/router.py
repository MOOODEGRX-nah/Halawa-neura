"""
Neura Intent Router — v2 (مع Browser + SessionVault)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import re


class IntentRouter:
    def __init__(self):
        self.patterns = {
            'media_search': [
                r'ابحث.*(فيديو|مقطع|يوتيوب)',
                r'فيديو',
                r'يوتيوب',
                r'جيب.*(فيديو|مقطع)',
                r'find.*video',
                r'search.*youtube',
            ],
            'browser_login': [
                r'سجل.*دخول',
                r'login.*site',
                r'احفظ.*جلسة',
            ],
            'browser_open_visible': [
                r'افتح.*بالمتصفح',
                r'شاهد.*موقع',
            ],
            'browser_headlines': [
                r'عناوين.*موقع',
                r'اخبار.*موقع',
                r'headlines',
            ],
            'browser_read': [
                r'افتح.*موقع',
                r'اقرا.*موقع',
                r'ابحث.*موقع',
                r'browse',
            ],
            'file_move': [
                r'انقل.*(ملف|مجلد)',
                r'move.*file',
            ],
            'file_copy': [
                r'انسخ.*(ملف|مجلد)',
                r'copy.*file',
            ],
            'file_delete': [
                r'احذف.*(ملف|مجلد)',
                r'delete.*file',
            ],
            'git_push': [
                r'ارفع.*جيت',
                r'push.*git',
            ],
            'git_commit': [
                r'كوميت',
                r'commit',
            ],
            'session_list': [
                r'اعرض.*جلسات',
                r'list.*sessions',
            ],
        }

    def detect_intent(self, text):
        text_lower = text.lower()
        for intent, patterns in self.patterns.items():
            for pattern in patterns:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    return intent
        return 'chat'

    def extract_params(self, text, intent):
        params = {}
        if intent == 'media_search':
            match = re.search(r'عن\s+(.+)', text)
            params['query'] = match.group(1).strip() if match else text
        elif intent in ('file_move', 'file_copy'):
            match = re.search(r'(ملف|مجلد)\s+(\S+)\s+(إلى|to)\s+(\S+)', text)
            if match:
                params['src'] = match.group(2)
                params['dst'] = match.group(4)
        elif intent in ('browser_read', 'browser_headlines'):
            match = re.search(r'(?:موقع|site)\s+(\S+)', text)
            if match:
                params['url'] = match.group(1)
        elif intent == 'browser_login':
            match = re.search(r'(?:في|in)\s+(?:موقع\s+)?(\S+)', text)
            params['url'] = match.group(1) if match else ''
            match = re.search(r'باسم\s+(\S+)', text)
            params['session_name'] = match.group(1) if match else 'default'
        return params


if __name__ == '__main__':
    r = IntentRouter()
    tests = [
        'سجل دخول في موقع uqu.edu.sa باسم جامعتي',
        'ابحث في موقع uqu.edu.sa عن القبول',
        'اعرض الجلسات',
    ]
    for t in tests:
        print(f'{t}  ->  {r.detect_intent(t)} / {r.extract_params(t, r.detect_intent(t))}')
