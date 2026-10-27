import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

def test_safety_gate_exists():
    from agent.safety import SafetyGate
    assert SafetyGate is not None
    assert hasattr(SafetyGate, '__init__')
