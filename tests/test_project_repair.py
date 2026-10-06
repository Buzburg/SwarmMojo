"""A repair uses recorded failed checks; it cannot expand edits, checks or approval."""
import asyncio
import io
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from app import patch_tasks as tasks, project_assistant, project_repair, validation_policy
from app.container_runner import ProcessResult
from scripts import project_workshop
from test_patch_staging import project, change, live
from test_project_assistant import completion
from test_task_worker import worker


def failed_task(project):
    source, project_id, base = project
    return asyncio.run(tasks.propose(project_id, base, [change(source, 'module.py', 'VALUE = 2 +\n')],
                                   [{'command': 'python.syntax', 'files': ['module.py']}]))


@pytest.fixture
def failed(project, monkeypatch):
    async def validation(stage, control, request):
        # Offline fixture for the existing validation journal contract, not enforcement evidence.
        tasks.durable_json(control / 'policy.json', {
            'version': validation_policy.POLICY_VERSION, 'request': request,
            'argv': validation_policy.command_for(request, stage), 'image_id': 'sha256:' + 'a' * 64,
            'sandbox_sha256': 'b' * 64, 'network': 'none', 'cpus': '2', 'memory': '256m', 'timeout_seconds': 30})
        tasks.durable_json(control / 'container.json', {
            'task_id': 'c' * 32, 'container_id': 'd' * 64, 'workspace': str(stage.resolve()),
            'state': 'cleaned', 'cleanup_error': None})
        return ProcessResult(1, '  File "module.py", line 1\n    VALUE = 2 +\nSyntaxError: invalid syntax\n')

    monkeypatch.setattr(validation_policy, 'validate', validation)
    task = failed_task(project)
    with pytest.raises(ValueError, match='Registered validation failed'):
        asyncio.run(tasks.validate_task(task['id']))
    return tasks.load_task(task['id'])


def model(monkeypatch, after='VALUE = 2\n'):
    calls = []

    async def generate(instruction, snapshots):
        calls.append((instruction, snapshots))
        assert 'SyntaxError' in instruction and len(instruction.encode()) <= 1024
        assert snapshots == {'module.py': 'VALUE = 2 +\n'}
        return completion({'changes': [{'path': 'module.py', 'after': after}]})

    monkeypatch.setattr(project_assistant, 'generate', generate)
    return calls


def test_repair_preserves_parent_base_preimages_checks_and_source(failed, project, monkeypatch):
    control, parent, old_patch = failed
    parent_bytes = (control / 'task.json').read_bytes()
    calls = model(monkeypatch)
    result = asyncio.run(project_repair.draft_repair(parent['id']))
    child_control, child, patch = tasks.load_task(result['task']['id'])
    assert len(calls) == 1 and child['state'] == 'staged' and child['id'] != parent['id']
    assert patch['checks'] == old_patch['checks'] and patch['base_commit'] == old_patch['base_commit']
    assert patch['changes'] == [{'path': 'module.py', 'before_sha256': tasks.sha(b'VALUE = 1\n'), 'after': 'VALUE = 2\n'}]
    assert (child_control / 'stage/module.py').read_text() == 'VALUE = 2\n'
    assert (control / 'stage/module.py').read_text() == 'VALUE = 2 +\n'
    assert (control / 'task.json').read_bytes() == parent_bytes
    assert (project[0] / 'module.py').read_text() == 'VALUE = 1\n'
    assert not list(child_control.glob('approval-*'))
    record = json.loads((tasks.STORE / 'repairs' / result['repair_id'] / 'repair.json').read_text())
    assert record['parent_task_id'] == parent['id'] and record['task_id'] == child['id']
    assert record['evidence_sha256'] == tasks.sha(tasks.canonical(parent['evidence']))


@pytest.mark.parametrize('tampering', ['state', 'exit', 'boolean', 'command', 'policy', 'missing_policy',
                                     'cleanup', 'missing_container', 'stage', 'preimage', 'source', 'revision'])
