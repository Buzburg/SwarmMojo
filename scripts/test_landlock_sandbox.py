"""Verify the compiled Mojo enforcement path, including negative filesystem checks."""
from pathlib import Path
import subprocess
import sys


if __name__ == '__main__':
    result = subprocess.run([sys.executable, '-m', 'pytest', 'tests/test_native_sandbox.py', '-q', '--tb=short'],
                            cwd=Path(__file__).resolve().parents[1])
    raise SystemExit(result.returncode)
