"""User-owned state is separate from immutable application files."""
import json
import os
import secrets
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


class DesktopSettings:
    def __init__(self, path=None):
        self.path = Path(path or config_directory() / 'settings.json')
        self.values = {'models_dir': str(model_directory()), 'check_updates': True,
                       'dedicated_coder': False, 'n_gpu_layers': -1, 'n_ctx': 4096}
        try:
            saved = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(saved, dict):
                raise ValueError('Settings must be an object')
            self.values.update({k:v for k,v in saved.items() if k in self.values})
        except FileNotFoundError:
            pass
        self.validate()

    def validate(self):
        if type(self.values['n_ctx']) is not int or not 512 <= self.values['n_ctx'] <= 32768:
            raise ValueError('Invalid context length')
        if type(self.values['n_gpu_layers']) is not int or self.values['n_gpu_layers'] not in (-1, 0):
            raise ValueError('Choose GPU or CPU mode')
        for name in ('check_updates', 'dedicated_coder'):
            if type(self.values[name]) is not bool:
                raise ValueError('Invalid settings flag')
        self.values['models_dir'] = str(Path(self.values['models_dir']).expanduser().resolve())

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
