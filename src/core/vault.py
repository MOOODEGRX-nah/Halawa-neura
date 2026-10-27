"""Local chat persistence. No model-generated memory is silently added to prompts."""
import json
import re
import sqlite3
import threading
from datetime import datetime, timezone


class ConversationVault:
    def __init__(self, data_dir):
        data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = data_dir / 'conversations.sqlite3'
        self._lock = threading.Lock()
        with self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, updated_at TEXT NOT NULL, messages TEXT NOT NULL)')
        self.path.chmod(0o600)

    def _connect(self):
        return sqlite3.connect(self.path, timeout=5)

    @staticmethod
    def _validate(session):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', session):
            raise ValueError('Invalid session ID')

    def save(self, session, messages):
        self._validate(session)
        encoded = json.dumps(messages, ensure_ascii=False)
        if len(encoded.encode()) > 4_000_000:
            raise ValueError('Vault session exceeds 4 MB')
        with self._lock, self._connect() as db:
            db.execute('INSERT INTO sessions VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at, messages=excluded.messages',
                       (session, datetime.now(timezone.utc).isoformat(), encoded))
        return {'status': 'saved', 'session': session, 'messages_count': len(messages)}

    def get(self, session):
        self._validate(session)
        with self._connect() as db:
            row = db.execute('SELECT updated_at, messages FROM sessions WHERE id=?', (session,)).fetchone()
        if not row:
            raise KeyError(session)
        return {'session': session, 'updated_at': row[0], 'messages': json.loads(row[1])}

    def list(self):
        with self._connect() as db:
            rows = db.execute('SELECT id, updated_at FROM sessions ORDER BY updated_at DESC').fetchall()
        return [{'session': row[0], 'updated_at': row[1]} for row in rows]

    def delete(self, session):
        self._validate(session)
        with self._lock, self._connect() as db:
            count = db.execute('DELETE FROM sessions WHERE id=?', (session,)).rowcount
        if not count:
            raise KeyError(session)
        return {'status': 'deleted', 'session': session}
