"""
Neura State - Import-Graph Leaf (T-0301)
Shared state singleton. Imports NOTHING from src/.
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
from threading import Lock
import json

@dataclass
class NeuraState:
    status: str = "loading"
    status_msg: str = "Loading..."
    current_model: str = ""
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)
    memory_context: str = ""
    active_skills: List[str] = field(default_factory=list)
    monitor_data: Dict[str, Any] = field(default_factory=lambda: {
        "cpu_percent": 0.0, "gpu_percent": 0.0,
        "ram_used_gb": 0.0, "vram_used_gb": 0.0,
        "tokens_per_sec": 0.0, "active_gpus": []
    })
    error_log: List[Dict[str, Any]] = field(default_factory=list)
    last_error: Optional[str] = None
    _lock: Lock = field(default_factory=Lock, repr=False)

    def update_status(self, status: str, msg: str = ""):
        with self._lock:
            self.status = status
            self.status_msg = msg or f"Status: {status}"

    def update_monitor(self, **kwargs):
        with self._lock:
            self.monitor_data.update(kwargs)

    def add_message(self, role: str, content: str):
        with self._lock:
            self.conversation_history.append({
                "role": role, "content": content,
                "timestamp": datetime.now().isoformat()
            })

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "status": self.status, "status_msg": self.status_msg,
                "current_model": self.current_model,
                "monitor_data": self.monitor_data,
                "last_error": self.last_error,
                "history_len": len(self.conversation_history)
            }

_neura_state_instance: Optional[NeuraState] = None

def get_state() -> NeuraState:
    global _neura_state_instance
    if _neura_state_instance is None:
        _neura_state_instance = NeuraState()
    return _neura_state_instance

if __name__ == "__main__":
    state = get_state()
    state.update_status("ready", "System Online - Dual GPU Active")
    state.update_monitor(active_gpus=["RX 9060 XT (Main)", "RX 580 (Draft/Services)"])
    state.add_message("user", "Hello Neura")
    print("="*50)
    print("T-0301 Success! State module initialized.")
    print("="*50)
    print(json.dumps(state.to_dict(), indent=2, ensure_ascii=False))
