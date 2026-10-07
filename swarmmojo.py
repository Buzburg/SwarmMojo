#!/usr/bin/env python3
"""SwarmMojo entry point; legacy ROMS commands and formats remain compatible."""
from __future__ import annotations

import os
from collections.abc import MutableMapping
from pathlib import Path


def configure_environment(environment: MutableMapping[str, str]) -> None:
    """Map explicit SwarmMojo settings before importing legacy runtime modules."""
    for name, value in list(environment.items()):
        if name.startswith("SWARMMOJO_"):
            environment["ROMS_" + name.removeprefix("SWARMMOJO_")] = value
    environment.setdefault("ROMS_STATE_DIR", str(Path.home() / ".swarmmojo"))


def main() -> None:
    configure_environment(os.environ)
    from roms import run_entry

    run_entry()


if __name__ == "__main__":
    main()
