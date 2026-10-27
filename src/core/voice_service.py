"""Optional local CLI speech adapters; no downloads or cloud fallback."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from src.core.neura_loop import InferenceError


class VoiceService:
    def __init__(self, tools_dir=None):
        self.tools_dir = Path(tools_dir) if tools_dir else Path.home() / 'Downloads/ai/neura AI/Neura_Package/tools'
        self.whisper = os.environ.get('NEURA_WHISPER_CLI') or shutil.which('whisper-cli')
        self.whisper_model = Path(os.environ.get('NEURA_WHISPER_MODEL', self.tools_dir / 'whisper-large-v3.bin'))
        self.ffmpeg = shutil.which('ffmpeg')
        self.piper = os.environ.get('NEURA_PIPER_CLI') or shutil.which('piper')
        self.piper_model = os.environ.get('NEURA_PIPER_MODEL')

    def capabilities(self):
        return {'stt': bool(self.whisper and shutil.which(self.whisper) and self.ffmpeg and self.whisper_model.is_file()),
                'tts': bool(self.piper and shutil.which(self.piper) and self.piper_model and Path(self.piper_model).is_file() and Path(self.piper_model + '.json').is_file()),
                'stt_reason': 'Requires whisper-cli, ffmpeg and a local GGML model',
                'tts_reason': 'Requires piper CLI and a local voice ONNX + JSON; Kokoro weights alone are insufficient'}

    def transcribe(self, raw, language='ar'):
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
        with tempfile.TemporaryDirectory(prefix='neura-stt-') as directory:
            root = Path(directory)
            (root / 'input').write_bytes(raw)
            try:
                subprocess.run([self.ffmpeg, '-v', 'error', '-nostdin', '-y', '-protocol_whitelist', 'file,pipe', '-f', demuxer, '-i', str(root / 'input'),
                                '-t', '120', '-ar', '16000', '-ac', '1', str(root / 'audio.wav')],
                               check=True, timeout=30, capture_output=True)
                subprocess.run([self.whisper, '-m', str(self.whisper_model), '-f', str(root / 'audio.wav'),
                                '-l', language, '-otxt', '-of', str(root / 'transcript')],
                               check=True, timeout=180, capture_output=True)
                text = (root / 'transcript.txt').read_text(encoding='utf-8').strip()
            except (subprocess.SubprocessError, OSError) as exc:
                raise InferenceError('Local transcription failed', 502, 'stt_failed') from exc
        if not text:
            raise InferenceError('No speech recognized', 422, 'no_speech')
        return {'text': text, 'language': language, 'engine': 'whisper.cpp'}

    def synthesize(self, text, language='ar'):
        if not self.capabilities()['tts']:
            raise InferenceError(self.capabilities()['tts_reason'], 501, 'tts_unavailable')
        # A single configured voice must explicitly declare its language.
        if language != os.environ.get('NEURA_PIPER_LANG', 'ar'):
            raise InferenceError('Configured voice does not support this language', 501, 'tts_language_unavailable')
        with tempfile.TemporaryDirectory(prefix='neura-tts-') as directory:
            output = Path(directory) / 'speech.wav'
            try:
                subprocess.run([self.piper, '--model', self.piper_model, '--output_file', str(output)],
                               input=text.encode(), check=True, timeout=90, capture_output=True)
                audio = output.read_bytes()
            except (subprocess.SubprocessError, OSError) as exc:
                raise InferenceError('Local speech synthesis failed', 502, 'tts_failed') from exc
        if not audio.startswith(b'RIFF') or len(audio) <= 44:
            raise InferenceError('Speech engine returned invalid audio', 502, 'tts_failed')
        return audio
