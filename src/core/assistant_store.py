"""Durable personal state for the assistant: user-approved memories, reminders and preferences.

Only text the user explicitly asked to remember is stored as memory. Nothing written by the
model, a project, a web page or a preview can add, change or delete an entry: the only writers
are the authenticated user-message dispatcher and the authenticated management API.
"""
import json
import re
import sqlite3
import threading
import time
import uuid

MAX_MEMORIES = 200
MAX_MEMORY_CHARS = 500
MAX_REMINDERS = 500
MAX_REMINDER_CHARS = 300
DEFAULT_PREFERENCES = {'city': 'الرياض', 'timezone': 'Asia/Riyadh', 'desktop_notifications': True,
                       'speak_reminders': True, 'use_memory_in_chat': True, 'persona': ''}


class AssistantError(ValueError):
    status = 400


def _clean(text, limit):
    text = re.sub(r'\s+', ' ', str(text or '')).strip(' \t\r\n.،,؛;')
    if not text:
        raise AssistantError('النص فارغ')
    if len(text) > limit:
        raise AssistantError('النص أطول من ' + str(limit) + ' حرفًا')
    return text


class AssistantStore:
    def __init__(self, data_dir):
        data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = data_dir / 'assistant.sqlite3'
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY, text TEXT NOT NULL, normalized TEXT NOT NULL UNIQUE,'
                        ' created REAL NOT NULL, updated REAL NOT NULL, source TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS reminders(id TEXT PRIMARY KEY, text TEXT NOT NULL, due REAL NOT NULL, timezone TEXT NOT NULL,'
                        ' created REAL NOT NULL, state TEXT NOT NULL, fired REAL, late INTEGER NOT NULL DEFAULT 0, session_id TEXT, request_id TEXT UNIQUE)')
        self.db.execute('CREATE INDEX IF NOT EXISTS reminders_due ON reminders(state, due)')
        self.db.execute('CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, payload TEXT NOT NULL, created REAL NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS preferences(id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)')
        self.db.commit()
        self.path.chmod(0o600)

    def close(self):
        with self.lock:
            self.db.close()

    # Memories -----------------------------------------------------------------------------
    @staticmethod
    def _memory(row):
        return {'id': row['id'], 'text': row['text'], 'created': row['created'], 'updated': row['updated'], 'source': row['source']}

    def remember(self, text, source='user_explicit'):
        from src.core.application_targets import normalize
        text = _clean(text, MAX_MEMORY_CHARS)
        normalized = normalize(text)
        now = time.time()
        with self.lock:
            row = self.db.execute('SELECT * FROM memories WHERE normalized=?', (normalized,)).fetchone()
            if row:
                return {**self._memory(row), 'duplicate': True}
            if self.db.execute('SELECT COUNT(*) FROM memories').fetchone()[0] >= MAX_MEMORIES:
                raise AssistantError('الذاكرة ممتلئة (' + str(MAX_MEMORIES) + ' معلومة)؛ احذف معلومات قديمة أولًا.')
            memory_id = 'm_' + uuid.uuid4().hex
            self.db.execute('INSERT INTO memories VALUES(?,?,?,?,?,?)', (memory_id, text, normalized, now, now, source))
            self.db.commit()
        return {'id': memory_id, 'text': text, 'created': now, 'updated': now, 'source': source, 'duplicate': False}

    def memories(self):
        with self.lock:
            return [self._memory(r) for r in self.db.execute('SELECT * FROM memories ORDER BY created').fetchall()]

    def update_memory(self, memory_id, text):
        from src.core.application_targets import normalize
        text = _clean(text, MAX_MEMORY_CHARS)
        with self.lock:
            try:
                count = self.db.execute('UPDATE memories SET text=?, normalized=?, updated=? WHERE id=?',
                                        (text, normalize(text), time.time(), memory_id)).rowcount
            except sqlite3.IntegrityError as exc:
                raise AssistantError('توجد معلومة مطابقة بالفعل') from exc
            self.db.commit()
        if not count:
            raise KeyError(memory_id)
        return next(m for m in self.memories() if m['id'] == memory_id)

    def forget(self, memory_id):
        with self.lock:
            row = self.db.execute('SELECT * FROM memories WHERE id=?', (memory_id,)).fetchone()
            if not row:
                raise KeyError(memory_id)
            self.db.execute('DELETE FROM memories WHERE id=?', (memory_id,))
            self.db.commit()
        return self._memory(row)

    def forget_all(self):
        with self.lock:
            count = self.db.execute('DELETE FROM memories').rowcount
            self.db.commit()
        return count

    def export_memories(self):
        return {'format': 'neura-memories', 'version': 1, 'memories': [{'text': m['text'], 'created': m['created']} for m in self.memories()]}

    def import_memories(self, payload):
        if not isinstance(payload, dict) or payload.get('format') != 'neura-memories' or payload.get('version') != 1:
            raise AssistantError('ملف الذاكرة غير صالح')
        items = payload.get('memories')
        if not isinstance(items, list) or len(items) > MAX_MEMORIES:
            raise AssistantError('ملف الذاكرة غير صالح أو أكبر من الحد')
        texts = [_clean(item.get('text') if isinstance(item, dict) else None, MAX_MEMORY_CHARS) for item in items]
        added = sum(not self.remember(text, 'user_import')['duplicate'] for text in texts)
        return {'added': added, 'skipped': len(texts) - added}

    def profile(self, limit_chars=1500):
        """Newest user-approved facts first, bounded; returned oldest-first for a stable prompt."""
        chosen, used = [], 0
        for memory in reversed(self.memories()):
            if used + len(memory['text']) + 3 > limit_chars:
                break
            chosen.append(memory['text'])
            used += len(memory['text']) + 3
        return list(reversed(chosen))

    # Reminders ----------------------------------------------------------------------------
    @staticmethod
    def _reminder(row):
        return {'id': row['id'], 'text': row['text'], 'due': row['due'], 'timezone': row['timezone'], 'created': row['created'],
                'state': row['state'], 'fired': row['fired'], 'late': bool(row['late'])}

    def add_reminder(self, text, due, timezone, session_id=None, request_id=None):
        text = _clean(text, MAX_REMINDER_CHARS)
        with self.lock:
            if request_id:
                row = self.db.execute('SELECT * FROM reminders WHERE request_id=?', (request_id,)).fetchone()
                if row:
                    return self._reminder(row)
            if self.db.execute("SELECT COUNT(*) FROM reminders WHERE state='pending'").fetchone()[0] >= MAX_REMINDERS:
                raise AssistantError('عدد التذكيرات المعلقة وصل إلى الحد؛ احذف بعضها أولًا.')
            reminder_id = 'rm_' + uuid.uuid4().hex
            self.db.execute('INSERT INTO reminders VALUES(?,?,?,?,?,?,?,?,?,?)',
                            (reminder_id, text, float(due), timezone, time.time(), 'pending', None, 0, session_id, request_id))
            self.db.commit()
            return self._reminder(self.db.execute('SELECT * FROM reminders WHERE id=?', (reminder_id,)).fetchone())

    def reminders(self, states=('pending',)):
        marks = ','.join('?' * len(states))
        with self.lock:
            return [self._reminder(r) for r in self.db.execute('SELECT * FROM reminders WHERE state IN (' + marks + ') ORDER BY due', tuple(states)).fetchall()]

    def cancel_reminder(self, reminder_id):
        with self.lock:
            row = self.db.execute("SELECT * FROM reminders WHERE id=?", (reminder_id,)).fetchone()
            if not row:
                raise KeyError(reminder_id)
            if row['state'] == 'pending':
                self.db.execute("UPDATE reminders SET state='cancelled' WHERE id=?", (reminder_id,))
                self.db.commit()
            return {**self._reminder(row), 'state': 'cancelled' if row['state'] == 'pending' else row['state']}

    def claim_due(self, now=None, grace=120):
        """Atomically move every due pending reminder to fired and record one event per reminder."""
        now = time.time() if now is None else now
        fired = []
        with self.lock:
            rows = self.db.execute("SELECT * FROM reminders WHERE state='pending' AND due<=? ORDER BY due", (now,)).fetchall()
            for row in rows:
                late = now - row['due'] > grace
                self.db.execute("UPDATE reminders SET state='fired', fired=?, late=? WHERE id=? AND state='pending'", (now, int(late), row['id']))
                reminder = {**self._reminder(row), 'state': 'fired', 'fired': now, 'late': late}
                self.db.execute('INSERT INTO events(kind,payload,created) VALUES(?,?,?)', ('reminder', json.dumps(reminder, ensure_ascii=False), now))
                fired.append(reminder)
            self.db.execute('DELETE FROM events WHERE created<?', (now - 7 * 86400,))
            self.db.commit()
        return fired

    def events(self, after=0, limit=50):
        with self.lock:
            rows = self.db.execute('SELECT * FROM events WHERE seq>? ORDER BY seq LIMIT ?', (int(after), int(limit))).fetchall()
            last = self.db.execute('SELECT COALESCE(MAX(seq),0) FROM events').fetchone()[0]
        return {'events': [{'seq': r['seq'], 'kind': r['kind'], **json.loads(r['payload'])} for r in rows], 'last': last}

    # Preferences --------------------------------------------------------------------------
    def preferences(self, values=None):
        with self.lock:
            row = self.db.execute('SELECT value FROM preferences WHERE id=1').fetchone()
            current = {**DEFAULT_PREFERENCES, **(json.loads(row['value']) if row else {})}
            if values:
                unknown = set(values) - set(DEFAULT_PREFERENCES)
                if unknown:
                    raise AssistantError('إعداد غير معروف: ' + ', '.join(sorted(unknown)))
                for key, value in values.items():
                    if isinstance(DEFAULT_PREFERENCES[key], bool):
                        if not isinstance(value, bool):
                            raise AssistantError('قيمة غير صالحة للإعداد ' + key)
                    elif key == 'persona':
                        value = re.sub(r'[ \t]+', ' ', str(value or '')).strip()
                        if len(value) > 600:
                            raise AssistantError('تعليمات الأسلوب أطول من 600 حرف')
                    else:
                        value = _clean(value, 80)
                    current[key] = value
                if 'timezone' in values:
                    from zoneinfo import ZoneInfo
                    try:
                        ZoneInfo(current['timezone'])
                    except Exception as exc:
                        raise AssistantError('منطقة زمنية غير معروفة') from exc
                self.db.execute('INSERT OR REPLACE INTO preferences VALUES(1,?)', (json.dumps(current, ensure_ascii=False),))
                self.db.commit()
            return current
