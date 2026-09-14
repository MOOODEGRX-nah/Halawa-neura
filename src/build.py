"""
بناء Neura كملف EXE (اختياري)
الطريقة الموصى بها للتوزيع: مجلد البرنامج مع install.bat + run.bat
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def build():
    try:
        import PyInstaller  # noqa
    except ImportError:
        print("ثبّت PyInstaller أولاً: pip install pyinstaller")
        return

    args = [
        sys.executable, "-m", "PyInstaller",
        str(ROOT / "src" / "neura_launcher.py"),
        "--name", "Neura",
        "--noconfirm",
        "--windowed",
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build_tmp"),
        "--specpath", str(ROOT / "build_tmp"),
        "--collect-all", "flet",
        "--hidden-import", "sqlite3",
        "--hidden-import", "requests",
    ]

    try:
        import llama_cpp  # noqa
        args += ["--collect-all", "llama_cpp"]
        print("📦 سيتم تضمين llama_cpp في الملف")
    except ImportError:
        print("⚠️ llama_cpp غير مثبت — سيُبنى بدون محرك الذكاء")

    subprocess.run(args, cwd=ROOT, check=True)

    # تجهيز المجلد المحمول
    pkg = ROOT / "Neura-Portable"
    if pkg.exists():
        shutil.rmtree(pkg)
    pkg.mkdir()
    shutil.copy(ROOT / "dist" / "Neura.exe", pkg / "Neura.exe")
    (pkg / "models").mkdir()
    (pkg / "data").mkdir()
    (pkg / "logs").mkdir()
    shutil.copy(ROOT / "README.md", pkg / "README.md")
    print(f"\n✅ جاهز: {pkg}")
    print("انسخ المجلد كاملاً لأي جهاز وسيعمل (النماذج تُحمّل تلقائياً)")


if __name__ == "__main__":
    build()
