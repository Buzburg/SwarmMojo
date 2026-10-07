"""Process-isolated Tool Runner for Omarchy OS.

Ported from NSagent sandbox.py. Executes registered tools in fresh,
isolated Python subprocesses, preventing crashes, memory leaks, or
segfaults from bringing down the main ROMS or Goose daemon.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional, Tuple


class ProcessSandbox:
    """Process-isolated tool runner."""

    _WORKER_MODULE = "app.sandbox_worker"

    def __init__(self, max_workers: int = 4) -> None:
        self._tools: Dict[str, Tuple[str, str]] = {}
        self._validators: Dict[str, Callable[[Dict[str, Any]], None]] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="sandbox-runner")

    def register(
        self,
        name: str,
        module_name: str,
        func_name: str,
        *,
        validator: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        """Register a tool under a public alias."""
        if not name or not isinstance(name, str):
            raise ValueError("tool name must be a non-empty string")
        if not module_name or not isinstance(module_name, str):
            raise ValueError("module_name must be a non-empty string")
        if not func_name or not isinstance(func_name, str):
            raise ValueError("func_name must be a non-empty string")

        with self._lock:
            self._tools[name] = (module_name, func_name)
            if validator is not None:
                self._validators[name] = validator

    def registered(self) -> Tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._tools.keys()))

    def invoke(
        self,
        name: str,
        args: Optional[Dict[str, Any]] = None,
        timeout: float = 10.0,
    ) -> Future:
        """Asynchronously dispatches a tool execution into an isolated subprocess."""
        args_payload = dict(args or {})
        return self._pool.submit(self._invoke_sync, name, args_payload, timeout)

    def invoke_sync(
        self,
        name: str,
        args: Optional[Dict[str, Any]] = None,
        timeout: float = 10.0,
    ) -> Dict[str, Any]:
        """Synchronously executes the tool in an isolated subprocess."""
        return self._invoke_sync(name, dict(args or {}), timeout)

    def _invoke_sync(
        self,
        name: str,
        args: Dict[str, Any],
        timeout: float,
    ) -> Dict[str, Any]:
        with self._lock:
            if name not in self._tools:
                return {
                    "ok": False,
                    "error": f"Unknown tool: {name!r}",
                    "traceback": "",
                }
            module_name, func_name = self._tools[name]
            validator = self._validators.get(name)

        if validator is not None:
            try:
                validator(args)
            except Exception as e:
                return {
                    "ok": False,
                    "error": f"Args rejected by validator: {e}",
                    "traceback": "",
                }

        request = {
            "module": module_name,
            "func": func_name,
            "args": args,
        }
        payload = json.dumps(request).encode("utf-8")

        try:
            proc = subprocess.run(
                [sys.executable, "-m", self._WORKER_MODULE],
                input=payload,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "error": "TimeoutExpired",
                "traceback": f"Tool {name!r} exceeded {timeout}s limit.",
            }
        except OSError as e:
            return {
                "ok": False,
                "error": f"Sandbox spawn failed: {e}",
                "traceback": "",
            }

        stdout_raw = proc.stdout.decode("utf-8", errors="replace").strip()
        stderr_raw = proc.stderr.decode("utf-8", errors="replace").strip()

        if not stdout_raw:
            return {
                "ok": False,
                "error": f"Worker exited with code {proc.returncode} and empty stdout",
                "traceback": stderr_raw,
            }

        try:
            resp = json.loads(stdout_raw)
        except json.JSONDecodeError:
            return {
                "ok": False,
                "error": f"Worker output non-JSON stdout (exit code {proc.returncode})",
                "traceback": f"stdout: {stdout_raw}\nstderr: {stderr_raw}",
            }

        if stderr_raw and isinstance(resp, dict):
            prev = resp.get("traceback") or ""
            resp["traceback"] = f"{prev}\n[stderr]: {stderr_raw}".strip()

        return resp


# Global process sandbox singleton
process_sandbox = ProcessSandbox()
