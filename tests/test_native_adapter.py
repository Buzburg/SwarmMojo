"""Exercise the actual opaque C ABI, including real recurrent decode cancellation."""
import concurrent.futures
import ctypes as c
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest
import psutil


def load():
    path = os.environ.get('OMARCHY_NATIVE_ADAPTER')
    if not path:
        pytest.skip('Requires the explicit compiled adapter artifact')
    lib = c.CDLL(path)
    signatures = {
        'wb_error': ([], c.c_char_p), 'wb_error_code': ([], c.c_int),
        'wb_model_open': ([c.c_char_p, c.c_int], c.c_void_p), 'wb_model_close': ([c.c_void_p], None),
        'wb_session_new': ([c.c_void_p, c.c_uint32, c.c_int], c.c_void_p), 'wb_session_close': ([c.c_void_p], None),
        'wb_session_cancel': ([c.c_void_p], c.c_int), 'wb_session_reset_cancel': ([c.c_void_p], c.c_int),
        'wb_tokenize': ([c.c_void_p, c.c_char_p, c.c_int, c.c_int, c.c_int, c.POINTER(c.c_int32), c.c_int, c.POINTER(c.c_int)], c.c_int),
        'wb_prefill': ([c.c_void_p, c.c_char_p, c.c_int], c.c_int),
        'wb_next': ([c.c_void_p, c.c_void_p, c.c_int, c.POINTER(c.c_int)], c.c_int),
        'wb_state_size': ([c.c_void_p], c.c_int64),
        'wb_state_get': ([c.c_void_p, c.c_void_p, c.c_size_t], c.c_int),
        'wb_state_set': ([c.c_void_p, c.c_void_p, c.c_size_t], c.c_int)}
    for name, (args, result) in signatures.items():
        getattr(lib, name).argtypes, getattr(lib, name).restype = args, result
    return lib


def snapshot(lib, session):
    size = lib.wb_state_size(session)
    assert 12 <= size <= 512 * 1024 * 1024, lib.wb_error()
    data = c.create_string_buffer(size)
    assert lib.wb_state_get(session, data, size) == 0, lib.wb_error()
    return data.raw


def next_token(lib, session):
    output, size = c.create_string_buffer(16384), c.c_int()
    status = lib.wb_next(session, output, len(output), c.byref(size))
    assert status in (0, 1), lib.wb_error()
    return status, output.raw[:size.value]


def test_null_arguments_and_missing_model_do_not_crash(tmp_path):
    lib = load()
    size = c.c_int()
    assert not lib.wb_model_open(None, 0) and lib.wb_error_code() == -2
    assert not lib.wb_model_open(os.fsencode(tmp_path / 'missing.gguf'), 0)
    assert lib.wb_error_code() == -1
    assert not lib.wb_session_new(None, 1024, 1) and lib.wb_error_code() == -2
    assert lib.wb_prefill(None, b'x', 1) == -2
    assert lib.wb_next(None, None, 0, c.byref(size)) == -2
    assert lib.wb_state_size(None) == -1 and lib.wb_error_code() == -2
    assert lib.wb_state_get(None, None, 0) == -2
    assert lib.wb_state_set(None, None, 0) == -2
    assert lib.wb_session_cancel(None) == -2
    assert lib.wb_session_reset_cancel(None) == -2
    assert lib.wb_tokenize(None, b'x', 1, 0, 0, None, 0, c.byref(size)) == -2
    lib.wb_model_close(None)
    lib.wb_session_close(None)


def test_real_model_ownership_buffers_state_and_abort_in_subprocess():
    load()
    assert os.environ.get('OMARCHY_STATE_MODEL'), 'Explicit model file is required for real native tests'
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--probe'],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, (result.stdout + result.stderr)[-5000:]
    assert json.loads(result.stdout)['native_contract'] == 'passed'


