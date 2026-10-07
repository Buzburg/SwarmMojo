"""Fresh promotion requires current policy; existing transactions remain recoverable."""
import ast
import asyncio
import os

import pytest

pytest.importorskip('fcntl', reason='Patch promotion uses POSIX file descriptors and locks')

from app import patch_promotion as promotion, patch_tasks as tasks, validation_policy
from app.container_runner import ProcessResult
from test_patch_staging import project, change


def prepared(project, monkeypatch, *, reviewed=True):
    source, project_id, base = project

    async def fixture_syntax_check(workspace, control, request):
        # Exercise real staging/validation with a trusted syntax fixture checker.
        # The container sandbox is separately tested; no proposed code executes here.
        validation_policy.command_for(request, workspace)
        for name in request['files']:
            ast.parse((workspace / name).read_text())
        tasks.durable_json(control / 'policy.json', {'version': validation_policy.POLICY_VERSION})
        return ProcessResult(0, 'Fixture syntax check passed')

    monkeypatch.setattr(validation_policy, 'validate', fixture_syntax_check)
    task = asyncio.run(tasks.propose(project_id, base,
        [change(source, 'module.py', 'VALUE = 2\n')],
        [{'command': 'python.syntax', 'files': ['module.py']}]))
    task = asyncio.run(tasks.validate_task(task['id']))
    assert task['state'] == 'validated' and task['evidence'][0]['exit_code'] == 0
    if reviewed:
        promotion.review(task['id'])
    return task


@pytest.mark.parametrize('operation', ['review', 'authorize', 'apply'])
def test_changed_policy_rejects_fresh_operation_without_source_changes(project, monkeypatch, operation):
    source, _, _ = project
    task = prepared(project, monkeypatch, reviewed=operation != 'review')
    token = promotion.authorize(task['id'], task['patch_sha256'], 'apply') if operation == 'apply' else None
    control, before, _ = tasks.load_task(task['id'])
    monkeypatch.setattr(validation_policy, 'POLICY_VERSION', 'python-validation-v2')
    with pytest.raises(ValueError, match='policy'):
        if operation == 'review':
            promotion.review(task['id'])
        elif operation == 'authorize':
            promotion.authorize(task['id'], task['patch_sha256'], 'apply')
        else:
            asyncio.run(promotion.promote(task['id'], token))
    assert (source / 'module.py').read_text() == 'VALUE = 1\n'
    assert tasks.load_task(task['id'])[1] == before
    if operation != 'apply':
        assert not (control / 'approval-apply.json').exists()


def test_policy_change_does_not_prevent_authorized_rollback(project, monkeypatch):
    source, _, _ = project
    task = prepared(project, monkeypatch)
    token = promotion.authorize(task['id'], task['patch_sha256'], 'apply')
    assert asyncio.run(promotion.promote(task['id'], token))['state'] == 'applied'
    monkeypatch.setattr(validation_policy, 'POLICY_VERSION', 'python-validation-v2')
    promotion.review(task['id'], rollback=True)
    rollback = promotion.authorize(task['id'], task['patch_sha256'], 'rollback')
    assert asyncio.run(promotion.promote(task['id'], rollback, rollback=True))['state'] == 'rolled_back'
    assert (source / 'module.py').read_text() == 'VALUE = 1\n'


@pytest.mark.parametrize('rollback', [False, True])
def test_policy_change_preserves_recovery_of_dispatched_transaction(project, monkeypatch, rollback):
    source, _, _ = project
    task = prepared(project, monkeypatch)
    original_replace = promotion.replace_entry

    def interrupted(*args, **kwargs):
        original_replace(*args, **kwargs)
        raise InterruptedError('Fixture interruption after the replacement reached disk')

    token = promotion.authorize(task['id'], task['patch_sha256'], 'apply')
    with monkeypatch.context() as interruption:
        interruption.setattr(promotion, 'replace_entry', interrupted)
        with pytest.raises(InterruptedError):
            asyncio.run(promotion.promote(task['id'], token))
    saved = tasks.load_task(task['id'])[1]
    assert saved['state'] == 'failed' and saved['transaction'] is not None
    monkeypatch.setattr(validation_policy, 'POLICY_VERSION', 'python-validation-v2')
    promotion.review(task['id'], rollback=rollback)
    direction = 'rollback' if rollback else 'apply'
    token = promotion.authorize(task['id'], task['patch_sha256'], direction)
    result = asyncio.run(promotion.promote(task['id'], token, rollback=rollback))
    assert result['state'] == ('rolled_back' if rollback else 'applied')
    assert (source / 'module.py').read_text() == ('VALUE = 1\n' if rollback else 'VALUE = 2\n')


@pytest.mark.parametrize('now,expired', [(99.999, False), (100, True), (100.001, True)])
def test_authorization_expiry_includes_exact_deadline(tmp_path, monkeypatch, now, expired):
    token = 'fixture-token'
    task = {'patch_sha256': 'a' * 64}
    tasks.durable_json(tmp_path / 'approval-apply.json', {
        'direction': 'apply', 'patch_sha256': task['patch_sha256'],
        'operator_uid': os.getuid(), 'expires_at': 100,
        'token_sha256': tasks.sha(token.encode()),
    })
    monkeypatch.setattr(promotion.time, 'time', lambda: now)
    if expired:
        with pytest.raises(PermissionError, match='expired'):
            promotion.check_authorization(tmp_path, task, token, 'apply')
    else:
        promotion.check_authorization(tmp_path, task, token, 'apply')
