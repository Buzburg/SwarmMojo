"""Select the pinned Linux/Pixi Python and Mojo libraries, including spaced paths."""
import os
from pathlib import Path
import sys


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    prefix = Path(os.getenv("ROMS_PYTHON_PREFIX", str(root / ".pixi/envs/default")))
    env = os.environ.copy()
    env.update(PYTHONHOME=str(prefix), PYTHONPATH=str(root),
               MOJO_PYTHON_LIBRARY=str(prefix / "lib/libpython3.12.so"),
               MODULAR_HOME=str(prefix / "share/max"),
               LD_LIBRARY_PATH=str(prefix / "lib"),
               PATH=str(prefix / "bin") + ":" + env.get("PATH", ""))
    if len(sys.argv) < 2:
        raise SystemExit("Usage: run_linux_env.py PROGRAM [ARGS...]")
    os.chdir(root)
    os.execvpe(sys.argv[1], sys.argv[1:], env)


if __name__ == "__main__":
    main()
