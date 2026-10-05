"""Require native Landlock enforcement inside the real rootless worker image."""
import asyncio
import json
import os
from pathlib import Path

import pytest

from app import container_runner
from app import validation_policy

IMAGE = os.getenv('OMARCHY_NATIVE_WORKER_IMAGE')
pytestmark = pytest.mark.skipif(not IMAGE, reason='Explicitly select the locally built native worker image')


def test_landlock_and_container_layers_operate_together(tmp_path, monkeypatch):
    stage, control = tmp_path / 'stage', tmp_path / 'control'
    stage.mkdir(mode=0o700)
    control.mkdir(mode=0o700)
    (stage / 'escape').symlink_to('/etc/passwd')
    monkeypatch.setenv('OMARCHY_COMBINED_SECRET', 'never-forward-this')
    code = r'''
import errno, json, os, pathlib
assert 'OMARCHY_COMBINED_SECRET' not in os.environ
assert os.geteuid() == 1000
assert pathlib.Path.cwd() == pathlib.Path('/workspace')
pathlib.Path('allowed').write_text('combined layers work')
for path in ('/tmp/blocked', '/etc/passwd', '/usr/bin/python3', 'escape'):
    try:
        pathlib.Path(path).write_text('forbidden')
    except OSError as error:
        assert error.errno in (errno.EACCES, errno.EPERM, errno.EROFS), (path, error)
    else:
        raise AssertionError('Outside write succeeded: ' + path)
try:
    pathlib.Path('/etc/passwd').read_text()
except PermissionError:
    pass
else:
    raise AssertionError('Read outside stage/toolchain succeeded')
print(json.dumps({'combined': 'passed'}))
'''
    result = asyncio.run(container_runner.execute(stage, control, IMAGE,
        ['/usr/bin/python3', '-I', '-B', '-c', code], memory='128m'))
    assert result.returncode == 0, result.output
    assert json.loads(result.output)['combined'] == 'passed'
    assert (stage / 'allowed').read_text() == 'combined layers work'
    assert container_runner.confirmed_clean(control)


def test_registered_validation_success_failure_and_policy_journal(tmp_path, monkeypatch):
    manifest = Path(__file__).resolve().parents[2] / 'deployment/packages/worker-image.manifest.json'
    metadata = json.loads(manifest.read_text())
    assert metadata['image_id'] == IMAGE
    config = tmp_path / 'image.json'
    config.write_text(json.dumps({'image_id': IMAGE, 'sandbox_sha256': metadata['sandbox_sha256'],
                                  'policy_version': validation_policy.POLICY_VERSION}))
    monkeypatch.setattr(validation_policy, 'IMAGE_CONFIG', config)
    stage = tmp_path / 'stage'
    stage.mkdir(mode=0o700)
    for name, source, expected in [('valid', 'x = 1\n', 0), ('invalid', 'def invalid(:\n', 1)]:
        (stage / 'module.py').write_text(source)
        control = tmp_path / name
        control.mkdir(mode=0o700)
        result = asyncio.run(validation_policy.validate(stage, control,
            {'command': 'python.syntax', 'files': ['module.py']}))
        assert result.returncode == expected, result.output
        policy = json.loads((control / 'policy.json').read_text())
        assert policy['image_id'] == IMAGE and policy['network'] == 'none'
        assert container_runner.confirmed_clean(control)
    tests = stage / 'tests'
    tests.mkdir()
    for success in (True, False):
        (tests / 'test_fixture.py').write_text(
            'import unittest\nclass Fixture(unittest.TestCase):\n'
            f'    def test_answer(self): self.assertTrue({success!r})\n')
        control = tmp_path / ('tests-pass' if success else 'tests-fail')
        control.mkdir(mode=0o700)
        result = asyncio.run(validation_policy.validate(stage, control, {'command': 'python.tests'}))
        assert result.returncode == (0 if success else 1), result.output
        assert 'Ran 1 test' in result.output
        assert container_runner.confirmed_clean(control)
