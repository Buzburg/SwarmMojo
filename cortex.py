#!/usr/bin/env python3
"""
Backwards-compatible entrypoint redirecting legacy `python cortex.py ...` calls to ROMS (`roms.py`).
"""

from roms import run_entry

if __name__ == "__main__":
    run_entry()
