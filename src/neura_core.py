import os
os.environ.setdefault("GGML_VULKAN", "1")
"""
عقل Neura — يعالج الطلبات: نوايا محلية آمنة + نموذج ذكاء للمحادثة
"""
import datetime
import re
import webbrowser

from safety import find_known_site, build_search_url
from config import APP_NAME

SYSTEM_PROMPT = """أنت مساعد ذكي اسمه Neura يعمل على جهاز المستخدم الشخصي.
قواعدك الصارمة:
1. أنت "مرشد آمن": ترشد المستخدم بالخطوات ولا تقترح أوامر حذف أو فورمات أو أوامر مدمرة أبداً.
2. ردودك مختصرة ومفيدة وبالعربية إلا إذا كتب المستخدم بلغة أخرى.
3. إذا لم تكن متأكداً من معلومة، قل ذلك بصراحة.
4. لا تخترع روابط أو مواقع غير معروفة."""


class NeuraCore:
    def __init__(self, config, db):
        self.config = config
        self.db = db
        self.llm = None
        self.status = "not_loaded"
        self.status_msg = ""

    # ===== تحميل النموذج =====
    def load_model(self):
        self.status = "loading"
        self.status_msg = "جاري تحميل النموذج..."
        try:
            from llama_cpp import Llama
        except ImportError:
            self.status = "basic"
            self.status_msg = "محرك الذكاء غير مثبت — أعمل بالوضع الأساسي"
            return

        path = self.config.models_dir / self.config.get("models.chat")
        if not path.exists():
            self.status = "basic"
            self.status_msg = "نموذج الذكاء غير محمّل بعد — حمّله من الإعدادات"
            return

        try:
            res = self.config.resources()
            self.llm = Llama(
                model_path=str(path),
                n_threads=int(res["n_threads"]),
                n_gpu_layers=int(res["n_gpu_layers"]),
                n_ctx=int(res["n_ctx"]),
                n_batch=int(res.get("n_batch", 1024)),
                verbose=False,
            )
            self.status = "ready"
            self.status_msg = "النموذج محمّل"
        except Exception as e:
            self.status = "error"
            self.status_msg = f"خطأ في تحميل النموذج: {e}"

    # ===== المعالجة الرئيسية =====
    def process(self, text):
        try:
            local = self._local_intents(text)
            if local:
                return {"reply": local}
            if self.llm:
                return {"reply": self._llm_chat(text)}
            return {"reply": self._basic_reply()}
        except Exception as e:
            return {"reply": f"حدث خطأ غير متوقع: {e}"}

    # ===== النوايا المحلية (تعمل دائماً، آمنة، فورية) =====
    def _local_intents(self, text):
        t = text.strip()
        tl = t.lower()
        now = datetime.datetime.now()

        if re.search(r"^(مرحبا|أهلا|اهلا|هلا|السلام عليكم|هاي|hello|hi)\b", tl):
            return (f"أهلاً بك! أنا {APP_NAME}، مساعدك على هذا الجهاز.\n"
                    "اسألني أي شيء، أو اطلب فتح موقع موثوق، أو قل: مساعدة")

        if any(w in tl for w in ["مساعدة", "ماذا تستطيع", "اوامر", "help"]):
            return ("إليك ما أستطيع فعله:\n"
                    "• محادثة ذكية (عند تحميل النموذج)\n"
                    "• افتح يوتيوب / جوجل / ويكيبيديا / قناة nasa\n"
                    "• ابحث عن <أي شيء>\n"
                    "• كم الساعة؟ / ما التاريخ؟\n"
                    "• أضف مهمة: <المهمة>\n"
                    "• تذكر أن <معلومة> / ماذا تتذكر؟\n"
                    "• وضع اللعب / الوضع العادي")

        if any(w in tl for w in ["كم الساعة", "الوقت الان", "الوقت الآن", "time"]):
            return f"🕐 الوقت الآن: {now.strftime('%H:%M')}"

        if any(w in tl for w in ["التاريخ", "ما هو اليوم", "date"]):
            days = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
            return f"📅 اليوم {days[now.weekday()]}، {now.strftime('%Y-%m-%d')}"

        m = re.match(r"^(?:ابحث لي عن|ابحث عن|بحث عن|دور على|search)\s+(.+)", t, re.IGNORECASE)
        if m:
            q = m.group(1).strip()
            webbrowser.open(build_search_url(q))
            return f"🔍 فتحت البحث عن: {q}"

        if re.match(r"^(?:افتح|open)\s+", tl):
            site = find_known_site(t, self.config.get("trusted_channels", {}))
            if site:
                name, url = site
                webbrowser.open(url)
                return f"✅ فتحت لك: {name}"
            return ("هذا الموقع ليس في قائمتي الموثوقة.\n"
                    "جرّب: افتح يوتيوب، افتح جوجل، افتح ويكيبيديا\n"
                    "أو قل: ابحث عن <اسم الموقع>")

        m = re.match(r"^تذكر (?:أن )?(.+)", t)
        if m:
            info = m.group(1).strip()
            key = "note_" + now.strftime("%Y%m%d%H%M%S")
            self.db.remember(key, info, "note")
            return f"🧠 حفظتها في ذاكرتي: {info}"

        if "ماذا تتذكر" in t or "ماذا تحفظ" in t:
            memories = self.db.all_memories()
            if not memories:
                return "لا توجد ذكريات بعد. قل: تذكر أن <معلومة>"
            lines = "\n".join(f"• {v}" for v in memories.values())
            return f"إليك ما أتذكره:\n{lines}"

        m = re.match(r"^(?:أضف مهمة|اضف مهمة|مهمة جديدة)[:：]?\s*(.+)", t)
        if m:
            title = m.group(1).strip()
            self.db.add_task(title)
            return f"📝 أضفت المهمة: {title}"

        if tl in ["المهام", "مهامي", "tasks"]:
            tasks = self.db.list_tasks()
            if not tasks:
                return "لا مهام لديك. أضف واحدة: أضف مهمة: <العنوان>"
            lines = "\n".join(f"{'✅' if done else '⬜'} {title}" for _, title, done in tasks)
            return f"مهامك:\n{lines}"

        if "وضع اللعب" in t:
            self.config.set("gaming_mode", True)
            return "🎮 تم تفعيل وضع اللعب (موارد محدودة).\nأعد تشغيل البرنامج ليُطبق."

        if "الوضع العادي" in t or "وضع العمل" in t:
            self.config.set("gaming_mode", False)
            return "💼 تم تفعيل الوضع العادي.\nأعد تشغيل البرنامج ليُطبق."

        return None

    # ===== المحادثة مع النموذج =====
    def _llm_chat(self, text):
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for user_msg, bot_msg in self.db.recent_conversations(4):
            messages.append({"role": "user", "content": user_msg})
            messages.append({"role": "assistant", "content": bot_msg})
        messages.append({"role": "user", "content": text})
        resp = self.llm.create_chat_completion(
            messages=messages, temperature=0.5, max_tokens=512)
        return resp["choices"][0]["message"]["content"].strip()

    def _basic_reply(self):
        return ("أعمل حالياً بالوضع الأساسي (النموذج الذكي غير محمّل).\n"
                f"السبب: {self.status_msg}\n\n"
                "المتاح الآن: فتح المواقع، البحث، الوقت والتاريخ، المهام، الذاكرة.\n"
                "لتفعيل الذكاء الكامل: الإعدادات ⚙️ ← تحميل النموذج")
