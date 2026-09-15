"""
المحدّث الذاتي الذكي:
- تحديث جزئي (~200KB) عبر Neura-Update-vX.zip
- تحقق SHA256 لكل ملف
- manifest.json يعالج الاستبدال والحذف
- fallback: full_update_required للنسخ الكاملة
"""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from cache import Cache
from config import APP_VERSION, get_base_path

REPO = "MOOODEGRX-nah/Halawa-neura"
API = f"https://api.github.com/repos/{REPO}/releases/latest"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ver_tuple(v: str):
    out = []
    for part in str(v).split("."):
        num = ""
        for ch in part:
            if ch.isdigit():
                num += ch
            else:
                break
        out.append(int(num) if num else 0)
    return tuple(out)


class Updater:
    def __init__(self):
        self.base = get_base_path()
        self.cache = Cache()

    def check(self):
        """يعيد معلومات الإصدار الأحدث، أو None إذا لا جديد"""
        with urllib.request.urlopen(API, timeout=15) as r:
            rel = json.load(r)
        tag = rel.get("tag_name", "").lstrip("v")
        if not tag or ver_tuple(tag) <= ver_tuple(APP_VERSION):
            return None
        asset = next((a for a in rel.get("assets", [])
                      if a["name"].startswith("Neura-Update")), None)
        if asset is None:
            return None
        return {"tag": tag, "asset": asset, "body": rel.get("body", "")}

    def apply(self, info, cb=None) -> bool:
        """يحمّل حزمة التحديث الجزئي ويطبقها"""
        if cb:
            cb("تحميل حزمة التحديث...")
        zip_path = self.cache.get_or_download(
            info["asset"]["browser_download_url"],
            info["asset"]["name"], cb=cb)

        tmp = Path(tempfile.mkdtemp())
        try:
            with zipfile.ZipFile(zip_path) as z:
                z.extractall(tmp)
            mfile = tmp / "manifest.json"
            if not mfile.exists():
                return False
            manifest = json.loads(mfile.read_text(encoding="utf-8"))

            if manifest.get("full_update_required"):
                if cb:
                    cb("تحديث كامل مطلوب — حمّل النسخة الكاملة من Releases")
                return False

            for relp in manifest.get("delete", []):
                p = self.base / relp
                if p.exists():
                    p.unlink()

            pip_needed = False
            for entry in manifest.get("files", []):
                src = tmp / entry["path"]
                dst = self.base / entry["path"]
                if not src.exists():
                    continue
                if dst.exists() and sha256(dst) == entry["sha256"]:
                    continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                if entry["path"] == "requirements.txt":
                    pip_needed = True

            if pip_needed:
                if cb:
                    cb("تثبيت مكتبات جديدة...")
                subprocess.run([sys.executable, "-m", "pip", "install", "-r",
                                str(self.base / "requirements.txt"),
                                "--no-warn-script-location"], cwd=self.base)

            self.cache.clean()
            return True
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
