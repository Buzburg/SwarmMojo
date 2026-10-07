"""Dedicated ephemeral worker subprocess invoked by ProcessSandbox.

Reads a single JSON document from stdin:
    {"module": str, "func": str, "args": dict}

Resolves module and func via importlib/getattr, executes func(**args),
and outputs a JSON document to stdout:
    {"ok": True, "result": ...} or {"ok": False, "error": ..., "traceback": ...}
"""

from __future__ import annotations

import importlib
import json
import sys
import traceback


def _emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    sys.stdout.flush()


def main() -> int:
    raw = sys.stdin.read()
    if not raw or not raw.strip():
        _emit({"ok": False, "error": "empty stdin", "traceback": ""})
        return 2

    try:
        req = json.loads(raw)
    except json.JSONDecodeError as e:
        _emit({"ok": False, "error": f"JSON decode error: {e}", "traceback": ""})
        return 2

    if not isinstance(req, dict):
        _emit({"ok": False, "error": "request must be a JSON object", "traceback": ""})
        return 2

    module_name = req.get("module")
    func_name = req.get("func")
    args = req.get("args") or {}

    if not isinstance(module_name, str) or not module_name:
        _emit({"ok": False, "error": "'module' must be a non-empty string", "traceback": ""})
        return 3

    if not isinstance(func_name, str) or not func_name:
        _emit({"ok": False, "error": "'func' must be a non-empty string", "traceback": ""})
        return 3

    if not isinstance(args, dict):
        _emit({"ok": False, "error": "'args' must be an object", "traceback": ""})
        return 3

    try:
        mod = importlib.import_module(module_name)
        func = getattr(mod, func_name)
    except Exception as e:
        _emit({
            "ok": False,
            "error": f"Failed to resolve {module_name}.{func_name}: {e}",
            "traceback": traceback.format_exc(),
        })
        return 3

    try:
        result = func(**args)
        _emit({"ok": True, "result": result})
        return 0
    except Exception as e:
        _emit({
            "ok": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        })
        return 0


if __name__ == "__main__":
    sys.exit(main())
