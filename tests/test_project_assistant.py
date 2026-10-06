"""Model output remains an untrusted proposal until typed staging and validation."""
import asyncio
import json
import os
import io
import sys
from pathlib import Path

import pytest

from app import project_assistant as assistant, patch_tasks as tasks, patch_promotion
from test_patch_staging import project, live
from test_task_worker import worker
from scripts import project_workshop


def completion(value, finish='stop'):
    return {'model': 'fixture', 'choices': [{'finish_reason': finish, 'message': {'content': json.dumps(value)}}]}


def test_valid_draft_binds_controller_hashes_and_preserves_source(project, monkeypatch):
    async def generate(instruction, snapshots):
        assert snapshots == {'module.py': 'VALUE = 1\n'}
        assert instruction == 'Change VALUE to 2'
        return completion({'changes': [{'path': 'module.py', 'after': 'VALUE = 2\n'}]})
    monkeypatch.setattr(assistant, 'generate', generate)
    result = asyncio.run(assistant.draft_change(project[1], ['module.py'], 'Change VALUE to 2',
                                               [{'command': 'python.syntax', 'files': ['module.py']}]))
    assert result['task']['state'] == 'staged'
    control, task, patch = tasks.load_task(result['task']['id'])
    assert patch['base_commit'] == project[2]
    assert patch['changes'][0]['before_sha256'] == tasks.sha(b'VALUE = 1\n')
    assert (control / 'stage/module.py').read_text() == 'VALUE = 2\n'
    assert (project[0] / 'module.py').read_text() == 'VALUE = 1\n'
    record = json.loads((tasks.STORE / 'drafts' / result['draft_id'] / 'draft.json').read_text())
    assert record['task_id'] == task['id'] and record['model'] == 'fixture'


@pytest.mark.parametrize('value,finish', [
    ({'changes': [{'path': '../outside', 'after': 'bad'}]}, 'stop'),
    ({'changes': [{'path': 'README.md', 'after': 'unselected'}]}, 'stop'),
    ({'changes': [{'path': 'module.py', 'after': 'x', 'approved': True}]}, 'stop'),
    ({'changes': [{'path': 'module.py', 'after': 'x'}], 'checks': [{'command': 'shell'}]}, 'stop'),
    ({'changes': [{'path': 'module.py', 'after': 'x'}, {'path': 'module.py', 'after': 'y'}]}, 'stop'),
    ({'changes': [{'path': 'module.py', 'after': 'VALUE = 1\n'}]}, 'stop'),
    ({'changes': [{'path': 'module.py', 'after': 3}]}, 'stop'),
    ({'changes': [{'path': 'module.py', 'after': 'x'}]}, 'length'),
])
def test_bad_model_output_cannot_stage_or_expand_authority(project, monkeypatch, value, finish):
    async def generate(*_):
        return completion(value, finish)
    monkeypatch.setattr(assistant, 'generate', generate)
    with pytest.raises(ValueError):
        asyncio.run(assistant.draft_change(project[1], ['module.py'], 'Requested edit',
            [{'command': 'python.syntax', 'files': ['module.py']}]))
    assert not list((tasks.STORE / 'tasks').glob('*'))
    assert (project[0] / 'module.py').read_text() == 'VALUE = 1\n'
    records = list((tasks.STORE / 'drafts').glob('*/draft.json'))
    assert len(records) == 1 and json.loads(records[0].read_text())['state'] == 'failed'


def test_user_edit_during_model_generation_is_preserved(project, monkeypatch):
    async def generate(*_):
        (project[0] / 'module.py').write_text('USER_EDIT = True\n')
        return completion({'changes': [{'path': 'module.py', 'after': 'VALUE = 2\n'}]})
    monkeypatch.setattr(assistant, 'generate', generate)
    with pytest.raises(ValueError, match='changed while the model'):
        asyncio.run(assistant.draft_change(project[1], ['module.py'], 'Change VALUE to 2',
            [{'command': 'python.syntax', 'files': ['module.py']}]))
    assert (project[0] / 'module.py').read_text() == 'USER_EDIT = True\n'
    assert not list((tasks.STORE / 'tasks').glob('*'))


