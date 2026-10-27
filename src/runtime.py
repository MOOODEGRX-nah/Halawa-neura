"""Paths and resource limits shared by every active entry point."""
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def data_directory():
    return Path(os.environ.get('NEURA_DATA_DIR', Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'neura-ai')).expanduser().resolve()


def model_directory() -> Path:
    configured = os.environ.get("NEURA_MODELS_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    candidates = [data_directory() / "models", ROOT.parent / "neura AI/Neura_Package/models",
                  Path.home() / "Downloads/ai/neura AI/Neura_Package/models"]
    return next((p for p in candidates if p.is_dir()), candidates[0]).resolve()

@dataclass
class Settings:
    config_dir: Path = field(default_factory=lambda: Path(os.environ.get("NEURA_REGISTRY_DIR", ROOT / "configs")))
    models_dir: Path = field(default_factory=model_directory)
    data_dir: Path = field(default_factory=lambda: data_directory())
    n_ctx: int = field(default_factory=lambda: int(os.environ.get("NEURA_N_CTX", "4096")))
    n_gpu_layers: int = field(default_factory=lambda: int(os.environ.get("NEURA_N_GPU_LAYERS", "-1")))
    n_threads: int = field(default_factory=lambda: int(os.environ.get("NEURA_N_THREADS", str(min(os.cpu_count() or 4, 8)))))
    timeout_s: float = field(default_factory=lambda: float(os.environ.get("NEURA_TIMEOUT_S", "180")))
    token: str = field(default_factory=lambda: os.environ.get("NEURA_TOKEN", ""))

    def __post_init__(self):
        self.config_dir = Path(self.config_dir).resolve()
        self.models_dir = Path(self.models_dir).resolve()
        self.data_dir = Path(self.data_dir).resolve()
        if not 512 <= self.n_ctx <= 32768:
            raise ValueError("NEURA_N_CTX must be between 512 and 32768")
        if self.timeout_s <= 0 or self.n_threads < 1:
            raise ValueError("Invalid timeout or thread count")
