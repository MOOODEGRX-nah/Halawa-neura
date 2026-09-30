"""
Neura STT — Whisper hardened ضد الهلوسة.
- amplify للإشارة الضعيفة
- condition_on_previous_text=False
- initial_prompt بالعربية
- language='ar' قسري (لا auto-detect)
- temperature=0.0 (no sampling)
- post-validation لفلترة الهلوسة
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import time
import numpy as np
import pyaudio
import whisper


class SpeechToText:
    def __init__(self, model_name='small', device='cpu'):
        print('[STT] Loading Whisper (%s) ...' % model_name)
        t0 = time.perf_counter()
        self.model = whisper.load_model(model_name, device=device)
        print('[STT] Loaded in %.1fs' % (time.perf_counter() - t0))

        self.audio = pyaudio.PyAudio()
        self.chunk = 1024
        self.format = pyaudio.paInt16
        self.channels = 1
        self.rate = 16000

    def record(self, duration=6.0):
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
            if (i + 1) % chunks_per_sec == 0:
                print('.', end='', flush=True)
        print(' done!')
        stream.stop_stream()
        stream.close()

        audio_bytes = b''.join(frames)
        audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        # amplify الإشارة الضعيفة (2x) + clip
        audio_np = np.clip(audio_np * 2.0, -1.0, 1.0)
        return audio_np

    def _rms(self, audio_np):
        return float(np.sqrt(np.mean(audio_np ** 2)))

    def _validate(self, text):
        """يفلتَر الهلوسة وخليط اللغات والنصوص الفارغة."""
        if not text:
            return False, 'empty'
        t = text.strip()
        if len(t) < 2:
            return False, 'too_short'

        # نسبة الحروف العربية
        ar = sum(1 for c in t if '\u0600' <= c <= '\u06FF')
        alpha = sum(1 for c in t if c.isalpha())
        if alpha > 0 and ar / alpha < 0.6:
            return False, 'mixed_language (arabic %.0f%%)' % (100 * ar / alpha)

        # هلوسة معروفة
        if t in ('شكراً', 'شكراً لكم', 'مع السلامة', 'انظر', 'اذهب', 'تفضل', 'النهاية'):
            return False, 'known_hallucination'

        # تحقق من عدم التكرار المرضي
        if len(t) > 6 and t[:len(t)//2] == t[len(t)//2:]:
            return False, 'repetition'

        return True, 'ok'

    def transcribe(self, audio_np):
        rms = self._rms(audio_np)
        if rms < 0.02:
            print('[STT] Silence (RMS=%.3f)' % rms)
            return '', 0.0, 'none'

        print('[STT] Transcribing (RMS=%.3f) ...' % rms)
        t0 = time.perf_counter()

        result = self.model.transcribe(
            audio_np,
            language='ar',                  # عربي قسري
            fp16=False,
            temperature=0.0,                # greedy (no sampling)
            condition_on_previous_text=False,  # المفتاح لمنع الهلوسة المتسلسلة
            initial_prompt='مرحباً، السلام عليكم، كيف حالك',
            no_speech_threshold=0.6,
            compression_ratio_threshold=2.4,
            logprob_threshold=-1.0,
            word_timestamps=False,
        )
        dt = time.perf_counter() - t0

        text = result['text'].strip()
        valid, reason = self._validate(text)
        if not valid:
            print('[STT] Rejected: %s -> "%s"' % (reason, text))
            return '', dt, 'rejected:' + reason

        print('[STT] Done in %.2fs: "%s"' % (dt, text))
        return text, dt, 'ar'

    def record_and_transcribe(self, duration=6.0):
        audio_np = self.record(duration)
        return self.transcribe(audio_np)

    def close(self):
        self.audio.terminate()


if __name__ == '__main__':
    print('=' * 60)
    print('Neura STT (hardened against hallucination)')
    print('=' * 60)
    print('اضغط Enter ثم تكلم بالعربية فوراً.')
    print()
    stt = SpeechToText(model_name='small', device='cpu')
    try:
        text, dt, lang = stt.record_and_transcribe(duration=6.0)
        print()
        print('=' * 60)
        if text:
            print('✅ النص:', text)
        else:
            print('❌ السبب:', lang)
        print('=' * 60)
    finally:
        stt.close()
