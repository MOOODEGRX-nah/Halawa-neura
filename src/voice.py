"""
الصوت: الاستماع (كلام → نص) والنطق (نص → كلام)
اختياري تماماً — إذا لم تُثبّت المكتبات يعمل البرنامج بدونه
"""
import threading


class JarvisVoice:
    def __init__(self, lang="ar-SA"):
        self.lang = lang
        self.tts_ok = False
        self.stt_ok = False
        self._local = threading.local()

        try:
            import pyttsx3  # noqa
            self.tts_ok = True
        except ImportError:
            pass

        try:
            import speech_recognition as sr
            self._rec = sr.Recognizer()
            self._rec.energy_threshold = 350
            self.stt_ok = True
        except ImportError:
            pass

    def _engine(self):
        """محرك نطق لكل خيط (لتجنب مشاكل تعدد الخيوط)"""
        if not hasattr(self._local, "engine"):
            import pyttsx3
            self._local.engine = pyttsx3.init()
            self._local.engine.setProperty("rate", 170)
        return self._local.engine

    def speak(self, text):
        """ينطق النص في خيط منفصل"""
        if not self.tts_ok:
            return False
        def _work():
            try:
                eng = self._engine()
                eng.say(text)
                eng.runAndWait()
            except Exception:
                pass
        threading.Thread(target=_work, daemon=True).start()
        return True

    def listen(self, timeout=6):
        """يستمع ويعيد النص، أو None إذا فشل"""
        if not self.stt_ok:
            return None
        import speech_recognition as sr
        try:
            with sr.Microphone() as src:
                self._rec.adjust_for_ambient_noise(src, duration=0.3)
                audio = self._rec.listen(src, timeout=timeout)
            return self._rec.recognize_google(audio, language=self.lang)
        except Exception:
            return None
