"""N030/N031: Neura Doctor — named checks that actually run, each with a reason and a fix.

Only checks that executed are counted; a check that cannot run reports «unknown», never «ok».
The synced-folder check (N031) looks for real sync markers on the data path, not just a word
in the name, so ordinary local folders are not flagged.
"""
import importlib.util
import os
import platform
import shutil
from pathlib import Path

SYNC_NAMES = ('dropbox', 'onedrive', 'google drive', 'googledrive', 'gdrive', 'nextcloud', 'owncloud', 'mega', 'pcloud', 'icloud', 'syncthing', 'seafile', 'box sync')
SYNC_MARKERS = ('.dropbox', '.dropbox.cache', '.stfolder', '.sync', '.nextcloudsync.log', '.owncloudsync.log', '.megaignore', '.seafile-data')


def synced_root(path):
    """Return the ancestor that looks like a sync client's folder, else None."""
    path = Path(path).resolve()
    for folder in [path, *path.parents]:
        if folder == folder.parent:
            break
        if any((folder / marker).exists() for marker in SYNC_MARKERS):
            return folder
        name = folder.name.lower()
        if any(name == n or name.startswith(n + ' ') or name.startswith(n + '-') for n in SYNC_NAMES):
            return folder
    return None


def check(identifier, label, status, detail, fix=''):
    return {'id': identifier, 'label': label, 'status': status, 'detail': detail, 'fix': fix}


def run(settings, coordinator=None, voice=None, knowledge=None, notifier=None, desktop=None):
    results = []
    from src.desktop.paths import VERSION
    results.append(check('version', 'إصدار Neura', 'ok', 'Neura ' + VERSION + ' · Python ' + platform.python_version() + ' · ' + platform.system()))

    data = Path(settings.data_dir)
    writable = os.access(data, os.W_OK)
    results.append(check('data_dir', 'مجلد البيانات', 'ok' if writable else 'fail', str(data), '' if writable else 'امنح المستخدم صلاحية الكتابة على المجلد.'))
    root = synced_root(data)
    results.append(check('synced_folder', 'مزامنة سحابية لمجلد البيانات', 'warn' if root else 'ok',
                         ('المجلد داخل مجلد مزامنة: ' + str(root)) if root else 'مجلد محلي غير متزامن.',
                         'قواعد البيانات المفتوحة قد تتلف مع المزامنة؛ انقل NEURA_DATA_DIR إلى مجلد محلي مثل ~/.local/share/neura-ai.' if root else ''))
    try:
        free = shutil.disk_usage(data).free / 1e9
        results.append(check('disk', 'المساحة الحرة', 'ok' if free >= 5 else 'warn' if free >= 1 else 'fail', f'{free:.1f} GB متاحة',
                             '' if free >= 5 else 'وفّر مساحة؛ المشاريع والمراجعات والسجلات تحتاج مساحة.'))
    except OSError as exc:
        results.append(check('disk', 'المساحة الحرة', 'unknown', str(exc)))

    models = Path(settings.models_dir)
    results.append(check('models_dir', 'مجلد النماذج', 'ok' if models.is_dir() else 'fail', str(models), '' if models.is_dir() else 'اختر مجلد ملفات GGUF من الإعدادات.'))
    if coordinator is not None and hasattr(coordinator, 'residency'):
        for tier, info in coordinator.residency.tiers.items():
            ok, note = coordinator.residency.availability(info['model_id'])
            results.append(check('model_' + tier, 'نموذج ' + tier.upper(), 'ok' if ok else 'fail', info['model_id'] + ' — ' + note,
                                 '' if ok else 'أكمل ملف النموذج أو اختر نموذجًا آخر للدور من «النماذج والأدوار».'))
    engine = importlib.util.find_spec('llama_cpp') is not None
    results.append(check('engine', 'محرك الاستدلال llama.cpp', 'ok' if engine else 'fail', 'مثبت' if engine else 'غير موجود', '' if engine else 'أعد تثبيت الحزمة.'))
    if settings.n_ctx < 8192:
        results.append(check('context', 'حجم السياق', 'warn', str(settings.n_ctx) + ' توكن',
                             'لإنشاء مواقع أكبر وتعديلات أطول اختر 8192 في الإعدادات إن كانت ذاكرة كرتك 12 GB أو أكثر.'))
    else:
        results.append(check('context', 'حجم السياق', 'ok', str(settings.n_ctx) + ' توكن'))

    if voice is not None:
        caps = voice.capabilities()
        results.append(check('stt', 'التعرف على الكلام', 'ok' if caps['stt'] else 'warn', caps.get('stt_engine') or 'غير متاح', '' if caps['stt'] else caps['stt_reason']))
        results.append(check('tts', 'النطق', 'ok' if caps['tts'] else 'warn', caps.get('tts_engine') or 'غير متاح', '' if caps['tts'] else caps['tts_reason']))
    ffmpeg = bool(shutil.which('ffmpeg'))
    results.append(check('ffmpeg', 'ffmpeg', 'ok' if ffmpeg else 'warn', 'مثبت' if ffmpeg else 'غير مثبت', '' if ffmpeg else 'sudo pacman -S ffmpeg'))
    if knowledge is not None:
        available = knowledge.embedder.available
        results.append(check('embedding', 'نموذج المعرفة (التضمين)', 'ok' if available else 'warn', str(knowledge.embedder.model_path or 'غير موجود'),
                             '' if available else 'ضع نموذج تضمين GGUF مثل nomic-embed-text في مجلد النماذج.'))
    if notifier is not None:
        results.append(check('notifications', 'إشعارات سطح المكتب', 'ok' if notifier.available() else 'warn', 'notify-send' if notifier.available() else 'غير متاحة',
                             '' if notifier.available() else 'sudo pacman -S libnotify'))
    if desktop is not None:
        try:
            status = desktop.status()
            results.append(check('desktop', 'جلسة سطح المكتب', 'ok' if status.get('desktop_available') else 'warn', status.get('reason') or 'متاحة'))
            results.append(check('brave', 'متصفح Brave للمهارات', 'ok' if status.get('brave_available') else 'warn', 'مثبت' if status.get('brave_available') else 'غير مثبت',
                                 '' if status.get('brave_available') else 'ثبّت Brave أو عطّل مهارات المتصفح.'))
        except Exception as exc:
            results.append(check('desktop', 'جلسة سطح المكتب', 'unknown', str(exc)[:200]))
    summary = {s: sum(r['status'] == s for r in results) for s in ('ok', 'warn', 'fail', 'unknown')}
    return {'checks': results, 'summary': summary, 'count': len(results)}
