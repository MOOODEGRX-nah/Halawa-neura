"""Own exactly one child backend; never kill unrelated listeners or processes."""
import importlib.util
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error
from src.runtime import ROOT
from src.desktop.paths import data_directory, state_directory


def apply_model_settings(models, tiers, folder, values):
    """Add the user's GGUF files to the runtime registry and apply role bindings.

    Files stay confined to the models folder (residency re-checks this). A role bound to a
    missing or disabled model keeps the binding so the UI reports the real reason instead of
    silently falling back to another model.
    """
    registry = models['models']
    for model_id, model in values.get('custom_models', {}).items():
        path = (folder / model['file'])
        size = path.stat().st_size if path.is_file() else 0
        registry[model_id] = {'name': model['name'], 'file': model['file'], 'size_gb': round(size / 1e9, 3), 'enabled': True,
                              'user_added': True, 'license_status': 'user supplied; check the publisher terms'}
    places = {**{k: tiers['tiers'] for k in tiers.get('tiers', {})}, **{k: tiers['hidden_tiers'] for k in tiers.get('hidden_tiers', {})}}
    for role, model_id in values.get('model_roles', {}).items():
        if role in places and model_id in registry:
            if role == 'vision' and not registry[model_id].get('projector'):
                continue
            places[role][role]['model_id'] = model_id
            if role == 'coder' and model_id == 'qwen2.5-coder-14b-q4':
                registry[model_id]['enabled'] = registry[model_id].get('enabled') or values.get('dedicated_coder', False)


def backend_python():
    if os.environ.get('NEURA_BACKEND_PYTHON'):
        return os.environ['NEURA_BACKEND_PYTHON']
    vendor = ROOT.parent / 'vendor'
    if vendor.is_dir() or importlib.util.find_spec('fastapi') is not None:
        return sys.executable
    # Source checkout convenience only; release packages contain their own backend.
    existing = Path.home() / 'Downloads/ai/neura-repo/.venv/bin/python'
    return str(existing) if existing.is_file() else sys.executable


class BackendService:
    def __init__(self, settings, *, popen=subprocess.Popen):
        self.settings = settings
        self.popen = popen
        self.process = None
        self.port = None
        self.instance = secrets.token_hex(16)
        self.log_path = state_directory() / 'backend.log'
        self._log = None
        self.update_reservation = None

    @property
    def url(self):
        return f'http://127.0.0.1:{self.port}'

    def environment(self):
        import yaml
        config = data_directory() / 'runtime-config'
        config.mkdir(parents=True, exist_ok=True, mode=0o700)
        models = yaml.safe_load((ROOT / 'configs/models.yaml').read_text())
        tiers = yaml.safe_load((ROOT / 'configs/tiers.yaml').read_text())
        folder = Path(self.settings.values['models_dir'])
        coder = models['models']['qwen2.5-coder-14b-q4']
        coder_path = folder / coder['file']
        if self.settings.values['dedicated_coder']:
            if not coder_path.is_file() or Path(str(coder_path) + '.aria2').exists():
                raise ValueError('ملف Qwen Coder غير موجود أو تنزيله غير مكتمل.')
            if coder.get('size_bytes') and coder_path.stat().st_size != coder['size_bytes']:
                raise ValueError('حجم ملف Qwen Coder غير مطابق للملف المسجل.')
            coder['enabled'] = True
            coder.pop('disabled_reason', None)
            tiers['hidden_tiers']['coder']['model_id'] = 'qwen2.5-coder-14b-q4'
        apply_model_settings(models, tiers, folder, self.settings.values)
        for name, value in [('models.yaml', models), ('tiers.yaml', tiers)]:
            (config / name).write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding='utf-8')
        vendor = ROOT.parent / 'vendor'
        paths = [str(ROOT)] + ([str(vendor)] if vendor.is_dir() else [])
        from src.core.resource_policy import read_config
        resource=read_config(data_directory(),{'mode':'auto'})
        import psutil
        owner={'pid':os.getpid(),'started':psutil.Process().create_time(),'webengine_executable':''}
        try:
            from PySide6.QtCore import QLibraryInfo
            owner['webengine_executable']=str(Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.LibraryExecutablesPath))/'QtWebEngineProcess')
        except ImportError:pass
        return {**os.environ,'NEURA_RESOURCE_PROTECTION':resource.model_dump_json(),'NEURA_DESKTOP_OWNER':json.dumps(owner), 'PYTHONPATH': os.pathsep.join(paths),
                'NEURA_DATA_DIR': str(data_directory()), 'NEURA_REGISTRY_DIR': str(config),
                'NEURA_MODELS_DIR': str(folder), 'NEURA_INSTANCE_ID': self.instance,
                'NEURA_N_CTX': str(self.settings.values['n_ctx']),
                'NEURA_N_GPU_LAYERS': str(self.settings.values['n_gpu_layers']),
                'NEURA_GPU_DEVICE': self.settings.values.get('gpu_device','auto'),
                'NEURA_GENERATION': json.dumps(self.settings.values['generation'])}

    def start(self):
        if self.process is not None and self.process.poll() is None:
            return
        if self.process is not None:
            self.stop()
        self.update_reservation=None
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(('127.0.0.1', 0))
            self.port = listener.getsockname()[1]
        self.log_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._log = self.log_path.open('a', encoding='utf-8')
        self.log_path.chmod(0o600)
        try:
            self.process = self.popen([backend_python(), '-m', 'src.desktop.server', '--port', str(self.port)],
                                      cwd=ROOT, env=self.environment(), stdout=self._log, stderr=self._log)
        except BaseException:
            self._log.close()
            self._log = None
            raise

    def health(self):
        if self.process is None or self.process.poll() is not None:
            return None
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(self.url + '/health', timeout=.3) as response:
                payload = json.load(response)
            return payload if payload.get('instance_id') == self.instance else None
        except (OSError, ValueError):
            return None

    def _update_request(self,action,reservation_id):
        if not self.health():raise RuntimeError('تعذر تأكيد هوية المحرك؛ أُجّل التحديث.')
        token=(data_directory()/'.api-token').read_text().strip()
        request=urllib.request.Request(self.url+'/lifecycle/update/'+action,
            data=json.dumps({'reservation_id':reservation_id,'instance_id':self.instance}).encode(),
            headers={'X-Neura-Token':token,'Content-Type':'application/json'})
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=5) as response:value=json.load(response)
        except urllib.error.HTTPError as exc:
            try:message=json.load(exc).get('error',{}).get('message') or 'أُجّل التحديث؛ راجع حالة المهام.'
            except (ValueError,OSError):message='أُجّل التحديث؛ تعذر تأكيد حالة المهام.'
            raise RuntimeError(message) from exc
        if action=='prepare' and value.get('instance_id')!=self.instance:raise RuntimeError('تغيرت هوية المحرك؛ لم يُوقف شيء.')
        return value

    def prepare_update(self):
        if not self.update_reservation:self.update_reservation='u_'+secrets.token_hex(16)
        return self._update_request('prepare',self.update_reservation)

    def release_update(self):
        reservation=self.update_reservation
        if not reservation:return
        if self.process is None:self.update_reservation=None;return
        self._update_request('release',reservation)
        if self.update_reservation==reservation:self.update_reservation=None

    def stop(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=3)
            self.process = None
        if self._log:
            self._log.close()
            self._log = None
        self.update_reservation=None
