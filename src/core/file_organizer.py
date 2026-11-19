"""N076: organize an approved folder by file type — preview first, never delete, always undoable.

Only regular, non-hidden files directly inside the chosen folder are moved, and only into
category sub-folders of that same folder. The plan is bound to a hash of the files it saw;
if anything changed before confirmation, nothing moves. Every executed move is journaled so
«تراجع عن آخر تنظيم» puts files back exactly where they were.
"""
import hashlib
import json
import os
import time
from pathlib import Path

CATEGORIES = {
    'الصور': {'jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'heic', 'bmp', 'tif', 'tiff', 'avif', 'ico'},
    'الفيديو': {'mp4', 'mkv', 'webm', 'avi', 'mov', 'm4v', 'wmv', 'flv'},
    'الصوتيات': {'mp3', 'wav', 'flac', 'ogg', 'm4a', 'opus', 'aac', 'wma'},
    'المستندات': {'pdf', 'doc', 'docx', 'odt', 'txt', 'md', 'rtf', 'xls', 'xlsx', 'ods', 'csv', 'ppt', 'pptx', 'odp', 'epub'},
    'الأرشيفات': {'zip', 'rar', '7z', 'tar', 'gz', 'tgz', 'xz', 'bz2', 'zst', 'iso'},
    'البرامج': {'appimage', 'deb', 'rpm', 'exe', 'msi', 'flatpakref', 'run'},
    'الكود': {'py', 'js', 'ts', 'html', 'css', 'json', 'c', 'cpp', 'h', 'rs', 'go', 'java', 'sh', 'yaml', 'yml', 'toml'},
}
MAX_FILES = 2000


class OrganizerError(ValueError):
    pass


def category(path):
    suffixes = [s.lower().lstrip('.') for s in path.suffixes]
    if not suffixes:
        return None
    for name, extensions in CATEGORIES.items():
        if suffixes[-1] in extensions:
            return name
    return None


def plan(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise OrganizerError('المجلد غير موجود أو ليس مجلدًا حقيقيًا.')
    root = root.resolve()
    entries = sorted(os.scandir(root), key=lambda e: e.name)
    if len(entries) > MAX_FILES:
        raise OrganizerError('المجلد يحتوي أكثر من ' + str(MAX_FILES) + ' عنصر؛ نظّمه على دفعات.')
    moves, seen, skipped = [], [], 0
    taken = {e.name for e in entries}
    for entry in entries:
        if entry.name.startswith('.') or entry.is_symlink() or not entry.is_file(follow_symlinks=False):
            continue
        stat = entry.stat(follow_symlinks=False)
        seen.append([entry.name, stat.st_size, stat.st_mtime_ns])
        target_dir = category(Path(entry.name))
        if not target_dir:
            skipped += 1
            continue
        if target_dir in taken and not (root / target_dir).is_dir():
            skipped += 1
            continue
        destination = Path(target_dir) / entry.name
        counter = 2
        while (root / destination).exists() or any(m['to'] == str(destination) for m in moves):
            destination = Path(target_dir) / (Path(entry.name).stem + ' (' + str(counter) + ')' + ''.join(Path(entry.name).suffixes[-1:]))
            counter += 1
        moves.append({'from': entry.name, 'to': str(destination)})
    digest = hashlib.sha256(json.dumps([str(root), seen, moves], ensure_ascii=False).encode()).hexdigest()
    summary = {}
    for move in moves:
        summary[Path(move['to']).parts[0]] = summary.get(Path(move['to']).parts[0], 0) + 1
    return {'root': str(root), 'moves': moves, 'summary': summary, 'skipped': skipped, 'hash': digest}


def describe(result, name):
    if not result['moves']:
        return 'المجلد «' + name + '» منظّم بالفعل أو لا يحتوي ملفات معروفة النوع؛ لن أنقل شيئًا.'
    parts = '، '.join(k + ': ' + str(v) for k, v in result['summary'].items())
    extra = ('، وسأترك ' + str(result['skipped']) + ' ملفًا غير معروف النوع مكانه') if result['skipped'] else ''
    return ('خطة تنظيم «' + name + '»: نقل ' + str(len(result['moves'])) + ' ملفًا إلى مجلدات فرعية (' + parts + ')' + extra +
            '. لن يُحذف أي شيء، ويمكنك التراجع بعدها بقول «تراجع عن آخر تنظيم». اضغط الزر للتنفيذ.')


def apply(root, expected_hash, journal_dir):
    current = plan(root)
    if current['hash'] != expected_hash:
        raise OrganizerError('تغيّرت ملفات المجلد منذ عرض الخطة؛ لم أنقل شيئًا. اطلب التنظيم من جديد.')
    root = Path(current['root'])
    journal_dir = Path(journal_dir)
    journal_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    done, created = [], []
    try:
        for move in current['moves']:
            source, target = root / move['from'], root / move['to']
            if not target.parent.exists():
                target.parent.mkdir(mode=0o755)
                created.append(str(target.parent.relative_to(root)))
            if target.exists():
                raise OrganizerError('ظهر ملف بنفس الاسم أثناء التنظيم: ' + move['to'])
            os.rename(source, target)
            done.append(move)
    except BaseException:
        for move in reversed(done):
            os.rename(root / move['to'], root / move['from'])
        for folder in reversed(created):
            try:
                (root / folder).rmdir()
            except OSError:
                pass
        raise
    record = {'root': str(root), 'moves': done, 'created': created, 'time': time.time()}
    path = journal_dir / ('organize-' + str(int(time.time() * 1000)) + '.json')
    path.write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
    path.chmod(0o600)
    return record


def undo_last(journal_dir):
    journals = sorted(Path(journal_dir).glob('organize-*.json')) if Path(journal_dir).is_dir() else []
    if not journals:
        raise OrganizerError('لا توجد عملية تنظيم سابقة للتراجع عنها.')
    path = journals[-1]
    record = json.loads(path.read_text(encoding='utf-8'))
    root = Path(record['root'])
    restored, missing = 0, 0
    for move in reversed(record['moves']):
        source, target = root / move['to'], root / move['from']
        if source.is_file() and not source.is_symlink() and not target.exists():
            os.rename(source, target)
            restored += 1
        else:
            missing += 1
    for folder in reversed(record['created']):
        try:
            (root / folder).rmdir()
        except OSError:
            pass
    path.rename(path.with_suffix('.undone'))
    return {'root': str(root), 'restored': restored, 'missing': missing}
