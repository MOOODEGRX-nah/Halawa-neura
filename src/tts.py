"""
Neura TTS — ثلاث محركات:
1) Edge-TTS (جودة احترافية، عربي ممتاز) — مع pygame للتشغيل
2) Piper (محلي ONNX، إن عمل)
3) Windows SAPI (احتياطي أخير)
"""
import sys
import os
import wave
import asyncio
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

VOICE_MODEL = 'models/tts/ar_JO-kareem-medium.onnx'
OUT_MP3 = 'data/tts_out.mp3'
OUT_WAV = 'data/tts_out.wav'

EDGE_VOICES = [
    'ar-SA-HamedNeural',   # ذكر (الأفضل)
    'ar-SA-ZariyahNeural', # أنثى
    'ar-EG-SalmaNeural',   # مصري
]


class TextToSpeech:
    def __init__(self, model_path=VOICE_MODEL):
        self.mode = None
        self.edge_voice = None
        self.mixer_ready = False

        # تهيئة pygame mixer مرة واحدة (إن وُجد)
        try:
            import pygame
            pygame.mixer.init()
            self.mixer_ready = True
        except Exception as e:
            print('[TTS] pygame unavailable:', e)

        # المحرك 1: Edge-TTS
        try:
            import edge_tts
            asyncio.run(self._test_edge())
            if self.edge_voice:
                self.mode = 'edge'
                print('[TTS] Engine: Edge-TTS ->', self.edge_voice)
                return
        except Exception as e:
            print('[TTS] Edge unavailable:', e)

        # المحرك 2: Piper
        try:
            from piper import PiperVoice
            self.piper = PiperVoice.load(model_path, config_path=model_path + '.json')
            test_wav = 'data/_tts_test.wav'
            os.makedirs('data', exist_ok=True)
            with wave.open(test_wav, 'wb') as f:
                f.setnchannels(1)
                f.setsampwidth(2)
                f.setframerate(getattr(self.piper.config, 'sample_rate', 22050))
                self.piper.synthesize('test', f)
            w = wave.open(test_wav, 'rb')
            n = w.getnframes()
            w.close()
            try: os.remove(test_wav)
            except OSError: pass
            if n > 0:
                self.mode = 'piper'
                print('[TTS] Engine: Piper (local ONNX)')
                return
        except Exception as e:
            print('[TTS] Piper unavailable:', e)

        # المحرك 3: SAPI
        try:
            import pyttsx3
            self.sapi = pyttsx3.init()
            voices = self.sapi.getProperty('voices') or []
            ar = [v for v in voices if 'ar' in str(v.languages).lower() or 'arabic' in v.name.lower()]
            if ar:
                self.sapi.setProperty('voice', ar[0].id)
                print('[TTS] Engine: SAPI Arabic ->', ar[0].name)
            else:
                print('[TTS] Engine: SAPI default')
            self.mode = 'sapi'
        except Exception as e:
            print('[TTS] FATAL:', e)

    async def _test_edge(self):
        import edge_tts
        for v in EDGE_VOICES:
            try:
                c = edge_tts.Communicate('test', voice=v)
                await c.save('data/_edge_test.mp3')
                if os.path.getsize('data/_edge_test.mp3') > 100:
                    self.edge_voice = v
                    try: os.remove('data/_edge_test.mp3')
                    except OSError: pass
                    return
            except Exception:
                continue

    def _edge_speak(self, text):
        import edge_tts
        import pygame

        # توليد MP3
        async def _run():
            c = edge_tts.Communicate(text, voice=self.edge_voice)
            await c.save(OUT_MP3)
        asyncio.run(_run())

        # تشغيل متزامن عبر pygame
        if self.mixer_ready:
            pygame.mixer.music.load(OUT_MP3)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.05)
        else:
            # احتياطي: افتح في تطبيق ويندوز الافتراضي
            os.startfile(OUT_MP3)
            time.sleep(4)

    def speak(self, text):
        print('[TTS] Speaking via %s ...' % self.mode)
        try:
            if self.mode == 'edge':
                self._edge_speak(text)
            elif self.mode == 'piper':
                with wave.open(OUT_WAV, 'wb') as f:
                    f.setnchannels(1)
                    f.setsampwidth(2)
                    f.setframerate(getattr(self.piper.config, 'sample_rate', 22050))
                    self.piper.synthesize(text, f)
                if self.mixer_ready:
                    import pygame
                    pygame.mixer.music.load(OUT_WAV)
                    pygame.mixer.music.play()
                    while pygame.mixer.music.get_busy():
                        time.sleep(0.05)
                else:
                    os.startfile(OUT_WAV)
                    time.sleep(4)
            elif self.mode == 'sapi':
                self.sapi.say(text)
                self.sapi.runAndWait()
            else:
                print('[TTS] no engine!')
                return
            print('[TTS] Done')
        except Exception as e:
            print('[TTS] Error:', e)


if __name__ == '__main__':
    tts = TextToSpeech()
    tts.speak('مرحباً! أنا نورا، مساعدك الذكي. الآن أستطيع الكلام بالعربية بوضوح!')
    print('✅ انتهت التجربة')
