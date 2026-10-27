#!/usr/bin/env python3
"""Compatibility entry point for the native desktop application."""
import runpy
from pathlib import Path
if __name__ == '__main__':
    runpy.run_path(str(Path(__file__).resolve().parent / 'neura-desktop.py'), run_name='__main__')
