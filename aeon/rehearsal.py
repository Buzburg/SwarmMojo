"""Bounded, advisory event-workflow rehearsal through a pinned TriggerTangle runner."""
from __future__ import annotations

import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import tempfile
import threading
import time
from typing import Any

INPUT_LIMIT = 800_000
OUTPUT_LIMIT = 2 * 1024 * 1024
TIMEOUT = 45.0
RUNNER_VERSION = '0.3.0'
RUNNER_SHA256 = 'abd32d7551954857205dbf80de24056558164b2cba02d387f994757ee244f34f'
RUNNER = Path(__file__).parent / 'vendor' / 'triggertangle' / 'trigger-tangle-harness.mjs'
STATUSES = {0: 'review-required', 1: 'blocked', 2: 'inconclusive'}
BOUNDARY = {'advisory_only': True, 'authorizes_apply': False, 'executionAllowed': False}


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _regular_read(descriptor: int, limit: int) -> bytes:
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError('Rehearsal inputs must be bounded regular files')
        with os.fdopen(descriptor, 'rb', closefd=False) as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError('Rehearsal input grew beyond its byte limit')
        return data
    finally:
        os.close(descriptor)


def _no_windows_links(path: Path) -> None:
    cursor = Path(path.anchor)
    for part in path.parts[1:]:
        cursor /= part
        info = cursor.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Rehearsal paths cannot contain symlinks or junctions')


