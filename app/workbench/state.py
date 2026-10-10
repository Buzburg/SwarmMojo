"""Real recurrent state, immutable authenticated checkpoints, and independent forks.

This operator API is separate from the installed HTTP service. Greedy sampling has
no RNG state; stochastic sampling and state fusion are deliberately unsupported.
"""
from __future__ import annotations

import ctypes as c
try:
    import fcntl
except ImportError:
    fcntl = None
import hashlib
import hmac
import json
import os
import re
import threading
import uuid
from contextlib import nullcontext
from pathlib import Path

from .receipts import private_directory

ROOT = Path(__file__).resolve().parents[2]
MAX_STATE = 512 * 1024 * 1024


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def read_private(path: Path, limit: int) -> bytes:
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)), 'rb') as stream:
        import stat
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError('Invalid or oversized checkpoint file')
        data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError('Checkpoint grew beyond its limit')
        return data


class CheckpointStore:
    def __init__(self, root: Path, key: bytes, *, max_total_bytes: int = 2 * 1024 * 1024 * 1024) -> None:
        self.root = private_directory(root)
        if len(key) != 32:
            raise ValueError('Expected a 32-byte private checkpoint authentication key')
        self.key = key
        if type(max_total_bytes) is not int or max_total_bytes < 1:
            raise ValueError('Invalid checkpoint storage budget')
        self.max_total_bytes = max_total_bytes

    def _path(self, name: str) -> Path:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', name):
            raise ValueError('Invalid checkpoint name')
        path = self.root / name
        if path.is_symlink():
            raise ValueError('Checkpoint cannot be a symlink')
        return path

    def save(self, name: str, session: Session) -> dict:
        with os.fdopen(os.open(self.root / '.lock', os.O_WRONLY | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600), 'w') as lock:
            if fcntl:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            with getattr(session, 'lock', nullcontext()):
                return self._save_locked(name, session)

    def _save_locked(self, name: str, session: Session) -> dict:
        target = self._path(name)
        if target.exists():
            raise FileExistsError('Checkpoint names are immutable; choose a new name')
        data = session.export()
        if len(data) > MAX_STATE:
            raise ValueError('Runtime state exceeds checkpoint budget')
        used = sum(path.stat().st_size for path in self.root.glob('*/state.bin') if not path.is_symlink())
        if used + len(data) > self.max_total_bytes:
            raise ValueError('Checkpoint storage budget exhausted; preserve/export or explicitly remove old records')
        staging = private_directory(self.root / ('.pending-' + uuid.uuid4().hex))
        metadata = {'format': 1, 'name': name, 'compatibility': session.compatibility,
            'turn': session.turn, 'transcript': session.transcript,
            'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        metadata['authentication'] = hmac.new(self.key, canonical(metadata), hashlib.sha256).hexdigest()
        if len(canonical(metadata)) > 1024 * 1024:
            raise ValueError('Checkpoint transcript exceeds its metadata budget')
        for filename, content in [('state.bin', data), ('manifest.json', canonical(metadata))]:
            with os.fdopen(os.open(staging / filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        descriptor = os.open(staging, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.rename(staging, target)
        descriptor = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return metadata

    def read(self, name: str, compatibility: dict) -> tuple[dict, bytes]:
        path = self._path(name)
        metadata = json.loads(read_private(path / 'manifest.json', 1024 * 1024))
        authentication = metadata.pop('authentication', '')
        expected = hmac.new(self.key, canonical(metadata), hashlib.sha256).hexdigest()
        if not isinstance(authentication, str) or not hmac.compare_digest(authentication, expected):
            raise ValueError('Checkpoint authentication failed')
        if metadata['name'] != name or metadata['compatibility'] != compatibility:
            raise ValueError('Checkpoint compatibility mismatch')
        data = read_private(path / 'state.bin', MAX_STATE)
        if len(data) != metadata['bytes'] or hashlib.sha256(data).hexdigest() != metadata['sha256']:
            raise ValueError('Corrupt or truncated checkpoint')
        return metadata, data


def verify_inputs(library: Path, model: Path, model_key: str) -> dict:
    """Verify native/model identities without loading a second model into this process."""
    manifest = json.loads(library.with_suffix('.json').read_text())
    inputs = json.loads((ROOT / 'config/build-inputs.json').read_text())
    expected = inputs['models'][model_key]
    if (manifest['abi'] != 1 or manifest['revision'] != inputs['runtime']['revision']
            or digest(library) != manifest['library_sha256']
            or digest(ROOT / 'native/rwkv_state.cpp') != manifest['source_sha256']):
        raise ValueError('State adapter does not match current pinned sources')
    for name, sha in manifest['runtime_libraries'].items():
        if digest(Path(name)) != sha:
            raise ValueError('Linked runtime library changed')
    if model.stat().st_size != expected['bytes'] or digest(model) != expected['sha256']:
        raise ValueError('Model identity does not match the input manifest')
    return {'model_sha256': expected['sha256'], 'runtime_revision': manifest['revision'],
            'runtime_libraries': manifest['runtime_libraries'], 'adapter_sha256': manifest['library_sha256']}


class Runtime:
    def __init__(self, library: Path, model: Path, *, model_key: str, gpu_layers: int = 0) -> None:
        self.handle = None
        self.library_path = Path(library).resolve()
        self.identity = {**verify_inputs(library, model, model_key), 'gpu_layers_requested': gpu_layers,
                         'format': 1, 'sampler': {'kind': 'greedy', 'rng_state': None}}
        self.lib = c.CDLL(str(self.library_path))
        signatures = {
            'wb_error': ([], c.c_char_p), 'wb_model_open': ([c.c_char_p, c.c_int], c.c_void_p),
            'wb_model_close': ([c.c_void_p], None),
            'wb_session_new': ([c.c_void_p, c.c_uint32, c.c_int], c.c_void_p),
            'wb_session_close': ([c.c_void_p], None),
            'wb_prefill': ([c.c_void_p, c.c_char_p, c.c_int], c.c_int),
            'wb_next': ([c.c_void_p, c.c_void_p, c.c_int, c.POINTER(c.c_int)], c.c_int),
            'wb_state_size': ([c.c_void_p], c.c_int64),
            'wb_state_get': ([c.c_void_p, c.c_void_p, c.c_size_t], c.c_int),
            'wb_state_set': ([c.c_void_p, c.c_void_p, c.c_size_t], c.c_int)}
        for name, (args, result) in signatures.items():
            function = getattr(self.lib, name)
            function.argtypes, function.restype = args, result
        self.handle = self.lib.wb_model_open(os.fsencode(model), gpu_layers)
        if not self.handle:
            raise RuntimeError(self.error())

    def error(self) -> str:
        return self.lib.wb_error().decode('utf-8', errors='replace')

    def session(self, *, persona: str = '', context: int = 2048, threads: int = 3) -> Session:
        if not self.handle:
            raise RuntimeError('Model is closed')
        return Session(self, persona, context, threads)

    def close(self) -> None:
        if self.handle:
            self.lib.wb_model_close(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class Session:
    def __init__(self, runtime: Runtime, persona: str, context: int, threads: int) -> None:
        from jinja2 import StrictUndefined
        from jinja2.sandbox import SandboxedEnvironment

        self.runtime, self.persona, self.context, self.threads = runtime, persona, context, threads
        self.lock = threading.RLock()
        template = (ROOT / 'config/rwkv-user-assistant.jinja').read_bytes()
        self.template = SandboxedEnvironment(undefined=StrictUndefined, autoescape=False).from_string(template.decode('utf-8'))
        self.handle = runtime.lib.wb_session_new(runtime.handle, context, threads)
        if not self.handle:
            raise RuntimeError(runtime.error())
        self.valid, self.turn = True, 0
        self.transcript: list[dict[str, str]] = []
        self.finish_reason = 'none'
        self.compatibility = {**runtime.identity, 'context': context, 'threads': threads,
            'persona_sha256': hashlib.sha256(persona.encode()).hexdigest(),
            'template_sha256': hashlib.sha256(template).hexdigest()}

    def _check(self, result: int) -> None:
        if result < 0:
            self.valid = False
            raise RuntimeError(self.runtime.error())

    def _active(self) -> None:
        if not self.handle or not self.valid:
            raise RuntimeError('Session closed or invalid; restore a checkpoint')

    def prefill(self, prompt: str) -> None:
        with self.lock:
            self._active()
            raw = prompt.encode('utf-8')
            self._check(self.runtime.lib.wb_prefill(self.handle, raw, len(raw)))

    def generate(self, tokens: int = 64) -> str:
        if type(tokens) is not int or not 1 <= tokens <= 1024:
            raise ValueError('Select 1–1024 generated tokens')
        with self.lock:
            self._active()
            output = bytearray()
            self.finish_reason = 'length'
            for _ in range(tokens):
                buffer, size = c.create_string_buffer(16384), c.c_int()
                result = self.runtime.lib.wb_next(self.handle, buffer, len(buffer), c.byref(size))
                self._check(result)
                if result == 1:
                    self.finish_reason = 'stop'
                    break
                output.extend(buffer.raw[:size.value])
            return output.decode('utf-8', errors='replace')

    def export(self) -> bytes:
        with self.lock:
            self._active()
            size = self.runtime.lib.wb_state_size(self.handle)
            if not 8 <= size <= MAX_STATE:
                raise ValueError('Invalid native state size')
            buffer = c.create_string_buffer(size)
            self._check(self.runtime.lib.wb_state_get(self.handle, buffer, size))
            return buffer.raw

    def _replace(self, data: bytes) -> None:
        handle = self.runtime.lib.wb_session_new(self.runtime.handle, self.context, self.threads)
        if not handle:
            raise RuntimeError(self.runtime.error())
        result = self.runtime.lib.wb_state_set(handle, data, len(data))
        if result < 0:
            message = self.runtime.error()
            self.runtime.lib.wb_session_close(handle)
            raise RuntimeError(message)
        old, self.handle = self.handle, handle
        if old:
            self.runtime.lib.wb_session_close(old)
        self.valid = True

    def restore(self, store: CheckpointStore, name: str) -> None:
        with self.lock:
            metadata, data = store.read(name, self.compatibility)
            self._replace(data)
            self.turn, self.transcript = metadata['turn'], metadata['transcript']

    def fork(self) -> Session:
        with self.lock:
            child = self.runtime.session(persona=self.persona, context=self.context, threads=self.threads)
            try:
                if child.compatibility != self.compatibility:
                    raise ValueError('Template changed; cannot fork into an incompatible session')
                child._replace(self.export())
                child.turn, child.transcript = self.turn, list(self.transcript)
                return child
            except BaseException:
                child.close()
                raise

    def chat(self, prompt: str, tokens: int = 64) -> str:
        with self.lock:
            previous = self.export()
            try:
                messages = [{'role': 'user', 'content': prompt}]
                if self.turn == 0 and self.persona:
                    messages.insert(0, {'role': 'system', 'content': self.persona})
                self.prefill(self.template.render(messages=messages, add_generation_prompt=True))
                answer = self.generate(tokens)
                self.prefill('\n\n')
                self.turn += 1
                self.transcript = [*self.transcript, {'user': prompt, 'assistant': answer, 'finish_reason': self.finish_reason}]
                return answer
            except BaseException:
                try:
                    self._replace(previous)
                except (RuntimeError, ValueError):
                    self.valid = False
                raise

    def close(self) -> None:
        with self.lock:
            if self.handle:
                self.runtime.lib.wb_session_close(self.handle)
                self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
