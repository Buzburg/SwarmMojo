"""Portable leaf-name validation for agent-accessible Markdown files."""
import re
from pathlib import Path

_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10)}

def markdown_path(directory: Path, name: str) -> Path:
    """Reject traversal, Windows device names, and symlink escapes."""
    stem = name.strip()
    if stem.lower().endswith(".md"):
        stem = stem[:-3]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _-]{0,119}", stem) or stem.upper() in _RESERVED:
        raise ValueError("Use a simple document name: letters, digits, spaces, underscores or hyphens.")
    root = directory.resolve()
    target = root / f"{stem}.md"
    if target.is_symlink() or target.resolve().parent != root:
        raise ValueError("Document must remain within its configured folder.")
    return target
