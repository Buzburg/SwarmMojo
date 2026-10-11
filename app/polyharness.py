"""PolyHarness integration for Swarmojo.

Provides programmatic and CLI invocation of the PolyHarness universal
agent configuration transpiler, progressive disclosure rule compiler,
and deterministic action guardrails.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


POLYHARNESS_ROOT = Path(__file__).resolve().parent.parent / "polyharness"
POLYHARNESS_BIN = POLYHARNESS_ROOT / "bin" / "polyharness.js"


def run_polyharness(argv: list[str] | None = None) -> int:
    """Execute PolyHarness CLI using node."""
    if argv is None:
        argv = sys.argv[1:]

    if not POLYHARNESS_BIN.is_file():
        sys.stderr.write(f"Error: PolyHarness executable not found at {POLYHARNESS_BIN}\n")
        return 1

    cmd = ["node", str(POLYHARNESS_BIN), *argv]
    try:
        proc = subprocess.run(cmd, check=False)
        return proc.returncode
    except FileNotFoundError:
        sys.stderr.write("Error: 'node' executable not found in PATH. Node.js is required for PolyHarness.\n")
        return 1


def main(argv: list[str] | None = None) -> int:
    return run_polyharness(argv)


if __name__ == "__main__":
    raise SystemExit(main())
