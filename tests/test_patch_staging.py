"""Stage and validate real fixture patches without changing the source checkout."""
import asyncio
import json
import os
from pathlib import Path
import subprocess

import pytest

from app import patch_tasks as tasks

live = pytest.mark.skipif(not os.getenv('OMARCHY_NATIVE_WORKER_IMAGE'), reason='Requires the built native worker image')


@pytest.fixture
def project(tmp_path, monkeypatch):
    source = tmp_path / 'repository with spaces'
    source.mkdir()
    def git(*args):
        return subprocess.run(['git', '-C', str(source), *args], check=True, text=True, capture_output=True).stdout.strip()
    git('init', '-q')
    (source / 'module.py').write_text('VALUE = 1\n')
    (source / 'README.md').write_text('original documentation\n')
    (source / 'tests').mkdir()
    (source / 'tests/test_value.py').write_text('import unittest\nclass TestValue(unittest.TestCase):\n    def test_value(self): self.assertTrue(True)\n')
    git('add', '.')
    git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'base')
    monkeypatch.setattr(tasks, 'STORE', tmp_path / 'store')
    registration = asyncio.run(tasks.register_project(str(source)))
    return source, registration['id'], git('rev-parse', 'HEAD')


def change(source, name, text):
    original = source / name
    return {'path': name, 'before_sha256': tasks.sha(original.read_bytes()) if original.exists() else None, 'after': text}


@live
def test_real_stage_validation_preserves_source_and_records_evidence(project):
    source, project_id, base = project
    (source / 'README.md').write_text('unrelated user edit\n')
    task = asyncio.run(tasks.propose(project_id, base, [change(source, 'module.py', 'VALUE = 2\n')],
        [{'command': 'python.syntax', 'files': ['module.py']}, {'command': 'python.tests'}]))
    assert task['state'] == 'staged'
    assert (source / 'module.py').read_text() == 'VALUE = 1\n'
    task = asyncio.run(tasks.validate_task(task['id']))
    assert task['state'] == 'validated'
    assert task['validated_patch_sha256'] == task['patch_sha256']
    assert [item['state'] for item in task['history']] == ['proposed', 'staged', 'validating', 'validated']
    assert [item['exit_code'] for item in task['evidence']] == [0, 0]
    assert (source / 'module.py').read_text() == 'VALUE = 1\n'
    assert (source / 'README.md').read_text() == 'unrelated user edit\n'
    control = tasks.task_directory(task['id'])
    assert json.loads((control / 'preimages.json').read_text())['module.py']['text'] == 'VALUE = 1\n'
    assert (control / 'stage/module.py').read_text() == 'VALUE = 2\n'


@live
@pytest.mark.parametrize('failure', ['syntax', 'outside', 'mutation', 'git_metadata'])
def test_failed_or_mutating_checks_never_validate(project, failure):
    source, project_id, base = project
    if failure == 'syntax':
        changes = [change(source, 'module.py', 'def broken(:\n')]
        checks = [{'command': 'python.syntax', 'files': ['module.py']}]
    else:
        action = {'outside': "Path('/tmp/forbidden-write').write_text('bad')",
                  'mutation': "Path('module.py').write_text('VALUE = 99\\n')",
                  'git_metadata': "Path('.git').write_text('attacker metadata')"}[failure]
        text = 'import unittest\nfrom pathlib import Path\nclass TestValue(unittest.TestCase):\n    def test_value(self): ' + action + '\n'
        changes = [change(source, 'tests/test_value.py', text)]
        checks = [{'command': 'python.tests'}]
    task = asyncio.run(tasks.propose(project_id, base, changes, checks))
    with pytest.raises(ValueError):
        asyncio.run(tasks.validate_task(task['id']))
    _, task, _ = tasks.load_task(task['id'])
    assert task['state'] == 'failed'
    assert task['evidence']
    if failure == 'mutation':
        assert 'mutated staged contents' in task['error']
        assert task['evidence'][0]['exit_code'] == 0
    else:
        assert task['evidence'][0]['exit_code'] != 0
    assert (source / 'module.py').read_text() == 'VALUE = 1\n'
    assert 'attacker' not in (tasks.task_directory(task['id']) / 'stage/.git').read_text()


@pytest.mark.parametrize('path', ['../escape.py', '/tmp/escape.py', 'a/../b.py', '.git/config', '.agents/rules.py', '.env.local', 'a\\b.py'])
def test_bad_patch_paths_are_rejected(project, path):
    _, project_id, base = project
    with pytest.raises(ValueError):
        asyncio.run(tasks.propose(project_id, base,
            [{'path': path, 'before_sha256': None, 'after': 'x=1'}], [{'command': 'python.tests'}]))


def test_digest_tampering_prevents_validation(project):
    source, project_id, base = project
    task = asyncio.run(tasks.propose(project_id, base, [change(source, 'module.py', 'VALUE = 2\n')],
        [{'command': 'python.syntax', 'files': ['module.py']}]))
    control = tasks.task_directory(task['id'])
    patch = json.loads((control / 'patch.json').read_text())
    patch['changes'][0]['after'] = 'VALUE = 999\n'
    tasks.durable_json(control / 'patch.json', patch)
    with pytest.raises(ValueError, match='digest'):
        asyncio.run(tasks.validate_task(task['id']))
    assert json.loads((control / 'task.json').read_text())['state'] == 'staged'


def test_preimage_tampering_prevents_validation(project):
    source, project_id, base = project
    task = asyncio.run(tasks.propose(project_id, base, [change(source, 'module.py', 'VALUE = 2\n')],
        [{'command': 'python.syntax', 'files': ['module.py']}]))
    control = tasks.task_directory(task['id'])
    tasks.durable_json(control / 'preimages.json', {'module.py': {'text': 'wrong backup', 'mode': 420}})
    with pytest.raises(ValueError, match='Preimage'):
        asyncio.run(tasks.validate_task(task['id']))


def test_existing_user_edit_conflicts_without_modification(project):
    source, project_id, base = project
    proposal = change(source, 'module.py', 'VALUE = 2\n')
    (source / 'module.py').write_text('valuable user edit\n')
    with pytest.raises(ValueError, match='conflicting edit'):
        asyncio.run(tasks.propose(project_id, base, [proposal], [{'command': 'python.syntax', 'files': ['module.py']}]))
    assert (source / 'module.py').read_text() == 'valuable user edit\n'
