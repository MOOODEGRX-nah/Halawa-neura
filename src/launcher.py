"""
Neura Launcher — المشغّل الذكي (يُبنى كـ Neura.exe)
يفحص المتطلبات تلقائياً ثم يشغّل البرنامج بدون نافذة سوداء.
"""
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

if getattr(sys, "frozen", False):
    BASE = Path(sys.executable).parent
else:
    BASE = Path(__file__).resolve().parent.parent

PYDIR = BASE / "python-embed"
PY = PYDIR / "python.exe"
PY_URL = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"
PIP_URL = "https://bootstrap.pypa.io/get-pip.py"


def log(msg):
    print(f"[Neura] {msg}")


def download(url: str, dest: Path):
    log(f"تحميل {dest.name}...")
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    tmp.rename(dest)


def ensure_python():
    if PY.exists():
        return
    log("Python المدمج غير موجود — جاري التثبيت...")
    zip_path = BASE / "python-embed.zip"
    download(PY_URL, zip_path)
    PYDIR.mkdir(exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(PYDIR)
    pth = PYDIR / "python311._pth"
    if pth.exists():
        text = pth.read_text(encoding="utf-8").replace("#import site", "import site")
        pth.write_text(text, encoding="utf-8")
    pip_script = PYDIR / "get-pip.py"
    download(PIP_URL, pip_script)
    subprocess.run([str(PY), str(pip_script), "--no-warn-script-location"], check=False)
    zip_path.unlink(missing_ok=True)


def ensure_requirements():
    req = BASE / "requirements.txt"
    if not req.exists():
        return
    log("تثبيت المتطلبات (مع دعم Vulkan)...")
    subprocess.run(
        [str(PY), "-m", "pip", "install", "-r", str(req),
         "--extra-index-url", "https://abetlen.github.io/llama-cpp-python/whl/vulkan",
         "--no-warn-script-location"],
        cwd=str(BASE),
    )


def launch():
    env = os.environ.copy()
    env.setdefault("GGML_VULKAN", "1")
    # إضافة مجلد src/ إلى PYTHONPATH حتى يجد Python الوحدات الداخلية
    src_dir = str(BASE / "src")
    env["PYTHONPATH"] = src_dir + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.run(
        [str(PY), str(BASE / "src" / "neura_app.py")],
        cwd=str(BASE),
        env=env,
    )


def main():
    try:
        ensure_python()
        ensure_requirements()
        launch()
    except Exception as e:
        log(f"خطأ: {e}")
        input("اضغط Enter للإغلاق...")


if __name__ == "__main__":
    main()
