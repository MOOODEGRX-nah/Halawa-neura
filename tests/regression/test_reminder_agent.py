"""Reminders while Neura is closed: exactly-once delivery shared with the app; user units only."""
import time

from src.core.assistant_store import AssistantStore
from src.desktop import reminder_agent


class Recorder:
    def __init__(self):
        self.sent = []

    def notify(self, title, body):
        self.sent.append(body)
        return True


def test_agent_delivers_due_reminders_once_and_records_events(tmp_path):
    store = AssistantStore(tmp_path)
    now = time.time()
    store.add_reminder('اشرب الماء', now - 600, 'Asia/Riyadh')
    store.add_reminder('لاحقًا', now + 3600, 'Asia/Riyadh')
    store.db.close()
    recorder = Recorder()
    first = reminder_agent.run_once(tmp_path, notifier=recorder, running=lambda d: False)
    second = reminder_agent.run_once(tmp_path, notifier=recorder, running=lambda d: False)
    assert first['delivered'] == 1 and second['delivered'] == 0
    assert recorder.sent[0].startswith('اشرب الماء') and 'فات موعده' in recorder.sent[0]
    again = AssistantStore(tmp_path)
    assert [e['text'] for e in again.events()['events']] == ['اشرب الماء']


def test_agent_defers_to_the_running_app(tmp_path):
    store = AssistantStore(tmp_path)
    store.add_reminder('x', time.time() - 5, 'Asia/Riyadh')
    store.db.close()
    recorder = Recorder()
    assert reminder_agent.run_once(tmp_path, notifier=recorder, running=lambda d: True)['skipped'] == 'app_running'
    assert recorder.sent == []


def test_units_are_user_level_and_removable(tmp_path):
    calls = []
    def runner(argv, **kwargs):
        calls.append(argv)
        return type('R', (), {'returncode': 0, 'stderr': b''})()
    reminder_agent.install(runner=runner, directory=tmp_path)
    service = (tmp_path / reminder_agent.SERVICE).read_text()
    assert 'ExecStart=' in service and '-m src.desktop.reminder_agent' in service and 'User=' not in service
    assert all(argv[:2] == ['systemctl', '--user'] for argv in calls) and ['systemctl', '--user', 'enable', '--now', reminder_agent.TIMER] in calls
    assert reminder_agent.installed(tmp_path)
    reminder_agent.uninstall(runner=runner, directory=tmp_path)
    assert not reminder_agent.installed(tmp_path) and not (tmp_path / reminder_agent.SERVICE).exists()
