"""
Neura Transaction Log
يسجل كل خطوة مع عكسها - للتراجع الكامل عند الطلب.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from datetime import datetime


class Transaction:
    """معاملة قابلة للتراجع - كل خطوة لها عكس."""

    def __init__(self, name='unnamed'):
        self.name = name
        self.steps = []
        self.completed = []
        self.started_at = datetime.now()
        self.committed = False

    def record(self, description, undo_fn, forward_fn=None):
        """
        يسجل خطوة جديدة.
        undo_fn: دالة تعكس هذه الخطوة
        forward_fn: دالة التنفيذ (اختياري للتوثيق)
        """
        self.steps.append({
            'description': description,
            'undo_fn': undo_fn,
            'forward_fn': forward_fn,
            'timestamp': datetime.now(),
            'executed': False
        })
        print(f'  [سجل] {description}')

    def execute(self, action_fn, description, undo_fn):
        """ينفذ خطوة ويسجلها مع عكسها."""
        print(f'  [تنفيذ] {description}')
        result = action_fn()
        self.record(description, undo_fn)
        self.completed.append({
            'description': description,
            'timestamp': datetime.now()
        })
        return result

    def commit(self):
        """يؤكد نجاح المعاملة."""
        self.committed = True
        print(f'✅ تم تنفيذ المعاملة بنجاح: {self.name}')
        print(f'   عدد الخطوات: {len(self.completed)}')

    def rewind(self):
        """يعيد كل شيء كما كان - بالترتيب العكسي."""
        if not self.completed:
            print('ℹ️  لا توجد خطوات للتراجع عنها')
            return

        print()
        print('⏪ بدء التراجع ...')
        print('-' * 40)

        errors = []
        for i, step in enumerate(reversed(self.completed), 1):
            desc = step['description']
            print(f'  [{i}/{len(self.completed)}] عكس: {desc}')
            try:
                # ابحث عن undo_fn في steps
                for s in self.steps:
                    if s['description'] == desc:
                        s['undo_fn']()
                        break
            except Exception as e:
                errors.append((desc, str(e)))
                print(f'    ⚠️ خطأ في التراجع: {e}')

        print('-' * 40)
        if errors:
            print(f'⚠️ تم التراجع مع {len(errors)} أخطاء')
        else:
            print('✅ تم التراجع بنجاح - كل شيء عاد كما كان')

    def summary(self):
        print()
        print('📊 ملخص المعاملة:', self.name)
        print(f'   البدء: {self.started_at}')
        print(f'   الحالة: {"مؤكدة" if self.committed else "غير مؤكدة"}')
        print(f'   الخطوات المنفذة: {len(self.completed)}')


if __name__ == '__main__':
    print('Demo: Transaction with Rollback')
    print('-' * 40)

    tx = Transaction('demo_test')
    counter = [0]

    def increment():
        counter[0] += 1
        print(f'    -> counter = {counter[0]}')

    def decrement():
        counter[0] -= 1
        print(f'    -> counter = {counter[0]} (undone)')

    tx.execute(increment, 'الزيادة بمقدار 1', decrement)
    tx.execute(increment, 'الزيادة بمقدار 1', decrement)
    tx.execute(increment, 'الزيادة بمقدار 1', decrement)

    print(f'\\nCounter بعد 3 زيادات: {counter[0]}')
    tx.commit()
    print()

    ans = input('هل تريد التراجع؟ [نعم/لا]: ').strip()
    if ans in ('نعم', 'yes', 'y'):
        tx.rewind()
        print(f'\\nCounter بعد التراجع: {counter[0]}')
