"""Execution Environment Sandbox for SwarmMojo MetaHarness.

Binds workspace execution to SwarmMojo specialized engines:
- Rewind: Automatic microsecond checkpoints before file mutations
- PathCarry: Cross-platform reserved-name, illegal-character, and traversal audit
- Sieve: Compaction of tool and terminal logs (95%+ noise reduction)
- Horizon: DAG tracking and anti-loop vector circuit breaker
"""
from __future__ import annotations

import os
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.meta.manifest import EnvironmentConfig
from app.engines import (
    RewindEngine,
    audit_filename,
    audit_directory,
    PathAuditResult,
    compact_text,
    HorizonManager,
)


class ExecutionEnvironment:
    """Execution environment runtime wrapping an EnvironmentConfig with safety engines."""

    def __init__(self, config: EnvironmentConfig):
        self.config = config
        self.root_path = Path(config.root_path).resolve()
        self.root_path.mkdir(parents=True, exist_ok=True)

        self.rewind = RewindEngine(root=str(self.root_path)) if config.snapshot_on_action else None
        self.horizon = HorizonManager(root=str(self.root_path)) if config.circuit_breaker_enabled else None

        if self.rewind:
            self.rewind.init()
        if self.horizon:
            self.horizon.init(f"Environment: {config.name}")

    def audit_path_safety(self, rel_path: str) -> PathAuditResult:
        """Run PathCarry audit on a relative path."""
        res = PathAuditResult()
        audit_filename(os.path.basename(rel_path), rel_path, res)
        return res

    def read_file(self, rel_path: str) -> Dict[str, Any]:
        """Safely read a file within the environment."""
        target = (self.root_path / rel_path).resolve()
        if not str(target).startswith(str(self.root_path)):
            return {"error": "Path traversal attempt forbidden", "path": rel_path}

        if not target.exists():
            return {"error": "File not found", "path": rel_path}

        try:
            content = target.read_text(encoding="utf-8", errors="replace")
            return {"success": True, "path": rel_path, "content": content, "size": len(content)}
        except Exception as e:
            return {"error": str(e), "path": rel_path}

    def write_file(self, rel_path: str, content: str, checkpoint_msg: Optional[str] = None) -> Dict[str, Any]:
        """Safely write a file within the environment, taking a snapshot first."""
        target = (self.root_path / rel_path).resolve()
        if not str(target).startswith(str(self.root_path)):
            return {"error": "Path traversal attempt forbidden", "path": rel_path}

        # Path safety audit
        if self.config.path_audit_enabled:
            audit = self.audit_path_safety(rel_path)
            if not audit.is_clean:
                return {
                    "error": "PathCarry security audit failed",
                    "path": rel_path,
                    "violations": audit.errors,
                }

        # Snapshot before file change
        snapshot_meta = None
        if self.rewind:
            msg = checkpoint_msg or f"Pre-write snapshot for {rel_path}"
            snapshot_meta = self.rewind.snapshot(message=msg)

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return {
                "success": True,
                "path": rel_path,
                "bytes_written": len(content.encode("utf-8")),
                "snapshot": snapshot_meta,
            }
        except Exception as e:
            # If write failed, attempt rollback
            if self.rewind and snapshot_meta:
                self.rewind.rollback(cp_id=snapshot_meta["checkpoint"])
            return {"error": str(e), "path": rel_path}

    def execute_command(self, cmd: List[str] | str, timeout: int = 30) -> Dict[str, Any]:
        """Run a shell command, checking anti-loop circuit breaker and compacting logs."""
        cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)

        # Check Horizon anti-loop circuit breaker
        if self.horizon:
            step_check = self.horizon.record_action(cmd_str)
            if step_check.get("is_loop"):
                return {
                    "error": "Horizon circuit breaker triggered: repeated failed action loop detected",
                    "command": cmd_str,
                    "is_loop": True,
                }

        env = {**os.environ, **self.config.env_vars}
        try:
            res = subprocess.run(
                cmd,
                cwd=str(self.root_path),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=isinstance(cmd, str),
            )
            raw_stdout = res.stdout or ""
            raw_stderr = res.stderr or ""
            combined = (raw_stdout + "\n" + raw_stderr).strip()

            # Sieve log compaction
            if self.config.log_compaction and len(combined.splitlines()) > 40:
                compacted = compact_text(combined, context_window=2, max_lines=40)
                output_text = compacted["text"]
                compression_pct = compacted["compression_ratio_pct"]
            else:
                output_text = combined
                compression_pct = 0.0

            success = (res.returncode == 0)
            if self.horizon and not success:
                self.horizon.record_action(cmd_str, success=False)

            return {
                "success": success,
                "returncode": res.returncode,
                "output": output_text,
                "compression_pct": compression_pct,
            }
        except subprocess.TimeoutExpired:
            return {"error": f"Command timed out after {timeout}s", "command": cmd_str}
        except Exception as e:
            return {"error": str(e), "command": cmd_str}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "root_path": str(self.root_path),
            "snapshots_active": self.rewind is not None,
            "horizon_active": self.horizon is not None,
        }
