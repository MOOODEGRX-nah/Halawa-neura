"""Conservative catalog matching and short-lived, user-only target references.

Aliases identify installed desktop entries; they never describe commands. Context
stores only catalog IDs mentioned by the user, never model/retrieved prose.
"""
import json
import re
import time
import unicodedata
from src.core.project_files import ProjectError

TARGET_TTL = 300
MAX_SESSIONS = 128
SESSION = re.compile(r'^[A-Za-z0-9_-]{1,80}$')
DESKTOP_ID = re.compile(r'^[A-Za-z0-9_.-]+\.desktop$')


def normalize(text):
    text = unicodedata.normalize('NFKC', text).casefold()
    text = re.sub(r'[\u064b-\u065f\u0670\u0640]', '', text)
    return re.sub(r'\s+', ' ', text.translate(str.maketrans('أإآٱ', 'اااا'))).strip(' \t\r\n؟?!.،,')


def key(text):
    return ' '.join(word[2:] if word.startswith('ال') and len(word)>3 else word
                    for word in normalize(text).replace('_', ' ').replace('-', ' ').split())


ALIASES = {
    'discord': {'aliases': ('discord', 'ديسكورد', 'دسكورد'),
                'ids': ('discord.desktop', 'com.discordapp.Discord.desktop'), 'name': 'Discord'},
    'brave': {'aliases': ('brave', 'بريف', 'برايف', 'براڤ'),
              'ids': ('brave-browser.desktop', 'brave.desktop', 'com.brave.Browser.desktop'), 'name': 'Brave'},
    'kate': {'aliases': ('kate', 'كيت'), 'ids': ('org.kde.kate.desktop',), 'name': 'Kate'},
    'dolphin': {'aliases': ('dolphin', 'دولفين', 'مدير الملفات'), 'ids': ('org.kde.dolphin.desktop',), 'name': 'Dolphin'},
    'kcalc': {'aliases': ('kcalc', 'الحاسبة', 'الالة الحاسبة'), 'ids': ('org.kde.kcalc.desktop',), 'name': 'KCalc'},
}


def catalog_apps(apps):
    return [app for app in apps if isinstance(app, dict) and isinstance(app.get('id'), str)
            and DESKTOP_ID.fullmatch(app['id']) and isinstance(app.get('name'), str)]


def names(app):
    extra = app.get('names', [])
    return [app['name']] + ([value for value in extra if isinstance(value, str)][:24] if isinstance(extra, list) else [])


def alias_for(target):
    target = key(target)
    return next((value for value in ALIASES.values() if target in {key(a) for a in value['aliases']}), None)


def resolve_application(target, apps, configuration=None):
    """Prefer exact names/curated IDs, then whole phrases; no fuzzy guessing."""
    apps = catalog_apps(apps)
    target_key = key(target)
    if not target_key:
        return []
    alias = alias_for(target)
    if alias:
        ids = list(alias['ids'])
        if alias['name']=='Brave':
            configured = (configuration or {}).get('brave_desktop_id')
            if configured:
                ids = [configured]  # Honor the reviewed browser selected in Settings.
        matches = [app for app in apps if app['id'] in ids]
        if matches:
            return matches
        target_key = key(alias['name'])
    exact = [app for app in apps if target_key in {key(n) for n in names(app)}
             or target_key == key(app['id'].removesuffix('.desktop'))]
    if exact:
        return exact
    return [app for app in apps if any(' '+target_key+' ' in ' '+key(n)+' ' for n in names(app))]


def mentioned_aliases(text):
    question=normalize(text)
    return [alias for alias in ALIASES.values() if any(
        re.search(r'(?<!\w)(?:ال)?'+re.escape(normalize(name))+r'(?!\w)',question)
        for name in alias['aliases'])]


def mentioned_applications(text, apps, configuration=None):
    """Only call for an unquoted user knowledge question, not generated output."""
    question = normalize(text)
    targets = []
    for alias in mentioned_aliases(text):
        targets.extend(resolve_application(alias['aliases'][0], apps, configuration))
    for app in catalog_apps(apps):
        if any(name and re.search(r'(?<!\w)'+re.escape(normalize(name))+r'(?!\w)',question) for name in names(app)):
            targets.append(app)
    return list({app['id']: app for app in targets}.values())


class TargetContext:
    def __init__(self, store, clock=time.time):
        self.store, self.clock = store, clock
        with store.lock:
            store.db.execute('CREATE TABLE IF NOT EXISTS chat_target_context(session_id TEXT PRIMARY KEY,targets TEXT,mentioned TEXT,updated REAL)')
            store.db.commit()

    @staticmethod
    def validate(session_id):
        if session_id is not None and (not isinstance(session_id, str) or not SESSION.fullmatch(session_id)):
            raise ProjectError('معرّف المحادثة غير صالح')

    def set(self, session_id, targets, mentioned=''):
        self.validate(session_id)
        if session_id is None:
            return
        targets = list(dict.fromkeys(app['id'] for app in catalog_apps(targets)))[:8]
        with self.store.lock:
            self.store.db.execute('DELETE FROM chat_target_context WHERE updated<?', (self.clock()-TARGET_TTL,))
            if not targets:
                self.store.db.execute('DELETE FROM chat_target_context WHERE session_id=?', (session_id,))
            else:
                self.store.db.execute('INSERT OR REPLACE INTO chat_target_context VALUES(?,?,?,?)',
                    (session_id, json.dumps(targets), mentioned[:160], self.clock()))
            self.store.db.execute('DELETE FROM chat_target_context WHERE session_id NOT IN(SELECT session_id FROM chat_target_context ORDER BY updated DESC LIMIT ?)', (MAX_SESSIONS,))
            self.store.db.commit()

    def get(self, session_id, apps):
        self.validate(session_id)
        if session_id is None:
            return []
        with self.store.lock:
            row = self.store.db.execute('SELECT * FROM chat_target_context WHERE session_id=?', (session_id,)).fetchone()
            if not row or not 0 <= self.clock()-row['updated'] <= TARGET_TTL:
                return []
            ids = json.loads(row['targets'])
        return [app for app in catalog_apps(apps) if app['id'] in ids]
