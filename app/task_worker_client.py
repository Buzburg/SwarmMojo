"""Bounded client for the private, same-user validation service."""
import json
import os
from pathlib import Path
import socket
import stat
import struct
import time

from app.json_protocol import unique_object

MAX_FRAME = 4096
MAX_RESPONSE = 65536


def socket_path() -> Path:
    return Path(os.getenv('OMARCHY_TASK_WORKER_SOCKET',
                         f'/run/user/{os.getuid()}/omarchy-task-worker/worker.sock'))


def verify_directory(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise PermissionError('Worker socket directory must be private and owned by this user')


def request(action: str, args: dict | None = None, *, timeout: float = 180) -> dict:
    path = socket_path()
    verify_directory(path.parent)
    info = path.lstat()
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise PermissionError('Worker endpoint must be a private same-user socket')
    frame = json.dumps({'v': 1, 'action': action, 'args': args or {}}, ensure_ascii=True).encode() + b'\n'
    if len(frame) > MAX_FRAME:
        raise ValueError('Worker request exceeds the frame limit')
    with socket.socket(socket.AF_UNIX) as client:
        deadline = time.monotonic() + timeout
        client.settimeout(timeout)
        client.connect(str(path))
        _, uid, _ = struct.unpack('3i', client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if uid != os.getuid():
            raise PermissionError('Worker peer is not this user')
        client.sendall(frame)
        response = bytearray()
        while not response.endswith(b'\n'):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Worker response deadline expired')
            client.settimeout(remaining)
            part = client.recv(min(4096, MAX_RESPONSE + 1 - len(response)))
            if not part:
                raise OSError('Worker disconnected before completing its response')
            response.extend(part)
            if len(response) > MAX_RESPONSE:
                raise ValueError('Worker response exceeds the frame limit')
        value = json.loads(response.decode('utf-8'), object_pairs_hook=unique_object)
        if (type(value) is not dict or type(value.get('ok')) is not bool
                or type(value.get('v')) is not int or value['v'] != 1):
            raise ValueError('Invalid worker response')
        return value