def test_unproven_or_stale_failure_does_not_reach_model(failed, project, monkeypatch, tampering):
    control, task, _ = failed
    if tampering == 'state':
        task['state'] = 'cleanup_required'
    elif tampering == 'exit':
        task['evidence'][0]['exit_code'] = 0
    elif tampering == 'boolean':
        task['evidence'][0]['exit_code'] = True
    elif tampering == 'command':
        task['evidence'][0]['command'] = {'command': 'shell'}
    elif tampering == 'policy':
        task['evidence'][0]['policy'] = '../outside.json'
    elif tampering == 'missing_policy':
        (control / 'check-0/policy.json').unlink()
    elif tampering == 'cleanup':
        path = control / 'check-0/container.json'
        value = json.loads(path.read_text())
        value['state'] = 'running'
        tasks.durable_json(path, value)
    elif tampering == 'missing_container':
        (control / 'check-0/container.json').unlink()
    elif tampering == 'stage':
        (control / 'stage/module.py').write_text('CHANGED = True\n')
    elif tampering == 'preimage':
        tasks.durable_json(control / 'preimages.json', {'module.py': {'text': 'fake', 'mode': 420}})
    elif tampering == 'source':
        (project[0] / 'module.py').write_text('USER_EDIT = True\n')
    elif tampering == 'revision':
        subprocess.run(['git', '-C', str(project[0]), '-c', 'user.name=Fixture',
                        '-c', 'user.email=fixture@example.invalid', 'commit', '--allow-empty', '-qm', 'new head'], check=True)
    tasks.durable_json(control / 'task.json', task)

    async def forbidden(*_):
        pytest.fail('Unproven failure reached model generation')
    monkeypatch.setattr(project_assistant, 'generate', forbidden)
    with pytest.raises((ValueError, OSError)):
        asyncio.run(project_repair.draft_repair(task['id']))
    assert len(list((tasks.STORE / 'tasks').iterdir())) == 1


@pytest.mark.parametrize('after', ['VALUE = 2 +\n', 'VALUE = 1\n', None])
def test_no_change_reversion_or_deletion_does_not_stage_repair(failed, monkeypatch, after):
    _, task, _ = failed
    model(monkeypatch, after)
    with pytest.raises(ValueError):
        asyncio.run(project_repair.draft_repair(task['id']))
    assert len(list((tasks.STORE / 'tasks').iterdir())) == 1
    record = json.loads(next((tasks.STORE / 'repairs').glob('*/repair.json')).read_text())
    assert record['state'] == 'failed'


def test_long_diagnostic_is_bounded_and_retains_full_output_identity(failed, monkeypatch):
    control, task, _ = failed
    output = 'SyntaxError: invalid syntax\n' + ('diagnostic detail \U0001f9ea\n' * 400)
    task['evidence'][0]['output'] = output
    tasks.durable_json(control / 'task.json', task)
    calls = model(monkeypatch)
    result = asyncio.run(project_repair.draft_repair(task['id']))
    assert len(calls[0][0].encode()) <= 1024
    record = json.loads((tasks.STORE / 'repairs' / result['repair_id'] / 'repair.json').read_text())
    assert record['diagnostic']['truncated'] is True
    assert len(record['diagnostic']['text'].encode()) <= 600
    assert record['diagnostic']['raw_sha256'] == tasks.sha(output.encode())


def test_model_cannot_change_validation_checks(failed, monkeypatch):
    _, task, _ = failed
    async def generate(*_):
        return completion({'changes': [{'path': 'module.py', 'after': 'VALUE = 2\n'}],
                           'checks': [{'command': 'shell'}]})
    monkeypatch.setattr(project_assistant, 'generate', generate)
    with pytest.raises(ValueError, match='changes array'):
        asyncio.run(project_repair.draft_repair(task['id']))
    assert len(list((tasks.STORE / 'tasks').iterdir())) == 1


@pytest.mark.parametrize('kind', ['error', 'cancel', 'incomplete', 'extra_path', 'source_edit', 'stage_edit'])
def test_generation_failure_or_race_preserves_original_attempt(failed, project, monkeypatch, kind):
    control, task, _ = failed
    before = (control / 'task.json').read_bytes()

    async def generate(*_):
        if kind == 'error':
            raise RuntimeError('fixture failure')
        if kind == 'cancel':
            raise asyncio.CancelledError()
        if kind == 'source_edit':
            (project[0] / 'module.py').write_text('USER_EDIT = True\n')
        if kind == 'stage_edit':
            (control / 'stage/module.py').write_text('CHANGED = True\n')
        return completion({'changes': [{'path': 'tests/test_value.py' if kind == 'extra_path' else 'module.py',
                                         'after': 'VALUE = 2\n'}]}, 'length' if kind == 'incomplete' else 'stop')
    monkeypatch.setattr(project_assistant, 'generate', generate)
    with pytest.raises((RuntimeError, ValueError, asyncio.CancelledError)):
        asyncio.run(project_repair.draft_repair(task['id']))
    assert (control / 'task.json').read_bytes() == before
    assert len(list((tasks.STORE / 'tasks').iterdir())) == 1
    assert (project[0] / 'module.py').read_text() == ('USER_EDIT = True\n' if kind == 'source_edit' else 'VALUE = 1\n')


