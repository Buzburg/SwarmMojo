"""Bounded broker actions; native Mojo owns socket access and framing."""
import ctypes
import json
import os
import re
import urllib.error
import urllib.request
from app.runtime_clock import current_time
from app import broker_protocol as protocol
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


def build_status() -> dict:
    try:
        health = gateway('/health')
        if type(health) is not dict:
            raise ValueError('Invalid gateway health response')
    except (OSError, ValueError):
        health = {}
    model_ready = health.get('upstream_ready') is True
    gateway_ready = health.get('status') == 'ready'
    try:
        worker = worker_request('ping', timeout=1)
        worker_reachable = worker.get('ok') is True and worker.get('result') == 'pong'
    except (OSError, ValueError):
        worker_reachable = False
    return {
        'ok': True, 'transport': 'native-mojo-unix', 'profile': 'omarchy-wsl-test',
        'rwkv7': 'ready' if model_ready else 'not_connected',
        'roms': health.get('status') if health.get('status') in {'ready', 'degraded'} else 'unavailable',
        'model': health.get('model') if isinstance(health.get('model'), str) else None,
        # Retained compatibility fields refer only to arbitrary chat-triggered execution.
        'sandbox': 'disabled', 'sandbox_scope': 'arbitrary_chat_execution', 'tool_execution': False,
        'features': {
            'chat': {'state': 'ready' if model_ready and gateway_ready else 'unavailable',
                     'reason': 'Live gateway and model health' if model_ready and gateway_ready else 'Gateway or model is not ready'},
            'knowledge_library': {'state': 'not_probed',
                                  'reason': 'Status does not test indexing; use --library for text files, repositories and folders'},
            'project_workshop': {'state': 'available' if model_ready and gateway_ready and worker_reachable and os.getenv('ROMS_GATEWAY_API_KEY') else 'unavailable',
                                 'reason': 'Requires authenticated gateway, model and worker; enforcement probe, checks and operator approval still required'},
            'validation_worker': {'state': 'reachable' if worker_reachable else 'unavailable',
                                  'reason': 'Reachability only; worker_status runs an enforcement probe before validation'},
            'arbitrary_execution': {'state': 'disabled', 'reason': 'Only registered project validation commands are exposed'},
            'desktop_control': {'state': 'unavailable', 'reason': 'Hyprland and Quickshell adapters are not integrated'},
            'recurrent_state': {'state': 'unavailable', 'reason': 'Real runtime checkpoint and independent fork are not integrated'},
            'web_evidence': {'state': 'unavailable', 'reason': 'No search service is configured'},
            'guest_delegation': {'state': 'unavailable', 'reason': 'Provider routing is not integrated'},
            'training': {'state': 'unavailable', 'reason': 'A verified model training workflow is not integrated'},
        },
    }


def handle(frame: bytearray) -> str:
    result: dict
    request_id = None
    legacy = bytes(frame) in (b'PING', b'STATUS')
    try:
        if legacy:
            action, args = bytes(frame).decode('ascii').lower(), {}
        else:
            request = protocol.parse(bytes(frame))
            request_id = request['id']
            action, args = request['action'], request['args']
        supported = {'ping', 'status', 'rwkv_status', 'mock', 'anchor', 'sandbox_status', 'landlock_probe',
                     'telemetry', 'os_controller', 'chat', 'worker_status', 'worker_recovery', 'task.status', 'task.validate'}
        if action not in supported:
            raise protocol.ProtocolError('NOT_IMPLEMENTED', 'This broker action is not implemented')
        if action not in {'chat', 'task.status', 'task.validate'} and args:
            raise ValueError('action does not accept arguments')
        if action == "ping":
            result = {"ok": True, "result": "pong"}
        elif action in ("status", "rwkv_status"):
            result = build_status()
        elif action == "mock":
            result = {"ok": True, "mock": True, "result": "Mock response; no model invoked"}
        elif action == "anchor":
            result = {"ok": True, "anchor": "[SYSTEM_ANCHOR]\nCurrent time: " + current_time() +
                      "\nCurrent external claims require source evidence; search is not configured."}
        elif action in ("sandbox_status", "landlock_probe"):
            abi = landlock_abi()
            result = {"ok": True, "sandbox": "disabled", "landlock_supported": abi >= 1,
                      "abi_version": abi, "landlock_abi": abi, "dry_run_only": True,
                      "scope": "kernel_abi_probe", "required_abi": 3, "required_abi_available": abi >= 3,
                      "enforcement_verified": False, "enforcement_probe_action": "worker_status"}
        elif action == "telemetry":
            result = {"ok": True, "type": "telemetry", "status": "unavailable",
                      "reason": "Runtime telemetry is not integrated"}
        elif action == "os_controller":
            result = {"ok": True, "controller": "unavailable", "hyprland_ipc": False,
                      "quickshell_ipc": False, "fastpath_enabled": False,
                      "reason": "Desktop adapters are not integrated; use the reviewed project workshop for file edits"}
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
    except protocol.ProtocolError as error:
        return protocol.encode(protocol.error_response(error.code, str(error), request_id))
    except UnicodeError:
        result = {"ok": False, "error": "invalid_request"}
    except (ValueError, RecursionError, TypeError):
        result = {"ok": False, "error": "invalid_request"}
    except (OSError, urllib.error.URLError, KeyError, IndexError):
        result = {"ok": False, "error": "service_unavailable"}
    if legacy:
        return protocol.encode(result)
    if not result['ok']:
        messages = {'invalid_request': 'Arguments do not match the action contract',
                    'service_unavailable': 'A required local service is unavailable',
                    'worker_unavailable': 'The private validation worker is unavailable',
                    'worker_busy': 'The private validation worker is busy',
                    'recovery_required': 'Recorded worker cleanup must complete before validation',
                    'cleanup_required': 'Worker cleanup is incomplete; inspect the retained task',
                    'validation_failed': 'The selected checks failed; inspect the retained task',
                    'validation_rejected': 'The task cannot be validated in its current state',
                    'request_timeout': 'The local service deadline expired'}
        code = result.get('error')
        return protocol.encode(protocol.error_response(code.upper() if code in messages else 'SERVICE_FAILURE',
            messages.get(code, 'The local service could not complete this action'), request_id))
    payload = {key: value for key, value in result.items() if key not in {'ok', 'v', 'id'}}
    if set(payload) == {'result'}:
        payload = payload['result']
    return protocol.encode({'v': 1, 'id': request_id, 'ok': True, 'result': payload})
