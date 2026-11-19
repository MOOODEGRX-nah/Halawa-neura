"""Optional local CLI speech adapters; no cloud fallback and no automatic downloads.

Engines and voices are discovered in this order: explicit NEURA_* variables, the user's
Neura data directory (`<data>/voice`), then the system PATH. A program named `piper` on the
PATH is only used when it is the Piper speech engine (a GTK mouse tool shares the name).
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from src.core.neura_loop import InferenceError
from src.core.resource_policy import owned_run

EMOJI = re.compile('[\U0001F000-\U0001FAFF☀-➿️‍]')


@lru_cache(maxsize=8)
def _is_piper_tts(path):
    try:
        out = subprocess.run([path, '--help'], capture_output=True, timeout=5, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return False
    text = (out.stdout + out.stderr).decode(errors='ignore')
    return '--model' in text and ('output_file' in text or 'output-file' in text)


def speakable(text, limit=1500):
    """Plain sentences for a voice: no code, markup, links or emoji."""
    text = re.sub(r'```[\s\S]*?```', ' ', text)
    text = re.sub(r'`[^`]*`', ' ', text)
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'https?://\S+', ' ', text)
    text = re.sub(r'^\s{0,3}(?:#{1,6}|[-*•]|\d+[.)])\s+', '', text, flags=re.M)
    text = re.sub(r'[*_~|>#]+', ' ', text)
    text = EMOJI.sub(' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > limit:
        cut = max(text.rfind(mark, 0, limit) for mark in '.،؟!?')
        text = text[:cut + 1 if cut > limit // 2 else limit]
    return text


class VoiceService:
    def __init__(self, tools_dir=None, data_dir=None):
        self.tools_dir = Path(tools_dir) if tools_dir else Path.home() / 'Downloads/ai/neura AI/Neura_Package/tools'
        self.voice_dir = Path(data_dir) / 'voice' if data_dir else None
        self.ffmpeg = shutil.which('ffmpeg')
        self.whisper = os.environ.get('NEURA_WHISPER_CLI') or self._first_executable('whisper.cpp/whisper-cli', 'whisper-cli') or shutil.which('whisper-cli')
        self.whisper_model = Path(os.environ.get('NEURA_WHISPER_MODEL') or self._whisper_model() or self.tools_dir / 'whisper-large-v3.bin')
        self.piper = os.environ.get('NEURA_PIPER_CLI') or self._first_executable('piper/piper')
        if not self.piper and shutil.which('piper') and _is_piper_tts(shutil.which('piper')):
            self.piper = shutil.which('piper')
        self.piper_model = os.environ.get('NEURA_PIPER_MODEL') or self._piper_voice()
        self.piper_lang = os.environ.get('NEURA_PIPER_LANG') or self._voice_language(self.piper_model) or 'ar'

    def _first_executable(self, *relative):
        if not self.voice_dir:
            return None
        for name in relative:
            path = self.voice_dir / name
            if path.is_file() and os.access(path, os.X_OK):
                return str(path)
        return None

    def _whisper_model(self):
        if not self.voice_dir or not (self.voice_dir / 'whisper').is_dir():
            return None
        models = sorted((self.voice_dir / 'whisper').glob('ggml-*.bin'))
        preferred = [m for m in models if 'large-v3-turbo' in m.name] or [m for m in models if 'large' in m.name] or models
        return str(preferred[0]) if preferred else None

    def _piper_voice(self):
        if not self.voice_dir or not (self.voice_dir / 'piper-voices').is_dir():
            return None
        voices = [v for v in sorted((self.voice_dir / 'piper-voices').glob('*.onnx')) if Path(str(v) + '.json').is_file()]
        arabic = [v for v in voices if v.name.startswith('ar')]
        return str((arabic or voices)[0]) if voices else None

    @staticmethod
    def _voice_language(model):
        if not model or not Path(str(model) + '.json').is_file():
            return None
        try:
            code = json.loads(Path(str(model) + '.json').read_text(encoding='utf-8'))['language']['code']
        except (OSError, ValueError, KeyError, TypeError):
            return None
        return str(code).split('_')[0].lower() or None

    def capabilities(self):
        stt = bool(self.whisper and shutil.which(self.whisper) and self.ffmpeg and self.whisper_model.is_file())
        tts = bool(self.piper and shutil.which(self.piper) and self.piper_model and Path(self.piper_model).is_file() and Path(str(self.piper_model) + '.json').is_file())
        return {'stt': stt, 'tts': tts,
                'stt_engine': 'whisper.cpp · ' + self.whisper_model.name if stt else None,
                'tts_engine': 'Piper · ' + Path(self.piper_model).stem if tts else None,
                'tts_language': self.piper_lang if tts else None,
                'stt_reason': 'Requires whisper-cli (pacman -S whisper-cpp), ffmpeg and a local GGML model in ~/.local/share/neura-ai/voice/whisper',
                'tts_reason': 'Requires the Piper speech engine and a local voice (.onnx + .onnx.json) in ~/.local/share/neura-ai/voice'}

    def transcribe(self, raw, language='ar'):
        from src.core.resource_policy import accelerator_allowed
        accelerator_allowed()
        if not self.capabilities()['stt']:
            raise InferenceError(self.capabilities()['stt_reason'], 501, 'stt_unavailable')
        if not raw or len(raw) > 20_000_000:
            raise InferenceError('Audio must be between 1 byte and 20 MB', 413, 'invalid_audio')
        if language not in ('ar', 'en', 'auto'):
            raise InferenceError('Unsupported language', 400, 'invalid_language')
        if raw.startswith(b'\x1a\x45\xdf\xa3'):
            demuxer = 'matroska'
        elif raw.startswith(b'RIFF') and raw[8:12] == b'WAVE':
            demuxer = 'wav'
        elif raw.startswith(b'OggS'):
            demuxer = 'ogg'
        elif raw[4:8] == b'ftyp':
            demuxer = 'mov'
        else:
            raise InferenceError('Unsupported audio format', 400, 'invalid_audio')
        threads = str(max(1, min(8, (os.cpu_count() or 4) // 2)))
        with tempfile.TemporaryDirectory(prefix='neura-stt-') as directory:
            root = Path(directory)
            (root / 'input').write_bytes(raw)
            try:
                owned_run([self.ffmpeg, '-v', 'error', '-nostdin', '-y', '-protocol_whitelist', 'file,pipe', '-f', demuxer, '-i', str(root / 'input'),
                           '-t', '120', '-ar', '16000', '-ac', '1', str(root / 'audio.wav')],
                          check=True, timeout=30, capture_output=True)
                owned_run([self.whisper, '-m', str(self.whisper_model), '-f', str(root / 'audio.wav'), '-t', threads,
                           '-l', language, '-nt', '-np', '-otxt', '-of', str(root / 'transcript')],
                          check=True, timeout=180, capture_output=True)
                text = (root / 'transcript.txt').read_text(encoding='utf-8').strip()
            except (subprocess.SubprocessError, OSError) as exc:
                raise InferenceError('Local transcription failed', 502, 'stt_failed') from exc
        # whisper prints bracketed non-speech markers such as [BLANK_AUDIO] or (music) on silence.
        text = re.sub(r'\[[^\]]*\]|\((?:music|موسيقى|silence|صمت)[^)]*\)', ' ', text, flags=re.I)
        text = re.sub(r'\s+', ' ', text).strip()
        if not text or re.fullmatch(r'[\W_]+', text):
            raise InferenceError('No speech recognized', 422, 'no_speech')
        return {'text': text, 'language': language, 'engine': 'whisper.cpp'}

    def synthesize(self, text, language='ar'):
        if not self.capabilities()['tts']:
            raise InferenceError(self.capabilities()['tts_reason'], 501, 'tts_unavailable')
        # A single configured voice must explicitly declare its language.
        if language != self.piper_lang:
            raise InferenceError('Configured voice does not support this language', 501, 'tts_language_unavailable')
        spoken = speakable(text)
        if not spoken:
            raise InferenceError('Nothing speakable in this reply', 422, 'tts_empty')
        with tempfile.TemporaryDirectory(prefix='neura-tts-') as directory:
            output = Path(directory) / 'speech.wav'
            try:
                owned_run([self.piper, '--model', str(self.piper_model), '--output_file', str(output)],
                          input=spoken.encode(), check=True, timeout=90, capture_output=True)
                audio = output.read_bytes()
            except (subprocess.SubprocessError, OSError) as exc:
                raise InferenceError('Local speech synthesis failed', 502, 'tts_failed') from exc
        if not audio.startswith(b'RIFF') or len(audio) <= 44:
            raise InferenceError('Speech engine returned invalid audio', 502, 'tts_failed')
        return audio
