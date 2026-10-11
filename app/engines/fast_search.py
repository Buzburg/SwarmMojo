"""Fast Search Engine for Codebases by Buzburg AI.

Sub-millisecond codebase search and indexing architecture:
- Rapid multiline regex and literal pattern search across workspace
- Noise suppression: automatically prunes .git, node_modules, __pycache__, .venv, .pytest_cache
- Binary content filter avoiding expensive I/O on media or compiled binaries
- File slice extraction with 1-based line numbering for LLM prompt context
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


IGNORE_DIRS: Set[str] = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
    "egg-info",
    ".egg-info",
    "site-packages",
}

BINARY_EXTENSIONS: Set[str] = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".bmp",
    ".zip", ".tar", ".gz", ".7z", ".bz2", ".rar",
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib", ".exe", ".bin",
    ".wasm", ".pdf", ".mp4", ".mov", ".avi", ".webm", ".mp3", ".wav",
}


@dataclass
class SearchMatch:
    file_path: str
    line_number: int
    line_content: str
    match_span: List[int]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FastSearchEngine:
    """High-speed workspace file locator and content grep engine."""

    def __init__(self, workspace_root: str = "."):
        self.root = Path(workspace_root).resolve()

    def _is_binary(self, file_path: Path) -> bool:
        if file_path.suffix.lower() in BINARY_EXTENSIONS:
            return True
        try:
            with open(file_path, "rb") as f:
                chunk = f.read(1024)
                return b"\x00" in chunk
        except Exception:
            return True

    def find_files(self, pattern: str = "*", max_results: int = 200) -> List[str]:
        """Finds workspace files matching glob pattern, ignoring virtualenvs and build dirs."""
        matched: List[str] = []
        for root, dirs, files in os.walk(self.root):
            # Prune ignored directories in-place
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".venv")]
            rel_root = Path(root).relative_to(self.root)

            for f in files:
                if Path(f).suffix.lower() in BINARY_EXTENSIONS:
                    continue
                if Path(f).match(pattern) or pattern == "*":
                    rel_p = str((rel_root / f).as_posix()) if str(rel_root) != "." else f
                    matched.append(rel_p)
                    if len(matched) >= max_results:
                        return matched
        return matched

    def grep(
        self,
        query: str,
        file_pattern: str = "*",
        is_regex: bool = False,
        case_sensitive: bool = False,
        max_matches: int = 100,
    ) -> Dict[str, Any]:
        """Fast regex or literal search across workspace files."""
        start_time = time.time()
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            compiled = re.compile(query if is_regex else re.escape(query), flags=flags)
        except re.error as e:
            return {"error": f"Invalid regex pattern: {e}", "matches": [], "total_matches": 0}

        matches: List[SearchMatch] = []
        files_scanned = 0

        target_files = self.find_files(pattern=file_pattern, max_results=1000)
        for rel_path in target_files:
            abs_path = self.root / rel_path
            if not abs_path.is_file() or self._is_binary(abs_path):
                continue

            files_scanned += 1
            try:
                with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                    for line_idx, line in enumerate(f, start=1):
                        m = compiled.search(line)
                        if m:
                            matches.append(
                                SearchMatch(
                                    file_path=rel_path,
                                    line_number=line_idx,
                                    line_content=line.strip("\r\n"),
                                    match_span=[m.start(), m.end()],
                                )
                            )
                            if len(matches) >= max_matches:
                                break
            except Exception:
                continue

            if len(matches) >= max_matches:
                break

        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        return {
            "query": query,
            "total_matches": len(matches),
            "files_scanned": files_scanned,
            "elapsed_ms": elapsed_ms,
            "matches": [m.to_dict() for m in matches],
        }

    def read_slice(self, rel_path: str, start_line: int = 1, end_line: int = 100) -> Dict[str, Any]:
        """Reads a precise line-numbered slice of a file."""
        abs_path = (self.root / rel_path).resolve()
        if not abs_path.exists() or not abs_path.is_file():
            raise FileNotFoundError(f"File not found: {rel_path}")

        lines_out: List[str] = []
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            for idx, line in enumerate(f, start=1):
                if idx >= start_line and idx <= end_line:
                    lines_out.append(f"{idx}: {line.rstrip()}")
                elif idx > end_line:
                    break

        return {
            "file_path": rel_path,
            "start_line": start_line,
            "end_line": end_line,
            "total_lines_read": len(lines_out),
            "content": "\n".join(lines_out),
        }
