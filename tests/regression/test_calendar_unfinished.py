"""N084 iCalendar exchange without accounts or duplicates; N083 unfinished work on request only."""
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from src.core.assistant import Assistant
from src.core.assistant_intents import parse
from src.core.assistant_store import AssistantStore
from src.core.calendar_ics import CalendarError, export_reminders, import_events, parse_events
from tests.regression.test_chat_dispatch import application

H = {'X-Neura-Token': 'test-token'}
NOW = datetime(2026, 11, 19, 10, 0, tzinfo=ZoneInfo('Asia/Riyadh'))
ICS = ('BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:abc-1\r\nDTSTART;TZID=Asia/Riyadh:20991120T150000\r\nSUMMARY:اجتماع الفريق\\, الغرفة 2\r\nEND:VEVENT\r\n'
       'BEGIN:VEVENT\r\nUID:abc-2\r\nDTSTART:20200101T100000Z\r\nSUMMARY:قديم\r\nEND:VEVENT\r\n'
       'BEGIN:VEVENT\r\nUID:abc-3\r\nDTSTART;VALUE=DATE:20991121\r\nSUMMARY:يوم كامل\r\nEND:VEVENT\r\n'
       'BEGIN:VEVENT\r\nUID:abc-4\r\nDTSTART:20991122T100000Z\r\nRRULE:FREQ=WEEKLY\r\nSUMMARY:أسبوعي\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n')


def test_import_is_idempotent_and_honest_about_skips(tmp_path):
    store = AssistantStore(tmp_path)
    first = import_events(store, ICS, 'Asia/Riyadh', time.time())
    assert [r['text'] for r in first['created']] == ['اجتماع الفريق, الغرفة 2'] and first['past'] == 1
    assert first['skipped'] == {'all_day': 1, 'recurring': 1, 'invalid': 0}
    again = import_events(store, ICS, 'Asia/Riyadh', time.time())
    assert again['created'] == [] and again['already_imported'] == 1 and len(store.reminders()) == 1
    due = datetime.fromtimestamp(store.reminders()[0]['due'], ZoneInfo('Asia/Riyadh'))
    assert (due.hour, due.minute) == (15, 0)
    with pytest.raises(CalendarError):
        parse_events('not a calendar')


def test_export_round_trips_with_stable_uids(tmp_path):
    store = AssistantStore(tmp_path)
    store.add_reminder('موعد طويل جدًا ' * 8 + '; مع فاصلة, ونقطة', time.time() + 3600, 'Asia/Riyadh')
    ics = export_reminders(store.reminders(), time.time())
    assert all(len(line.encode()) <= 75 for line in ics.split('\r\n'))
    events, _ = parse_events(ics)
    assert events[0]['uid'] == store.reminders()[0]['id'] + '@neura.local' and events[0]['summary'].endswith('; مع فاصلة, ونقطة')


def test_calendar_api(system):
    app, desktop, dispatch = application(system)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        assert client.get('/assistant/reminders.ics').status_code == 403
        imported = client.post('/assistant/calendar/import', json={'ics': ICS}, headers=H).json()
        assert len(imported['created']) == 1
        exported = client.get('/assistant/reminders.ics', headers=H)
        assert exported.headers['content-type'].startswith('text/calendar') and 'اجتماع الفريق' in exported.text
        assert client.post('/assistant/calendar/import', json={'ics': 'hello world!'}, headers=H).status_code == 400
    app.state.project_store.close()


@pytest.mark.parametrize('text', ['ما الأعمال غير المكتملة؟', 'وش باقي علي؟', 'اعرض المشاريع المعلقة', "what's unfinished?"])
def test_unfinished_intent(text):
    assert parse(text, NOW).name == 'work.unfinished'


def test_unfinished_lists_only_neura_records(tmp_path):
    assistant = Assistant(tmp_path, workspace=lambda: [{'title': 'مشروع «مقهى»', 'detail': 'فشل آخر توليد'}])
    reply = assistant.handle(parse('ما الأعمال غير المكتملة', NOW))
    assert 'مقهى' in reply['message'] and 'لا أقرأ سجل المتصفح' in reply['message']
    empty = Assistant(tmp_path / 'b').handle(parse('ما الأعمال غير المكتملة', NOW))
    assert 'لا توجد أعمال غير مكتملة' in empty['message']


def test_unfinished_projects_provider(system):
    from src.backend.api import unfinished_projects
    app, desktop, dispatch = application(system)
    store = app.state.project_store
    store.create('مقهى', 'موقع')
    assert unfinished_projects(store) == []
    store.close()
