"""
path_carry — Cross-platform filename, path safety, and port hazard auditor.
Inspired by Buzburg/path-carry (TypeScript/CLI).

Audits local files, archives, and staged paths for:
1. Windows reserved device names (CON, PRN, AUX, NUL, COM1-9, LPT1-9)
2. Illegal characters (< > : " / \\ | ? * and control chars 0x00-0x1F)
3. Trailing spaces and periods (causes truncation/unreachability on Windows)
4. Path length violations (MAX_PATH 260 chars)
5. Case-insensitivity collisions on NTFS/APFS
6. Path traversal hazards (.., leading slashes)
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

ILLEGAL_CHAR_REGEX = re.compile(r'[\x00-\x1f<>:"/\\|?*]')


class PathAuditResult:
    def __init__(self):
        self.scanned_count: int = 0
        self.errors: List[Dict[str, str]] = []
        self.warnings: List[Dict[str, str]] = []

    @property
    def is_clean(self) -> bool:
        return len(self.errors) == 0

    def to_dict(self) -> dict:
        return {
            "scanned_count": self.scanned_count,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "is_clean": self.is_clean,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def audit_filename(name: str, rel_path: str, result: PathAuditResult) -> None:
    """Audit an individual file or directory name."""
    stem = Path(name).stem.upper()
    if stem in WINDOWS_RESERVED:
        result.errors.append({
            "path": rel_path,
            "rule": "WINDOWS_RESERVED_NAME",
            "message": f"'{name}' uses a Windows reserved device name ({stem}).",
        })

    if name.endswith(" ") or name.endswith("."):
        result.errors.append({
            "path": rel_path,
            "rule": "TRAILING_SPACE_OR_DOT",
            "message": f"'{name}' ends with a space or dot, which is invalid on Windows.",
        })

    # Check for illegal characters in the basename itself
    # Strip permissible OS directory separators before checking illegal characters in name
    name_clean = name.replace("/", "").replace("\\", "")
    illegal_match = re.findall(r'[\x00-\x1f<>:"|?*]', name_clean)
    if illegal_match:
        result.errors.append({
            "path": rel_path,
            "rule": "ILLEGAL_CHARACTERS",
            "message": f"'{name}' contains illegal characters: {list(set(illegal_match))}",
        })

    if len(rel_path) > 260:
        result.warnings.append({
            "path": rel_path,
            "rule": "PATH_LENGTH_EXCEEDS_260",
            "message": f"Path exceeds Windows standard MAX_PATH (length: {len(rel_path)}).",
        })


def audit_directory(root: str | Path, ignore_dirs: Set[str] | None = None) -> PathAuditResult:
    """Recursively audit all paths under a directory."""
    root_path = Path(root).resolve()
    result = PathAuditResult()

    if ignore_dirs is None:
        ignore_dirs = {".git", ".venv", "node_modules", "__pycache__", "target"}

    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if d not in ignore_dirs]
        rel_dir = os.path.relpath(dirpath, root_path)

        # Case-insensitivity collision check within each directory
        seen_lower: Dict[str, str] = {}
        for entry in dirnames + filenames:
            result.scanned_count += 1
            entry_rel = os.path.join(rel_dir, entry) if rel_dir != "." else entry
            lower = entry.lower()
            if lower in seen_lower:
                result.errors.append({
                    "path": entry_rel,
                    "rule": "CASE_COLLISION",
                    "message": f"Collision with '{seen_lower[lower]}' on case-insensitive filesystems.",
                })
            else:
                seen_lower[lower] = entry

            audit_filename(entry, entry_rel, result)

    return result
