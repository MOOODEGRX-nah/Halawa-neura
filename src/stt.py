import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import time
import numpy as np
import pyaudio
import whisper


class SpeechToText:
    """Whisper STT engine - simple, reliable, full-duration recording."""

    def __init__(self, model_name='base', device='cpu'):
        print('[STT] Loading Whisper model (%s) on %s ...' % (model_name, device))
        t0 = time.perf_counter()
        self.model = whisper.load_model(model_name, device=device)
        print('[STT] Whisper loaded in %.1fs' % (time.perf_counter() - t0))

        self.audio = pyaudio.PyAudio()
        self.chunk = 1024
        self.format = pyaudio.paInt16
        self.channels = 1
        self.rate = 16000

    def record(self, duration=5.0):
        """Record audio for FULL duration. No early stopping."""
        print('[STT] Recording %.1fs - SPEAK NOW!' % duration, flush=True)
        stream = self.audio.open(
            format=self.format,
            channels=self.channels,
            rate=self.rate,
            input=True,
            frames_per_buffer=self.chunk,
        )
        frames = []
        n_chunks = int(self.rate / self.chunk * duration)
        chunks_per_sec = self.rate // self.chunk

        for i in range(n_chunks):
            data = stream.read(self.chunk, exception_on_overflow=False)
            frames.append(data)
            # Visual progress: print a dot each second
            if (i + 1) % chunks_per_sec == 0:
                print('.', end='', flush=True)
        print(' done!')

        stream.stop_stream()
        stream.close()
        audio_bytes = b''.join(frames)
        audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        return audio_np

    def has_voice(self, audio_np, threshold=0.005):
        """Check if audio has meaningful signal."""
        rms = np.sqrt(np.mean(audio_np ** 2))
        return rms > threshold, rms

    def transcribe(self, audio_np, language=None):
        """Transcribe with auto language detection."""
        has_v, rms = self.has_voice(audio_np)
        if not has_v:
            print('[STT] No voice detected (RMS=%.4f, below threshold)' % rms)
            return '', 0.0, 'none'

        print('[STT] Transcribing (RMS=%.4f) ...' % rms)
        t0 = time.perf_counter()

        # Auto-detect language
        if language is None:
            audio_pad = whisper.pad_or_trim(audio_np)
            mel = whisper.log_mel_spectrogram(audio_pad).to(self.model.device)
            _, probs = self.model.detect_language(mel)
            language = max(probs, key=probs.get)
            confidence = probs[language]
            print('[STT] Detected language: %s (%.1f%%)' % (language, confidence * 100))

        result = self.model.transcribe(audio_np, language=language, fp16=False)
        dt = time.perf_counter() - t0
        text = result['text'].strip()
        print('[STT] Done in %.2fs: "%s"' % (dt, text))
        return text, dt, language

    def record_and_transcribe(self, duration=5.0, language=None):
        """Full pipeline: record full duration, then transcribe."""
        audio_np = self.record(duration)
        return self.transcribe(audio_np, language=language)

    def close(self):
        self.audio.terminate()


def demo():
    print('=' * 70)
    print('T-0415: Whisper STT Demo (simple full-duration mode)')
    print('=' * 70)
    print('Press ENTER then SPEAK IMMEDIATELY.')
    print('You can speak Arabic or English - auto-detected.')
    print('')

    stt = SpeechToText(model_name='base', device='cpu')

    try:
        text, dt, lang = stt.record_and_transcribe(duration=6.0)
        print('')
        print('=' * 70)
        print('RESULT:')
        if text:
            print('  Text     :', text)
            print('  Language :', lang)
            print('  Time     : %.2fs' % dt)
        else:
            print('  (no voice detected - try speaking louder)')
        print('=' * 70)
    finally:
        stt.close()


if __name__ == '__main__':
    demo()
