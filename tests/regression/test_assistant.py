"""Personal assistant: memory, reminders, clock, calculator and weather without loading a model."""
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from src.core.assistant import Assistant, best_matches, fit_history
from src.core.assistant_intents import parse
from src.core.assistant_store import AssistantStore, AssistantError
from src.core.assistant_tools import calculate, ToolError, hijri, due_text, Weather
from tests.regression.test_chat_dispatch import application, request_id

RIYADH = ZoneInfo('Asia/Riyadh')
NOW = datetime(2026, 11, 19, 14, 30, tzinfo=RIYADH)  # Thursday


def local(ts):
    return datetime.fromtimestamp(ts, RIYADH)


@pytest.mark.parametrize('text,expected', [
    ('ذكّرني بعد ١٠ دقائق أن أشرب الماء', ('أشرب الماء', datetime(2026, 11, 19, 14, 40))),
    ('ذكرني بعد ساعتين بالاتصال على أمي', ('الاتصال على أمي', datetime(2026, 11, 19, 16, 30))),
    ('ذكرني غداً الساعة ٩ صباحاً بالاجتماع', ('الاجتماع', datetime(2026, 11, 20, 9, 0))),
    ('ذكرني الساعة 5 أن أصلي العصر', ('أصلي العصر', datetime(2026, 11, 19, 17, 0))),
    ('ذكرني يوم الجمعة الساعة 8 مساء بموعد العشاء', ('موعد العشاء', datetime(2026, 11, 20, 20, 0))),
    ('ذكرني الليلة بإخراج القمامة', ('إخراج القمامة', datetime(2026, 11, 19, 21, 0))),
    ('ذكرني بكرة العصر أروح للبنك', ('أروح للبنك', datetime(2026, 11, 20, 17, 0))),
    ('ذكرني أن أتصل بأحمد بعد ساعة', ('أتصل بأحمد', datetime(2026, 11, 19, 15, 30))),
    ('نبهني بعد نص ساعة', ('تذكير من Neura', datetime(2026, 11, 19, 15, 0))),
    ('ذكرني بعد ساعة ونص', ('تذكير من Neura', datetime(2026, 11, 19, 16, 0))),
    ('اضبط مؤقت 5 دقائق', ('انتهى المؤقت', datetime(2026, 11, 19, 14, 35))),
    ('مؤقت لمدة ربع ساعة', ('انتهى المؤقت', datetime(2026, 11, 19, 14, 45))),
    ('remind me in 20 minutes to check the oven', ('check the oven', datetime(2026, 11, 19, 14, 50))),
    ('ذكرني الساعة 2 بالدواء', ('الدواء', datetime(2026, 11, 20, 2, 0))),
])
def test_reminder_times_and_wording(text, expected):
    intent = parse(text, NOW)
    assert intent.name == 'reminder.create'
    assert intent.args['text'] == expected[0]
    assert local(intent.args['due']).replace(tzinfo=None) == expected[1]


@pytest.mark.parametrize('text', ['ذكرني بالاجتماع', 'ذكرني', 'ذكرني اليوم الساعة 9 صباحا بالاجتماع'])
def test_unresolved_or_past_reminder_asks_instead_of_guessing(text):
    intent = parse(text, NOW)
    assert intent.name == 'clarify' and 'لم أنشئ تذكيرًا' in intent.args['message']


@pytest.mark.parametrize('text,name', [
    ('تذكّر أن اسمي أحمد', 'memory.save'), ('احفظ في ذاكرتك أن عيد ميلادي 5 مارس', 'memory.save'),
    ('ماذا تتذكر عني؟', 'memory.list'), ('انسَ أنني أحب القهوة', 'memory.forget'), ('امسح ذاكرتك كلها', 'memory.forget_all'),
    ('ما هي تذكيراتي', 'reminder.list'), ('هل عندي تذكيرات', 'reminder.list'), ('الغ تذكير الاجتماع', 'reminder.cancel'),
    ('الغ كل التذكيرات', 'reminder.cancel_all'), ('كم الساعة الآن؟', 'clock.time'), ('كم الساعة في لندن', 'clock.time'),
    ('ما تاريخ اليوم', 'clock.date'), ('وش التاريخ الهجري', 'clock.date'), ('احسب 15 × 4 + ٣', 'calc'), ('12*12', 'calc'),
    ('15% من 200', 'calc'), ('ما الطقس في جدة؟', 'weather'), ('كيف الجو بالرياض', 'weather'), ('الطقس غدا في دبي', 'weather'),
])
def test_assistant_intents(text, name):
    assert parse(text, NOW).name == name


@pytest.mark.parametrize('text', ['لا تذكرني', 'كيف أضبط تذكير', 'هل تتذكر اسمي؟', 'افتح يوتيوب', 'ما هو الذكاء الاصطناعي',
                                  'الساعة الذكية أفضل؟', 'برمج لي موقع', 'ما اليوم الوطني السعودي', '«ذكرني بعد 5 دقائق»',
                                  'اشرح كيف تعمل التذكيرات', 'احذف Login', 'ما هي عاصمة اليابان؟', 'تذكر ؟'])
