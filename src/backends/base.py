"""
Base interface for all inference backends in Neura.
This ensures we can swap between llama-cpp-python, llama-server, or others
without changing the core application logic.
"""
from typing import Protocol, Dict, Any, Optional

class InferenceBackend(Protocol):
    def load(self, model_path: str, **kwargs) -> None:
        """Load a model into memory/VRAM."""
        ...

    def generate(self, prompt=None, *, messages=None, stream=False, **kwargs):
        """Generate chat completion or native token chunks using structured messages."""
        ...

    def health_check(self) -> Dict[str, Any]:
        """Return the current status of the backend."""
        ...

    def unload(self) -> None:
        """Free up memory/VRAM by unloading the model."""
        ...
