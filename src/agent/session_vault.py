"""Explicit browser-session storage with confined names and domain boundaries."""
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from src.runtime import Settings


class SessionVault:
    def __init__(self, sessions_dir=None):
        self.sessions_dir = Path(sessions_dir or Settings().data_dir / 'browser_sessions').resolve()

    def _path(self, name):
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', name):
            raise ValueError('Invalid session name')
        path = (self.sessions_dir / (name + '.json')).resolve()
        if not path.is_relative_to(self.sessions_dir):
            raise ValueError('Session path escapes vault')
        return path

    def _load(self, name):
        try:
            return json.loads(self._path(name).read_text(encoding='utf-8'))
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def get_state(self, name):
        data = self._load(name)
        return data.get('state', data) if data else None

    def get_state_for_domain(self, domain):
        domain = (domain or '').lower().rstrip('.')
        if not domain or not self.sessions_dir.exists():
            return None, None
        for file in self.sessions_dir.glob('*.json'):
            data = self._load(file.stem) or {}
            saved = (data.get('domain') or '').lower().lstrip('.').rstrip('.')
            if saved and (domain == saved or domain.endswith('.' + saved)):
                return file.stem, data.get('state')
        return None, None

    def save_persistent(self, name, storage_state, domain=None):
        path = self._path(name)
        self.sessions_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        wrapper = {'domain': domain or '', 'saved_at': datetime.now(timezone.utc).isoformat(), 'state': storage_state}
        fd, temporary = tempfile.mkstemp(dir=self.sessions_dir, prefix='.session-')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(wrapper, stream, ensure_ascii=False)
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return str(path)

    def delete_persistent(self, name):
        path = self._path(name)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_persistent(self):
        if not self.sessions_dir.exists():
            return []
        return [{'name': p.stem, 'domain': (data := self._load(p.stem) or {}).get('domain', ''),
                 'modified': data.get('saved_at')} for p in self.sessions_dir.glob('*.json')]