def test_non_requests_stay_with_chat(text):
    intent = parse(text, NOW)
    assert intent is None


def test_calculator_is_restricted_and_exact():
    assert calculate('15 × 4 + ٣')['display'] == '63'
    assert calculate('2 اس 10')['display'] == '1,024'
    assert calculate('15% من 200')['display'] == '30'
    assert calculate('جذر 144')['display'] == '12'
    assert calculate('10 / 4')['display'] == '2.5'
    for bad in ['__import__("os")', '1/0', '9**9**9', 'open("x")', '2 +', 'abc']:
        with pytest.raises(ToolError):
            calculate(bad)


def test_hijri_conversion_known_dates():
    from datetime import date
    assert hijri(date(2026, 2, 18))['month'] in (8, 9)        # around the start of Ramadan 1447
    assert hijri(date(2026, 11, 19))['year'] == 1448


def test_store_memories_are_deduplicated_bounded_and_exportable(tmp_path):
    store = AssistantStore(tmp_path)
    first = store.remember('اسمي أحمد')
    assert store.remember('اسمي احمد')['duplicate']
    with pytest.raises(AssistantError):
        store.remember('   ')
    exported = store.export_memories()
    other = AssistantStore(tmp_path / 'other')
    assert other.import_memories(exported) == {'added': 1, 'skipped': 0}
    assert store.forget(first['id'])['text'] == 'اسمي أحمد' and not store.memories()
    with pytest.raises(AssistantError):
        other.import_memories({'format': 'other'})
    assert (tmp_path / 'assistant.sqlite3').stat().st_mode & 0o777 == 0o600


def test_reminders_fire_once_and_late_ones_are_marked(tmp_path):
    sent = []
    clock = [1000.0]

    class Recorder:
        def available(self): return True
        def notify(self, title, body): sent.append(body)

    assistant = Assistant(tmp_path, notifier=Recorder(), clock=lambda: clock[0])
    assistant.store.add_reminder('اشرب الماء', 1060, 'Asia/Riyadh', request_id='r1')
    assistant.store.add_reminder('قديم', 500, 'Asia/Riyadh')
    assert assistant.store.add_reminder('اشرب الماء', 1060, 'Asia/Riyadh', request_id='r1')['text'] == 'اشرب الماء'
    fired = assistant.deliver_due()
    assert [r['text'] for r in fired] == ['قديم'] and fired[0]['late'] and 'فات موعده' in sent[0]
    clock[0] = 1061
    assert [r['text'] for r in assistant.deliver_due()] == ['اشرب الماء']
    assert assistant.deliver_due() == [] and len(sent) == 2
    events = assistant.store.events()
    assert [e['text'] for e in events['events']] == ['قديم', 'اشرب الماء'] and assistant.store.events(events['last'])['events'] == []


def test_forget_matches_by_words(tmp_path):
    store = AssistantStore(tmp_path)
    store.remember('أنا أحب القهوة بدون سكر'); store.remember('اسمي أحمد')
    assert [m['text'] for m in best_matches('احب القهوة', store.memories())] == ['أنا أحب القهوة بدون سكر']


def test_weather_is_sourced_and_failure_is_honest(tmp_path):
    def fetch(url, params):
        assert 'api.open-meteo.com' in url and params['latitude'] == 21.4858
        return {'current': {'time': '2026-11-19T14:30', 'temperature_2m': 31.4, 'apparent_temperature': 33.0, 'relative_humidity_2m': 55,
                            'wind_speed_10m': 12.2, 'weather_code': 1},
                'daily': {'time': ['2026-11-19', '2026-11-20'], 'weather_code': [1, 3], 'temperature_2m_max': [33.1, 32.0],
                          'temperature_2m_min': [24.2, 23.9], 'precipitation_probability_max': [0, 10]}}
    weather = Weather(fetch=fetch)
    text = weather.describe(weather.forecast('جدة'))
    assert 'جدة' in text and '31°' in text and 'Open-Meteo' in text
    tomorrow = weather.describe(weather.forecast('جدة', 1))
    assert 'غدًا' in tomorrow and 'غائم' in tomorrow
    def broken(url, params): raise OSError('offline')
    with pytest.raises(ToolError):
        Weather(fetch=broken).forecast('جدة')


