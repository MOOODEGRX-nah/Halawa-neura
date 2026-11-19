"""N089/N092: voice comparison/selection and wake-word matching without false triggers."""
import json
import os
import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.core.voice_service import VoiceService, wake_command
from src.core.neura_loop import InferenceError


@pytest.mark.parametrize('text,expected', [
    ('نيورا', ''), ('يا نيورا', ''), ('يا نيورا، كم الساعة؟', 'كم الساعة'), ('Hey Neura what time is it', 'what time is it'),
    ('نيورا ذكرني بعد ساعة بالاجتماع', 'ذكرني بعد ساعة بالاجتماع'), ('  ...يا نيوره افتح يوتيوب', 'افتح يوتيوب'),
    ('نِيُورَا شغل الموسيقى', 'شغل الموسيقى'),
])
def test_wake_phrase_activates(text, expected):
    assert wake_command(text) == expected


@pytest.mark.parametrize('text', [
    'كنت أتكلم مع نيورا أمس', 'نيورون في الدماغ', 'neural networks are fun', 'نيوراليا', 'شكرا', '', 'يا جماعة نيورا',
    'Neurallink is a company', 'انا نيورا', 'نورة جات',
])
def test_ordinary_speech_never_triggers(text):
    assert wake_command(text) is None


def fake_voice(tmp_path, names):
    voice = tmp_path / 'voice'
    (voice / 'piper').mkdir(parents=True, exist_ok=True)
    engine = voice / 'piper' / 'piper'
    engine.write_text('#!/bin/sh\nexit 0\n')
    engine.chmod(engine.stat().st_mode | stat.S_IEXEC)
    (voice / 'piper-voices').mkdir(exist_ok=True)
    for name, language in names:
        (voice / 'piper-voices' / (name + '.onnx')).write_bytes(b'0' * 1000)
        (voice / 'piper-voices' / (name + '.onnx.json')).write_text(json.dumps({'language': {'code': language}, 'audio': {'quality': 'medium', 'sample_rate': 22050}}))
    return VoiceService(data_dir=tmp_path)


def test_voices_are_listed_and_selection_persists(tmp_path, monkeypatch):
    for key in ('NEURA_PIPER_CLI', 'NEURA_PIPER_MODEL', 'NEURA_PIPER_LANG'):
        monkeypatch.delenv(key, raising=False)
    service = fake_voice(tmp_path, [('ar_JO-kareem-low', 'ar_JO'), ('ar_JO-kareem-medium', 'ar_JO'), ('en_US-amy-medium', 'en_US')])
    listing = service.voices()
    assert [v['id'] for v in listing['voices']] == ['ar_JO-kareem-low', 'ar_JO-kareem-medium', 'en_US-amy-medium']
    assert listing['voices'][0]['selected'] and listing['sample_text']
    service.select_voice('ar_JO-kareem-medium')
    again = fake_voice(tmp_path, [])
    assert Path(again.piper_model).stem == 'ar_JO-kareem-medium'
    with pytest.raises(InferenceError):
        again.select_voice('../../etc/passwd')
    with pytest.raises(InferenceError) as wrong_language:
        again.synthesize('hello', 'ar', voice='en_US-amy-medium')
    assert wrong_language.value.code == 'tts_language_unavailable'
