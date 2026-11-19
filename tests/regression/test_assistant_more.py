"""N082 video bookmarks, N039 lasting reply preferences, N047 multi-step requests."""
from datetime import datetime
from zoneinfo import ZoneInfo

from src.core.assistant import Assistant
from src.core.assistant_intents import parse
from tests.regression.test_chat_dispatch import application, request_id

NOW = datetime(2026, 11, 19, 14, 30, tzinfo=ZoneInfo('Asia/Riyadh'))


def test_video_bookmark_and_resume_opens_at_the_saved_position(system):
    app, desktop, dispatch = application(system)
    saved = dispatch.dispatch('احفظ الفيديو https://www.youtube.com/watch?v=abcdefghijk عند 12:30', request_id(), session_id='v')
    assert saved['kind'] == 'assistant' and 'عند 12:30' in saved['message']
    opened = dispatch.dispatch('أكمل الفيديو', request_id(), session_id='v')
    assert opened['result']['status'] == 'launched' and desktop.calls == [('browser', 'https://www.youtube.com/watch?v=abcdefghijk&t=750s')]
    assert 'abcdefghijk' in dispatch.dispatch('ما هي الفيديوهات المحفوظة', request_id(), session_id='v')['message']
    app.state.project_store.close()


def test_persona_is_saved_only_after_confirmation(system):
    app, desktop, dispatch = application(system)
    rid = request_id()
    offer = dispatch.dispatch('من الآن فصاعدًا رد باختصار وبالنقاط', rid, session_id='p')
    assert offer['kind'] == 'clarification' and app.state.assistant.store.preferences()['persona'] == ''
    dispatch.choose(rid, offer['choices'][0]['id'], 'p')
    assert 'رد باختصار' in app.state.assistant.store.preferences()['persona']
    assert parse('هل دائما ترد باختصار؟', NOW) is None
    app.state.project_store.close()


def test_chains_run_each_step_in_order_and_stop_on_failure(tmp_path):
    assistant = Assistant(tmp_path)
    steps = assistant.chain('ذكرني بعد ساعة أن أشرب الماء ثم احسب 6 × 7')
    assert [s.name for s in steps] == ['reminder.create', 'calc']
    result = assistant.run_chain(steps)
    assert '1) تمام، سأذكرك' in result['message'] and '2) الناتج: 42' in result['message']
    failed = assistant.run_chain(assistant.chain('ما الطقس في كاتماندو ثم كم الساعة'))  # offline in tests: the weather step fails
    assert 'توقفت هنا' in failed['message'] and 'الساعة الآن' not in failed['message']
    assert assistant.chain('اشرح البرمجة ثم احسب 2+2') is None          # a non-assistant step: ordinary chat
    assert assistant.chain('امسح ذاكرتك كلها ثم كم الساعة') is None     # destructive steps never chain


def test_chain_through_dispatcher_creates_one_reminder(system):
    app, desktop, dispatch = application(system)
    result = dispatch.dispatch('ذكرني بعد 10 دقائق أن أتصل بأمي ثم ما تاريخ اليوم', request_id(), session_id='c')
    assert result['kind'] == 'assistant' and len(app.state.assistant.store.reminders()) == 1 and 'هـ' in result['message']
    app.state.project_store.close()