def test_cpp_allocation_failure_returns_error_and_allows_retry(tmp_path):
    load()
    root = Path(__file__).resolve().parents[1]
    library = Path(os.environ['OMARCHY_NATIVE_ADAPTER'])
    executable = tmp_path / 'allocation-failure'
    subprocess.run(['c++', '-std=c++17', str(root / 'tests/native_allocation_failure.cpp'),
                    '-I' + str(root / 'native'), str(library), '-Wl,-rpath,' + str(library.parent),
                    '-o', str(executable)], check=True, capture_output=True, timeout=30)
    result = subprocess.run([str(executable), os.environ['OMARCHY_STATE_MODEL']],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, (result.stdout + result.stderr)[-3000:]


def probe():
    lib = load()
    model = lib.wb_model_open(os.fsencode(os.environ['OMARCHY_STATE_MODEL']), 0)
    assert model, lib.wb_error()
    first = second = None
    try:
        needed = c.c_int()
        text = 'café\t日本語\n'.encode()
        assert lib.wb_tokenize(model, text, len(text), 0, 0, None, 0, c.byref(needed)) == -6
        assert needed.value > 0
        tokens = (c.c_int32 * needed.value)()
        assert lib.wb_tokenize(model, text, len(text), 0, 0, tokens, len(tokens), c.byref(needed)) == 0
        assert lib.wb_tokenize(model, text, len(text), 7, 0, tokens, len(tokens), c.byref(needed)) == -2
        assert not lib.wb_session_new(model, 1, 1) and lib.wb_error_code() == -2
        first = lib.wb_session_new(model, 1024, 1)
        second = lib.wb_session_new(model, 1024, 1)
        assert first and second, lib.wb_error()
        resident = psutil.Process().memory_info().rss
        for _ in range(12):
            temporary = lib.wb_session_new(model, 128, 1)
            assert temporary, lib.wb_error()
            assert lib.wb_session_cancel(temporary) == 0
            assert lib.wb_prefill(temporary, b'x', 1) == -4
            lib.wb_session_close(temporary)
        assert psutil.Process().memory_info().rss - resident < 64 * 1024 * 1024
        # Sessions own their model independently of the caller's model handle.
        lib.wb_model_close(model)
        model = None
        initial = snapshot(lib, first)
        assert lib.wb_prefill(first, None, 5) == -2
        assert snapshot(lib, first) == initial
        prompt = b'User: Count from one.\n\nAssistant:'
        assert lib.wb_prefill(first, prompt, len(prompt)) == 0, lib.wb_error()
        before = snapshot(lib, first)
        assert lib.wb_state_get(first, None, len(before)) == -2
        short = c.create_string_buffer(len(before) - 1)
        assert lib.wb_state_get(first, short, len(short)) == -2
        assert snapshot(lib, first) == before
        size = c.c_int()
        assert lib.wb_next(first, None, 0, c.byref(size)) == -6 and size.value > 0
        assert snapshot(lib, first) == before
        assert lib.wb_state_set(second, before, len(before)) == 0, lib.wb_error()
        expected = [next_token(lib, first) for _ in range(4)]
        assert [next_token(lib, second) for _ in range(4)] == expected
        assert lib.wb_state_set(first, before, len(before)) == 0
        assert [next_token(lib, first) for _ in range(4)] == expected
        original = snapshot(lib, first)
        other = b'\n\nUser: A different question.\n\nAssistant:'
        assert lib.wb_prefill(second, other, len(other)) == 0
        assert snapshot(lib, first) == original
        # Native parser failure cannot leave a possibly partially restored context usable.
        assert lib.wb_state_set(second, before[:16], 16) < 0
        assert lib.wb_next(second, None, 0, c.byref(size)) == -5
        assert lib.wb_state_set(second, before, len(before)) == 0
        assert next_token(lib, second) == expected[0]
        assert lib.wb_state_set(first, initial, len(initial)) == 0
        long_prompt = b'word ' * 600
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            operation = pool.submit(lib.wb_prefill, first, long_prompt, len(long_prompt))
            time.sleep(0.05)
            assert not operation.done(), 'Decode finished before the cancellation check'
            started = time.monotonic()
            assert lib.wb_session_cancel(first) == 0
            assert operation.result(timeout=10) == -4
            assert time.monotonic() - started < 10
        assert lib.wb_session_reset_cancel(first) == 0
        assert lib.wb_state_size(first) == -1 and lib.wb_error_code() == -5
        assert lib.wb_state_set(first, before, len(before)) == 0
        assert next_token(lib, first) == expected[0]
        print(json.dumps({'native_contract': 'passed'}))
    finally:
        lib.wb_session_close(first)
        lib.wb_session_close(second)
        lib.wb_model_close(model)


if __name__ == '__main__':
    probe()
