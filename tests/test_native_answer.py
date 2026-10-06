"""Fixed grammar through the actual C adapter and supplied recurrent model."""
import ctypes as c
import json
import os
from pathlib import Path
import subprocess
import sys

from test_native_adapter import load, next_token, snapshot

PROMPT = b'User: Reply as JSON with one string field named answer. What is 7 times 8? Give only the number in answer.\n\nAssistant:'


def test_native_answer_grammar_ownership_bounds_and_generation():
    load()
    completed = subprocess.run([sys.executable, str(Path(__file__).resolve())],
                               capture_output=True, text=True, timeout=120)
    assert completed.returncode == 0, (completed.stdout + completed.stderr)[-6000:]
    value = json.loads(completed.stdout)
    assert value['answer'] == '56'


def probe():
    lib = load()
    model = lib.wb_model_open(os.fsencode(os.environ['OMARCHY_STATE_MODEL']), 0)
    assert model, lib.wb_error()
    first = second = plain = None
    try:
        first = lib.wb_session_new(model, 1024, 2)
        second = lib.wb_session_new(model, 1024, 2)
        plain = lib.wb_session_new(model, 1024, 2)
        assert first and second and plain, lib.wb_error()
        initial = snapshot(lib, plain)
        for session in (first, second):
            assert lib.wb_session_answer_format(session) == 0, lib.wb_error()
            assert lib.wb_session_answer_format(session) == 0, lib.wb_error()
            assert lib.wb_state_size(session) == -1 and lib.wb_error_code() == -5
            assert lib.wb_state_set(session, initial, len(initial)) == -5
            data = c.create_string_buffer(len(initial))
            assert lib.wb_state_get(session, data, len(initial)) == -5
            assert lib.wb_prefill(session, PROMPT, len(PROMPT)) == 0, lib.wb_error()
            assert lib.wb_session_answer_format(session) == -5
            assert lib.wb_prefill(session, b'Unexpected second prompt', 24) == -5
        lib.wb_model_close(model)
        model = None
        size = c.c_int()
        assert lib.wb_next(first, None, 0, c.byref(size)) == -6 and size.value > 0
        assert lib.wb_session_cancel(first) == 0
        assert lib.wb_next(first, None, 0, c.byref(size)) == -4
        assert lib.wb_session_reset_cancel(first) == 0
        output = bytearray()
        for _ in range(512):
            result, piece = next_token(lib, first)
            assert next_token(lib, second) == (result, piece), 'Session grammar state crossed owners or advanced on failure'
            if result == 1:
                break
            output.extend(piece)
        else:
            raise AssertionError('Grammar generation failed to finish within its token budget')
        assert len(output) <= 6600
        value = json.loads(output.decode('utf-8'))
        assert set(value) == {'answer'} and isinstance(value['answer'], str)
        assert 1 <= len(value['answer']) <= 1600
        assert snapshot(lib, plain) == initial, 'Grammar sessions changed an unrelated plain session'
        print(json.dumps(value))
    finally:
        for session in (first, second, plain):
            lib.wb_session_close(session)
        lib.wb_model_close(model)


if __name__ == '__main__':
    probe()
