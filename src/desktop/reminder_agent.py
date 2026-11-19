"""Reminders while Neura is fully closed: an optional systemd *user* timer (no root, no model).

Every minute the timer runs ``python -m src.desktop.reminder_agent``. If the Neura engine is running
(verified through the protected endpoint record) the app's own scheduler owns delivery and the
agent does nothing. Otherwise due reminders are claimed atomically from the same store, so a
reminder is delivered exactly once whether the app or the agent sees it first; the claim also
records the event, so the reminder appears in Neura's chat the next time it opens.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

SERVICE = 'neura-reminders.service'
TIMER = 'neura-reminders.timer'


def units_directory():
    return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'systemd' / 'user'


def engine_running(data_dir):
    from src.core.discovery import DiscoveryError, discover
    try:
        discover(data_dir)
        return True
    except DiscoveryError:
        return False


def run_once(data_dir, notifier=None, clock=time.time, running=engine_running):
    if running(data_dir):
        return {'delivered': 0, 'skipped': 'app_running'}
    from src.core.assistant import Notifier
    from src.core.assistant_store import AssistantStore
    from src.core.assistant_tools import due_text
    store = AssistantStore(Path(data_dir))
    try:
        fired = store.claim_due(clock())
        prefs = store.preferences()
    finally:
        store.db.close()
    notifier = notifier or Notifier()
    for reminder in fired:
        if prefs['desktop_notifications']:
            late = '\n(فات موعده: ' + due_text(reminder['due'], reminder['timezone'], clock()) + ')' if reminder['late'] else ''
            notifier.notify('⏰ تذكير من Neura', reminder['text'] + late)
    return {'delivered': len(fired)}


def unit_files(python, root, vendor):
    paths = ':'.join(str(p) for p in (root, vendor) if p)
    service = ('[Unit]\nDescription=Neura AI reminders while the app is closed\n\n[Service]\nType=oneshot\n'
               'WorkingDirectory=' + str(root) + '\nEnvironment=PYTHONPATH=' + paths + '\n'
               'ExecStart=' + str(python) + ' -m src.desktop.reminder_agent\nNice=10\n')
    timer = ('[Unit]\nDescription=Check Neura AI reminders every minute\n\n[Timer]\nOnBootSec=1min\nOnUnitActiveSec=1min\n'
             'AccuracySec=10s\n\n[Install]\nWantedBy=timers.target\n')
    return {SERVICE: service, TIMER: timer}


def _systemctl(runner, *args):
    return runner(['systemctl', '--user', *args], check=False, timeout=20, capture_output=True)


def install(runner=subprocess.run, directory=None):
    from src.runtime import ROOT
    from src.desktop.service import backend_python
    vendor = ROOT.parent / 'vendor'
    directory = Path(directory or units_directory())
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in unit_files(backend_python(), ROOT, vendor if vendor.is_dir() else None).items():
        (directory / name).write_text(text, encoding='utf-8')
    _systemctl(runner, 'daemon-reload')
    result = _systemctl(runner, 'enable', '--now', TIMER)
    if getattr(result, 'returncode', 1) != 0:
        raise RuntimeError('تعذر تفعيل مؤقت التذكيرات (systemctl --user): ' + (getattr(result, 'stderr', b'') or b'').decode(errors='ignore')[:200])
    return True


def uninstall(runner=subprocess.run, directory=None):
    directory = Path(directory or units_directory())
    if (directory / TIMER).exists():
        _systemctl(runner, 'disable', '--now', TIMER)
    for name in (SERVICE, TIMER):
        try:
            (directory / name).unlink()
        except FileNotFoundError:
            pass
    _systemctl(runner, 'daemon-reload')
    return True


def installed(directory=None):
    return (Path(directory or units_directory()) / TIMER).is_file()


if __name__ == '__main__':
    from src.desktop.paths import data_directory
    result = run_once(data_directory())
    sys.exit(0)
