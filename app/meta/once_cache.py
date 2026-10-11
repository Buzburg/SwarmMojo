"""Deduplicated Command Execution Cache (Once Engine) for SwarmMojo by Buzburg AI.

Adapted from once daemon architecture:
- Run expensive commands once, cache outputs in memory for a configurable TTL.
- Eliminates redundant tool invocations (e.g. repeated git status, system probes, lints).
- Content and environment-hashed keys with per-session isolation.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class OnceEntry:
    key_hash: str
    command: str
    cwd: str
    stdout: str
    stderr: str
    exit_code: int
    executed_at: float
    ttl_seconds: float
    hits: int = 0

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.executed_at) > self.ttl_seconds

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OnceExecutionCache:
    """In-memory cache daemon for command deduplication."""

    def __init__(self, default_ttl_seconds: float = 60.0):
        self.default_ttl = default_ttl_seconds
        self.cache: Dict[str, OnceEntry] = {}

    def _compute_key(self, command: str, cwd: str, tenant_id: str = "default") -> str:
        norm_cwd = str(Path(cwd).resolve())
        raw = f"{tenant_id}:{norm_cwd}:{command.strip()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get_or_run(
        self,
        command: str,
        cwd: str = ".",
        ttl_seconds: Optional[float] = None,
        tenant_id: str = "default",
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """Returns cached output if available and unexpired, otherwise executes and caches."""
        key = self._compute_key(command, cwd, tenant_id)
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl

        if not force_refresh and key in self.cache:
            entry = self.cache[key]
            if not entry.is_expired:
                entry.hits += 1
                return {
                    "from_cache": True,
                    "command": entry.command,
                    "stdout": entry.stdout,
                    "stderr": entry.stderr,
                    "exit_code": entry.exit_code,
                    "hits": entry.hits,
                    "age_s": round(time.time() - entry.executed_at, 2),
                }

        # Execute command
        start = time.time()
        try:
            res = subprocess.run(
                command,
                cwd=cwd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            stdout = res.stdout
            stderr = res.stderr
            exit_code = res.returncode
        except Exception as e:
            stdout = ""
            stderr = str(e)
            exit_code = -1

        entry = OnceEntry(
            key_hash=key,
            command=command,
            cwd=cwd,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            executed_at=time.time(),
            ttl_seconds=ttl,
            hits=0,
        )
        self.cache[key] = entry

        return {
            "from_cache": False,
            "command": command,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "hits": 0,
            "execution_ms": round((time.time() - start) * 1000, 2),
        }

    def purge_expired(self) -> int:
        expired_keys = [k for k, v in self.cache.items() if v.is_expired]
        for k in expired_keys:
            del self.cache[k]
        return len(expired_keys)

    def stats(self) -> Dict[str, Any]:
        return {
            "total_entries": len(self.cache),
            "total_hits": sum(v.hits for v in self.cache.values()),
        }
