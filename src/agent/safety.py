"""
Neura Safety Gate
بوابة الموافقة - لا شيء يُنفذ بدون إذنك الصريح.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class SafetyGate:
    """يعرض خطة العمل ويطلب موافقتك الصريحة قبل التنفيذ."""

    DANGEROUS_KEYWORDS = ['delete', 'remove', 'rm', 'format', 'sudo', 'push']

    def __init__(self, interactive=True):
        self.interactive = interactive
        self.log = []

    def _is_dangerous(self, plan):
        plan_lower = str(plan).lower()
        return any(kw in plan_lower for kw in self.DANGEROUS_KEYWORDS)

    def request_approval(self, plan, context=None):
        """
        يعرض الخطة ويطلب الموافقة.
        يرجع: 'approved' | 'denied' | 'edit'
        """
        print()
        print('=' * 60)
        if self._is_dangerous(plan):
            print('⚠️  تحذير: هذه العملية قد تكون خطيرة')
        print('🛡️  Safety Gate - خطة العمل المقترحة:')
        print('=' * 60)
        print(plan)
        if context:
            print()
            print('📋 السياق:', context)
        print('=' * 60)

        if not self.interactive:
            print('[Auto-approved: non-interactive mode]')
            decision = 'approved'
        else:
            try:
                answer = input('هل توافق على التنفيذ؟ [نعم/لا/عدّل]: ').strip()
            except EOFError:
                answer = 'لا'

            if answer in ('نعم', 'yes', 'y', 'ن'):
                decision = 'approved'
            elif answer in ('عدّل', 'edit', 'e'):
                decision = 'edit'
            else:
                decision = 'denied'

        self.log.append({'plan': plan, 'decision': decision})
        print(f'[قرار: {decision}]')
        print()
        return decision


if __name__ == '__main__':
    gate = SafetyGate()
    print('Demo: SafetyGate')
    print('-' * 40)
    decision = gate.request_approval(
        plan='نقل ملف C:/Users/test.txt إلى D:/backup/',
        context='المستخدم طلب نقل الملف للنسخ الاحتياطي'
    )
    print('Final decision:', decision)
