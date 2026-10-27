#!/usr/bin/env bash
set -euo pipefail
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf -- "$TEMP_DIR"' EXIT
curl --fail --location --proto '=https' --tlsv1.2 https://raw.githubusercontent.com/MOOODEGRX-nah/Halawa-neura/main/packaging/linux/install.py --output "$TEMP_DIR/install.py"
python "$TEMP_DIR/install.py"
