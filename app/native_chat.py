"""Bounded, cancellation-owned Mojo inference subprocess for scoped broker chat."""
import asyncio
import json
import os
import re
from pathlib import Path

from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment

from app.broker_protocol import ProtocolError
from app.container_runner import _settle
from app.json_protocol import unique_object
from app.native_model_worker import ROOT, worker_manifest

TIMEOUT = 110.0
OUTPUT_LIMIT = 65536
_active: set[int] = set()
_runtimes: dict[int, dict] = {}
_cleanup_failed = False


def status() -> dict:
    configured = bool(os.getenv('OMARCHY_NATIVE_CHAT_BINARY'))
    return {'state': 'cleanup_required' if _cleanup_failed else 'running' if _active else 'idle' if configured else 'unconfigured',
            'active_processes': len(_active), 'session_lifetime': 'one_request',
            'loaded_sessions': len(_runtimes), 'sessions': [{'pid': pid, **facts} for pid, facts in _runtimes.items()],
            'reason': 'Each request verifies and loads its model; no idle model session is retained'}


def environment() -> dict[str, str]:
    names = ('HOME', 'USER', 'LOGNAME', 'PATH', 'LANG', 'PYTHONHOME', 'LD_LIBRARY_PATH',
             'MOJO_PYTHON_LIBRARY', 'MODULAR_HOME', 'ROMS_PYTHON_PREFIX', 'OMARCHY_NATIVE_MODEL')
    return {**{key: os.environ[key] for key in names if key in os.environ},
            'PYTHONPATH': str(ROOT), 'PYTHONNOUSERSITE': '1'}


async def read_bounded(stream: asyncio.StreamReader) -> bytes:
    data = bytearray()
    while block := await stream.read(8192):
        data.extend(block)
        if len(data) > OUTPUT_LIMIT:
            raise ProtocolError('RESPONSE_TOO_LARGE', 'Native worker output exceeded its byte limit')
    return bytes(data)


def validate_runtime(runtime: object) -> dict:
    if (type(runtime) is not dict or set(runtime) != {'model_sha256', 'adapter_sha256', 'runtime_revision',
            'backend', 'context', 'threads', 'sampler', 'generated_tokens', 'session_lifetime'} or
            any(not isinstance(runtime[key], str) or not re.fullmatch(r'[0-9a-f]{64}', runtime[key])
                for key in ('model_sha256', 'adapter_sha256')) or
            not isinstance(runtime['runtime_revision'], str) or not re.fullmatch(r'[0-9a-f]{40}', runtime['runtime_revision']) or
            runtime['backend'] != 'cpu' or runtime['context'] != 4096 or runtime['threads'] != 4 or
            type(runtime['context']) is not int or type(runtime['threads']) is not int or
            runtime['sampler'] != 'greedy-json-answer-v1' or runtime['session_lifetime'] != 'one_request' or
            type(runtime['generated_tokens']) is not int or not 0 <= runtime['generated_tokens'] <= 512):
        raise ValueError('Invalid native runtime facts')
    return runtime


async def read_native(stream: asyncio.StreamReader, pid: int) -> dict | None:
    messages = []
    size = 0
    while True:
        try:
            line = await stream.readline()
        except ValueError:
            raise ProtocolError('RESPONSE_TOO_LARGE', 'Native worker frame exceeded its byte limit') from None
        if not line:
            break
        size += len(line)
        if size > OUTPUT_LIMIT:
            raise ProtocolError('RESPONSE_TOO_LARGE', 'Native worker output exceeded its byte limit')
        value = json.loads(line, object_pairs_hook=unique_object)
        if not messages:
            if type(value) is not dict or set(value) != {'event', 'native_runtime'} or value['event'] != 'ready':
                raise ValueError('Native worker omitted its loaded-session event')
            runtime = validate_runtime(value['native_runtime'])
            if runtime['generated_tokens'] != 0:
                raise ValueError('Invalid initial native runtime state')
            _runtimes[pid] = runtime
        elif len(messages) == 1:
            if type(value) is not dict or set(value) != {'choices', 'native_runtime'}:
                raise ValueError('Invalid native worker response')
            runtime = validate_runtime(value['native_runtime'])
            if any(runtime[key] != _runtimes[pid][key] for key in runtime if key != 'generated_tokens'):
                raise ValueError('Native runtime identity changed during generation')
        else:
            raise ValueError('Native worker returned extra frames')
        messages.append(value)
    return messages[1] if len(messages) == 2 else None


async def run_worker(binary: Path, payload: bytes, env: dict[str, str]) -> dict:
    process, cancelled = await _settle(asyncio.create_task(asyncio.create_subprocess_exec(
        str(binary), str(os.getpid()), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE, env=env, cwd=ROOT, start_new_session=True)))
    _active.add(process.pid)
    readers = [asyncio.create_task(read_native(process.stdout, process.pid)), asyncio.create_task(read_bounded(process.stderr))]

    async def cleanup_owned() -> None:
        for reader in readers:
            if not reader.done():
                reader.cancel()
        await asyncio.gather(*readers, return_exceptions=True)
        async def discard(stream) -> None:
            while await stream.read(8192):
                pass
        async def reap() -> None:
            await asyncio.gather(process.wait(), discard(process.stdout), discard(process.stderr))
        if process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(reap(), 5)
            except TimeoutError:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await asyncio.wait_for(reap(), 5)
        else:
            await asyncio.wait_for(reap(), 5)
        _active.discard(process.pid)
        _runtimes.pop(process.pid, None)

    async def cleanup() -> None:
        global _cleanup_failed
        try:
            await cleanup_owned()
        except BaseException:
            _cleanup_failed = True
            raise

    try:
        if cancelled:
            raise asyncio.CancelledError
        async with asyncio.timeout(TIMEOUT):
            process.stdin.write(payload)
            await process.stdin.drain()
            process.stdin.close()
            value, _ = await asyncio.gather(*readers)
            code = await process.wait()
        if code:
            raise ProtocolError('NATIVE_MODEL_FAILURE', 'The native model worker did not complete the request')
        if value is None:
            raise ValueError('Invalid native worker response')
        return value
    except TimeoutError:
        raise ProtocolError('REQUEST_TIMEOUT', 'The native generation deadline expired') from None
    finally:
        _, interrupted = await _settle(asyncio.create_task(cleanup()))
        if interrupted:
            raise asyncio.CancelledError


async def generate(messages: list[dict[str, str]]) -> dict:
    if _cleanup_failed:
        raise ProtocolError('CLEANUP_REQUIRED', 'A previous native worker could not be reaped')
    binary = Path(os.environ['OMARCHY_NATIVE_CHAT_BINARY'])
    # Small artifact/source checks stay outside the model worker; large model hashing
    # happens inside that owned process so status and cancellation remain responsive.
    worker_manifest(binary)
    template = SandboxedEnvironment(undefined=StrictUndefined, autoescape=False).from_string(
        (ROOT / 'config/rwkv-user-assistant.jinja').read_text())
    prompt = template.render(messages=messages, add_generation_prompt=True)
    if len(prompt.encode()) > 16384:
        raise ProtocolError('REQUEST_TOO_LARGE', 'Rendered native prompt exceeds its byte budget')
    return await run_worker(binary, json.dumps({'prompt': prompt, 'tokens': 512}).encode(), environment())
