"""
يبني حزمة التحديث الجزئي: Neura-Update-vX.zip
الاستخدام: python tools/make_update_zip.py v0.1.3
"""
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from updater import sha256

BASE = Path(__file__).resolve().parent.parent
INCLUDE = ["src", "install.bat", "run.bat", "requirements.txt"]


def main(tag: str):
    files = []
    out = BASE / f"Neura-Update-{tag}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root in INCLUDE:
            p = BASE / root
            items = [p] if p.is_file() else [
                x for x in p.rglob("*")
                if x.is_file() and x.suffix != ".pyc" and "__pycache__" not in x.parts
            ]
            for f in items:
                rel = f.relative_to(BASE).as_posix()
                z.write(f, rel)
                files.append({"path": rel, "sha256": sha256(f)})
        manifest = {
            "version": tag.lstrip("v"),
            "full_update_required": False,
            "delete": [],
            "files": files,
        }
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"OK {out.name} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "v0.0.0")
