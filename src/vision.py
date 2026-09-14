"""
رؤية الشاشة — يلتقط الشاشة ويحللها بنموذج LLaVA ليشرح لك ماذا تفعل
"""


class JarvisVision:
    def __init__(self, config):
        self.config = config
        self.llm = None
        self.status = "not_loaded"
        self.status_msg = ""

    def load(self):
        try:
            from llama_cpp import Llama
            from llama_cpp.llama_chat_format import Llava15ChatHandler
        except ImportError:
            self.status = "unavailable"
            self.status_msg = "مكتبة llama-cpp-python غير مثبتة"
            return

        model = self.config.models_dir / self.config.get("models.vision")
        mmproj = self.config.models_dir / self.config.get("models.vision_mmproj")
        if not model.exists() or not mmproj.exists():
            self.status = "missing"
            self.status_msg = "نموذج الرؤية غير محمّل (حمّله من الإعدادات)"
            return

        try:
            handler = Llava15ChatHandler(clip_model_path=str(mmproj), verbose=False)
            res = self.config.resources()
            self.llm = Llama(
                model_path=str(model),
                chat_handler=handler,
                n_ctx=2048,
                n_threads=int(res["n_threads"]),
                n_gpu_layers=min(int(res["n_gpu_layers"]), 20),
                verbose=False,
            )
            self.status = "ready"
            self.status_msg = "الرؤية جاهزة"
        except Exception as e:
            self.status = "error"
            self.status_msg = str(e)

    def capture(self):
        """يلتقط الشاشة ويصغرها لتوفير الموارد"""
        import mss
        from PIL import Image
        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[1])
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        max_w = 768
        if img.width > max_w:
            ratio = max_w / img.width
            img = img.resize((max_w, int(img.height * ratio)))
        return img

    def ask(self, question):
        """يسأل عن محتوى الشاشة. يعيد (الإجابة، مسار الصورة)"""
        import base64
        import io

        if self.status != "ready":
            return f"الرؤية غير متاحة: {self.status_msg}", None

        img = self.capture()
        save_path = self.config.data_dir / "screen_capture.jpg"
        img.save(save_path, "JPEG", quality=70)

        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=60)
        b64 = base64.b64encode(buf.getvalue()).decode()

        resp = self.llm.create_chat_completion(
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text",
                     "text": f"أنت مساعد ينظر إلى شاشة المستخدم. {question} أجب باختصار بالعربية."}
                ]
            }],
            max_tokens=300,
        )
        return resp["choices"][0]["message"]["content"].strip(), str(save_path)
