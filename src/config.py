"""
إدارة الإعدادات والمسارات
"""
import json
import sys
from pathlib import Path

APP_NAME = "Neura"
APP_VERSION = "0.2.2"


def get_base_path() -> Path:
    """مسار المجلد الرئيسي (يعمل مع EXE ومع الكود المصدري)"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


DEFAULT_CONFIG = {
    "language": "ar-SA",
    "gaming_mode": False,
    "voice_enabled": True,
    "vision_enabled": False,
    "models": {
        "chat": "Qwen2.5-7B-Instruct-Q4_K_M.gguf",
        "vision": "llava-v1.5-7b-q4_k.gguf",
        "vision_mmproj": "mmproj-model-f16.gguf"
    },
    "resources": {
        "normal": {"n_threads": 6, "n_gpu_layers": 33, "n_ctx": 4096},
        "gaming": {"n_threads": 2, "n_gpu_layers": 20, "n_ctx": 2048}
    },
    "github": {"enabled": False, "repo": ""},
    "trusted_channels": {
        "mrbeast": "https://www.youtube.com/@MrBeast",
        "nasa": "https://www.youtube.com/@NASA",
        "national geographic": "https://www.youtube.com/@NatGeo"
    }
}


class Config:
    def __init__(self, base_path=None):
        self.base_path = Path(base_path) if base_path else get_base_path()
        self.data_dir = self.base_path / "data"
        self.models_dir = self.base_path / "models"
        self.logs_dir = self.base_path / "logs"
        for d in (self.data_dir, self.models_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "config.json"
        self.data = {}
        self.load()

    def load(self):
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self.data = {}
        self.data = self._merge(DEFAULT_CONFIG, self.data)
        self.save()

    def _merge(self, default, user):
        result = dict(default)
        for k, v in user.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = self._merge(result[k], v)
            else:
                result[k] = v
        return result

    def save(self):
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self, key, default=None):
        val = self.data
        for k in key.split("."):
            if isinstance(val, dict) and k in val:
                val = val[k]
            else:
                return default
        return val

    def set(self, key, value):
        keys = key.split(".")
        d = self.data
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        d[keys[-1]] = value
        self.save()

    def resources(self):
        mode = "gaming" if self.data.get("gaming_mode") else "normal"
        return self.data["resources"][mode]

    def list_available_models(self):
        """يمسح مجلد models ويعيد كل ملفات .gguf المتاحة مع أحجامها"""
        result = {"chat": [], "vision": [], "vision_mmproj": []}
        if not self.models_dir.exists():
            return result
        for f in self.models_dir.iterdir():
            if f.suffix.lower() == ".gguf" and f.stat().st_size > 1_000_000:
                mb = f.stat().st_size // 1_000_000
                name = f.name
                low = name.lower()
                if "mmproj" in low:
                    result["vision_mmproj"].append((name, mb))
                elif any(k in low for k in ("llava", "vision", "moondream")):
                    result["vision"].append((name, mb))
                else:
                    result["chat"].append((name, mb))
        return result
