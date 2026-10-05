"""Invoke the actual compiled Mojo enforcement path; no Python Landlock substitute."""
import json
import os
from pathlib import Path
import subprocess
import threading

import pytest

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Native Linux sandbox')


@pytest.fixture(scope='module')
def sandbox():
    binary = Path(os.getenv('OMARCHY_SANDBOX_BINARY', '/opt/roms-env/bin/staging-sandbox'))
    assert binary.is_file(), f'Required compiled enforcement artifact missing: {binary}'
    return str(binary)


def invoke(binary, stage, code, *args, **kwargs):
    return subprocess.run([binary, str(stage), '--', '/usr/bin/python3', '-I', '-B', '-c', code, *args],
                          capture_output=True, text=True, timeout=15, **kwargs)


def test_actual_native_rules_deny_outside_operations(sandbox, tmp_path):
    stage, outside = tmp_path / 'stage', tmp_path / 'outside'
    stage.mkdir(mode=0o700)
    outside.mkdir()
    secret = outside / 'existing'
    secret.write_text('untouched outside data')
    (outside / 'empty').mkdir()
    (stage / 'escape').symlink_to(outside, target_is_directory=True)
    code = r'''
import ctypes, errno, json, os, pathlib, sys
outside = pathlib.Path(sys.argv[1])
pathlib.Path('good').write_text('stage data')
pathlib.Path('a').mkdir()
pathlib.Path('b').mkdir()
pathlib.Path('a/item').write_text('movable')
os.rename('a/item', 'b/item')
os.link('b/item', 'a/link')
os.truncate('good', 3)
operations = {
 'read': lambda: (outside / 'existing').read_text(),
 'create': lambda: (outside / 'created').write_text('bad'),
 'open_truncate': lambda: (outside / 'existing').write_text('bad'),
 'truncate': lambda: os.truncate(outside / 'existing', 0),
 'rename_out': lambda: os.rename('good', outside / 'moved'),
 'rename_in': lambda: os.rename(outside / 'existing', 'stolen'),
 'link_out': lambda: os.link('good', outside / 'linked'),
 'link_in': lambda: os.link(outside / 'existing', 'linked'),
 'remove': lambda: os.unlink(outside / 'existing'),
 'mkdir': lambda: os.mkdir(outside / 'new-dir'),
 'rmdir': lambda: os.rmdir(outside / 'empty'),
 'symlink_create': lambda: os.symlink('target', outside / 'new-link'),
 'fifo': lambda: os.mkfifo(outside / 'new-fifo'),
 'symlink_escape': lambda: pathlib.Path('escape/existing').write_text('bad'),
}
denied = {}
for name, operation in operations.items():
    try:
        operation()
    except OSError as error:
        assert error.errno in (errno.EACCES, errno.EPERM, errno.EXDEV), (name, error)
        denied[name] = error.errno
    else:
        raise AssertionError('Sandbox allowed ' + name)
assert 'OMARCHY_TEST_SECRET' not in os.environ
assert ctypes.CDLL(None).prctl(39, 0, 0, 0, 0) == 1
print(json.dumps({'denied': denied, 'allowed_stage_write': pathlib.Path('good').read_text()}))
'''
    result = invoke(sandbox, stage, code, str(outside), env=dict(os.environ, OMARCHY_TEST_SECRET='do-not-inherit'))
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert len(report['denied']) == 14
    assert report['allowed_stage_write'] == 'sta'
    assert secret.read_text() == 'untouched outside data'
    assert sorted(path.name for path in outside.iterdir()) == ['empty', 'existing']


def test_inherited_outside_descriptor_is_closed(sandbox, tmp_path):
    stage = tmp_path / 'stage'
    stage.mkdir(mode=0o700)
    target = tmp_path / 'outside'
    target.write_text('preserved')
    fd = os.open(target, os.O_WRONLY)
    try:
        code = 'import os,sys,errno\ntry: os.write(int(sys.argv[1]),b"bad")\nexcept OSError as e: assert e.errno==errno.EBADF\nelse: raise AssertionError("inherited writable fd survived")'
        result = invoke(sandbox, stage, code, str(fd), pass_fds=(fd,))
    finally:
        os.close(fd)
    assert result.returncode == 0, result.stderr
    assert target.read_text() == 'preserved'


@pytest.mark.parametrize('kind', ['symlink_leaf', 'symlink_parent', 'public', 'root', 'foreign', 'missing', 'dot'])
def test_invalid_stage_never_runs_command(sandbox, tmp_path, kind):
    stage = tmp_path / 'stage'
    stage.mkdir(mode=0o700)
    selected = stage
    if kind == 'symlink_leaf':
        selected = tmp_path / 'link'
        selected.symlink_to(stage, target_is_directory=True)
    elif kind == 'symlink_parent':
        link = tmp_path / 'link'
        link.symlink_to(tmp_path, target_is_directory=True)
        selected = link / 'stage'
    elif kind == 'public':
        stage.chmod(0o777)
    elif kind == 'root':
        selected = Path('/')
    elif kind == 'foreign':
        selected = Path('/usr')
    elif kind == 'missing':
        selected = stage / 'missing'
    elif kind == 'dot':
        selected = str(stage) + '/../stage'
    result = invoke(sandbox, selected, 'print("UNSAFE_COMMAND_RAN")')
    assert result.returncode != 0
    assert 'UNSAFE_COMMAND_RAN' not in result.stdout


def test_symlink_replacement_race_cannot_redirect_writes(sandbox, tmp_path):
    stage, held, outside = tmp_path / 'stage', tmp_path / 'held', tmp_path / 'outside'
    stage.mkdir(mode=0o700)
    outside.mkdir(mode=0o700)
    stop = threading.Event()
    errors = []
    def swap():
        try:
            while not stop.is_set():
                stage.rename(held)
                stage.symlink_to(outside, target_is_directory=True)
                stage.unlink()
                held.rename(stage)
        except Exception as error:
            errors.append(error)
        finally:
            if stage.is_symlink():
                stage.unlink()
            if held.exists():
                held.rename(stage)
    thread = threading.Thread(target=swap)
    thread.start()
    try:
        for _ in range(24):
            result = invoke(sandbox, stage, 'from pathlib import Path; Path("probe").write_text("safe")')
            assert result.returncode in (0, 1), result.stderr
    finally:
        stop.set()
        thread.join(timeout=5)
    assert not thread.is_alive() and not errors
    assert not list(outside.iterdir()), 'Stage replacement redirected a confined write outside'


def test_probe_is_separate_from_enforcement(sandbox):
    result = subprocess.run([sandbox, '--probe'], capture_output=True, text=True, check=True)
    assert int(result.stdout) >= 3
