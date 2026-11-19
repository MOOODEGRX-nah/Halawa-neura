"""P02: user model registry, role bindings, generation defaults and assistant persona."""
import json

import pytest
import yaml
from fastapi.testclient import TestClient

from src.desktop.paths import DesktopSettings
from src.desktop.service import apply_model_settings
from src.runtime import ROOT
from tests.regression.test_chat_dispatch import application


def base():
    return (yaml.safe_load((ROOT / 'configs/models.yaml').read_text()), yaml.safe_load((ROOT / 'configs/tiers.yaml').read_text()))


def test_custom_models_and_roles_are_applied_to_the_runtime_registry(tmp_path):
    (tmp_path / 'mine.gguf').write_bytes(b'GGUF' + b'\0' * 100)
    models, tiers = base()
    values = {'custom_models': {'user-mine-abc123': {'name': 'نموذجي', 'file': 'mine.gguf'}},
              'model_roles': {'daily': 'user-mine-abc123', 'vision': 'qwen3.5-9b-q4', 'expert': 'not-registered'}}
    apply_model_settings(models, tiers, tmp_path, values)
    assert models['models']['user-mine-abc123']['enabled'] and models['models']['user-mine-abc123']['file'] == 'mine.gguf'
    assert tiers['tiers']['daily']['model_id'] == 'user-mine-abc123'
    assert tiers['tiers']['vision']['model_id'] == 'qwen3-vl-8b-q4'        # a text model cannot take the image role
    assert tiers['tiers']['expert']['model_id'] == 'qwen3.5-9b-claude-distilled-q4'


@pytest.mark.parametrize('values', [
    {'custom_models': {'user-x': {'name': 'x', 'file': '../escape.gguf'}}},
    {'custom_models': {'user-x': {'name': 'x', 'file': '/abs/model.gguf'}}},
    {'custom_models': {'evil': {'name': 'x', 'file': 'a.gguf'}}},
    {'custom_models': {'user-x': {'name': 'x', 'file': 'a.bin'}}},
    {'model_roles': {'admin': 'qwen3.5-9b-q4'}},
    {'generation': {'temperature': 3, 'top_p': .9, 'max_tokens': 800}},
    {'generation': {'temperature': .7, 'top_p': 0, 'max_tokens': 800}},
    {'generation': {'temperature': .7, 'top_p': .9, 'max_tokens': 99999}},
])
def test_invalid_model_settings_are_rejected(tmp_path, values):
    path = tmp_path / 'settings.json'
    path.write_text(json.dumps(values))
    with pytest.raises(ValueError):
        DesktopSettings(path)


def test_valid_model_settings_round_trip(tmp_path):
    path = tmp_path / 'settings.json'
    settings = DesktopSettings(path)
    settings.values.update(custom_models={'user-mine-1': {'name': 'نموذجي', 'file': 'mine.gguf'}}, model_roles={'coder': 'user-mine-1'},
                           generation={'temperature': 0.2, 'top_p': 0.8, 'max_tokens': 1200})
    settings.save()
    again = DesktopSettings(path)
    assert again.values['model_roles'] == {'coder': 'user-mine-1'} and again.values['generation']['max_tokens'] == 1200


def test_generation_defaults_apply_only_when_the_request_does_not_choose(system, monkeypatch):
    monkeypatch.setenv('NEURA_GENERATION', json.dumps({'temperature': 0.1, 'top_p': 0.5, 'max_tokens': 300}))
    app, desktop, dispatch = application(system)
    headers = {'X-Neura-Token': 'test-token'}
    with TestClient(app, base_url='http://127.0.0.1') as client:
        client.post('/v1/chat/completions', json={'messages': [{'role': 'user', 'content': 'مرحبا'}]}, headers=headers)
        first = system.backend.calls[-1]
        assert first['temperature'] == 0.1 and first['top_p'] == 0.5 and first['max_tokens'] == 300
        client.post('/v1/chat/completions', json={'messages': [{'role': 'user', 'content': 'مرحبا'}], 'temperature': 0.9}, headers=headers)
        assert system.backend.calls[-1]['temperature'] == 0.9 and system.backend.calls[-1]['top_p'] == 0.5
    app.state.project_store.close()


def test_persona_reaches_the_model_and_is_bounded(system):
    app, desktop, dispatch = application(system)
    headers = {'X-Neura-Token': 'test-token'}
    with TestClient(app, base_url='http://127.0.0.1') as client:
        assert client.put('/assistant/preferences', json={'persona': 'رد باختصار وبلهجة سعودية'}, headers=headers).status_code == 200
        assert client.put('/assistant/preferences', json={'persona': 'x' * 700}, headers=headers).status_code == 422
        client.post('/v1/chat/completions', json={'messages': [{'role': 'user', 'content': 'مرحبا'}]}, headers=headers)
        assert 'رد باختصار وبلهجة سعودية' in system.backend.calls[-1]['messages'][0]['content']
        assert client.put('/assistant/preferences', json={'persona': ''}, headers=headers).json()['persona'] == ''
    app.state.project_store.close()