def test_duplicate_keys_in_model_json_are_rejected():
    response = completion({})
    response['choices'][0]['message']['content'] = '{"changes":[],"changes":[]}'
    with pytest.raises(ValueError, match='duplicate'):
        assistant.parse_changes(response, {'module.py': 'VALUE = 1\n'})


def test_formatting_preserves_final_terminator_and_keeps_intended_blank_lines():
    response = completion({'changes': [{'path': 'module.py', 'after': 'VALUE = 2\n\n'}]})
    assert assistant.parse_changes(response, {'module.py': 'VALUE = 1\n'})[0]['after'] == 'VALUE = 2\n\n'
    response = completion({'changes': [{'path': 'module.py', 'after': 'VALUE = 2'}]})
    assert assistant.parse_changes(response, {'module.py': 'VALUE = 1\r\n'})[0]['after'] == 'VALUE = 2\r\n'


@live
@pytest.mark.parametrize('accept', [False, True])
def test_workshop_operator_flow_with_actual_validation_service(project, worker, monkeypatch, capsys, accept):
    async def generate(*_):
        return completion({'changes': [{'path': 'module.py', 'after': 'VALUE = 2\n'}]})
    monkeypatch.setattr(assistant, 'generate', generate)
    stream = io.StringIO()
    monkeypatch.setattr(stream, 'isatty', lambda: True)
    monkeypatch.setattr(sys, 'stdin', stream)
    inputs = iter(['1', 'module.py', '1', 'Change VALUE to 2', '/exit'])
    def respond(prompt):
        if prompt.startswith('Type APPLY') or prompt.startswith('Type UNDO'):
            return ' '.join(prompt.split()[1:3]) if accept else ''
        if prompt.startswith('Press Enter for another'):
            return 'UNDO'
        return next(inputs)
    monkeypatch.setattr('builtins.input', respond)
    asyncio.run(project_workshop.main())
    assert (project[0] / 'module.py').read_text() == 'VALUE = 1\n'
    records = list((tasks.STORE / 'tasks').glob('*/task.json'))
    assert len(records) == 1
    assert json.loads(records[0].read_text())['state'] == ('rolled_back' if accept else 'awaiting_apply')
    output = capsys.readouterr().out
    assert 'Selected checks passed' in output
    assert ('Changes applied.' in output) == accept


@pytest.mark.skipif(not os.getenv('ROMS_LIVE_DRAFT'), reason='Explicit live model verification required')
def test_real_goose_draft_validate_apply_and_rollback(project, monkeypatch):
    settings = dict(line.split('=', 1) for line in Path('/home/rryan/.config/goose/runtime.env').read_text().splitlines() if '=' in line)
    monkeypatch.setenv('ROMS_GATEWAY_API_KEY', settings['ROMS_GATEWAY_API_KEY'])
    result = asyncio.run(assistant.draft_change(project[1], ['module.py'],
        'Change the existing VALUE constant from 1 to 2. Keep its name and everything else unchanged.',
        [{'command': 'python.syntax', 'files': ['module.py']}]))
    task = asyncio.run(tasks.validate_task(result['task']['id']))
    assert task['state'] == 'validated'
    control, _, patch = tasks.load_task(task['id'])
    # Require the requested fixture edit, not merely any syntactically valid output.
    assert patch['changes'] == [{'path': 'module.py', 'before_sha256': tasks.sha(b'VALUE = 1\n'), 'after': 'VALUE = 2\n'}]
    record = json.loads((tasks.STORE / 'drafts' / result['draft_id'] / 'draft.json').read_text())
    assert record['model'] == 'goose-2.9b'
    assert record['usage']['completion_tokens'] > 0
    patch_promotion.review(task['id'])
    token = patch_promotion.authorize(task['id'], task['patch_sha256'], 'apply')
    assert asyncio.run(patch_promotion.promote(task['id'], token))['state'] == 'applied'
    assert (project[0] / 'module.py').read_text() == 'VALUE = 2\n'
    token = patch_promotion.authorize(task['id'], task['patch_sha256'], 'rollback')
    assert asyncio.run(patch_promotion.promote(task['id'], token, rollback=True))['state'] == 'rolled_back'
    assert (project[0] / 'module.py').read_text() == 'VALUE = 1\n'
