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


def _review_report(value: object, snapshots: dict[str, bytes | None]) -> dict:
    """Bind PTRM's declared coverage and findings to the selected source bytes."""
    if (type(value) is not dict or type(value.get('schema_version')) is not int
            or value['schema_version'] != 1 or value.get('mode') != 'advisory_static_rules'):
        raise ValueError('Unsupported advisory reviewer response')
    entries, findings = value.get('files'), value.get('findings')
    if type(entries) is not list or len(entries) != len(snapshots) or type(findings) is not list:
        raise ValueError('Invalid advisory reviewer file coverage')
    hashes = {name: None if data is None else hashlib.sha256(data).hexdigest()
              for name, data in snapshots.items()}
    reviewed, seen, truncated = {}, set(), False
    for entry in entries:
        if type(entry) is not dict or type(entry.get('path')) is not str:
            raise ValueError('Invalid advisory reviewer file entry')
        name = entry['path']
        if name not in snapshots or name in seen:
            raise ValueError('Advisory reviewer returned unexpected or duplicate files')
        seen.add(name)
        if entry.get('status') == 'reviewed':
            if hashes[name] is None or entry.get('sha256') != hashes[name]:
                raise ValueError('Advisory review source hash mismatch')
            if type(entry.get('possibly_truncated')) is not bool:
                raise ValueError('Advisory review must declare truncation')
            reviewed[name] = entry
            truncated |= entry['possibly_truncated']
        elif entry.get('status') != 'skipped' or not isinstance(entry.get('reason'), str) or not entry['reason']:
            raise ValueError('Advisory reviewer must explain each skipped file')
    coverage = {'requested': len(snapshots), 'reviewed': len(reviewed), 'skipped': len(snapshots) - len(reviewed)}
    supplied = value.get('coverage')
    if (type(supplied) is not dict or any(type(supplied.get(k)) is not int or supplied[k] != v
                                         for k, v in coverage.items())):
        raise ValueError('Advisory review coverage counts disagree with files')
    counts = dict.fromkeys(reviewed, 0)
    line_counts = {name: len(snapshots[name].decode('utf-8').splitlines()) for name in reviewed}
    for finding in findings:
        if type(finding) is not dict or type(finding.get('path')) is not str or finding['path'] not in reviewed:
            raise ValueError('Advisory finding refers to an unreviewed file')
        name = finding['path']
        if finding.get('source_sha256') != hashes[name] or finding.get('verified') is not False:
            raise ValueError('Advisory finding has invalid source or verification status')
        start, end = finding.get('start_line'), finding.get('end_line')
        if (type(start) is not int or type(end) is not int
                or not 1 <= start <= end <= line_counts[name]):
            raise ValueError('Advisory finding is outside the selected source')
        counts[name] += 1
        if counts[name] > 200:
            raise ValueError('Advisory findings exceeded the per-file limit')
    incomplete = bool(coverage['skipped']) or truncated
    status = 'not_reviewed' if not reviewed else 'partial' if incomplete else 'reviewed'
    report = {key: value[key] for key in ('schema_version', 'mode', 'files', 'findings')}
    report.update({'coverage': coverage, 'coverage_status': 'none' if not reviewed else 'partial' if incomplete else 'complete',
              'possibly_truncated': truncated, 'status': status, 'source_sha256': hashes,
              'advisory_only': True, 'authorizes_apply': False,
              'limitations': 'Coverage counts supported rule scans, not defects detected or proof of safety.'})
    if incomplete:
        report['reason'] = f"{coverage['reviewed']} of {coverage['requested']} files scanned; {coverage['skipped']} skipped."
        if truncated:
            report['reason'] += ' Findings may be truncated.'
    return report


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
    worker_sha256 = hashlib.sha256(worker.read_bytes()).hexdigest()
    python_library = str(Path(sys.prefix) / 'lib' / f'libpython{sys.version_info.major}.{sys.version_info.minor}.so')
    launch = ('import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); '
              'runpy.run_module("ptrm_reviewer",run_name="__main__")')
    response = await run_process(['/usr/bin/env', 'MOJO_PYTHON_LIBRARY=' + python_library,
        'LD_LIBRARY_PATH=' + str(Path(python_library).parent), 'PYTHONHOME=' + sys.prefix,
        sys.executable, '-B', '-c', launch, str(dependency), 'review', '--root', str(root),
        '--worker', str(worker), *files], 30)
    if any(patch_tasks.read_file(root, name) != content for name, content in snapshots.items()):
        raise ValueError('Reviewed source changed during analysis')
    if hashlib.sha256(worker.read_bytes()).hexdigest() != worker_sha256:
        raise ValueError('Reviewer worker changed during analysis')
    if response.returncode:
        return {**base, 'status': 'failed', 'reason': 'PTRM exited unsuccessfully', 'diagnostics': response.output[-2000:]}
    report = _review_report(json.loads(response.output), snapshots)
    return {**report, 'worker_sha256': worker_sha256}


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
