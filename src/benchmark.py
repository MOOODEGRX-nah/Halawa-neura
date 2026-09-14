"""Neura Benchmark - قياس شامل لقدرات الجهاز والديلاي الفعلي"""
import os, sys, time, subprocess
from pathlib import Path
import math

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parent.parent

def ps(cmd):
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                           capture_output=True, text=True, timeout=15)
        return r.stdout.strip()
    except Exception:
        return ""

def hr(t):
    print("\n" + "=" * 58); print(t); print("=" * 58)

def cpu_single():
    n = 2_000_000
    t0 = time.perf_counter(); s = 0.0
    for i in range(n): s += math.sqrt(i)
    return n / (time.perf_counter() - t0) / 1e6

def _work(n):
    s = 0.0
    for i in range(n): s += math.sqrt(i)
    return s

def cpu_multi(cores):
    import multiprocessing as mp
    n = 1_000_000
    t0 = time.perf_counter()
    with mp.Pool(cores) as p: p.map(_work, [n] * cores)
    return cores * n / (time.perf_counter() - t0) / 1e6

def ram_bw():
    size = 64 * 1024 * 1024
    a = bytearray(size)
    t0 = time.perf_counter()
    for _ in range(8): a = bytes(a)
    return 8 * size * 2 / (time.perf_counter() - t0) / 1e6

def disk_speed():
    tmp = ROOT / "data" / "_bench.tmp"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    size = 128 * 1024 * 1024
    chunk = b"\x00" * (1024 * 1024)
    t0 = time.perf_counter()
    with open(tmp, "wb") as f:
        for _ in range(size // (1024 * 1024)): f.write(chunk)
    w = time.perf_counter() - t0
    t0 = time.perf_counter()
    with open(tmp, "rb") as f:
        while f.read(8 * 1024 * 1024): pass
    r = time.perf_counter() - t0
    tmp.unlink(missing_ok=True)
    return size / w / 1e6, size / r / 1e6

def main():
    hr("[1/7] مواصفات الجهاز")
    cores = int(ps("(Get-CimInstance Win32_Processor).NumberOfCores") or os.cpu_count() or 8)
    print("CPU   :", ps("(Get-CimInstance Win32_Processor).Name"))
    print("Cores :", cores, "| Threads:", ps("(Get-CimInstance Win32_Processor).NumberOfLogicalProcessors"))
    print("RAM   :", ps("[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB,1)"), "GB @",
          ps("(Get-CimInstance Win32_PhysicalMemory | Measure-Object Speed -Average).Average"), "MHz (EXPO?)")
    print("GPU   :", ps("(Get-CimInstance Win32_VideoController).Name"))
    vram = ps("Get-ItemProperty 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Class\\{4d36e968-e325-11ce-bfc1-08002be10318}\\0000' -EA SilentlyContinue | Select -EA SilentlyContinue -ExpandProperty 'HardwareInformation.qwMemorySize'")
    if vram.isdigit(): print("VRAM  :", round(int(vram) / 1e9, 1), "GB")

    hr("[2/7] المعالج - نواة واحدة")
    s1 = cpu_single(); print(f"{s1:.1f} مليون عملية/ثانية")

    hr("[3/7] المعالج - كل الأنوية")
    try:
        sm = cpu_multi(cores)
        print(f"{sm:.1f} مليون عملية/ث | كفاءة التوازي: {sm / s1 / cores * 100:.0f}%")
    except Exception as e:
        sm = s1 * cores * 0.8; print("تعذر قياس متعدد (تقدير):", e)

    hr("[4/7] عرض نطاق الرام (تقريبي)")
    bw = ram_bw(); print(f"{bw / 1000:.1f} GB/s")

    hr("[5/7] سرعة القرص (تحميل النموذج)")
    w, r = disk_speed()
    print(f"كتابة: {w:.0f} MB/s | قراءة: {r:.0f} MB/s")
    print(f"زمن تحميل نموذج 4.7GB تقريبا: {4700 / r:.1f} ثانية")

    hr("[6/7] تقدير الديلاي النظري")
    print("حد CPU-GPU (PCIe 4.0 x16): ~26 GB/s -> لا يستخدم اصلا مع التفريغ الكامل")
    print("مهام CPU الطرفية (امان/نوايا/DB): < 5 ملي ثانية")
    print("الواجهة Flet: < 50 ملي ثانية")

    hr("[7/7] الاختبار الحقيقي للنموذج")
    try:
        from config import Config
        cfg = Config()
        model = cfg.models_dir / cfg.get("models.chat")
        if not model.exists():
            print("النموذج غير محمل بعد - اعد التشغيل بعد اكتمال التحميل")
        else:
            t0 = time.perf_counter()
            from llama_cpp import Llama
            llm = Llama(model_path=str(model), n_ctx=512, n_threads=cores, verbose=False)
            load = time.perf_counter() - t0
            print(f"زمن تحميل النموذج بالذاكرة: {load:.1f} ث")
            t0 = time.perf_counter()
            out = llm("مرحبا، اشرح لي ", max_tokens=48, temperature=0.7)
            gen = time.perf_counter() - t0
            toks = out.get("usage", {}).get("completion_tokens", 48)
            print(f"زمن توليد {toks} توكن: {gen:.2f} ث")
            print(f"السرعة: {toks / gen:.1f} توكن/ثانية  (وضع CPU الحالي)")
            print(f"الديلاي لأول رد: ~{gen / toks:.2f} ث لكل توكن")
    except ImportError:
        print("llama-cpp غير مثبت - وضع اساسي فقط")
    except Exception as e:
        print("خطأ بالاختبار الحقيقي:", e)

    hr("انتهى القياس - ارسل النتيجة للمساعد")

if __name__ == "__main__":
    main()
