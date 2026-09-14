"""
نقطة بداية Neura — يجهز البيئة ثم يشغل الواجهة
"""
import sys
from pathlib import Path

# إصلاح ضروري لـ Python المدمج: إضافة مجلد هذا الملف لمسار الاستيراد
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import Config
import downloader


def console_download_if_missing(cfg):
    chat_model = cfg.models_dir / cfg.get("models.chat")
    if chat_model.exists():
        return
    print("=" * 50)
    print("أول تشغيل: يحتاج Neura إلى تحميل نموذج الذكاء (~4.7GB)")
    ans = input("هل تريد التحميل الآن؟ (y/n): ").strip().lower()
    if ans in ("y", "yes", "نعم"):
        def cb(d, t):
            pct = (d * 100 // t) if t else 0
            print(f"\rجاري التحميل... {pct}%", end="", flush=True)
        try:
            downloader.download_model("chat", cfg.models_dir, cb)
            print("\nاكتمل التحميل!")
        except Exception as e:
            print(f"\nفشل التحميل: {e}")
            print("يمكنك التحميل لاحقاً من داخل البرنامج (الإعدادات)")
    else:
        print("سيعمل Neura بالوضع الأساسي (يمكن التحميل لاحقاً من الإعدادات)")


def main():
    cfg = Config()
    if "--skip-download" not in sys.argv:
        try:
            console_download_if_missing(cfg)
        except (EOFError, KeyboardInterrupt):
            pass

    try:
        import flet as ft
        from neura_app import main as app_main
        ft.app(target=app_main, assets_dir=str(Path(__file__).resolve().parent.parent / "assets"))
    except ImportError:
        print("مكتبة flet غير مثبتة. شغل install.bat أولاً.")
        input("اضغط Enter للخروج...")


if __name__ == "__main__":
    main()
