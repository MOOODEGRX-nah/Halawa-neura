"""N103: protected local discovery of the running Neura engine for API clients (CLI, Telegram).

The desktop picks a free port each start, so clients never assume a fixed port. The desktop writes
``runtime-endpoint.json`` (0600, atomic) with the port, the engine instance id and its own pid; a
client accepts it only if the pid is alive and ``/health`` on that port answers with the same
instance id. A stale file (crash, reboot, another program on the port) is refused, never trusted.
The token stays in its own 0600 file and is never written to the endpoint record.
"""
import json
import os
import time
import urllib.request
from pathlib import Path

ENDPOINT = 'runtime-endpoint.json'


class DiscoveryError(RuntimeError):
    pass


def write_endpoint(data_dir, port, instance, pid=None):
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    record = {'port': int(port), 'instance_id': str(instance), 'pid': int(pid or os.getpid()), 'written': time.time()}
    temporary = data_dir / (ENDPOINT + '.tmp')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
        json.dump(record, handle)
    os.replace(temporary, data_dir / ENDPOINT)
    return record


def clear_endpoint(data_dir, instance):
    path = Path(data_dir) / ENDPOINT
    try:
        if json.loads(path.read_text(encoding='utf-8')).get('instance_id') == instance:
            path.unlink()
    except (OSError, ValueError):
        pass


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _health(url):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url + '/health', timeout=2) as response:
        return json.load(response)


def read_token(data_dir):
    token = os.environ.get('NEURA_TOKEN', '')
    if token:
        return token
    try:
        return (Path(data_dir) / '.api-token').read_text().strip()
    except OSError as exc:
        raise DiscoveryError('لم أجد رمز الدخول المحلي؛ شغّل Neura مرة واحدة على الأقل.') from exc


def discover(data_dir, *, health=_health, alive=_alive):
    """Return the verified base URL of the running engine, or raise DiscoveryError with a reason."""
    override = os.environ.get('NEURA_API_URL', '').rstrip('/')
    if override:
        if not override.startswith(('http://127.0.0.1:', 'http://localhost:')):
            raise DiscoveryError('NEURA_API_URL يجب أن يكون عنوانًا محليًا على 127.0.0.1.')
        return override
    path = Path(data_dir) / ENDPOINT
    try:
        if path.stat().st_mode & 0o077:
            raise DiscoveryError('ملف عنوان المحرك مكشوف لمستخدمين آخرين؛ لن أثق به.')
        record = json.loads(path.read_text(encoding='utf-8'))
        port, instance, pid = int(record['port']), str(record['instance_id']), int(record['pid'])
    except FileNotFoundError as exc:
        raise DiscoveryError('Neura غير مشغّل الآن؛ افتح التطبيق أولًا.') from exc
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise DiscoveryError('ملف عنوان المحرك تالف؛ أعد تشغيل Neura.') from exc
    if not 1024 <= port <= 65535:
        raise DiscoveryError('منفذ المحرك غير صالح؛ أعد تشغيل Neura.')
    if not alive(pid):
        raise DiscoveryError('عنوان المحرك قديم (التطبيق مغلق أو انهار)؛ افتح Neura من جديد.')
    url = 'http://127.0.0.1:' + str(port)
    try:
        payload = health(url)
    except Exception as exc:
        raise DiscoveryError('المحرك لا يستجيب على العنوان المسجل؛ ربما ما زال يبدأ أو توقف.') from exc
    if payload.get('instance_id') != instance:
        raise DiscoveryError('برنامج آخر يرد على المنفذ المسجل؛ رفضت الاتصال حمايةً لرمزك.')
    return url
