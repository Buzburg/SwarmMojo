"""Operator-requested, read-only workflow rehearsal with authenticated evidence."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from app.container_runner import OutputLimitExceeded, run_process

from .integrations import get_dependency
from .receipts import Collector

INPUT_LIMIT = 800_000
OUTPUT_LIMIT = 2 * 1024 * 1024
RUNNER_VERSION = '0.3.0'
STATUSES = {0: 'review-required', 1: 'blocked', 2: 'inconclusive'}
BOUNDARY = {'advisory_only': True, 'authorizes_apply': False, 'executionAllowed': False}


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read(path: Path, limit: int = INPUT_LIMIT) -> bytes:
    """Read an operator-selected regular file without following symlink components."""
    path = path.expanduser().absolute()
    if '..' in path.parts:
        raise ValueError('Rehearsal paths cannot contain parent traversal')
    directory = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    finally:
        os.close(directory)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError('Rehearsal input must be a bounded regular file')
        data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError('Rehearsal file grew beyond its byte limit')
        return data


def _invalid_constant(value: str) -> None:
    raise ValueError('Non-finite JSON numbers are unsupported')


def _decode(data: bytes) -> tuple[str, Any]:
    text = data.decode('utf-8-sig', errors='strict')
    return text, json.loads(text, parse_constant=_invalid_constant)


def _same_json(left: Any, right: Any) -> bool:
    """Preserve JSON scalar types while allowing equivalent JavaScript numbers."""
    if type(left) in (int, float) and type(right) in (int, float):
        return left == right
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(_same_json(left[key], right[key]) for key in left)
    if type(left) is list:
        return len(left) == len(right) and all(_same_json(a, b) for a, b in zip(left, right))
    return left == right


def _validate_report(report: Any, exit_code: int, inputs: dict[str, Any],
                     hashes: dict[str, str], budget: dict[str, int]) -> None:
    if (type(report) is not dict or report.get('schema') != 'triggertangle.harness/v1'
            or exit_code not in STATUSES or report.get('status') != STATUSES[exit_code]
            or report.get('executionAllowed') is not False or report.get('budget') != budget
            or not _same_json(report.get('inputs'), inputs)):
        raise ValueError('Invalid rehearsal response or exit-status agreement')
    if any(type(report['budget'].get(key)) is not int for key in budget):
        raise ValueError('Invalid rehearsal response budget')
    if report.get('evidence') != {'runnerVersion': RUNNER_VERSION, **hashes}:
        raise ValueError('Rehearsal response does not match the input text or runner version')
    suite = inputs['suite']
    cases = report.get('cases')
    if (type(suite) is not dict or type(suite.get('cases')) is not list
            or type(cases) is not list or not 1 <= len(cases) <= 8
            or len(cases) != len(suite['cases'])):
        raise ValueError('Invalid rehearsal case coverage')
    for case, expected in zip(cases, suite['cases']):
        if (type(case) is not dict or type(expected) is not dict
                or type(expected.get('required')) is not list or not 1 <= len(expected['required']) <= 8
                or type(expected.get('forbidden', [])) is not list or len(expected.get('forbidden', [])) > 8
                or any(not _same_json(case.get(key), expected.get(key)) for key in ('id', 'name', 'seed', 'required'))
                or not _same_json(case.get('forbidden'), expected.get('forbidden', []))):
            raise ValueError('Rehearsal cases do not match the selected suite')
        for side in ('baseline', 'candidate'):
            review = case.get(side)
            if (type(review) is not dict or review.get('status') not in STATUSES.values()
                    or review.get('analysisStatus') not in {'settles', 'loop-found', 'inconclusive'}
                    or type(review.get('complete')) is not bool or type(review.get('reason')) is not str
                    or type(review.get('stats')) is not dict
                    or type(review.get('required')) is not list or type(review.get('forbidden')) is not list
                    or len(review['required']) != len(expected['required'])
                    or len(review['forbidden']) != len(expected.get('forbidden', []))):
                raise ValueError('Invalid rehearsal case review')
            stats = review['stats']
            for key, minimum, maximum in (('states', 1, budget['maxStates']), ('transitions', 0, budget['maxTransitions'])):
                if type(stats.get(key)) is not int or not minimum <= stats[key] <= maximum:
                    raise ValueError('Invalid rehearsal analysis counts')
            analysis_status = review['analysisStatus']
            if ((analysis_status == 'settles' and not review['complete'])
                    or (analysis_status == 'inconclusive' and review['complete'])):
                raise ValueError('Rehearsal completeness contradicts the analysis status')
            for key in ('workflowStarts', 'emittedEvents'):
                count = stats.get(key)
                needs_counts = analysis_status == 'settles' and review['complete']
                if (key not in stats or (not needs_counts and count is not None)
                        or (needs_counts and (type(count) is not str or not count.isascii() or not count.isdecimal()))):
                    raise ValueError('Invalid rehearsal delivery counts')
            for key in ('required', 'forbidden'):
                for observation, match in zip(review[key], expected.get(key, [])):
                    if (type(observation) is not dict or not _same_json(observation.get('match'), match)
                            or type(observation.get('observed')) is not bool):
                        raise ValueError('Invalid rehearsal outcome observation')
            if analysis_status == 'loop-found' or any(item['observed'] for item in review['forbidden']):
                expected_status = 'blocked'
            elif not review['complete']:
                expected_status = 'inconclusive'
            elif any(not item['observed'] for item in review['required']):
                expected_status = 'blocked'
            else:
                expected_status = 'review-required'
            if review['status'] != expected_status:
                raise ValueError('Rehearsal case status contradicts its recorded outcomes')
    for key in ('regressions', 'notes'):
        if type(report.get(key)) is not list or not all(type(item) is str for item in report[key]):
            raise ValueError('Invalid rehearsal explanation')
    candidates = [case['candidate']['status'] for case in cases]
    aggregate = 'blocked' if 'blocked' in candidates else 'inconclusive' if 'inconclusive' in candidates else 'review-required'
    regressions = [case['id'] for case in cases if case['baseline']['status'] == 'review-required'
                   and case['candidate']['status'] != 'review-required']
    if report['status'] != aggregate or report['regressions'] != regressions:
        raise ValueError('Rehearsal summary contradicts its scenario results')


async def rehearse(baseline: Path, candidate: Path, suite: Path, collector: Collector, *,
                   max_states: int = 256, max_transitions: int = 2048) -> dict[str, Any]:
    """Rehearse private snapshots; neither a result nor its receipt grants execution rights."""
    evidence: dict[str, Any] = {}
    try:
        if type(max_states) is not int or not 1 <= max_states <= 512:
            raise ValueError('State budget must be between 1 and 512')
        if type(max_transitions) is not int or not 1 <= max_transitions <= 8192:
            raise ValueError('Transition budget must be between 1 and 8192')
        configured = get_dependency('triggertangle')
        node = Path(os.getenv('OMARCHY_NODE_BINARY', '/usr/bin/node'))
        if not configured:
            result = {'status': 'unavailable', 'reason': 'TriggerTangle is not configured'}
        elif not node.is_absolute() or not node.is_file() or not os.access(node, os.X_OK):
            result = {'status': 'unavailable', 'reason': 'Configure an absolute executable OMARCHY_NODE_BINARY'}
        else:
            root = Path(configured).expanduser().absolute()
            runner = root / 'dist/trigger-tangle-harness.mjs'
            if not runner.is_file():
                result = {'status': 'unavailable', 'reason': 'Build the configured TriggerTangle harness first'}
            else:
                runner_bytes = _read(runner, 4 * 1024 * 1024)
                paths = {'baseline': baseline, 'candidate': candidate, 'suite': suite}
                originals = {name: _read(path) for name, path in paths.items()}
                decoded = {name: _decode(data) for name, data in originals.items()}
                inputs = {name: value for name, (_, value) in decoded.items()}
                text_hashes = {name + 'TextSha256': _digest(text.encode('utf-8'))
                               for name, (text, _) in decoded.items()}
                budget = {'maxStates': max_states, 'maxTransitions': max_transitions}
                evidence = {'runner_sha256': _digest(runner_bytes), 'runner': str(runner),
                            'node': str(node.resolve()), 'budget': budget,
                            'input_sha256': {name: _digest(data) for name, data in originals.items()},
                            'input_paths': {name: str(path.expanduser().absolute()) for name, path in paths.items()}}
                with tempfile.TemporaryDirectory(prefix='rehearsal-', dir=collector.root) as temporary:
                    snapshots = {name: Path(temporary) / (name + '.json') for name in paths}
                    for name, path in snapshots.items():
                        path.write_bytes(originals[name])
                        path.chmod(0o600)
                    command = [str(node.resolve()), str(runner)]
                    for name, path in snapshots.items():
                        command.extend(['--' + name, str(path)])
                    command.extend(['--max-states', str(max_states), '--max-transitions', str(max_transitions)])
                    response = await run_process(command, 45, limit=OUTPUT_LIMIT)
                    if (any(_read(path) != originals[name] for name, path in paths.items())
                            or any(_read(path) != originals[name] for name, path in snapshots.items())
                            or _read(runner, 4 * 1024 * 1024) != runner_bytes):
                        raise ValueError('Rehearsal inputs or runner changed during analysis')
                    report = json.loads(response.output, parse_constant=_invalid_constant)
                    _validate_report(report, response.returncode, inputs, text_hashes, budget)
                    result = {'status': report['status'], 'report': report}
    except (OSError, ValueError, RuntimeError, TypeError, TimeoutError, OutputLimitExceeded) as error:
        result = {'status': 'failed', 'reason': str(error)[:500] or type(error).__name__}
    result = {**result, 'evidence': evidence, **BOUNDARY}
    result['receipt'] = collector.record('triggertangle-rehearsal', [result])
    return result
