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
            'file_move': [
                r'انقل.*(ملف|مجلد)',
                r'move.*file',
                r'move.*folder',
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
                r'git push',
            ],
            'git_commit': [
                r'كوميت',
                r'commit',
            ],
        }

    def detect_intent(self, text):
        """يحدد النية من النص."""
        text_lower = text.lower()

        for intent, patterns in self.patterns.items():
            for pattern in patterns:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    return intent

        return 'chat'  # افتراضي: محادثة عادية

    def extract_params(self, text, intent):
        """يستخرج المعاملات من النص."""
        params = {}

        if intent == 'media_search':
            # استخراج موضوع البحث
            match = re.search(r'عن\s+(.+)', text)
            if match:
                params['query'] = match.group(1).strip()
            else:
                # fallback: كل النص بعد "ابحث"
                params['query'] = text

        elif intent in ('file_move', 'file_copy'):
            # استخراج المصدر والوجهة
            match = re.search(r'(ملف|مجلد)\s+(\S+)\s+(إلى|to)\s+(\S+)', text)
            if match:
                params['src'] = match.group(2)
                params['dst'] = match.group(4)

        return params


if __name__ == '__main__':
    router = IntentRouter()

    tests = [
        'ابحث عن فيديوهات RTX 5090 benchmarks',
        'انقل ملف test.txt إلى backup/',
        'ارفع المشروع لجيت',
        'ما هو أفضل كرت شاشة؟',
    ]

    print('Intent Router Demo')
    print('=' * 60)
    for text in tests:
        intent = router.detect_intent(text)
        params = router.extract_params(text, intent)
        print(f'النص: {text}')
        print(f'  النية: {intent}')
        print(f'  المعاملات: {params}')
        print()
