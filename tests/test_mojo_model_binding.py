"""Compile and run the real Mojo -> C -> RWKV binding, without HTTP or mock output."""
import os
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from test_native_adapter import load, next_token

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def binding(tmp_path_factory):
    library = os.environ.get('OMARCHY_NATIVE_ADAPTER')
    model = os.environ.get('OMARCHY_STATE_MODEL')
    if not library or not model:
        pytest.skip('Requires explicit compiled adapter and actual model')
    compiler = shutil.which('mojo')
    assert compiler, 'The selected binding profile requires the Mojo compiler'
    output = tmp_path_factory.mktemp('mojo model binding') / 'probe'
    result = subprocess.run([compiler, 'build', str(ROOT / 'tests/native_model_binding.mojo'),
                             '-I', str(ROOT), '-Xlinker', str(Path(library).resolve()),
                             '--Werror', '-o', str(output)], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    return output, model


def run(binding, mode, *, model=None):
    binary, configured_model = binding
    return subprocess.run([str(binary), model or configured_model, mode],
                          capture_output=True, text=True, timeout=60)


@pytest.mark.parametrize('mode,prompt', [
    ('generate', 'User: What is 7 times 8?\n\nAssistant:'),
    ('reset', 'User: What is 7 times 8?\n\nAssistant:'),
    ('unicode', 'User: café 中文 🙂\n\nAssistant:'),
])
def test_moved_mojo_session_matches_native_token_bytes(binding, mode, prompt):
    lib = load()
    model = lib.wb_model_open(os.fsencode(binding[1]), 0)
    assert model, lib.wb_error()
    session = lib.wb_session_new(model, 1024, 2)
    lib.wb_model_close(model)
    assert session, lib.wb_error()
    expected = bytearray()
    try:
        encoded = prompt.encode()
        assert lib.wb_prefill(session, encoded, len(encoded)) == 0, lib.wb_error()
        for _ in range(12):
            status, piece = next_token(lib, session)
            if status == 1:
                break
            expected.extend(piece)
    finally:
        lib.wb_session_close(session)
    assert expected, 'Real model must produce token bytes'
    result = run(binding, mode)
    assert result.returncode == 0, result.stderr[-4000:]
    assert bytes.fromhex(result.stdout.strip()) == bytes(expected)


@pytest.mark.parametrize('mode,message', [
    ('invalid-context', 'Invalid native session context'),
    ('invalid-path', 'Invalid native model path'),
    ('closed', 'Native session is closed'),
    ('unready', 'native code -5'),
    ('empty', 'Prompt must contain'),
    ('cancel', 'native code -4'),
])
def test_invalid_or_cancelled_session_fails_cleanly(binding, mode, message):
    result = run(binding, mode)
    assert result.returncode == 1, result.stderr[-4000:]
    assert message in result.stderr
    assert not result.stdout.strip()


def test_missing_model_fails_without_mock_generation(binding, tmp_path):
    result = run(binding, 'generate', model=str(tmp_path / 'missing.gguf'))
    assert result.returncode == 1, result.stderr[-4000:]
    assert 'Model load failed (native code -1)' in result.stderr
    assert not result.stdout.strip()


def test_mojo_fixed_answer_format_generates_real_json(binding):
    result = run(binding, 'answer')
    assert result.returncode == 0, result.stderr[-4000:]
    assert json.loads(bytes.fromhex(result.stdout.strip())) == {'answer': '56'}


def test_session_cannot_be_copied_into_two_owners(binding, tmp_path):
    source = tmp_path / 'copy_session.mojo'
    source.write_text('''from app_mojo.rwkv_engine import RWKV7Session
def main() raises:
    var original = RWKV7Session("unused-model")
    var alias = original
    print(original.is_open())
    alias.close()
''')
    result = subprocess.run(['mojo', 'build', str(source), '-I', str(ROOT),
                             '-o', str(tmp_path / 'must-not-build')],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode != 0
    assert 'RWKV7Session' in result.stderr and 'cop' in result.stderr.lower()