def test_fit_history_keeps_latest_turns_and_summarizes_older_requests():
    messages = [{'role': 'system', 'content': 'S'}]
    for i in range(60):
        messages += [{'role': 'user', 'content': 'طلب رقم ' + str(i) + ' ' + 'س' * 300}, {'role': 'assistant', 'content': 'ر' * 600}]
    messages.append({'role': 'user', 'content': 'السؤال الأخير'})
    fitted, dropped = fit_history(messages, 4096, 800)
    assert dropped > 0 and fitted[-1]['content'] == 'السؤال الأخير' and fitted[0]['role'] == 'system'
    assert 'ملخص طلبات المستخدم الأقدم' in fitted[0]['content']
    assert '(1) طلب رقم 0' in fitted[0]['content']          # the task-defining first request is never the one dropped
    assert fitted[1]['role'] == 'user'
    assert sum(len(m['content']) for m in fitted) < (4096 - 800) * 2.5
    short = [{'role': 'user', 'content': 'مرحبا'}]
    assert fit_history(short, 4096, 800) == (short, 0)


def test_dispatcher_handles_assistant_requests_without_model(system):
    app, desktop, dispatch = application(system)
    result = dispatch.dispatch('تذكّر أن اسمي أحمد', request_id(), session_id='s1')
    assert result['kind'] == 'assistant' and result['decision']['intent'] == 'assistant' and 'اسمي أحمد' in result['message']
    rid = request_id()
    created = dispatch.dispatch('ذكرني بعد 10 دقائق أن أشرب الماء', rid, session_id='s1')
    assert created['kind'] == 'assistant' and created['reminder']['text'] == 'أشرب الماء'
    assert dispatch.dispatch('ذكرني بعد 10 دقائق أن أشرب الماء', rid, session_id='s1') == created   # retry is not a duplicate
    assert len(app.state.assistant.store.reminders()) == 1
    assert 'أشرب الماء' in dispatch.dispatch('ما هي تذكيراتي', request_id(), session_id='s1')['message']
    assert dispatch.dispatch('احسب 6 × 7', request_id())['message'] == 'الناتج: 42'
    assert 'الساعة الآن' in dispatch.dispatch('كم الساعة؟', request_id())['message']
    assert not system.backend.calls and not system.backend.loads and not desktop.calls
    app.state.project_store.close()


def test_forget_all_requires_explicit_choice(system):
    app, desktop, dispatch = application(system)
    store = app.state.assistant.store
    store.remember('اسمي أحمد'); store.remember('أحب الشاي')
    rid = request_id()
    result = dispatch.dispatch('امسح ذاكرتك كلها', rid, session_id='s1')
    assert result['kind'] == 'clarification' and len(store.memories()) == 2
    chosen = dispatch.choose(rid, result['choices'][0]['id'], 's1')
    assert chosen['kind'] == 'assistant' and store.memories() == []
    app.state.project_store.close()


def test_api_management_requires_token_and_injects_memory(system):
    app, desktop, dispatch = application(system)
    headers = {'X-Neura-Token': 'test-token'}
    with TestClient(app, base_url='http://127.0.0.1') as client:
        assert client.get('/assistant/memories').status_code == 403
        saved = client.post('/assistant/memories', json={'text': 'أعيش في جدة'}, headers=headers).json()
        assert client.get('/assistant/memories', headers=headers).json()['memories'][0]['id'] == saved['id']
        assert client.put('/assistant/preferences', json={'city': 'جدة'}, headers=headers).json()['city'] == 'جدة'
        assert client.put('/assistant/preferences', json={'timezone': 'Mars/Base'}, headers=headers).status_code == 400
        due = time.time() + 3600
        reminder = client.post('/assistant/reminders', json={'text': 'اجتماع', 'due': due}, headers=headers).json()
        assert client.post('/assistant/reminders', json={'text': 'قديم', 'due': time.time() - 5}, headers=headers).status_code == 400
        assert client.delete('/assistant/reminders/' + reminder['id'], headers=headers).json()['state'] == 'cancelled'
        reply = client.post('/v1/chat/completions', json={'messages': [{'role': 'user', 'content': 'ما اسم مدينتي؟'}]}, headers=headers)
        assert reply.status_code == 200
        system_prompt = system.backend.calls[-1]['messages'][0]['content']
        assert 'أعيش في جدة' in system_prompt and 'Asia/Riyadh' in system_prompt
        assert client.delete('/assistant/memories/' + saved['id'], headers=headers).status_code == 200
        assert client.delete('/assistant/memories/' + saved['id'], headers=headers).status_code == 404
    app.state.project_store.close()


def test_assistant_page_assets_are_served_and_stale_ui_text_is_gone(system):
    app, desktop, dispatch = application(system)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        page = client.get('/').text
        assert 'id="tab-assistant"' in page and 'id="pg-assistant"' in page and '/assets/assistant.js' in page
        assert 'جامعتي' not in page and '/run</span>' not in page
        script = client.get('/assets/assistant.js')
        assert script.status_code == 200 and script.headers['content-type'].startswith('text/javascript')
        assert client.get('/assets/assistant.css').headers['content-type'].startswith('text/css')
        assert client.get('/assets/other.js').status_code == 404
    app.state.project_store.close()
