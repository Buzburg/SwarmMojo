"""Bounded broker actions; native Mojo owns socket access and framing."""
import ctypes
import json
import os
import re
import urllib.error
import urllib.request
from app.runtime_clock import current_time
from app.json_protocol import unique_object
from app.task_worker_client import request as worker_request


def landlock_abi() -> int:
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    return int(libc.syscall(ctypes.c_long(444), ctypes.c_void_p(), ctypes.c_size_t(0), ctypes.c_uint(1)))


def gateway(path: str, body: dict | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    key = os.getenv("ROMS_GATEWAY_API_KEY", "")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    data = json.dumps(body).encode() if body is not None else None
    port = int(os.getenv("ROMS_GATEWAY_PORT", "8844"))
    request = urllib.request.Request(f"http://127.0.0.1:{port}" + path, data, headers)
    with urllib.request.urlopen(request, timeout=120 if body else 3) as response:
        return json.load(response)


def handle(frame: bytearray) -> str:
    result: dict
    request_id = None
    version = None
    try:
        text = bytes(frame).decode("utf-8", errors="strict")
        if text in ("PING", "STATUS", "MOCK", "ANCHOR"):
            action, args = text.lower(), {}
        elif not text.lstrip().startswith("{"):
            action, args = text, {}
        else:
            request = json.loads(text, object_pairs_hook=unique_object)
            if not isinstance(request, dict) or type(request.get("v")) is not int or request["v"] != 1:
                raise ValueError("unsupported version")
            if set(request) - {"v", "id", "action", "args"}:
                raise ValueError("unknown fields")
            version = 1
            request_id = request.get("id")
            if request_id is not None and (not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', request_id)):
                raise ValueError("invalid id")
            action, args = request.get("action"), request.get("args", {})
            if not isinstance(action, str) or not isinstance(args, dict):
                raise ValueError("invalid action or args")
        if action not in {'chat', 'task.status', 'task.validate'} and args:
            raise ValueError('action does not accept arguments')
        if action == "ping":
            result = {"ok": True, "result": "pong"}
        elif action in ("status", "rwkv_status"):
            try:
                health = gateway("/health")
            except (OSError, ValueError):
                health = {"upstream_ready": False, "status": "unavailable"}
            result = {"ok": True, "transport": "native-mojo-unix",
                      "rwkv7": "ready" if health.get("upstream_ready") else "not_connected",
                      "roms": health.get("status"), "model": health.get("model"),
                      "sandbox": "disabled", "tool_execution": False}
        elif action == "mock":
            result = {"ok": True, "mock": True, "result": "Mock response; no model invoked"}
        elif action == "anchor":
            result = {"ok": True, "anchor": "[SYSTEM_ANCHOR]\nCurrent time: " + current_time() +
                      "\nCurrent external claims require source evidence; search is not configured."}
        elif action in ("sandbox_status", "landlock_probe"):
            abi = landlock_abi()
            result = {"ok": True, "sandbox": "disabled", "landlock_supported": abi >= 1,
                      "abi_version": abi, "landlock_abi": abi, "dry_run_only": True}
        elif action == "telemetry":
            result = {"ok": True, "type": "telemetry", "status": "unavailable"}
        elif action == "os_controller":
            result = {"ok": True, "controller": "unavailable", "hyprland_ipc": False,
                      "quickshell_ipc": False, "fastpath_enabled": False}
        elif action == "chat":
            prompt = args.get("prompt")
            if set(args) != {"prompt"} or not isinstance(prompt, str) or not prompt.strip():
                raise ValueError("chat requires a text prompt")
            response = gateway("/v1/chat/completions", {"messages": [{"role": "user", "content": prompt}],
                               "max_tokens": 256, "stream": False, "temperature": 0.3})
            result = {"ok": True, "result": response["choices"][0]["message"]["content"]}
        elif action == 'worker_status':
            result = worker_request('capabilities', timeout=45)
        elif action == 'worker_recovery':
            result = worker_request('recovery', timeout=5)
        elif action in {'task.status', 'task.validate'}:
            if set(args) != {'task_id'} or not isinstance(args['task_id'], str) or not re.fullmatch(r'[a-f0-9]{32}', args['task_id']):
                raise ValueError('A valid task ID is required')
            result = worker_request(action, args)
        else:
            result = {"ok": False, "error": "unsupported_v1_action" if version else "unsupported_command"}
    except UnicodeError:
        result = {"ok": False, "error": "unsupported_command"}
    except (ValueError, RecursionError, TypeError):
        result = {"ok": False, "error": "invalid_request"}
    except (OSError, urllib.error.URLError, KeyError, IndexError):
        result = {"ok": False, "error": "service_unavailable"}
    if version:
        result["v"] = version
    if request_id is not None:
        result["id"] = request_id
    return json.dumps(result, ensure_ascii=True, separators=(",", ":")) + "\n"
