from pathlib import Path
from unittest.mock import patch
import pytest

MID='qwen3.5-9b-q4'

def test_availability_and_registration(system):
    manager=system.residency
    assert manager.availability(MID)[0]
    manager.register_load(MID);assert manager.current_model_id==MID
    manager.register_unload();assert manager.current_model_id is None


def test_download_marker_blocks_preallocated_file(system):
    path=system.residency.model_path(MID)
    Path(str(path)+'.aria2').write_bytes(b'incomplete')
    assert not system.residency.availability(MID)[0]


def test_size_and_missing_file(system):
    path=system.residency.model_path(MID)
    path.write_bytes(b'GGUFbad')
    assert 'size' in system.residency.availability(MID)[1]
    path.unlink()
    assert 'Missing' in system.residency.availability(MID)[1]


def test_registry_path_escape(system):
    system.residency.get_model_info(MID)['file']='../escape.gguf'
    with pytest.raises(ValueError,match='escapes'):
        system.residency.model_path(MID)


def test_budget_uses_measured_free_memory(system):
    with patch('src.backends.residency.gpu_memory',return_value={'free_gb':1}):
        allowed,reason=system.residency.can_load(MID)
    assert not allowed and 'Estimated' in reason


def test_shared_model_policy_is_requested_tier(system):
    manager=system.residency
    manager.register_load('gemma-4-e4b-q4')
    assert 'unload' in manager.can_load('qwen3.5-9b-claude-distilled-q4',tier='expert')[1]
    assert 'unload' not in manager.can_load('qwen3.5-9b-claude-distilled-q4',tier='coder')[1]


def test_missing_projector(system):
    info=system.residency.get_model_info('qwen3-vl-8b-q4')
    (system.models_dir/info['projector']).unlink()
    assert not system.residency.availability('qwen3-vl-8b-q4')[0]
