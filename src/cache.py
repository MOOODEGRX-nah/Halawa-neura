"""
نظام Cache: لا تحمّل أي بايت مرتين
مكان التخزين: LocalAppData ثم Neura ثم cache
"""
import os
import urllib.request
from pathlib import Path


def cache_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    d = Path(local) / "Neura" / "cache" if local else Path.home() / ".neura-cache"
    (d / "wheels").mkdir(parents=True, exist_ok=True)
    (d / "updates").mkdir(parents=True, exist_ok=True)
    return d


def download(url: str, dest: Path, cb=None) -> Path:
    """تحميل مع شريط تقدم اختياري cb(done, total)"""
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=30) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length", 0))
        done = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if cb:
                cb(done, total)
    tmp.rename(dest)
    return dest


class Cache:
    def __init__(self):
        self.dir = cache_dir()

    def get_or_download(self, url: str, name: str, sub: str = "updates", cb=None) -> Path:
        p = self.dir / sub / name
        if p.exists() and p.stat().st_size > 0:
            return p
        return download(url, p, cb)

    def clean(self, keep: int = 3):
        for sub in ("updates",):
            files = sorted((self.dir / sub).glob("*"), key=lambda x: x.stat().st_mtime)
            for old in files[:-keep]:
                old.unlink(missing_ok=True)
