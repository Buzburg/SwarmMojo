import asyncio
import json

import pytest
from app import patch_tasks
from app.container_runner import ProcessResult
from app.workbench import integrations
from app.workbench.qualification import adoption_decision, environment_record
from app.workbench.receipts import Collector

pytest_plugins = ['test_patch_staging']


def test_missing_reviewer_is_unavailable_not_a_clean_review(tmp_path, monkeypatch):
    monkeypatch.delenv('OMARCHY_PTRM_ROOT', raising=False)
    monkeypatch.setattr(integrations, 'SETTINGS', tmp_path / 'not-configured.json')
    result = asyncio.run(integrations.review_files(tmp_path, ['a.py']))
    assert result['status'] == 'unavailable' and result['advisory_only']
    assert result['authorizes_apply'] is False


def test_reviewer_binds_results_to_exact_files(tmp_path, monkeypatch):
    dependency = tmp_path / 'ptrm'
    (dependency / 'bin').mkdir(parents=True)
    (dependency / 'bin/ptrm-review-worker').write_text('fixture')
    monkeypatch.setenv('OMARCHY_PTRM_ROOT', str(dependency))
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'a.py').write_text('VALUE = 1\n')
    async def fake(command, timeout, **kwargs):
        (source / 'a.py').write_text('CHANGED = True\n')
        return ProcessResult(0, json.dumps({'findings': []}))
    monkeypatch.setattr(integrations, 'run_process', fake)
    with pytest.raises(ValueError, match='changed'):
        asyncio.run(integrations.review_files(source, ['a.py']))


def test_adoption_requires_every_capability_and_measured_improvement():
    baseline = {'checkpoint_sha256': 'a', 'task_success': 1.0, 'median_seconds': 5.0,
                'machine_sha256': 'host', 'workload_sha256': 'tasks', 'representative_tasks': 10}
    candidate = {**baseline, 'median_seconds': 3.0, 'streaming': True, 'cancellation': True,
                 'recovery': True, 'recurrent_checkpoint': True, 'representative_tasks': 10}
    assert adoption_decision(baseline, candidate)['eligible']
    for key in ['streaming', 'cancellation', 'recovery', 'recurrent_checkpoint']:
        assert not adoption_decision(baseline, {**candidate, key: False})['eligible']
    assert not adoption_decision(baseline, {**candidate, 'checkpoint_sha256': 'other'})['eligible']
    assert not adoption_decision(baseline, {**candidate, 'task_success': .8})['eligible']
    assert not adoption_decision(baseline, {**candidate, 'median_seconds': 6.0})['eligible']
    assert not adoption_decision(baseline, {**candidate, 'machine_sha256': 'other'})['eligible']
    assert not adoption_decision(baseline, {**candidate, 'workload_sha256': 'easier'})['eligible']
    assert not adoption_decision({**baseline, 'representative_tasks': 0}, candidate)['eligible']


def test_host_inventory_cannot_claim_target_or_gpu_qualification():
    result = environment_record()
    assert result['target_qualified'] is False
    assert result['gpu_model_placement'] == 'unverified'
    assert result['cpu'] and result['kernel']


def test_workshop_review_cannot_validate_or_apply_a_staged_change(project, tmp_path, monkeypatch):
    source, project_id, base = project
    task = asyncio.run(patch_tasks.propose(project_id, base,
        [{'path': 'module.py', 'before_sha256': patch_tasks.sha((source / 'module.py').read_bytes()),
          'after': 'VALUE = 2\n'}], [{'command': 'python.syntax', 'files': ['module.py']}]))
    async def advisory(root, paths):
        assert root.name == 'stage' and paths == ['module.py']
        return {'status': 'reviewed', 'findings': [], 'advisory_only': True, 'authorizes_apply': False}
    monkeypatch.setattr(integrations, 'review_files', advisory)
    collector = Collector(tmp_path / 'collector')
    result = asyncio.run(integrations.review_task(task['id'], collector))
    assert not result['authorizes_apply'] and collector.verify(result['receipt']['id'])['valid']
    assert patch_tasks.load_task(task['id'])[1]['state'] == 'staged'
    assert (source / 'module.py').read_text() == 'VALUE = 1\n'
