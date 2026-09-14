"""
تحميل نماذج الذكاء الاصطناعي من HuggingFace (مرة واحدة فقط)
"""
import requests
from pathlib import Path

MODELS = {
    "chat": {
        "url": "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m.gguf",
        "filename": "qwen2.5-7b-instruct-q4_k_m.gguf",
        "desc": "نموذج المحادثة Qwen 2.5 7B (~4.7GB)"
    },
    "vision": {
        "url": "https://huggingface.co/mys/ggml_llava-v1.5-7b/resolve/main/ggml-model-q4_k.gguf",
        "filename": "llava-v1.5-7b-q4_k.gguf",
        "desc": "نموذج الرؤية LLaVA 7B (~4.3GB)"
    },
    "vision_mmproj": {
        "url": "https://huggingface.co/mys/ggml_llava-v1.5-7b/resolve/main/mmproj-model-f16.gguf",
        "filename": "mmproj-model-f16.gguf",
        "desc": "معالج الصور mmproj (~600MB)"
    },
}


def download_model(key, dest_dir, progress_cb=None):
    """يحمّل نموذجاً مع دعم شريط التقدم. يعيد مسار الملف."""
    info = MODELS[key]
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / info["filename"]
    tmp = dest_dir / (info["filename"] + ".part")

    with requests.get(info["url"], stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
                done += len(chunk)
                if progress_cb:
                    progress_cb(done, total)

    tmp.replace(final)  # إعادة تسمية فقط بعد اكتمال التحميل
    return final
