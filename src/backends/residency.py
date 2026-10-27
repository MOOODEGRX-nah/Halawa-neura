"""Model availability and explicitly estimated GPU memory budgets."""
from pathlib import Path
import os
import yaml
from src.runtime import Settings


def gpu_memory():
    """Read AMD sysfs counters. Missing counters remain unknown."""
    configured = os.environ.get('NEURA_GPU_SYSFS')
    devices = [Path(configured)] if configured else list(Path('/sys/class/drm').glob('card[0-9]*/device'))
    readings = []
    for p in devices:
        try:
            total = int((p / 'mem_info_vram_total').read_text())
            used = int((p / 'mem_info_vram_used').read_text())
            readings.append({'device': str(p), 'total_gb': total / 1e9,
                             'used_gb': used / 1e9, 'free_gb': (total - used) / 1e9})
        except (OSError, ValueError):
            continue
    return max(readings, key=lambda r: r['total_gb']) if readings else None


class ResidencyManager:
    def __init__(self, config_dir=None, total_vram_gb=16.0, models_dir=None):
        settings = Settings()
        self.models_dir = Path(models_dir or settings.models_dir).resolve()
        config_dir = Path(config_dir or settings.config_dir)
        self.total_vram_gb = total_vram_gb
        self.tiers_config = self._load_yaml(config_dir / 'tiers.yaml')
        self.models_config = self._load_yaml(config_dir / 'models.yaml')
        if not isinstance(self.models_config.get('models'), dict):
            raise ValueError('models.yaml must contain a model-ID dictionary')
        self.current_model_id = None

    @staticmethod
    def _load_yaml(path):
        with path.open(encoding='utf-8') as f:
            return yaml.safe_load(f) or {}

    @property
    def tiers(self):
        return {**self.tiers_config.get('tiers', {}), **self.tiers_config.get('hidden_tiers', {})}

    def get_model_info(self, model_id):
        return self.models_config['models'].get(model_id)

    def model_path(self, model_id):
        model = self.get_model_info(model_id)
        if not model:
            raise ValueError(f'Unknown model: {model_id}')
        path = (self.models_dir / model['file']).resolve()
        if not path.is_relative_to(self.models_dir):
            raise ValueError('Model path escapes NEURA_MODELS_DIR')
        return path

    def availability(self, model_id):
        model = self.get_model_info(model_id)
        if not model or not model.get('enabled', False):
            return False, (model or {}).get('disabled_reason', 'Model disabled or unknown')
        p = self.model_path(model_id)
        if not p.is_file():
            return False, f'Missing model file: {p.name}'
        if Path(str(p) + '.aria2').exists():
            return False, f'Incomplete download marker exists: {p.name}.aria2'
        if model.get('size_bytes') and p.stat().st_size != model['size_bytes']:
            return False, f'Unexpected file size: {p.name}'
        try:
            with p.open('rb') as f:
                if f.read(4) != b'GGUF':
                    return False, 'Invalid GGUF header'
        except OSError:
            return False, 'Cannot read model file'
        if model.get('projector'):
            projector = (self.models_dir / model['projector']).resolve()
            if not projector.is_relative_to(self.models_dir) or not projector.is_file():
                return False, 'Vision projector missing'
            if Path(str(projector) + '.aria2').exists():
                return False, 'Vision projector download incomplete'
        return True, 'File available; inference quality is tested separately'

    def estimate_vram_usage_gb(self, model_id, context_length=4096):
        model = self.get_model_info(model_id)
        if not model:
            raise ValueError(f'Unknown model: {model_id}')
        return float(model.get('size_gb', 0)) + context_length / 1024 * 0.5 + 1.0

    def can_load(self, model_id, context_length=4096, tier=None):
        available, reason = self.availability(model_id)
        if not available:
            return False, reason
        policy = self.tiers.get(tier, {}).get('residency')
        reason = 'Coordinator must unload current model first. ' if policy == 'alone' and self.current_model_id not in (None, model_id) else ''
        measured = gpu_memory()
        budget = measured['free_gb'] if measured and self.current_model_id is None else self.total_vram_gb
        estimate = self.estimate_vram_usage_gb(model_id, context_length)
        if estimate > budget:
            return False, f'Estimated VRAM {estimate:.1f} GB exceeds budget {budget:.1f} GB'
        return True, reason + 'Load permitted by estimate (not an allocation guarantee)'

    def register_load(self, model_id):
        self.current_model_id = model_id

    def register_unload(self):
        self.current_model_id = None