@live
def test_workshop_repairs_actual_failure_validates_and_waits_for_review(project, worker, monkeypatch, capsys):
    from app.task_worker_client import request
    task = failed_task(project)
    assert request('task.validate', {'task_id': task['id']})['error'] == 'validation_failed'
    model(monkeypatch)
    stream = io.StringIO()
    monkeypatch.setattr(stream, 'isatty', lambda: True)
    monkeypatch.setattr(sys, 'stdin', stream)
    answers = iter(['1', 'module.py', '1', '/repair ' + task['id'], '', '/exit'])
    monkeypatch.setattr('builtins.input', lambda _: next(answers))
    asyncio.run(project_workshop.main())
    child = [json.loads(path.read_text()) for path in (tasks.STORE / 'tasks').glob('*/task.json')
             if path.parent.name != task['id']][0]
    assert child['state'] == 'awaiting_apply'
    assert child['evidence'][0]['exit_code'] == 0
    assert tasks.load_task(task['id'])[1]['state'] == 'failed'
    assert (project[0] / 'module.py').read_text() == 'VALUE = 1\n'
    assert 'Selected checks passed' in capsys.readouterr().out


@pytest.mark.skipif(not os.getenv('ROMS_LIVE_DRAFT'), reason='Explicit isolated live-model repair verification required')
def test_real_model_repairs_actual_unittest_failure(project, monkeypatch):
    from app import patch_promotion
    settings = dict(line.split('=', 1) for line in (Path.home() / '.config/goose/runtime.env').read_text().splitlines() if '=' in line)
    monkeypatch.setenv('ROMS_GATEWAY_API_KEY', settings['ROMS_GATEWAY_API_KEY'])
    source, project_id, _ = project
    test_source = ('import ast\nfrom pathlib import Path\nimport unittest\n'
                   'class TestValue(unittest.TestCase):\n'
                   '    def test_value(self):\n'
                   '        value = ast.literal_eval(ast.parse(Path("module.py").read_text()).body[0].value)\n'
                   '        self.assertEqual(value, 2)\n')
    (source / 'tests/test_value.py').write_text(test_source)
    subprocess.run(['git', '-C', str(source), 'add', 'tests/test_value.py'], check=True)
    subprocess.run(['git', '-C', str(source), '-c', 'user.name=Fixture', '-c',
                    'user.email=fixture@example.invalid', 'commit', '-qm', 'required value behavior'], check=True)
    base = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    task = asyncio.run(tasks.propose(project_id, base, [change(source, 'module.py', 'VALUE = 3\n')],
                                   [{'command': 'python.tests'}]))
    with pytest.raises(ValueError, match='Registered validation failed'):
        asyncio.run(tasks.validate_task(task['id']))
    result = asyncio.run(project_repair.draft_repair(task['id']))
    child = asyncio.run(tasks.validate_task(result['task']['id']))
    assert child['state'] == 'validated' and child['evidence'][0]['exit_code'] == 0
    _, _, patch = tasks.load_task(child['id'])
    assert patch['checks'] == [{'command': 'python.tests'}]
    assert patch['changes'][0]['path'] == 'module.py'
    assert patch['changes'][0]['after'] == 'VALUE = 2\n'
    assert (project[0] / 'module.py').read_text() == 'VALUE = 1\n'
    assert (project[0] / 'tests/test_value.py').read_text() == test_source
    record = json.loads((tasks.STORE / 'repairs' / result['repair_id'] / 'repair.json').read_text())
    assert record['model'] == 'goose-2.9b' and record['usage']['completion_tokens'] > 0
    patch_promotion.review(child['id'])
    token = patch_promotion.authorize(child['id'], child['patch_sha256'], 'apply')
    assert asyncio.run(patch_promotion.promote(child['id'], token))['state'] == 'applied'
    assert (project[0] / 'module.py').read_text() == 'VALUE = 2\n'
    token = patch_promotion.authorize(child['id'], child['patch_sha256'], 'rollback')
    assert asyncio.run(patch_promotion.promote(child['id'], token, rollback=True))['state'] == 'rolled_back'
    assert (project[0] / 'module.py').read_text() == 'VALUE = 1\n'
