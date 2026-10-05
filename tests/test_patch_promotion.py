"""Real validated patch promotion, conflict preservation and process-crash recovery."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import io
import sys

import pytest

from app import patch_promotion as promotion
from app import patch_tasks as tasks
from scripts import patch_tasks_cli
from test_patch_staging import project, change, live

pytestmark = live


def prepared(project, changes=None):
    source, project_id, base = project
    changes = changes or [change(source, 'module.py', 'VALUE = 2\n'),
                          change(source, 'tests/test_value.py', None),
                          change(source, 'new/sub/file.py', 'NEW = True\n'),
                          change(source, 'empty.txt', '')]
    task = asyncio.run(tasks.propose(project_id, base, changes,
                                    [{'command': 'python.syntax', 'files': ['module.py']}]))
    task = asyncio.run(tasks.validate_task(task['id']))
    promotion.review(task['id'])
    return task


def approved(task, rollback=False):
    return promotion.authorize(task['id'], task['patch_sha256'], 'rollback' if rollback else 'apply')


def apply(task, rollback=False):
    return asyncio.run(promotion.promote(task['id'], approved(task, rollback), rollback=rollback))


def test_roundtrip_and_duplicate_requests_preserve_unrelated_user_edits(project):
    source, _, _ = project
    original = (source / 'tests/test_value.py').read_bytes()
    mode = (source / 'module.py').stat().st_mode
    task = prepared(project)
    (source / 'README.md').write_text('user-owned edit\n')
    review = promotion.review(task['id'])
    assert '-VALUE = 1' in review['diff'] and '+VALUE = 2' in review['diff']
    assert apply(task)['state'] == 'applied'
    assert (source / 'module.py').read_text() == 'VALUE = 2\n'
    assert (source / 'module.py').stat().st_mode == mode
    assert not (source / 'tests/test_value.py').exists()
    assert (source / 'empty.txt').read_bytes() == b''
    assert apply(task)['state'] == 'applied'
    assert apply(task, rollback=True)['state'] == 'rolled_back'
    assert (source / 'module.py').read_text() == 'VALUE = 1\n'
    assert (source / 'tests/test_value.py').read_bytes() == original
    assert not (source / 'new').exists() and not (source / 'empty.txt').exists()
    (source / 'module.py').write_text('later user edit\n')
    assert apply(task, rollback=True)['state'] == 'rolled_back'
    assert (source / 'module.py').read_text() == 'later user edit\n'
    assert (source / 'README.md').read_text() == 'user-owned edit\n'


@pytest.mark.parametrize('invalid', ['missing', 'wrong_token', 'expired', 'wrong_digest', 'wrong_direction'])
def test_authorization_is_required_and_bound_to_patch_and_direction(project, invalid):
    source, _, _ = project
    task = prepared(project)
    token = approved(task) if invalid != 'missing' else 'absent'
    path = tasks.task_directory(task['id']) / 'approval-apply.json'
    if invalid in {'expired', 'wrong_digest', 'wrong_direction'}:
        approval = json.loads(path.read_text())
        approval[{'expired': 'expires_at', 'wrong_digest': 'patch_sha256', 'wrong_direction': 'direction'}[invalid]] = (
            0 if invalid == 'expired' else 'wrong')
        tasks.durable_json(path, approval)
    if invalid == 'wrong_token':
        token = 'wrong'
    with pytest.raises((PermissionError, FileNotFoundError)):
        asyncio.run(promotion.promote(task['id'], token))
    assert (source / 'module.py').read_text() == 'VALUE = 1\n'
    assert not (source / 'new').exists()


@pytest.mark.parametrize('conflict', ['edit', 'head', 'symlink', 'root', 'stage'])
def test_preflight_conflicts_preserve_all_source_files(project, conflict):
    source, _, _ = project
    task = prepared(project)
    if conflict == 'edit':
        (source / 'tests/test_value.py').write_text('later edit')
    elif conflict == 'head':
        subprocess.run(['git', '-C', str(source), '-c', 'user.name=Fixture', '-c',
                        'user.email=fixture@example.invalid', 'commit', '--allow-empty', '-qm', 'later'], check=True)
    elif conflict == 'symlink':
        (source / 'new').symlink_to(source / 'tests', target_is_directory=True)
    elif conflict == 'root':
        moved = source.with_name('moved')
        source.rename(moved)
        shutil.copytree(moved, source)
    else:
        (tasks.task_directory(task['id']) / 'stage/module.py').write_text('CHANGED = True\n')
    with pytest.raises((promotion.Conflict, OSError)):
        apply(task)
    assert (source / 'module.py').read_text() == 'VALUE = 1\n'
    assert not (source / 'empty.txt').exists()


def test_rollback_conflict_and_duplicate_apply_preserve_later_user_edits(project):
    source, _, _ = project
    task = prepared(project)
    apply(task)
    (source / 'new/sub/file.py').write_text('later edit\n')
    assert apply(task)['state'] == 'applied'
    with pytest.raises(promotion.Conflict, match='Conflicting user edit'):
        apply(task, rollback=True)
    assert (source / 'module.py').read_text() == 'VALUE = 2\n'
    assert (source / 'new/sub/file.py').read_text() == 'later edit\n'


@pytest.mark.parametrize('rollback', [False, True])
@pytest.mark.parametrize('crash_at', ['replacement', 'temporary_write'])
def test_fresh_process_recovers_interrupted_transaction(project, rollback, crash_at):
    source, _, _ = project
    task = prepared(project)
    token = approved(task)
    pid = os.fork()
    if pid == 0:
        try:
            if crash_at == 'replacement':
                original = promotion.replace_entry
                def crash(*args, **kwargs):
                    original(*args, **kwargs)
                    os._exit(77)
                promotion.replace_entry = crash
            else:
                def crash(descriptor, mode):
                    os.ftruncate(descriptor, 1)
                    os.fsync(descriptor)
                    os._exit(77)
                promotion.os.fchmod = crash
            asyncio.run(promotion.promote(task['id'], token))
        finally:
            os._exit(78)
    _, status = os.waitpid(pid, 0)
    assert os.waitstatus_to_exitcode(status) == 77
    assert tasks.load_task(task['id'])[1]['state'] == 'applying'
    result = apply(task, rollback=rollback)
    assert result['state'] == ('rolled_back' if rollback else 'applied')
    assert (source / 'module.py').read_text() == ('VALUE = 1\n' if rollback else 'VALUE = 2\n')
    assert not list(source.rglob('.omarchy-*.tmp'))
    if not rollback:
        apply(task, rollback=True)
    assert not (source / 'new').exists()


def test_last_moment_edit_is_preserved(project, monkeypatch):
    source, _, _ = project
    task = prepared(project)
    original = promotion.replace_entry
    def interfere(*args, **kwargs):
        (source / 'module.py').write_text('concurrent user edit\n')
        return original(*args, **kwargs)
    monkeypatch.setattr(promotion, 'replace_entry', interfere)
    with pytest.raises(promotion.Conflict, match='immediately before'):
        apply(task)
    assert (source / 'module.py').read_text() == 'concurrent user edit\n'
    assert not (source / 'new').exists()


def test_windows_drive_roundtrip_with_native_private_journal(project):
    source, _, base = project
    workspace = Path(__file__).resolve().parents[2]
    if not str(workspace).startswith('/mnt/'):
        pytest.skip('Requires the actual Windows-mounted workspace')
    with tempfile.TemporaryDirectory(prefix='promotion-fixture-', dir=workspace / 'tmp') as directory:
        target = Path(directory) / 'repository'
        shutil.copytree(source, target)
        registration = asyncio.run(tasks.register_project(str(target)))
        task = prepared((target, registration['id'], base))
        assert apply(task)['state'] == 'applied'
        assert (target / 'new/sub/file.py').read_text() == 'NEW = True\n'
        assert apply(task, rollback=True)['state'] == 'rolled_back'
        assert (target / 'module.py').read_text() == 'VALUE = 1\n'
        assert not (target / 'new').exists()


@pytest.mark.parametrize('response', ['pipe', 'decline', 'confirm'])
def test_operator_cli_requires_interactive_exact_confirmation(project, monkeypatch, capsys, response):
    source, _, _ = project
    task = prepared(project)
    monkeypatch.setattr(sys, 'argv', ['patch_tasks_cli', 'apply', task['id']])
    stream = io.StringIO()
    monkeypatch.setattr(stream, 'isatty', lambda: response != 'pipe')
    monkeypatch.setattr(sys, 'stdin', stream)
    monkeypatch.setattr('builtins.input', lambda _: 'apply ' + task['patch_sha256'][:12] if response == 'confirm' else 'yes')
    if response == 'confirm':
        asyncio.run(patch_tasks_cli.main())
        assert (source / 'module.py').read_text() == 'VALUE = 2\n'
    else:
        with pytest.raises(ValueError, match='interactive|No matching approval'):
            asyncio.run(patch_tasks_cli.main())
        assert (source / 'module.py').read_text() == 'VALUE = 1\n'
        assert not (tasks.task_directory(task['id']) / 'approval-apply.json').exists()
    output = capsys.readouterr().out
    assert task['patch_sha256'] in output and str(source) in output
    assert 'token_sha256' not in output


def test_rollback_resumes_after_process_crash_and_retains_user_directory(project):
    source, _, _ = project
    task = prepared(project)
    apply(task)
    (source / 'new/sub/user.txt').write_text('preserve me')
    token = approved(task, rollback=True)
    pid = os.fork()
    if pid == 0:
        try:
            original = promotion.replace_entry
            def crash(*args, **kwargs):
                original(*args, **kwargs)
                os._exit(77)
            promotion.replace_entry = crash
            asyncio.run(promotion.promote(task['id'], token, rollback=True))
        finally:
            os._exit(78)
    _, status = os.waitpid(pid, 0)
    assert os.waitstatus_to_exitcode(status) == 77
    result = apply(task, rollback=True)
    assert result['state'] == 'rolled_back'
    assert set(result['retained_directories']) == {'new', 'new/sub'}
    assert (source / 'new/sub/user.txt').read_text() == 'preserve me'
    assert (source / 'module.py').read_text() == 'VALUE = 1\n'


def test_review_describes_empty_files_and_missing_final_newlines(project):
    source, _, _ = project
    task = prepared(project, [change(source, 'module.py', 'VALUE = 2'), change(source, 'empty.txt', '')])
    review = promotion.review(task['id'])
    assert '+VALUE = 2\n\\ No newline at end of file\n' in review['diff']
    empty = review['changes'][1]
    assert empty['before_exists'] is False and empty['after_exists'] is True
    assert empty['before_sha256'] is None and empty['after_sha256'] == tasks.sha(b'')
    apply(task)
    reverse = promotion.review(task['id'], rollback=True)['changes'][1]
    assert reverse['before_exists'] is True and reverse['after_exists'] is False


def test_recovery_of_noop_before_interrupted_change(project):
    source, _, _ = project
    task = prepared(project, [change(source, 'module.py', 'VALUE = 1\n'),
                              change(source, 'README.md', 'changed\n')])
    token = approved(task)
    pid = os.fork()
    if pid == 0:
        try:
            original = promotion.replace_entry
            def crash(*args, **kwargs):
                original(*args, **kwargs)
                os._exit(77)
            promotion.replace_entry = crash
            asyncio.run(promotion.promote(task['id'], token))
        finally:
            os._exit(78)
    _, status = os.waitpid(pid, 0)
    assert os.waitstatus_to_exitcode(status) == 77
    assert apply(task)['state'] == 'applied'
    assert apply(task, rollback=True)['state'] == 'rolled_back'
    assert (source / 'README.md').read_text() == 'original documentation\n'


def test_extended_metadata_is_preserved_by_refusing_unsupported_promotion(project):
    source, _, _ = project
    task = prepared(project)
    target = source / 'tests/test_value.py'
    original = target.read_bytes()
    os.setxattr(target, 'user.fixture', b'preserve this metadata')
    with pytest.raises(promotion.Conflict, match='extended metadata'):
        apply(task)
    assert os.getxattr(target, 'user.fixture') == b'preserve this metadata'
    assert target.read_bytes() == original
    assert (source / 'module.py').read_text() == 'VALUE = 1\n'
