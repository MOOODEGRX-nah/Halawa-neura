"""
Neura File Actions
عمليات ملفات آمنة مع snapshot + rollback.
"""
import sys
import os
import shutil
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from safety import SafetyGate
from transaction import Transaction


SNAPSHOTS_DIR = 'data/snapshots'


def _snapshot_path(src):
    """يولد مسار snapshot فريد."""
    os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    basename = os.path.basename(src)
    return os.path.join(SNAPSHOTS_DIR, f'{ts}_{basename}')


def _ensure_parent(dst):
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)


def safe_move(src, dst, tx=None, auto_approve=False):
    """
    ينقل ملفاً مع:
    - نسخة احتياطية (snapshot)
    - تأكيد من المستخدم (Safety Gate)
    - قدرة على التراجع
    """
    gate = SafetyGate(interactive=not auto_approve)

    if not os.path.exists(src):
        return {'ok': False, 'error': f'الملف المصدر غير موجود: {src}'}

    src_abs = os.path.abspath(src)
    dst_abs = os.path.abspath(dst)

    plan = (
        f'📁 نقل ملف:\n'
        f'  المصدر: {src_abs}\n'
        f'  الوجهة: {dst_abs}\n'
        f'  الحجم: {os.path.getsize(src)} bytes'
    )
    context = 'سيتم إنشاء نسخة احتياطية قبل النقل'

    decision = gate.request_approval(plan, context)
    if decision != 'approved':
        return {'ok': False, 'reason': 'user_denied'}

    snapshot = _snapshot_path(src)
    shutil.copy2(src, snapshot)
    print(f'💾 Snapshot محفوظ: {snapshot}')

    _ensure_parent(dst)

    # نفّذ النقل
    if tx is None:
        tx = Transaction(f'move_{os.path.basename(src)}')

    def do_move():
        shutil.move(src, dst)

    def undo_move():
        shutil.move(dst, src)
        print(f'    تم استعادة الملف إلى موقعه الأصلي')

    tx.execute(do_move, f'move {src_abs} -> {dst_abs}', undo_move)
    tx.commit()

    return {
        'ok': True,
        'src': src_abs,
        'dst': dst_abs,
        'snapshot': snapshot,
        'transaction': tx
    }


def safe_copy(src, dst, tx=None, auto_approve=False):
    """نسخ آمن مع snapshot."""
    gate = SafetyGate(interactive=not auto_approve)

    if not os.path.exists(src):
        return {'ok': False, 'error': f'الملف المصدر غير موجود: {src}'}

    src_abs = os.path.abspath(src)
    dst_abs = os.path.abspath(dst)

    plan = (
        f'📋 نسخ ملف:\n'
        f'  المصدر: {src_abs}\n'
        f'  الوجهة: {dst_abs}'
    )

    decision = gate.request_approval(plan)
    if decision != 'approved':
        return {'ok': False, 'reason': 'user_denied'}

    _ensure_parent(dst)

    if tx is None:
        tx = Transaction(f'copy_{os.path.basename(src)}')

    def do_copy():
        shutil.copy2(src, dst)

    def undo_copy():
        if os.path.exists(dst):
            os.remove(dst)
            print(f'    تم حذف النسخة: {dst}')

    tx.execute(do_copy, f'copy {src_abs} -> {dst_abs}', undo_copy)
    tx.commit()

    return {'ok': True, 'src': src_abs, 'dst': dst_abs, 'transaction': tx}


def safe_delete(path, tx=None, auto_approve=False):
    """حذف آمن مع snapshot - يمكن التراجع."""
    gate = SafetyGate(interactive=not auto_approve)

    if not os.path.exists(path):
        return {'ok': False, 'error': f'الملف غير موجود: {path}'}

    plan = (
        f'🗑️  حذف ملف (مع snapshot للتراجع):\n'
        f'  المسار: {os.path.abspath(path)}\n'
        f'  الحجم: {os.path.getsize(path)} bytes'
    )

    decision = gate.request_approval(plan)
    if decision != 'approved':
        return {'ok': False, 'reason': 'user_denied'}

    snapshot = _snapshot_path(path)
    shutil.copy2(path, snapshot)
    print(f'💾 Snapshot قبل الحذف: {snapshot}')

    if tx is None:
        tx = Transaction(f'delete_{os.path.basename(path)}')

    path_abs = os.path.abspath(path)

    def do_delete():
        os.remove(path_abs)

    def undo_delete():
        shutil.copy2(snapshot, path_abs)
        print(f'    تم استعادة الملف من الـ snapshot')

    tx.execute(do_delete, f'delete {path_abs}', undo_delete)
    tx.commit()

    return {'ok': True, 'path': path_abs, 'snapshot': snapshot, 'transaction': tx}


if __name__ == '__main__':
    print('Neura File Actions - Full Demo')
    print('=' * 60)

    # أنشئ ملف تجريبي
    test_dir = 'data/test_agent'
    os.makedirs(test_dir, exist_ok=True)
    test_file = os.path.join(test_dir, 'hello.txt')
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write('مرحباً! هذا ملف تجريبي لاختبار Neura Agent\n')
    print(f'\\n📝 تم إنشاء ملف تجريبي: {test_file}')

    # جرب النقل
    print('\\n--- اختبار 1: نقل الملف ---')
    result = safe_move(test_file, os.path.join(test_dir, 'moved.txt'))

    if result['ok']:
        tx = result['transaction']
        print('\\nالملف الآن في الموقع الجديد')

        ans = input('\\nهل تريد التراجع عن النقل؟ [نعم/لا]: ').strip()
        if ans in ('نعم', 'yes', 'y'):
            tx.rewind()

    print('\\n✅ انتهت الاختبارات')
