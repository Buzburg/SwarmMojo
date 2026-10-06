"""Read-only advisory review and explicitly requested workflow analysis."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

from app import patch_tasks
from app.container_runner import run_process

from .receipts import Collector

SETTINGS = Path(__file__).resolve().parents[2] / 'config/workbench.local.json'


def get_dependency(name: str) -> str | None:
    value = os.getenv('OMARCHY_' + name.upper() + '_ROOT')
    if value:
        return value
    if SETTINGS.is_file():
        value = json.loads(SETTINGS.read_text()).get(name)
        if value is not None and not isinstance(value, str):
            raise ValueError('Invalid operator integration setting')
        return value
    return None


async def review_files(root: Path, files: list[str]) -> dict:
    configured = get_dependency('ptrm')
    base = {'advisory_only': True, 'authorizes_apply': False}
    if not configured:
        return {**base, 'status': 'unavailable', 'reason': 'PTRM source and native worker are not configured'}
    dependency = Path(configured).resolve()
    worker = dependency / 'bin/ptrm-review-worker'
    if not worker.is_file():
        return {**base, 'status': 'unavailable', 'reason': 'Build the configured PTRM native worker first'}
    if not 1 <= len(files) <= 64 or len(set(files)) != len(files):
        raise ValueError('Select 1–64 distinct review files')
    snapshots = {name: patch_tasks.read_file(root, patch_tasks.patch_path(name)) for name in files}
    python_library = str(Path(sys.prefix) / 'lib' / f'libpython{sys.version_info.major}.{sys.version_info.minor}.so')
    launch = ('import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); '
              'runpy.run_module("ptrm_reviewer",run_name="__main__")')
    response = await run_process(['/usr/bin/env', 'MOJO_PYTHON_LIBRARY=' + python_library,
        'LD_LIBRARY_PATH=' + str(Path(python_library).parent), 'PYTHONHOME=' + sys.prefix,
        sys.executable, '-c', launch, str(dependency), 'review', '--root', str(root),
        '--worker', str(worker), *files], 30)
    if any(patch_tasks.read_file(root, name) != content for name, content in snapshots.items()):
        raise ValueError('Reviewed source changed during analysis')
    if response.returncode:
        return {**base, 'status': 'failed', 'reason': 'PTRM exited unsuccessfully', 'diagnostics': response.output[-2000:]}
    value = json.loads(response.output)
    if type(value) is not dict:
        raise ValueError('Invalid advisory reviewer response')
    return {**value, **base, 'status': 'reviewed', 'source_sha256': {
        name: None if data is None else hashlib.sha256(data).hexdigest() for name, data in snapshots.items()},
        'worker_sha256': hashlib.sha256(worker.read_bytes()).hexdigest()}


async def review_task(task_id: str, collector: Collector | None = None) -> dict:
    control, task, patch = patch_tasks.load_task(task_id)
    with patch_tasks.task_lock(control):
        stage = control / 'stage'
        if collector is not None and collector.root.is_relative_to(stage):
            raise ValueError('Collector storage must remain outside the worker stage')
        if patch_tasks.inventory(stage) != task['stage_inventory']:
            raise ValueError('Staged files changed; review cannot use stale validation')
        paths = [change['path'] for change in patch['changes'] if change['after'] is not None]
        report = await review_files(stage, paths) if paths else {
            'status': 'not_applicable', 'reason': 'Deletion-only patch', 'advisory_only': True, 'authorizes_apply': False}
        if patch_tasks.inventory(stage) != task['stage_inventory']:
            raise ValueError('Stage changed during advisory review')
        report['task_id'], report['patch_sha256'] = task_id, task['patch_sha256']
        if collector is not None:
            report['receipt'] = collector.record('workshop-review', [{'task': task, 'review': report}])
        return report


async def analyze_runs(runs: Path, policy: Path, output: Path, collector: Collector) -> dict:
    configured = get_dependency('triad')
    if not configured:
        return {'status': 'unavailable', 'reason': 'Triad is not configured', 'authorizes_apply': False}
    dependency = Path(configured).resolve()
    inputs = {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest() for path in (runs, policy)}
    response = await run_process(['/bin/bash', str(dependency / 'scripts/run.sh'),
        '--input', str(runs.resolve()), '--policy', str(policy.resolve()), '--output', str(output.resolve())], 180)
    if any(hashlib.sha256(Path(name).read_bytes()).hexdigest() != sha for name, sha in inputs.items()):
        raise ValueError('Analysis inputs changed during execution')
    report = {'status': 'passed' if response.returncode == 0 else 'failed',
        'input_sha256': inputs, 'output_directory': str(output.resolve()), 'diagnostics': response.output,
        'authorizes_apply': False}
    report['receipt'] = collector.record('triad-analysis', [report])
    return report
