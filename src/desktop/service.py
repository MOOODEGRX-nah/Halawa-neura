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
from src.runtime import ROOT
from src.desktop.paths import data_directory, state_directory


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
        for name, value in [('models.yaml', models), ('tiers.yaml', tiers)]:
            (config / name).write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding='utf-8')
        vendor = ROOT.parent / 'vendor'
        paths = [str(ROOT)] + ([str(vendor)] if vendor.is_dir() else [])
        return {**os.environ, 'PYTHONPATH': os.pathsep.join(paths),
                'NEURA_DATA_DIR': str(data_directory()), 'NEURA_REGISTRY_DIR': str(config),
                'NEURA_MODELS_DIR': str(folder), 'NEURA_INSTANCE_ID': self.instance,
                'NEURA_N_CTX': str(self.settings.values['n_ctx']),
                'NEURA_N_GPU_LAYERS': str(self.settings.values['n_gpu_layers']),
                'NEURA_GPU_DEVICE': self.settings.values.get('gpu_device','auto')}

    def start(self):
        if self.process is not None and self.process.poll() is None:
            return
        if self.process is not None:
            self.stop()
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
