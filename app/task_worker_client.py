"""Bounded client for the private, same-user validation service."""
import asyncio
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


def endpoint_and_frame(action: str, args: dict | None) -> tuple[Path, bytes]:
    path = socket_path()
    verify_directory(path.parent)
    info = path.lstat()
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise PermissionError('Worker endpoint must be a private same-user socket')
    frame = json.dumps({'v': 1, 'action': action, 'args': args or {}}, ensure_ascii=True).encode() + b'\n'
    if len(frame) > MAX_FRAME:
        raise ValueError('Worker request exceeds the frame limit')
    return path, frame


def verify_peer(client: socket.socket) -> None:
    _, uid, _ = struct.unpack('3i', client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    if uid != os.getuid():
        raise PermissionError('Worker peer is not this user')


def decode_response(response: bytearray) -> dict:
    value = json.loads(response.decode('utf-8'), object_pairs_hook=unique_object)
    if (type(value) is not dict or type(value.get('ok')) is not bool
            or type(value.get('v')) is not int or value['v'] != 1):
        raise ValueError('Invalid worker response')
    return value


def request(action: str, args: dict | None = None, *, timeout: float = 180) -> dict:
    path, frame = endpoint_and_frame(action, args)
    with socket.socket(socket.AF_UNIX) as client:
        deadline = time.monotonic() + timeout
        client.settimeout(timeout)
        client.connect(str(path))
        verify_peer(client)
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
        return decode_response(response)


async def async_request(action: str, args: dict | None = None, *, timeout: float = 180) -> dict:
    path, frame = endpoint_and_frame(action, args)
    loop = asyncio.get_running_loop()
    async with asyncio.timeout(timeout):
        with socket.socket(socket.AF_UNIX) as client:
            client.setblocking(False)
            await loop.sock_connect(client, str(path))
            verify_peer(client)
            await loop.sock_sendall(client, frame)
            response = bytearray()
            while not response.endswith(b'\n'):
                part = await loop.sock_recv(client, min(4096, MAX_RESPONSE + 1 - len(response)))
                if not part:
                    raise OSError('Worker disconnected before completing its response')
                response.extend(part)
                if len(response) > MAX_RESPONSE:
                    raise ValueError('Worker response exceeds the frame limit')
            return decode_response(response)
