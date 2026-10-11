"""Packaging manifests and file listing for Swarmojo by Buzburg AI."""
from __future__ import annotations
from pathlib import Path
from typing import Set

DIRECTORIES = [
    "aeon",
    "app",
    "swarm_mojo",
    "docs",
    "scripts",
    "tests",
    "examples",
    ".github",
    "packaging",
]

ROOT_FILES = ["pyproject.toml", "README.md", "LICENSE"]
EXTRA_FILES = {"NOTICE"}

EXCLUDED_EXTENSIONS = {".pyc", ".db", ".sqlite", ".log"}


def source_files(root: Path) -> Set[Path]:
    """Finds release source files under root directory."""
    files: Set[Path] = set()
    for item in root.rglob("*"):
        if item.is_file():
            if item.suffix in EXCLUDED_EXTENSIONS:
                continue
            if any(part.startswith(".") and part != ".github" for part in item.relative_to(root).parts):
                continue
            files.add(item)
    return files
