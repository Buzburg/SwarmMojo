"""Fixed grammar through the actual C adapter and supplied recurrent model."""
import ctypes as c
import json
import os
import struct
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
            assert lib.wb_state_set(session, initial, len(initial)) == -2
            empty = snapshot(lib, session)
            assert lib.wb_state_set(session, empty, len(empty)) == 0
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


def test_formatted_checkpoint_replay_fork_rejection_and_recovery():
    load()
    completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--checkpoint'],
                               capture_output=True, text=True, timeout=120)
    assert completed.returncode == 0, (completed.stdout + completed.stderr)[-6000:]
    assert json.loads(completed.stdout) == {'checkpoint': 'passed'}


def checkpoint_probe():
    lib = load()
    model = lib.wb_model_open(os.fsencode(os.environ['OMARCHY_STATE_MODEL']), 0)
    assert model, lib.wb_error()
    sessions = []
    try:
        for _ in range(3):
            session = lib.wb_session_new(model, 1024, 2)
            assert session, lib.wb_error()
            sessions.append(session)
        first, branch, plain = sessions
        for session in (first, branch):
            assert lib.wb_session_answer_format(session) == 0
        empty = snapshot(lib, first)
        assert lib.wb_prefill(first, PROMPT, len(PROMPT)) == 0
        prefix = bytearray()
        for _ in range(3):
            status, piece = next_token(lib, first)
            assert status == 0
            prefix.extend(piece)
        saved = snapshot(lib, first)
        assert struct.unpack_from('=I', saved, 20)[0] == 3
        assert lib.wb_state_set(plain, saved, len(saved)) == -2
        assert lib.wb_state_set(branch, saved, len(saved)) == 0, lib.wb_error()
        query_size = c.c_int()
        assert lib.wb_next(first, None, 0, c.byref(query_size)) == -6
        assert snapshot(lib, first) == saved
        assert lib.wb_state_get(first, None, len(saved)) == -2
        assert lib.wb_state_get(first, c.create_string_buffer(len(saved)), len(saved) - 1) == -2

        def changed(offset, fmt, value):
            data = bytearray(saved)
            struct.pack_into(fmt, data, offset, value)
            return bytes(data)

        # Preflight rejects malformed envelopes and impossible replay before touching the live state.
        bad_states = [saved[:20], saved[:-1], saved + b'x',
                      changed(4, '=I', 2), changed(20, '=I', 0xffffffff),
                      changed(8, '=i', -1), changed(12, '=I', 2),
                      changed(16, '=i', 0x7fffffff), changed(32, '=i', -1)]
        count = c.c_int()
        assert lib.wb_tokenize(model, b'Z', 1, 0, 0, None, 0, c.byref(count)) == -6
        tokens = (c.c_int32 * count.value)()
        assert lib.wb_tokenize(model, b'Z', 1, 0, 0, tokens, count.value, c.byref(count)) == 0
        bad_states.append(changed(32, '=i', tokens[0]))  # Root requires an opening brace.
        for data in bad_states:
            assert lib.wb_state_set(first, data, len(data)) < 0
            assert snapshot(lib, first) == saved, lib.wb_error()

        # Valid envelope but truncated native payload must invalidate until an authenticated restore.
        offset = 32 + 3 * 4
        truncated = bytearray(saved[:offset + 4])
        struct.pack_into('=Q', truncated, 24, 4)
        assert lib.wb_state_set(branch, bytes(truncated), len(truncated)) < 0
        assert lib.wb_next(branch, None, 0, c.byref(query_size)) == -5
        assert lib.wb_state_set(branch, saved, len(saved)) == 0
        assert lib.wb_session_cancel(branch) == 0
        assert lib.wb_state_set(branch, saved, len(saved)) == 0
        assert lib.wb_next(branch, None, 0, c.byref(query_size)) == -4
        assert lib.wb_session_reset_cancel(branch) == 0

        expected = []
        for _ in range(512):
            token = next_token(lib, first)
            expected.append(token)
            if token[0] == 1:
                break
        else:
            raise AssertionError('Checkpoint test generation exceeded token budget')
        assert snapshot(lib, branch) == saved, 'Advancing the first session changed the fork'
        assert [next_token(lib, branch) for _ in expected] == expected
        assert lib.wb_state_set(first, saved, len(saved)) == 0
        assert [next_token(lib, first) for _ in expected] == expected
        value = json.loads((prefix + b''.join(piece for _, piece in expected)).decode())
        assert value == {'answer': '56'}
        ended = snapshot(lib, first)
        assert lib.wb_state_set(branch, ended, len(ended)) == 0
        assert next_token(lib, branch) == (1, b'')
        assert lib.wb_state_set(first, empty, len(empty)) == 0
        assert lib.wb_next(first, None, 0, c.byref(query_size)) == -5
        assert lib.wb_prefill(first, PROMPT, len(PROMPT)) == 0
        print(json.dumps({'checkpoint': 'passed'}))
    finally:
        for session in sessions:
            lib.wb_session_close(session)
        lib.wb_model_close(model)


if __name__ == '__main__':
    checkpoint_probe() if '--checkpoint' in sys.argv else probe()
