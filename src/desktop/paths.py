"""User-owned state is separate from immutable application files."""
import json
import os
import secrets
import re
from pathlib import Path
from src.runtime import ROOT, model_directory

VERSION = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()


def directory(variable, default, suffix='neura-ai'):
    return Path(os.environ.get(variable, default)).expanduser() / suffix


def config_directory():
    explicit = os.environ.get('NEURA_SETTINGS_DIR')
    return Path(explicit).expanduser() if explicit else directory('XDG_CONFIG_HOME', Path.home() / '.config')


def data_directory():
    explicit = os.environ.get('NEURA_DATA_DIR')
    return Path(explicit).expanduser() if explicit else directory('XDG_DATA_HOME', Path.home() / '.local/share')


def state_directory():
    explicit = os.environ.get('NEURA_STATE_DIR')
    return Path(explicit).expanduser() if explicit else directory('XDG_STATE_HOME', Path.home() / '.local/state')


def cache_directory():
    # The privileged installer independently resolves this location for PKEXEC_UID.
    return Path.home() / '.cache/neura-ai/updates'


def setup_preview_environment():
    """Portable review profile; never reuse production projects, tokens or grants."""
    original=config_directory()/'settings.json'
    config=directory('XDG_CONFIG_HOME',Path.home()/'.config',suffix='neura-ai-preview')
    data=directory('XDG_DATA_HOME',Path.home()/'.local/share',suffix='neura-ai-preview')
    state=directory('XDG_STATE_HOME',Path.home()/'.local/state',suffix='neura-ai-preview')
    os.environ.update(NEURA_SETTINGS_DIR=str(config),NEURA_DATA_DIR=str(data),NEURA_STATE_DIR=str(state),NEURA_PREVIEW='1')
    if not (config/'settings.json').exists():
        settings=DesktopSettings(config/'settings.json')
        try:
            saved=json.loads(original.read_text())
            for key in ('models_dir','dedicated_coder','n_ctx','n_gpu_layers','gpu_device'):
                if key in saved:settings.values[key]=saved[key]
            settings.validate()
        except (OSError,ValueError,TypeError):
            settings=DesktopSettings(config/'settings.json')
        settings.values['check_updates']=False
        settings.values['approved_locations']={}
        settings.save()


ROLE_NAMES = ('fast', 'daily', 'expert', 'vision', 'coder')


def validate_model_settings(values):
    """User model registry, role bindings and generation defaults (CFG01/03/05)."""
    custom = values['custom_models']
    if not isinstance(custom, dict) or len(custom) > 32:
        raise ValueError('قائمة النماذج المضافة غير صالحة')
    for model_id, model in custom.items():
        if not re.fullmatch(r'user-[a-z0-9-]{1,40}', str(model_id)) or not isinstance(model, dict) or set(model) != {'name', 'file'}:
            raise ValueError('نموذج مضاف غير صالح')
        if not isinstance(model['name'], str) or not 1 <= len(model['name']) <= 80 or any(ord(c) < 32 for c in model['name']):
            raise ValueError('اسم النموذج غير صالح')
        if not isinstance(model['file'], str) or not re.fullmatch(r'[^/\\\x00]{1,200}\.gguf', model['file'], re.I) or model['file'].startswith('.'):
            raise ValueError('ملف النموذج يجب أن يكون اسم ملف GGUF داخل مجلد النماذج')
    roles = values['model_roles']
    if not isinstance(roles, dict) or any(role not in ROLE_NAMES or not isinstance(model, str) or not re.fullmatch(r'[a-z0-9.-]{1,60}', model) for role, model in roles.items()):
        raise ValueError('إسناد أدوار النماذج غير صالح')
    generation = values['generation']
    if not isinstance(generation, dict) or set(generation) != {'temperature', 'top_p', 'max_tokens'}:
        raise ValueError('إعدادات التوليد غير صالحة')
    if type(generation['temperature']) not in (int, float) or not 0 <= generation['temperature'] <= 2:
        raise ValueError('العشوائية يجب أن تكون بين 0 و2')
    if type(generation['top_p']) not in (int, float) or not 0 < generation['top_p'] <= 1:
        raise ValueError('Top-P يجب أن يكون أكبر من 0 وحتى 1')
    if type(generation['max_tokens']) is not int or not 64 <= generation['max_tokens'] <= 4096:
        raise ValueError('طول الرد يجب أن يكون بين 64 و4096')


class DesktopSettings:
    def __init__(self, path=None):
        self.path = Path(path or config_directory() / 'settings.json')
        self.values = {'models_dir': str(model_directory()), 'check_updates': True,
                       'dedicated_coder': False, 'n_gpu_layers': -1, 'n_ctx': 4096,
                       'brave_desktop_id':'brave-browser.desktop', 'approved_locations':{}, 'gpu_device':'auto','disabled_skills':[],
                       'run_in_background': True, 'model_roles': {}, 'custom_models': {},
                       'generation': {'temperature': 0.7, 'top_p': 0.9, 'max_tokens': 800}}
        try:
            saved = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(saved, dict):
                raise ValueError('Settings must be an object')
            self.values.update({k:v for k,v in saved.items() if k in self.values})
        except FileNotFoundError:
            pass
        self.validate()

    def validate(self):
        disabled=self.values['disabled_skills']
        if not isinstance(disabled,list) or any(name not in ('prepare_static_cv','prepare_static_services','prepare_static_site','open_website','search_web','search_youtube','open_file','open_folder','open_application','list_recent_applications') for name in disabled):
            raise ValueError('قائمة المهارات المعطلة غير صالحة')
        if type(self.values['n_ctx']) is not int or not 512 <= self.values['n_ctx'] <= 32768:
            raise ValueError('Invalid context length')
        if type(self.values['n_gpu_layers']) is not int or self.values['n_gpu_layers'] not in (-1, 0):
            raise ValueError('Choose GPU or CPU mode')
        for name in ('check_updates', 'dedicated_coder', 'run_in_background'):
            if type(self.values[name]) is not bool:
                raise ValueError('Invalid settings flag')
        self.values['models_dir'] = str(Path(self.values['models_dir']).expanduser().resolve())
        if not isinstance(self.values['brave_desktop_id'],str) or not re.fullmatch(r'[A-Za-z0-9_.-]*brave[A-Za-z0-9_.-]*\.desktop',self.values['brave_desktop_id'],re.I):
            raise ValueError('اختر desktop entry صالحًا لتطبيق Brave')
        places=self.values['approved_locations']
        if not isinstance(self.values['gpu_device'],str) or len(self.values['gpu_device'])>200 or any(ord(c)<32 for c in self.values['gpu_device']):
            raise ValueError('اختيار GPU غير صالح')
        if not isinstance(places,dict) or len(places)>24:
            raise ValueError('عدد الأماكن المختارة يتجاوز الحد')
        for key,location in places.items():
            if not re.fullmatch(r'l_[a-f0-9]{32}',key) or not isinstance(location,dict) or set(location)!= {'path','kind'}:
                raise ValueError('مكان مختار غير صالح')
            if location['kind'] not in ('file','folder') or not isinstance(location['path'],str) or not Path(location['path']).is_absolute():
                raise ValueError('المكان المختار يجب أن يكون ملفًا أو مجلدًا بمسار مطلق')

        validate_model_settings(self.values)

    def save(self):
        self.validate()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.path.with_name('.settings-' + secrets.token_hex(8))
        try:
            with temporary.open('x', encoding='utf-8') as f:
                temporary.chmod(0o600)
                json.dump(self.values, f, ensure_ascii=False, indent=2)
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)
