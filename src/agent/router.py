"""
Neura Intent Router
يفهم نوايا المستخدم ويختار الأداة المناسبة تلقائياً.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import re


class IntentRouter:
    """يحلل النص ويحدد الأداة المناسبة."""

    def __init__(self):
        self.patterns = {
            'media_search': [
                r'ابحث.*(فيديو|مقطع|يوتيوب)',
                r'جيب.*(فيديو|مقطع)',
                r'find.*video',
                r'search.*youtube',
            ],
            'browser_headlines': [
                r'عناوين.*موقع',
                r'اخبار.*موقع',
                r'ابحث.*موقع',
                r'headlines',
            ],
            'browser_read': [
                r'افتح.*موقع',
                r'اقرا.*موقع',
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
        return params


if __name__ == '__main__':
    router = IntentRouter()
    tests = [
        'ابحث عن فيديوهات RTX 5090 benchmarks',
        'عناوين موقع bbc.com',
        'افتح موقع example.com',
        'ابحث في موقع uqu.edu.sa عن القبول',
        'انقل ملف test.txt إلى backup/',
        'ما هو أفضل كرت شاشة؟',
    ]
    print('Intent Router Demo')
    print('=' * 60)
    for text in tests:
        intent = router.detect_intent(text)
        params = router.extract_params(text, intent)
        print(f'النص: {text}')
        print(f'  النية: {intent} | المعاملات: {params}')
        print()
