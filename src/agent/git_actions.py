"""
Neura Git Actions
عمليات Git آمنة مع Safety Gate + Transaction Rollback.
"""
import sys
import os
import subprocess
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from safety import SafetyGate
from transaction import Transaction


def _run_git(*args, cwd=None):
    """يشغل أمر git ويرجع النتيجة."""
    cmd = ['git'] + list(args)
    try:
        result = subprocess.run(
            cmd, cwd=cwd,
            capture_output=True, text=True,
            encoding='utf-8', errors='replace',
            timeout=30
        )
        return {
            'ok': result.returncode == 0,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'returncode': result.returncode
        }
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def _get_current_branch(cwd=None):
    r = _run_git('rev-parse', '--abbrev-ref', 'HEAD', cwd=cwd)
    return r['stdout'].strip() if r['ok'] else None


def _get_current_commit(cwd=None):
    r = _run_git('rev-parse', 'HEAD', cwd=cwd)
    return r['stdout'].strip() if r['ok'] else None


def _get_status_summary(cwd=None):
    r = _run_git('status', '--short', cwd=cwd)
    if not r['ok']:
        return []
    return [l for l in r['stdout'].strip().split('\n') if l.strip()]


def safe_commit(message, files=None, cwd=None, auto_approve=False):
    """commit آمن مع Safety Gate + rollback via git reset."""
    gate = SafetyGate(interactive=not auto_approve)
    if cwd is None:
        cwd = os.getcwd()

    commit_before = _get_current_commit(cwd)
    branch = _get_current_branch(cwd)
    status = _get_status_summary(cwd)

    if not status and not files:
        return {'ok': False, 'error': 'لا توجد تغييرات للـ commit'}

    files_list = files if files else [s for s in status]
    plan = (
        f'📝 Git Commit:\n'
        f'  الفرع: {branch}\n'
        f'  الرسالة: {message}\n'
        f'  الملفات ({len(files_list)}):\n'
    )
    for f in files_list[:10]:
        plan += f'    - {f}\n'
    if len(files_list) > 10:
        plan += f'    ... و {len(files_list) - 10} ملفات أخرى\n'

    decision = gate.request_approval(plan, context='سيتم حفظ الكوميت السابق للتراجع')
    if decision != 'approved':
        return {'ok': False, 'reason': 'user_denied'}

    tx = Transaction(f'commit_{branch}_{datetime.now().strftime("%H%M%S")}')

    # git add
    if files:
        add_result = _run_git('add', *files, cwd=cwd)
    else:
        add_result = _run_git('add', '.', cwd=cwd)

    if not add_result['ok']:
        return {'ok': False, 'error': f'git add failed: {add_result["stderr"]}'}

    tx.record(f'git add {" ".join(files) if files else "."}', lambda: None)

    # git commit
    commit_result = _run_git('commit', '-m', message, cwd=cwd)
    if not commit_result['ok']:
        return {'ok': False, 'error': f'git commit failed: {commit_result["stderr"]}'}

    commit_after = _get_current_commit(cwd)

    def undo_commit():
        reset_result = _run_git('reset', '--soft', commit_before, cwd=cwd)
        if reset_result['ok']:
            print(f'    تم التراجع عن الكوميت (العودة لـ {commit_before[:8]})')
        else:
            print(f'    ⚠️ فشل التراجع: {reset_result["stderr"]}')

    tx.execute(
        lambda: commit_result,
        f'git commit -m "{message}" ({commit_after[:8]})',
        undo_commit
    )
    tx.commit()

    return {
        'ok': True,
        'branch': branch,
        'commit_before': commit_before,
        'commit_after': commit_after,
        'transaction': tx
    }


def safe_push(remote='origin', branch=None, cwd=None, auto_approve=False):
    """git push آمن مع تأكيد صريح (عملية خارجية لا تراجع عنها)."""
    gate = SafetyGate(interactive=not auto_approve)
    if cwd is None:
        cwd = os.getcwd()
    if branch is None:
        branch = _get_current_branch(cwd)

    commit = _get_current_commit(cwd)
    plan = (
        f'🚀 Git Push (عملية خارجية - لا يمكن التراجع عنها!):\n'
        f'  Remote: {remote}\n'
        f'  الفرع: {branch}\n'
        f'  الكوميت: {commit[:8] if commit else "unknown"}'
    )

    decision = gate.request_approval(
        plan,
        context='⚠️  تحذير: هذه العملية ترسل البيانات للـ remote ولا يمكن التراجع عنها بسهولة'
    )
    if decision != 'approved':
        return {'ok': False, 'reason': 'user_denied'}

    push_result = _run_git('push', remote, branch, cwd=cwd)
    if not push_result['ok']:
        return {'ok': False, 'error': f'git push failed: {push_result["stderr"]}'}

    return {'ok': True, 'remote': remote, 'branch': branch, 'commit': commit}


def safe_commit_and_push(message, files=None, remote='origin', cwd=None, auto_approve=False):
    """commit + push مع تأكيد منفصل لكل خطوة."""
    print('\n[الخطوة 1/2] Git Commit ...')
    commit_result = safe_commit(message, files, cwd, auto_approve)
    if not commit_result['ok']:
        return commit_result

    print('\n[الخطوة 2/2] Git Push ...')
    push_result = safe_push(remote, cwd=cwd, auto_approve=auto_approve)

    return {
        'ok': push_result['ok'],
        'commit': commit_result,
        'push': push_result,
        'transaction': commit_result.get('transaction')
    }


if __name__ == '__main__':
    print('Neura Git Actions - Full Demo')
    print('=' * 60)

    cwd = os.getcwd()
    branch = _get_current_branch(cwd)
    print(f'\n📍 المجلد: {cwd}')
    print(f'🌿 الفرع: {branch}')

    # ملف تجريبي خارج gitignore
    test_file = os.path.join('tests', 'agent', 'git_test.txt')
    os.makedirs(os.path.dirname(test_file), exist_ok=True)
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write(f'Git test file - {datetime.now()}\n')
    print(f'\n📝 تم إنشاء ملف تجريبي: {test_file}')

    # الاختبار 1: Commit + Rollback
    print('\n--- اختبار 1: Git Commit + Rollback ---')
    commit_result = safe_commit(
        message='test: git actions demo',
        files=[test_file],
        cwd=cwd
    )

    if commit_result['ok']:
        tx = commit_result['transaction']
        print(f'\n✅ تم الكوميت: {commit_result["commit_after"][:8]}')

        ans = input('\nهل تريد التراجع عن الكوميت؟ [نعم/لا]: ').strip()
        if ans in ('نعم', 'yes', 'y'):
            tx.rewind()
            print(f'\n✅ تم التراجع - الكوميت الحالي: {_get_current_commit(cwd)[:8]}')

    # الاختبار 2: Commit + Push (اختياري - يحتاج تأكيد صارم)
    ans = input('\nهل تريد اختبار Commit + Push الحقيقي؟ [نعم/لا]: ').strip()
    if ans in ('نعم', 'yes', 'y'):
        print('\n--- اختبار 2: Git Commit + Push ---')

        test_file2 = os.path.join('tests', 'agent', 'git_test2.txt')
        with open(test_file2, 'w', encoding='utf-8') as f:
            f.write(f'Push test - {datetime.now()}\n')

        result = safe_commit_and_push(
            message='test: git push demo',
            files=[test_file2],
            cwd=cwd
        )

        if result['ok']:
            print('\n✅ تم الكوميت والدفع بنجاح!')
        else:
            print(f'\n❌ فشلت العملية: {result}')

    print('\n✅ انتهت الاختبارات')
