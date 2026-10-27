#!/usr/bin/env python3
"""Source and /opt desktop entry point."""
from pathlib import Path
import sys
root = Path(__file__).resolve().parent
vendor = root.parent / 'vendor'
if vendor.is_dir():
    sys.path.insert(0, str(vendor))
sys.path.insert(0, str(root))
from src.desktop.app import main
raise SystemExit(main())
