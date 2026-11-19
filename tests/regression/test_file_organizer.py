"""N076: organize an approved folder with preview, hash-bound confirmation and undo."""
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src.core import file_organizer
from src.core.assistant import Assistant
from src.core.assistant_intents import parse
from src.core.file_organizer import OrganizerError

NOW = datetime(2026, 11, 19, 14, 30, tzinfo=ZoneInfo('Asia/Riyadh'))


def folder(tmp_path):
    root = tmp_path / 'Downloads'
    root.mkdir()
    for name in ['photo.JPG', 'clip.mp4', 'song.mp3', 'report.pdf', 'archive.tar.gz', 'setup.AppImage', 'notes.md', 'mystery.xyz', '.hidden.png']:
        (root / name).write_text(name)
    (root / 'existing').mkdir()
    (root / 'الصور').mkdir()
    (root / 'الصور' / 'photo.JPG').write_text('older')
    os.symlink(root / 'report.pdf', root / 'link.pdf')
    return root


def test_plan_apply_and_undo(tmp_path):
    root = folder(tmp_path)
    plan = file_organizer.plan(root)
    moves = {m['from']: m['to'] for m in plan['moves']}
    assert moves['photo.JPG'] == 'الصور/photo (2).JPG' and moves['clip.mp4'] == 'الفيديو/clip.mp4' and moves['archive.tar.gz'] == 'الأرشيفات/archive.tar.gz'
    assert 'mystery.xyz' not in moves and '.hidden.png' not in moves and 'link.pdf' not in moves and plan['skipped'] == 1
    record = file_organizer.apply(root, plan['hash'], tmp_path / 'journal')
    assert (root / 'الفيديو' / 'clip.mp4').read_text() == 'clip.mp4' and (root / 'الصور' / 'photo.JPG').read_text() == 'older'
    assert (root / 'mystery.xyz').exists() and len(record['moves']) == len(plan['moves'])
    undone = file_organizer.undo_last(tmp_path / 'journal')
    assert undone['restored'] == len(plan['moves']) and (root / 'clip.mp4').exists() and not (root / 'الفيديو').exists()
    assert (root / 'الصور').exists()                       # it existed before; never removed
    with pytest.raises(OrganizerError):
        file_organizer.undo_last(tmp_path / 'journal')


def test_changed_folder_after_preview_moves_nothing(tmp_path):
    root = folder(tmp_path)
    plan = file_organizer.plan(root)
    (root / 'new.png').write_text('x')
    with pytest.raises(OrganizerError):
        file_organizer.apply(root, plan['hash'], tmp_path / 'journal')
    assert (root / 'clip.mp4').exists() and not (root / 'الفيديو').exists()


@pytest.mark.parametrize('text,name', [('نظم مجلد التنزيلات', 'files.organize'), ('رتب ملفات مجلد المستندات', 'files.organize'),
                                       ('organize the folder Downloads', 'files.organize'), ('تراجع عن آخر تنظيم', 'files.undo')])
def test_intents(text, name):
    assert parse(text, NOW).name == name


@pytest.mark.parametrize('text', ['رتب الأقسام في الموقع', 'نظم وقتي', 'رتب العناوين'])
def test_project_edits_are_not_file_organizing(text):
    intent = parse(text, NOW)
    assert intent is None or not intent.name.startswith('files.')


def test_assistant_flow_requires_an_approved_folder_and_confirmation(tmp_path):
    root = folder(tmp_path)
    approved = {}
    assistant = Assistant(tmp_path / 'data', locations=lambda: approved)
    reply = assistant.handle(parse('نظم مجلد التنزيلات', NOW))
    assert reply['result']['status'] == 'unavailable' and (root / 'clip.mp4').exists()
    approved['l_' + 'a' * 32] = {'path': str(root), 'kind': 'folder'}
    preview = assistant.handle(parse('نظم مجلد التنزيلات', NOW))
    assert preview['kind'] == 'clarification' and (root / 'clip.mp4').exists()
    option = preview['_options'][0]
    done = assistant.choose(option['name'], option['args'])
    assert 'الفيديو' in done['message'] and (root / 'الفيديو' / 'clip.mp4').exists()
    assert 'أُعيد' in assistant.handle(parse('تراجع عن آخر تنظيم', NOW))['message'] and (root / 'clip.mp4').exists()
