"""
Neura SessionVault v2
جلسات دائمة + ربط تلقائي بالنطاق. لا كلمات مرور أبداً.
"""
import sys
import os
import json
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SESSIONS_DIR = 'data/sessions'
os.makedirs(SESSIONS_DIR, exist_ok=True)


class SessionVault:
    def __init__(self):
        self.sessions_dir = SESSIONS_DIR

    def _path(self, name):
        return os.path.join(self.sessions_dir, f'{name}.json')

    def _load(self, name):
        try:
            with open(self._path(name), 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    def get_state(self, name):
        """يرجع حالة الجلسة بالاسم (يدعم الصيغة القديمة والجديدة)."""
        data = self._load(name)
        if not data:
            return None
        return data.get('state', data)

    def get_state_for_domain(self, domain):
        """بحث تلقائي: هل توجد جلسة محفوظة لهذا النطاق؟"""
        domain = (domain or '').lower()
        if not domain:
            return None, None
        for f in os.listdir(self.sessions_dir):
            if not f.endswith('.json'):
                continue
            name = f[:-5]
            data = self._load(name)
            if not data or 'state' not in data:
                continue
            d = (data.get('domain') or '').lower()
            if d and (domain == d or domain.endswith(d) or d.endswith(domain)):
                return name, data['state']
        return None, None

    def save_persistent(self, name, storage_state, domain=None):
        wrapper = {
            'domain': domain or '',
            'saved_at': datetime.now().isoformat(),
            'state': storage_state,
        }
        with open(self._path(name), 'w', encoding='utf-8') as fh:
            json.dump(wrapper, fh, ensure_ascii=False)
        print(f'💾 Session محفوظة: {name} (نطاق: {domain})')
        return self._path(name)

    def delete_persistent(self, name):
        if os.path.exists(self._path(name)):
            os.remove(self._path(name))
            return True
        return False

    def list_persistent(self):
        out = []
        for f in os.listdir(self.sessions_dir):
            if f.endswith('.json'):
                name = f[:-5]
                data = self._load(name) or {}
                out.append({
                    'name': name,
                    'domain': data.get('domain', '(قديم - أعد الدخول)'),
                    'modified': data.get('saved_at', '?'),
                })
        return out


if __name__ == '__main__':
    v = SessionVault()
    print('الجلسات:')
    for s in v.list_persistent():
        print(f'  • {s["name"]} | {s["domain"]} | {s["modified"]}')
