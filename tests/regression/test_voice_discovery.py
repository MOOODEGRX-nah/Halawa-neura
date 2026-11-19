"""Local voice engines are discovered in the Neura data directory and verified before use."""
import json
import os
import stat

import pytest

from src.core import voice_service
from src.core.voice_service import VoiceService, speakable
from src.core.neura_loop import InferenceError

FAKE_PIPER = '''#!/bin/sh
if [ "$1" = "--help" ]; then echo "usage: piper --model MODEL --output_file FILE"; exit 0; fi
out=""
while [ $# -gt 0 ]; do [ "$1" = "--output_file" ] && out="$2"; shift; done
cat > "$out.txt"
printf 'RIFF\\044\\000\\000\\000WAVEfmt \\020\\000\\000\\000\\001\\000\\001\\000\\200\\076\\000\\000\\000\\175\\000\\000\\002\\000\\020\\000data\\000\\000\\000\\000xxxx' > "$out"
'''
MOUSE_PIPER = '#!/bin/sh\necho "Piper - configure your gaming mouse"\n'


def executable(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ('NEURA_WHISPER_CLI', 'NEURA_WHISPER_MODEL', 'NEURA_PIPER_CLI', 'NEURA_PIPER_MODEL', 'NEURA_PIPER_LANG'):
        monkeypatch.delenv(name, raising=False)
    voice_service._is_piper_tts.cache_clear()


def voices(tmp_path):
    root = tmp_path / 'voice'
    (root / 'whisper').mkdir(parents=True)
    (root / 'whisper' / 'ggml-small.bin').write_bytes(b'x')
    (root / 'whisper' / 'ggml-large-v3-turbo-q5_0.bin').write_bytes(b'x')
    (root / 'piper-voices').mkdir()
    (root / 'piper-voices' / 'ar_JO-kareem-medium.onnx').write_bytes(b'x')
    (root / 'piper-voices' / 'ar_JO-kareem-medium.onnx.json').write_text(json.dumps({'language': {'code': 'ar_JO'}}))
    (root / 'piper-voices' / 'en_US-amy-low.onnx').write_bytes(b'x')
    (root / 'piper-voices' / 'en_US-amy-low.onnx.json').write_text(json.dumps({'language': {'code': 'en_US'}}))
    return root


def test_discovers_preferred_models_and_bundled_piper(tmp_path, monkeypatch):
    root = voices(tmp_path)
    executable(root / 'piper' / 'piper', FAKE_PIPER)
    monkeypatch.setattr(voice_service.shutil, 'which', lambda name: name if os.path.isabs(name) else None)
    service = VoiceService(tools_dir=tmp_path / 'none', data_dir=tmp_path)
    assert service.whisper_model.name == 'ggml-large-v3-turbo-q5_0.bin'
    assert service.piper_model.endswith('ar_JO-kareem-medium.onnx') and service.piper_lang == 'ar'
    caps = service.capabilities()
    assert caps['tts'] and caps['tts_engine'] == 'Piper · ar_JO-kareem-medium'
    audio = service.synthesize('**مرحبًا** بك 👋 في `Neura`: https://example.com', 'ar')
    assert audio.startswith(b'RIFF')
    with pytest.raises(InferenceError):
        service.synthesize('hello', 'en')


def test_gtk_mouse_tool_named_piper_is_never_used(tmp_path, monkeypatch):
    voices(tmp_path)
    mouse = executable(tmp_path / 'bin' / 'piper', MOUSE_PIPER)
    real_which = voice_service.shutil.which
    monkeypatch.setattr(voice_service.shutil, 'which', lambda name: str(mouse) if name == 'piper' else real_which(name) if os.path.isabs(name) else None)
    service = VoiceService(tools_dir=tmp_path / 'none', data_dir=tmp_path)
    assert service.piper is None and not service.capabilities()['tts']


def test_speakable_removes_code_markup_links_and_emoji():
    text = 'مرحبًا **محمد** 👋\n```python\nprint(1)\n```\n- أولًا [الرابط](https://x.y)\nزر https://example.com الآن'
    assert speakable(text) == 'مرحبًا محمد أولًا الرابط زر الآن'
    long = ('جملة قصيرة. ' * 400)
    assert len(speakable(long)) <= 1500 and speakable(long).endswith('.')
