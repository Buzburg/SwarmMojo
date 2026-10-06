"""Private rootless validation service; no apply, approval, shell or import API."""
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import socket
import struct
import tempfile

from app import patch_tasks, validation_policy
from app.config import WORKSPACES_DIR
from app.container_runner import CleanupRequired
from app.json_protocol import unique_object
from app.task_worker_client import MAX_FRAME, MAX_RESPONSE, socket_path, verify_directory


def task_summary(task: dict) -> dict:
    keys = ('id', 'state', 'source', 'base_commit', 'patch_sha256', 'validated_patch_sha256', 'error')
    return {key: task[key] for key in keys if key in task}


class Worker:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.clients: set[asyncio.Task] = set()

    async def probe(self) -> dict:
        WORKSPACES_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Retain the native directory on uncertain cleanup, just like real tasks.
        base = Path(tempfile.mkdtemp(prefix='capability-', dir=WORKSPACES_DIR))
        stage, control = base / 'stage', base / 'control'
        stage.mkdir(mode=0o700)
        control.mkdir(mode=0o700)
        (stage / 'probe.py').write_text('CAPABILITY_PROBE = True\n')
        try:
            result = await validation_policy.validate(stage, control, {'command': 'python.syntax', 'files': ['probe.py']})
            if result.returncode:
                raise RuntimeError('Native/container capability probe failed: ' + result.output[-1000:])
            policy = json.loads((control / 'policy.json').read_text())
            return {'available': True, 'policy_version': policy['version'], 'image_id': policy['image_id'],
                    'sandbox_sha256': policy['sandbox_sha256'], 'checked_at': datetime.now(timezone.utc).isoformat(),
                    'apply': False, 'arbitrary_commands': False}
        finally:
            from app.container_runner import confirmed_clean
            # A pre-launch failure has no container journal. Otherwise require confirmed absence.
            if not (control / 'container.json').exists() or confirmed_clean(control):
                import shutil
                shutil.rmtree(base)

    async def dispatch(self, request: dict) -> dict:
        if (type(request) is not dict or set(request) != {'v', 'action', 'args'}
                or type(request['v']) is not int or request['v'] != 1
                or type(request['action']) is not str or type(request['args']) is not dict):
            raise ValueError('Invalid worker request')
        action, args = request['action'], request['args']
        if action == 'ping' and not args:
            return {'result': 'pong'}
        if action in {'task.status', 'task.validate'}:
            if set(args) != {'task_id'} or not isinstance(args['task_id'], str):
                raise ValueError('A task ID is required')
            patch_tasks.identifier(args['task_id'])
            task = patch_tasks.load_task(args['task_id'])[1]
            if action == 'task.status':
                return {'task': task_summary(task)}
            if task['state'] != 'staged':
                raise ValueError('Only staged tasks can be validated')
        elif action != 'capabilities' or args:
            raise ValueError('Unsupported worker action or arguments')
        try:
            await asyncio.wait_for(self.lock.acquire(), 0.2)
        except TimeoutError:
            return {'ok': False, 'error': 'worker_busy'}
        try:
            capability = await self.probe()
            if action == 'capabilities':
                return {'capabilities': capability}
            try:
                task = await patch_tasks.validate_task(args['task_id'])
            except ValueError:
                task = patch_tasks.load_task(args['task_id'])[1]
                return {'ok': False, 'error': 'validation_failed' if task['state'] == 'failed' else 'validation_rejected',
                        'task': task_summary(task)}
            return {'task': task_summary(task), 'capabilities': capability}
        finally:
            self.lock.release()

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        handler = asyncio.current_task()
        if len(self.clients) >= 16:
            writer.close()
            return
        self.clients.add(handler)
        try:
            await self.respond(reader, writer)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass  # Peer disconnected; worker cleanup has already finished.
            self.clients.discard(handler)

    async def respond(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        operation = disconnect = None
        try:
            peer = writer.get_extra_info('socket')
            _, uid, _ = struct.unpack('3i', peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid != os.getuid():
                raise PermissionError('Wrong peer UID')
            raw = await asyncio.wait_for(reader.readuntil(b'\n'), 5)
            if len(raw) > MAX_FRAME:
                raise ValueError('Oversized request')
            request = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_object)
            operation = asyncio.create_task(self.dispatch(request))
            disconnect = asyncio.create_task(reader.read(1))
            await asyncio.wait({operation, disconnect}, return_when=asyncio.FIRST_COMPLETED)
            if disconnect.done():
                operation.cancel()
                await asyncio.gather(operation, return_exceptions=True)
                if disconnect.result():
                    raise ValueError('Only one request per connection is accepted')
                return
            result = {'ok': True, **await operation, 'v': 1}
        except (ValueError, UnicodeError, RecursionError, asyncio.LimitOverrunError, asyncio.IncompleteReadError):
            result = {'ok': False, 'v': 1, 'error': 'invalid_request'}
        except TimeoutError:
            result = {'ok': False, 'v': 1, 'error': 'request_timeout'}
        except CleanupRequired as error:
            result = {'ok': False, 'v': 1, 'error': 'cleanup_required', 'detail': str(error)[:512]}
        except (OSError, RuntimeError, KeyError, TypeError) as error:
            result = {'ok': False, 'v': 1, 'error': 'worker_unavailable', 'detail': str(error)[:512]}
        finally:
            for pending in (operation, disconnect):
                if pending is not None and not pending.done():
                    pending.cancel()
            await asyncio.gather(*(item for item in (operation, disconnect) if item is not None), return_exceptions=True)
        try:
            encoded = json.dumps(result, ensure_ascii=True).encode() + b'\n'
            if len(encoded) > MAX_RESPONSE:
                encoded = b'{"ok":false,"v":1,"error":"response_too_large"}\n'
            writer.write(encoded)
            await asyncio.wait_for(writer.drain(), 5)
        except (OSError, TimeoutError):
            pass  # Disconnected clients have no remaining response channel.


async def serve(path: Path | None = None) -> None:
    path = path or socket_path()
    verify_directory(path.parent)
    if path.exists() or path.is_symlink():
        raise FileExistsError('Refusing to replace an existing worker endpoint')
    worker = Worker()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for event in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(event, stop.set)
    # Bind explicitly: asyncio's path helper may remove pre-existing socket paths.
    sock = socket.socket(socket.AF_UNIX)
    try:
        sock.bind(str(path))
        path.chmod(0o600)
        identity = path.stat()
        sock.listen(16)
        sock.setblocking(False)
        server = await asyncio.start_unix_server(worker.handle, sock=sock, limit=MAX_FRAME)
        async with server:
            await stop.wait()
        pending = list(worker.clients)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        if path.exists() and path.lstat().st_ino == identity.st_ino:
            path.unlink()
    finally:
        sock.close()


if __name__ == '__main__':
    asyncio.run(serve())
