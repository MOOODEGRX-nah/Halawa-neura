"""
Neura AI-Bench — يقيس القوة الحقيقية لمحركات الـ AI في الكرت
مقياسان حاسمان:
  pp (Prompt Processing) = عمليات مصفوفات = محركات الـ AI  -> TFLOPS فعّالة
  tg (Token Generation)  = عرض نطاق الذاكرة               -> سرعة VRAM
+ مقارنة مع CPU لإظهار مضاعفة الـ GPU
"""
import subprocess, sys, time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
MODEL = BASE / "models" / "Qwen2.5-7B-Instruct-Q4_K_M.gguf"
PARAMS = 7.0e9


def vulkan_info():
    code = "from llama_cpp import llama_cpp; llama_cpp.llama_backend_init()"
    r = subprocess.run([sys.executable, "-c", code],
                       capture_output=True, text=True, timeout=120)
    return [l for l in r.stderr.splitlines() if "vulkan" in l.lower()]


def bench(n_gpu_layers, flash, label, threads=8):
    from llama_cpp import Llama
    t0 = time.perf_counter()
    llm = Llama(model_path=str(MODEL), n_ctx=2048, n_batch=512,
                n_gpu_layers=n_gpu_layers, n_threads=threads,
                flash_attn=flash, verbose=False)
    load = time.perf_counter() - t0

    prompt = ("Explain the importance of fast language models in one paragraph. " * 12)
    t0 = time.perf_counter()
    out = llm(prompt, max_tokens=1)
    dt = time.perf_counter() - t0
    pp_tok = out["usage"]["prompt_tokens"]
    pp_tps = pp_tok / dt if dt > 0 else 0
    tflops = 2 * PARAMS * pp_tok / 1e12 / dt if dt > 0 else 0

    t0 = time.perf_counter()
    out = llm("Count from 1 to 100:", max_tokens=100)
    dt = time.perf_counter() - t0
    tg_tok = out["usage"]["completion_tokens"]
    tg_tps = tg_tok / dt if dt > 0 else 0

    print(f"[{label}]")
    print(f"  load: {load:.1f}s | pp: {pp_tps:.0f} tok/s ({tflops:.1f} TFLOPS) | tg: {tg_tps:.1f} tok/s")
    return pp_tps, tg_tps, tflops


print("== جهاز Vulkan ودعم محركات المصفوفات ==")
for l in vulkan_info():
    print("  ", l)

print("\n== اختبار 1: GPU (Vulkan + FlashAttention) — محركات الـ AI ==")
g = bench(-1, True, "GPU-Vulkan-FA")

print("\n== اختبار 2: GPU بدون FlashAttention ==")
bench(-1, False, "GPU-Vulkan")

print("\n== اختبار 3: CPU فقط — للمقارنة ==")
c = bench(0, False, "CPU")

print("\n== الحكم ==")
speedup = g[0] / c[0] if c[0] > 0 else 0
print(f"  تسريع GPU/CPU في عمليات المصفوفات: {speedup:.1f}x")
print(f"  TFLOPS فعّالة على GPU: {g[2]:.1f}")
if g[2] >= 10:
    print("  ✅ محركات المصفوفات (الـ NPU المدمج) تعمل بكامل طاقتها — قوة ممتازة")
elif g[2] >= 4:
    print("  ⚠️ المحركات تعمل لكن دون طاقتها — جرّب n_batch=1024")
else:
    print("  ❌ المحركات غير مستغلة فعلياً — تحقق من تعريفات Vulkan")