def _windows_read(path: Path, limit: int) -> bytes:
    """Open without reparse traversal and verify the opened handle's actual path."""
    import msvcrt
    from ctypes import wintypes
    _no_windows_links(path)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    final_path = kernel.GetFinalPathNameByHandleW
    final_path.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    final_path.restype = wintypes.DWORD
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    # Read access, read sharing only, existing file, open final reparse point itself.
    handle = create(str(path), 0x80000000, 1, None, 3, 0x00200000 | 0x02000000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        length = final_path(handle, buffer, len(buffer), 0)
        if not 0 < length < len(buffer):
            raise ValueError('Cannot verify rehearsal input handle')
        actual = buffer.value
        if actual.startswith('\\\\?\\UNC\\'):
            actual = '\\\\' + actual[8:]
        elif actual.startswith('\\\\?\\'):
            actual = actual[4:]
        if os.path.normcase(actual) != os.path.normcase(str(path)):
            raise ValueError('Rehearsal input resolved through a changed path')
        _no_windows_links(path)
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        handle = None  # The descriptor now owns the handle.
        data = _regular_read(descriptor, limit)
        _no_windows_links(path)
        return data
    finally:
        if handle is not None:
            close(handle)


def _read(path: Path, limit: int = INPUT_LIMIT) -> bytes:
    path = Path(path).expanduser()
    if '..' in path.parts:
        raise ValueError('Rehearsal paths cannot contain parent traversal')
    path = path.absolute()
    if os.name == 'nt':
        return _windows_read(path, limit)
    directory = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    finally:
        os.close(directory)
    return _regular_read(descriptor, limit)


def read_input(path: Path) -> bytes:
    """Read an operator-selected regular file; reject link components and oversized data."""
    try:
        return _read(path)
    except OSError as exc:
        raise ValueError('Cannot read rehearsal input: ' + str(exc)) from exc


def _invalid_constant(value: str) -> None:
    raise ValueError('Non-finite JSON numbers are unsupported')


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('Non-finite JSON numbers are unsupported')
    return number


def decode_input(data: bytes) -> tuple[str, Any]:
    """Decode strict UTF-8 JSON, stripping only an optional leading BOM."""
    try:
        text = data.decode('utf-8-sig', errors='strict')
        return text, json.loads(text, parse_constant=_invalid_constant, parse_float=_finite_float)
    except (UnicodeError, RecursionError) as exc:
        raise ValueError('Invalid rehearsal input encoding or nesting') from exc


def _same_json(left: Any, right: Any) -> bool:
    """Preserve JSON scalar types while allowing equivalent JavaScript numbers."""
    if type(left) in (int, float) and type(right) in (int, float):
        return left == right
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(_same_json(left[key], right[key]) for key in left)
    if type(left) is list:
        return len(left) == len(right) and all(_same_json(a, b) for a, b in zip(left, right))
    return left == right


def _validate_report(report: Any, exit_code: int, inputs: dict[str, Any],
                     hashes: dict[str, str], budget: dict[str, int]) -> None:
    if (type(report) is not dict or report.get('schema') != 'triggertangle.harness/v1'
            or exit_code not in STATUSES or report.get('status') != STATUSES[exit_code]
            or report.get('executionAllowed') is not False or report.get('budget') != budget
            or not _same_json(report.get('inputs'), inputs)):
        raise ValueError('Invalid rehearsal response or exit-status agreement')
    if any(type(report['budget'].get(key)) is not int for key in budget):
        raise ValueError('Invalid rehearsal response budget')
    if report.get('evidence') != {'runnerVersion': RUNNER_VERSION, **hashes}:
        raise ValueError('Rehearsal response does not match input text or runner version')
    suite, cases = inputs['suite'], report.get('cases')
    if (type(suite) is not dict or type(suite.get('cases')) is not list
            or report.get('name') != suite.get('name')
            or type(cases) is not list or not 1 <= len(cases) <= 8
            or len(cases) != len(suite['cases'])):
        raise ValueError('Invalid rehearsal case coverage')
    for case, expected in zip(cases, suite['cases']):
        if (type(case) is not dict or type(expected) is not dict
                or type(expected.get('required')) is not list or not 1 <= len(expected['required']) <= 8
                or type(expected.get('forbidden', [])) is not list or len(expected.get('forbidden', [])) > 8
                or any(not _same_json(case.get(key), expected.get(key)) for key in ('id', 'name', 'seed', 'required'))
                or not _same_json(case.get('forbidden'), expected.get('forbidden', []))):
            raise ValueError('Rehearsal cases do not match the selected suite')
        for side in ('baseline', 'candidate'):
            review = case.get(side)
            if (type(review) is not dict or review.get('status') not in STATUSES.values()
                    or review.get('analysisStatus') not in {'settles', 'loop-found', 'inconclusive'}
                    or type(review.get('complete')) is not bool or type(review.get('reason')) is not str
                    or type(review.get('stats')) is not dict
                    or type(review.get('required')) is not list or type(review.get('forbidden')) is not list
                    or len(review['required']) != len(expected['required'])
                    or len(review['forbidden']) != len(expected.get('forbidden', []))):
                raise ValueError('Invalid rehearsal case review')
            stats = review['stats']
            for key, minimum, maximum in (('states', 1, budget['maxStates']), ('transitions', 0, budget['maxTransitions'])):
                if type(stats.get(key)) is not int or not minimum <= stats[key] <= maximum:
                    raise ValueError('Invalid rehearsal analysis counts')
            analysis_status = review['analysisStatus']
            if ((analysis_status == 'settles' and not review['complete'])
                    or (analysis_status == 'inconclusive' and review['complete'])):
                raise ValueError('Rehearsal completeness contradicts analysis status')
            for key in ('workflowStarts', 'emittedEvents'):
                count = stats.get(key)
                needs_counts = analysis_status == 'settles' and review['complete']
                if (key not in stats or (not needs_counts and count is not None)
                        or (needs_counts and (type(count) is not str or not count.isascii() or not count.isdecimal()))):
                    raise ValueError('Invalid rehearsal delivery counts')
            for key in ('required', 'forbidden'):
                for observation, match in zip(review[key], expected.get(key, [])):
                    if (type(observation) is not dict or not _same_json(observation.get('match'), match)
                            or type(observation.get('observed')) is not bool):
                        raise ValueError('Invalid rehearsal outcome observation')
            if analysis_status == 'loop-found' or any(item['observed'] for item in review['forbidden']):
                expected_status = 'blocked'
            elif not review['complete']:
                expected_status = 'inconclusive'
            elif any(not item['observed'] for item in review['required']):
                expected_status = 'blocked'
            else:
                expected_status = 'review-required'
            if review['status'] != expected_status:
                raise ValueError('Rehearsal case status contradicts recorded outcomes')
    for key in ('regressions', 'notes'):
        if type(report.get(key)) is not list or not all(type(item) is str for item in report[key]):
            raise ValueError('Invalid rehearsal explanation')
    candidates = [case['candidate']['status'] for case in cases]
    aggregate = 'blocked' if 'blocked' in candidates else 'inconclusive' if 'inconclusive' in candidates else 'review-required'
    regressions = [case['id'] for case in cases if case['baseline']['status'] == 'review-required'
                   and case['candidate']['status'] != 'review-required']
    if report['status'] != aggregate or report['regressions'] != regressions:
        raise ValueError('Rehearsal summary contradicts scenario results')


def _stop(process: subprocess.Popen[bytes]) -> None:
    if os.name != 'nt':
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
    elif process.poll() is None:
        process.kill()


def _run(command: list[str], cancelled: threading.Event | None) -> tuple[int, bytes]:
    if cancelled is not None and cancelled.is_set():
        raise RuntimeError('Rehearsal cancelled')
    environment = {key: value for key, value in os.environ.items()
                   if key.upper() not in {'NODE_OPTIONS', 'NODE_PATH'}}
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, shell=False, env=environment,
                               start_new_session=os.name != 'nt')
    output = bytearray()
    overflow = threading.Event()
    read_errors: list[OSError] = []

    def drain() -> None:
        assert process.stdout is not None
        try:
            while True:
                chunk = process.stdout.read(8192)
                if not chunk:
                    return
                room = max(0, OUTPUT_LIMIT - len(output))
                output.extend(chunk[:room])
                if len(chunk) > room:
                    overflow.set()
                    return
        except OSError as exc:
            read_errors.append(exc)

    reader = threading.Thread(target=drain, daemon=True, name='aeon-rehearsal-output')
    reader.start()
    deadline = time.monotonic() + TIMEOUT
    try:
        while process.poll() is None:
            if cancelled is not None and cancelled.is_set():
                raise RuntimeError('Rehearsal cancelled')
            if overflow.is_set():
                raise RuntimeError('Rehearsal output exceeded its byte limit')
            if time.monotonic() >= deadline:
                raise RuntimeError('Rehearsal timed out')
            time.sleep(0.02)
    finally:
        _stop(process)
        process.wait(timeout=5)
        reader.join(timeout=2)
        if not reader.is_alive() and process.stdout is not None:
            process.stdout.close()
    if reader.is_alive() or read_errors:
        raise RuntimeError('Rehearsal output could not be read completely')
    if cancelled is not None and cancelled.is_set():
        raise RuntimeError('Rehearsal cancelled')
    if overflow.is_set():
        raise RuntimeError('Rehearsal output exceeded its byte limit')
    return process.returncode, bytes(output)


