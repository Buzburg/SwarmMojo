"""Operator-owned TraceSeal collection, outside the model and validation worker."""
from __future__ import annotations

import os
import re
import stat
import uuid
from collections.abc import Iterable
from pathlib import Path

from .vendor.traceseal import core


def private_directory(path: Path) -> Path:
    path = Path(path).expanduser().absolute()
    if os.name != 'posix' or path.resolve() != path:
        raise ValueError('Private collector storage requires Linux without symlink components')
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError('Collector storage must be owned by this user and mode 0700')
    return path


class Collector:
    def __init__(self, root: Path | None = None) -> None:
        default = Path(os.getenv('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'omarchy-workbench'
        self.root = private_directory(root or default)
        private_directory(self.root / 'runs')
        private_directory(self.root / 'checkpoints')
        self.key_path = self.root / 'collector.key'
        if not self.key_path.exists():
            try:
                core.keygen(self.key_path)
            except FileExistsError:
                pass  # Another operator invocation initialized the same private store.
        with os.fdopen(os.open(self.key_path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) & 0o077 or info.st_nlink != 1):
                raise ValueError('Collector key must be a private regular file')
            self.key = stream.read(33)
        if len(self.key) != 32:
            raise ValueError('Collector key must contain exactly 32 bytes')

    def record(self, kind: str, events: Iterable[dict]) -> dict:
        run_id = uuid.uuid4().hex
        directory = private_directory(self.root / 'runs' / run_id)
        checkpoint = self.root / 'checkpoints' / (run_id + '.json')
        def records():
            yield {'kind': kind, 'collector_id': run_id, 'boundary': 'recorded evidence, not authorization'}
            yield from events
        core.seal(records(), directory / 'events.jsonl', checkpoint, self.key)
        descriptor = os.open(checkpoint.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return {'id': run_id, 'checkpoint': str(checkpoint), 'complete': True}

    def verify(self, run_id: str) -> dict:
        if not re.fullmatch(r'[a-f0-9]{32}', run_id):
            raise ValueError('Invalid receipt ID')
        directory = self.root / 'runs' / run_id
        checkpoint = self.root / 'checkpoints' / (run_id + '.json')
        log = directory / 'events.jsonl'
        if not checkpoint.is_file():
            return {'valid': False, 'events': 0, 'reason': 'Collection incomplete: no finalized checkpoint'}
        if directory.is_symlink() or log.is_symlink() or checkpoint.is_symlink():
            raise ValueError('Receipt paths cannot be symlinks')
        return core.verify(log, checkpoint, self.key).to_dict()
