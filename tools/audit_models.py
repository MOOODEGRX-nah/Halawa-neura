"""Read GGUF metadata without loading weights; optionally hash local assets."""
import argparse
import hashlib
import json
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.runtime import model_directory

def read_metadata(path):
    with open(path, "rb") as f:
        def number(fmt):
            size = struct.calcsize("<" + fmt)
            data = f.read(size)
            if len(data) != size:
                raise ValueError("Truncated GGUF header")
            return struct.unpack("<" + fmt, data)[0]
        def string():
            n = number("Q")
            if n > 32_000_000:
                raise ValueError("Invalid GGUF string length")
            data = f.read(n)
            if len(data) != n:
                raise ValueError("Truncated GGUF string")
            return data.decode("utf-8", errors="replace")
        def value(kind):
            scalar = {0:"B", 1:"b", 2:"H", 3:"h", 4:"I", 5:"i", 6:"f", 7:"?", 10:"Q", 11:"q", 12:"d"}
            if kind in scalar:
                return number(scalar[kind])
            if kind == 8:
                return string()
            if kind == 9:
                subtype, count = number("I"), number("Q")
                if count > 10_000_000:
                    raise ValueError("Invalid GGUF array length")
                for _ in range(count):
                    value(subtype)
                return {"array_length": count}
            raise ValueError(f"Unknown GGUF type {kind}")
        if f.read(4) != b"GGUF":
            raise ValueError("Not a GGUF file")
        version = number("I")
        if version not in (2, 3):
            raise ValueError(f"Unsupported GGUF version {version}")
        tensors, count = number("Q"), number("Q")
        if count > 100_000:
            raise ValueError("Invalid metadata count")
        metadata = {}
        for _ in range(count):
            key = string()
            metadata[key] = value(number("I"))
        return {"gguf_version": version, "tensor_count": tensors,
                "metadata": {k:v for k,v in metadata.items()
                             if k.startswith("general.") or k == "tokenizer.chat_template"
                             or k.endswith("context_length")}}

def audit(directory, hashes=False):
    records = []
    for p in sorted(Path(directory).glob("*.gguf")):
        record = {"file": p.name, "size_bytes": p.stat().st_size,
                  "download_incomplete": Path(str(p) + ".aria2").exists()}
        try:
            record.update(read_metadata(p))
        except (OSError, ValueError, struct.error) as exc:
            record["error"] = str(exc)
        if hashes:
            digest = hashlib.sha256()
            with p.open("rb") as f:
                for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
                    digest.update(block)
            record["sha256"] = digest.hexdigest()
        records.append(record)
    return {"created_at": datetime.now(timezone.utc).isoformat(), "models_dir": str(directory), "models": records}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-dir", type=Path, default=model_directory())
    parser.add_argument("--sha256", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = json.dumps(audit(args.models_dir, args.sha256), ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(args.output)
    else:
        print(report)
