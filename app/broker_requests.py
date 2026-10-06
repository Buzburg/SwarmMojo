"""Durable at-most-once dispatch for the broker's registered validation action."""
from collections.abc import Callable, Iterator
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import stat
import time

from app import broker_protocol as protocol
from app.config import DATA_DIR
from app.json_protocol import unique_object
from app.patch_promotion import open_root
from app.patch_tasks import canonical, durable_json, sha

STORE = DATA_DIR / 'broker-requests'
MAX_RECORDS = 1000
MAX_RECORD_BYTES = 2 * protocol.MAX_FRAME + 4096


def owned(info: os.stat_result, *, directory: bool = False, private: bool = True) -> None:
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if (not expected(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & (0o077 if private else 0o022)
            or (not directory and info.st_nlink != 1)):
        raise ValueError('Unsafe request journal ownership or permissions')


@contextmanager
def journal() -> Iterator[Path]:
    parent = open_root(STORE.parent)
    try:
        owned(os.fstat(parent), directory=True, private=False)
        try:
            os.mkdir(STORE.name, 0o700, dir_fd=parent)
        except FileExistsError:
            pass  # The existing leaf is verified without following links below.
        os.fsync(parent)
        directory = os.open(STORE.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    finally:
        os.close(parent)
    try:
        owned(os.fstat(directory), directory=True)
        yield Path(f'/proc/self/fd/{directory}')
    finally:
        os.close(directory)


@contextmanager
def locked(root: Path) -> Iterator[None]:
    fd = os.open(root / '.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        owned(os.fstat(fd))
        deadline = time.monotonic() + 1
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise protocol.ProtocolError('JOURNAL_BUSY', 'The request journal is busy; retry the same request') from None
                time.sleep(0.01)
        yield
    finally:
        os.close(fd)


def read_record(path: Path) -> dict | None:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, 'rb') as stream:
        owned(os.fstat(stream.fileno()))
        raw = stream.read(MAX_RECORD_BYTES + 1)
    if len(raw) > MAX_RECORD_BYTES:
        raise ValueError('Oversized request journal')
    record = json.loads(raw, object_pairs_hook=unique_object)
    if type(record) is not dict or set(record) != {'request', 'digest', 'response', 'response_sha256'}:
        raise ValueError('Invalid request journal')
    try:
        request = protocol.parse(canonical(record['request']))
    except protocol.ProtocolError as error:
        raise ValueError('Invalid saved request') from error
    if (request['action'] != 'task.validate' or set(request['args']) != {'task_id'}
            or record['digest'] != sha(canonical(request)) or path.name != request['id'] + '.json'):
        raise ValueError('Request journal identity mismatch')
    response = record['response']
    if response is None:
        if record['response_sha256'] is not None:
            raise ValueError('Invalid pending request journal')
    else:
        if (type(response) is not str or len(response.encode()) > protocol.MAX_FRAME
                or record['response_sha256'] != sha(response.encode())):
            raise ValueError('Invalid saved response')
        value = json.loads(response, object_pairs_hook=unique_object)
        if (type(value) is not dict or type(value.get('ok')) is not bool
                or type(value.get('v')) is not int or value['v'] != 1 or value.get('id') != request['id']
                or set(value) != {'v', 'id', 'ok', 'result' if value['ok'] else 'error'}):
            raise ValueError('Saved response does not match its request')
    return record


def available_slot(root: Path) -> None:
    # Count all entries, including incomplete atomic-write temporaries. Never evict
    # an old ID: forgetting it could turn a delayed retry into a second execution.
    with os.scandir(root) as entries:
        count = sum(1 for _ in zip(entries, range(MAX_RECORDS + 2)))
    if count >= MAX_RECORDS + 1:  # The permanent lock consumes one entry.
        raise protocol.ProtocolError('JOURNAL_FULL', 'Request history is full; retained requests remain replayable')


def execute(request: dict, operation: Callable[[], str]) -> str:
    dispatched = False
    try:
        with journal() as root:
            path = root / (request['id'] + '.json')
            digest = sha(canonical(request))
            with locked(root):
                record = read_record(path)
                if record is not None:
                    if record['digest'] != digest:
                        raise protocol.ProtocolError('CONFLICT', 'This request ID is already bound to different arguments')
                    if record['response'] is None:
                        raise protocol.ProtocolError('REQUEST_UNCERTAIN', 'No completed reply is recorded; query task.status for the retained task')
                    return record['response']
                available_slot(root)
                record = {'request': request, 'digest': digest, 'response': None, 'response_sha256': None}
                durable_json(path, record)
            # Intent and its directory entry are durable before any worker contact.
            dispatched = True
            response = operation()
            record.update(response=response, response_sha256=sha(response.encode()))
            with locked(root):
                if read_record(path) != dict(record, response=None, response_sha256=None):
                    raise ValueError('Request intent changed during dispatch')
                durable_json(path, record)
            return response
    except protocol.ProtocolError as error:
        if dispatched:
            raise protocol.ProtocolError('REQUEST_UNCERTAIN', 'No completed reply is confirmed; query task.status for the retained task') from error
        raise
    except (OSError, ValueError, TypeError, KeyError, IndexError, RecursionError) as error:
        code = 'REQUEST_UNCERTAIN' if dispatched else 'JOURNAL_UNAVAILABLE'
        message = ('No completed reply is confirmed; query task.status for the retained task' if dispatched else
                   'The request journal is unavailable; no validation was dispatched')
        raise protocol.ProtocolError(code, message) from error
