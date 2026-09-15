"""
Neura Doctor — فحص شامل ودقيق لكل مكونات النظام
الاستخدام: python-embed/python.exe tools/diagnose.py
"""
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SRC = BASE / "src"
sys.path.insert(0, str(SRC))

RESULTS = []


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as ex:
        ok, detail = False, f"{type(ex).__name__}: {ex}"
    RESULTS.append(ok)
    tag = " OK " if ok else "FAIL"
    print(f"[{tag}] {name}: {detail}")
    return ok


print("=" * 62)
print(f"  Neura Doctor — {BASE}")
print("=" * 62)

# 1) البنية
def t_structure():
    need = [SRC, BASE / "python-embed" / "python.exe", BASE / "models",
            BASE / "data", BASE / "logs", BASE / "requirements.txt"]
    miss = [str(p.name) for p in need if not p.exists()]
    return (not miss, "كل الملفات موجودة" if not miss else f"ناقص: {miss}")
check("بنية المجلد", t_structure)

# 2) Python
def t_python():
    v = sys.version_info
    return (v >= (3, 9), f"Python {v.major}.{v.minor}.{v.micro}")
check("إصدار Python", t_python)

# 3-10) المكتبات
for lib, nice in [("flet", "الواجهة"), ("requests", "الشبكة"),
                  ("PIL", "الصور"), ("mss", "التقاط الشاشة"),
                  ("llama_cpp", "محرك الذكاء"), ("speech_recognition", "التعرف على الصوت"),
                  ("pyttsx3", "النطق"), ("github", "PyGithub")]:
    def t(lib=lib, nice=nice):
        m = __import__(lib)
        ver = getattr(m, "__version__", "مثبتة")
        return True, f"{nice} ({ver})"
    check(f"مكتبة {lib}", t)

# 11) Vulkan
def t_vulkan():
    code = "from llama_cpp import llama_cpp; llama_cpp.llama_backend_init()"
    r = subprocess.run([sys.executable, "-c", code],
                       capture_output=True, text=True, timeout=90)
    m = re.search(r"ggml_vulkan: Found (\d+) Vulkan devices", r.stderr)
    if not m:
        return False, "لا أجهزة Vulkan مكتشفة"
    d = re.search(r"ggml_vulkan: 0 = (.+?) \|", r.stderr)
    return True, f"{m.group(1)} جهاز: {d.group(1) if d else 'غير معروف'}"
check("أجهزة Vulkan", t_vulkan)

# 12) النماذج
def t_models():
    import config as C
    cfg = C.Config()
    info = cfg.list_available_models()
    active = cfg.get("models.chat")
    found = any(n == active for n, _ in info["chat"])
    sizes = {n: mb for n, mb in info["chat"]}
    return (found, f"{len(info['chat'])} محادثة / {len(info['vision'])} رؤية | "
                   f"النشط: {active} ({sizes.get(active, 0)} MB) "
                   + ("موجود" if found else "— غير موجود"))
check("النماذج والمنتقي", t_models)

# 13) صلاحيات الكتابة
def t_write():
    bad = []
    for d in ("data", "logs", "models"):
        p = BASE / d / "_wt.tmp"
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x", encoding="utf-8")
            p.unlink()
        except Exception:
            bad.append(d)
    return (not bad, "كتابة سليمة في data/logs/models" if not bad else f"مشكلة: {bad}")
check("صلاحيات الكتابة", t_write)

# 14) Cache
def t_cache():
    import cache
    d = cache.cache_dir()
    return d.exists(), str(d)
check("نظام Cache", t_cache)

# 15) اتصال GitHub + المحدّث
def t_net():
    url = "https://api.github.com/repos/MOOODEGRX-nah/Halawa-neura/releases/latest"
    with urllib.request.urlopen(url, timeout=15) as r:
        rel = json.load(r)
    import updater
    info = updater.Updater().check()
    state = f"تحديث متاح: v{info['tag']}" if info else "أنت على أحدث إصدار"
    return True, f"آخر Release: {rel['tag_name']} | {state}"
check("GitHub والمحدّث", t_net)

# 16) الأمان وقاعدة البيانات
def t_safety():
    try:
        import safety
        import database
        return True, "وحدتا الأمان وقاعدة البيانات تستوردان بنجاح"
    except ImportError as e:
        return False, f"مكتبة مفقودة: {e}"
check("الأمان + قاعدة البيانات", t_safety)

# 17) الصوت TTS
def t_tts():
    import pyttsx3
    e = pyttsx3.init()
    n = len(e.getProperty("voices"))
    e.stop()
    return True, f"{n} صوت متاح في النظام"
check("محرك النطق TTS", t_tts)

# 18) سرعة التوليد (GPU أم CPU)
def t_speed():
    import config as C
    from llama_cpp import Llama
    cfg = C.Config()
    m = cfg.models_dir / cfg.get("models.chat")
    if not m.exists():
        return False, "النموذج غير موجود — لا يمكن القياس"
    llm = Llama(model_path=str(m), n_ctx=512, n_gpu_layers=-1,
                n_threads=4, verbose=False)
    llm("تسخين ", max_tokens=4)
    t0 = time.perf_counter()
    out = llm("مرحبا ", max_tokens=32)
    tps = out["usage"]["completion_tokens"] / (time.perf_counter() - t0)
    gpu = tps >= 20
    return (gpu, f"{tps:.1f} توكن/ثانية — " + ("GPU نشط عبر Vulkan" if gpu else "تحذير: يبدو CPU فقط"))
check("سرعة التوليد", t_speed)

print("=" * 62)
good, total = sum(RESULTS), len(RESULTS)
print(f"  النتيجة النهائية: {good}/{total} فحص ناجح")
if good == total:
    print("  Neura سليم تماماً وجاهز بكامل قوته")
else:
    print("  راجع أسطر FAIL أعلاه — كل سطر يذكر السبب بدقة")
print("=" * 62)