def rehearse(baseline: Path, candidate: Path, suite: Path, *, node: str | None = None,
             max_states: int = 256, max_transitions: int = 2048,
             cancelled: threading.Event | None = None) -> dict[str, Any]:
    """Review private snapshots. A result cannot approve workflows or execute their actions."""
    try:
        if type(max_states) is not int or not 1 <= max_states <= 512:
            raise ValueError('State budget must be between 1 and 512')
        if type(max_transitions) is not int or not 1 <= max_transitions <= 8192:
            raise ValueError('Transition budget must be between 1 and 8192')
        if cancelled is not None and cancelled.is_set():
            raise RuntimeError('Rehearsal cancelled')
        selected = node if node is not None else shutil.which('node')
        if not selected or not Path(selected).is_absolute() or not Path(selected).is_file():
            raise ValueError('Node.js is required; configure an absolute executable node path')
        if not os.access(selected, os.X_OK):
            raise ValueError('Configured Node.js path is not executable')
        runner_bytes = _read(RUNNER, 4 * 1024 * 1024)
        if _digest(runner_bytes) != RUNNER_SHA256:
            raise ValueError('Vendored TriggerTangle runner failed its SHA256 integrity check')
        paths = {'baseline': Path(baseline), 'candidate': Path(candidate), 'suite': Path(suite)}
        originals = {name: read_input(path) for name, path in paths.items()}
        decoded = {name: decode_input(data) for name, data in originals.items()}
        inputs = {name: value for name, (_, value) in decoded.items()}
        text_hashes = {name + 'TextSha256': _digest(text.encode('utf-8')) for name, (text, _) in decoded.items()}
        budget = {'maxStates': max_states, 'maxTransitions': max_transitions}
        with tempfile.TemporaryDirectory(prefix='aeon-rehearsal-') as temporary:
            snapshots = {name: Path(temporary) / (name + '.json') for name in paths}
            runner_copy = Path(temporary) / 'trigger-tangle-harness.mjs'
            for path, data in [(runner_copy, runner_bytes), *[(snapshots[name], data) for name, data in originals.items()]]:
                path.write_bytes(data)
                path.chmod(0o600)
            command = [str(Path(selected).resolve()), str(runner_copy)]
            for name, path in snapshots.items():
                command.extend(['--' + name, str(path)])
            command.extend(['--max-states', str(max_states), '--max-transitions', str(max_transitions)])
            exit_code, output = _run(command, cancelled)
            if (any(read_input(path) != originals[name] for name, path in paths.items())
                    or any(read_input(path) != originals[name] for name, path in snapshots.items())
                    or _read(RUNNER, 4 * 1024 * 1024) != runner_bytes
                    or _read(runner_copy, 4 * 1024 * 1024) != runner_bytes):
                raise ValueError('Rehearsal inputs or runner changed during analysis')
            _, report = decode_input(output)
            _validate_report(report, exit_code, inputs, text_hashes, budget)
        return {'status': report['status'], 'report': report, **BOUNDARY,
                'evidence': {'runner_sha256': RUNNER_SHA256,
                             'input_sha256': {name: _digest(data) for name, data in originals.items()}}}
    except (OSError, UnicodeError, TypeError, KeyError, RecursionError, subprocess.SubprocessError) as exc:
        raise ValueError('Rehearsal failed: ' + str(exc)[:500]) from exc
