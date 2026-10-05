"""Drop-in Code Search Plugin for ROMS (zg / ripgrep functionality).

Provides ultra-fast local code search across workspaces, repositories, and directories
without requiring any background server or external daemon.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import List

from app.config import BASE_DIR, BASE_REPOS_DIR, WORKSPACES_DIR

IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".gemini",
    "dist",
    "build",
}


def register_tools(mcp):
    """Registers high-speed codebase search tools with FastMCP."""

    @mcp.tool()
    def search_codebase(
        pattern: str,
        target_dir: str = "",
        file_extension: str = "",
        max_matches: int = 15,
    ) -> str:
        """Searches files in the codebase for a text pattern or regex (like zg / ripgrep).

        Args:
            pattern: Search string or regex pattern
            target_dir: Optional subfolder path (defaults to ROMS root or repos)
            file_extension: Filter by extension, e.g. '.py', '.mojo', '.md'
            max_matches: Maximum number of match snippets to return
        """
        search_root = Path(target_dir) if target_dir else BASE_DIR
        if not search_root.is_absolute():
            search_root = BASE_DIR / search_root

        if not search_root.exists():
            return f"Directory '{search_root}' does not exist."

        # Try ripgrep or zg if installed on the host
        rg_path = shutil.which("rg") or shutil.which("zvec-grep")
        if rg_path:
            cmd = [rg_path, "-n", "-m", str(max_matches), pattern, str(search_root)]
            if file_extension:
                cmd.extend(["-g", f"*{file_extension}"])
            for ig in IGNORE_DIRS:
                cmd.extend(["-g", f"!{ig}/*"])
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if res.stdout.strip():
                    return res.stdout.strip()
            except Exception:
                pass

        # Native high-performance streaming python search
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except Exception:
            regex = re.compile(re.escape(pattern), re.IGNORECASE)

        matches: List[str] = []
        ext_filter = file_extension.lower().strip() if file_extension else ""

        for root, dirs, files in os.walk(search_root):
            # Prune ignored directories in-place
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

            for fname in files:
                if ext_filter and not fname.lower().endswith(ext_filter):
                    continue

                fpath = Path(root) / fname
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        for line_num, line in enumerate(f, 1):
                            if regex.search(line):
                                rel_path = fpath.relative_to(BASE_DIR) if fpath.is_relative_to(BASE_DIR) else fpath
                                matches.append(f"{rel_path}:{line_num}: {line.strip()[:140]}")
                                if len(matches) >= max_matches:
                                    break
                except Exception:
                    continue

                if len(matches) >= max_matches:
                    break
            if len(matches) >= max_matches:
                break

        if not matches:
            return f"No matches found for pattern '{pattern}'."
        return "\n".join(matches)

    @mcp.tool()
    def find_symbol_definition(symbol_name: str, target_dir: str = "") -> str:
        """Finds definition of a function, class, or struct across python, mojo, or code files."""
        pattern = rf"(def|fn|class|struct|interface)\s+{re.escape(symbol_name)}\b"
        return search_codebase(pattern=pattern, target_dir=target_dir, max_matches=10)
