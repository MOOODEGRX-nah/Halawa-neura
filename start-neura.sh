#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"
PYTHON="${NEURA_PYTHON:-$PROJECT_DIR/.venv/bin/python}"
if [[ ! -x "$PYTHON" && -z "${NEURA_PYTHON:-}" && -x "$HOME/Downloads/ai/neura-repo/.venv/bin/python" ]]; then
  PYTHON="$HOME/Downloads/ai/neura-repo/.venv/bin/python"
fi
if [[ ! -x "$PYTHON" ]]; then
  echo 'Python environment missing. Follow README_AR.md, or set NEURA_PYTHON to an existing environment.' >&2
  exit 1
fi
"$PYTHON" -c 'import fastapi, uvicorn, yaml, pydantic, llama_cpp' || {
  echo 'Missing dependencies. See requirements-backend.txt and README_AR.md.' >&2
  exit 1
}
echo 'Neura: http://127.0.0.1:8000/ (one API process, one model at a time)'
exec "$PYTHON" -m uvicorn src.backend.api:app --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
