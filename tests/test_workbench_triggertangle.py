"""The harness may advise and record evidence, but never grants execution authority."""
import asyncio
import copy
import hashlib
import json
from pathlib import Path

import pytest

from app.container_runner import OutputLimitExceeded, ProcessResult
from app.workbench import integrations, triggertangle
from app.workbench.receipts import Collector
from scripts import workbench

pytest_plugins = ['test_patch_staging']


@pytest.fixture
def rehearsal(tmp_path, monkeypatch):
    root = tmp_path / 'reviewed runner'
    (root / 'dist').mkdir(parents=True)
    runner = root / 'dist/trigger-tangle-harness.mjs'
    runner.write_text('// trusted test fixture\n')
    monkeypatch.setenv('OMARCHY_TRIGGERTANGLE_ROOT', str(root))
    monkeypatch.setenv('OMARCHY_NODE_BINARY', '/bin/true')
    match = {'resource': 'invoice', 'event': 'draft', 'data': {'order': 'sample'}}
    blueprint = {'version': 1, 'name': 'Example', 'seed': match, 'workflows': []}
    suite = {'version': 1, 'name': 'Business outcome', 'cases': [
        {'id': 'invoice-draft', 'name': 'Keep invoice drafts', 'seed': match, 'required': [match]}]}
    paths = {}
    for name, value in [('baseline', blueprint), ('candidate', blueprint), ('suite', suite)]:
        path = tmp_path / (name + '.json')
        path.write_bytes(json.dumps(value).encode())
        paths[name] = path
    return paths, Collector(tmp_path / 'collector'), runner


def report_for(command, *, status='review-required'):
    inputs, evidence = {}, {'runnerVersion': '0.3.0'}
    for name in ('baseline', 'candidate', 'suite'):
        data = Path(command[command.index('--' + name) + 1]).read_bytes()
        text = data.decode('utf-8-sig')
        inputs[name] = json.loads(text)
        evidence[name + 'TextSha256'] = hashlib.sha256(text.encode()).hexdigest()
    cases = []
    for case in inputs['suite']['cases']:
        analysis_status = {'review-required': 'settles', 'blocked': 'loop-found', 'inconclusive': 'inconclusive'}[status]
        review = {'status': status, 'analysisStatus': analysis_status, 'complete': status != 'inconclusive',
                  'reason': 'Fixture result', 'stats': {'states': 1, 'transitions': 0,
                                                       'workflowStarts': '0', 'emittedEvents': '0'},
                  'required': [{'match': match, 'observed': True} for match in case['required']],
                  'forbidden': [{'match': match, 'observed': False} for match in case.get('forbidden', [])]}
        if status != 'review-required':
            review['stats'].update(workflowStarts=None, emittedEvents=None)
        cases.append(copy.deepcopy({**case, 'forbidden': case.get('forbidden', []),
                                   'baseline': review, 'candidate': copy.deepcopy(review)}))
    return {'schema': 'triggertangle.harness/v1', 'status': status, 'executionAllowed': False,
            'budget': {'maxStates': int(command[command.index('--max-states') + 1]),
                       'maxTransitions': int(command[command.index('--max-transitions') + 1])},
            'inputs': inputs, 'evidence': evidence, 'cases': cases, 'regressions': [], 'notes': []}


def invoke(rehearsal, **kwargs):
    paths, collector, _ = rehearsal
    return asyncio.run(triggertangle.rehearse(**paths, collector=collector, **kwargs))


@pytest.mark.parametrize(('exit_code', 'status'), [(0, 'review-required'), (1, 'blocked'), (2, 'inconclusive')])
def test_rehearsal_records_exact_snapshots_without_authorizing(rehearsal, monkeypatch, exit_code, status):
    paths, collector, runner = rehearsal
    originals = {name: path.read_bytes() for name, path in paths.items()}
    snapshot_paths = []
    async def fake(command, timeout, limit):
        assert timeout == 45 and limit == 2 * 1024 * 1024
        assert command[:2] == [str(Path('/bin/true').resolve()), str(runner)]
        for name in paths:
            snapshot = Path(command[command.index('--' + name) + 1])
            assert snapshot.is_relative_to(collector.root)
            assert snapshot.read_bytes() == originals[name]
            assert snapshot.stat().st_mode & 0o777 == 0o600
            snapshot_paths.append(snapshot)
        report = report_for(command, status=status)
        report.update(advisory_only=False, authorizes_apply=True)
        return ProcessResult(exit_code, json.dumps(report))
    monkeypatch.setattr(triggertangle, 'run_process', fake)
    result = invoke(rehearsal)
    assert result['status'] == status
    assert result['advisory_only'] and result['authorizes_apply'] is False and result['executionAllowed'] is False
    assert collector.verify(result['receipt']['id'])['valid']
    assert result['evidence']['input_sha256'] == {name: hashlib.sha256(data).hexdigest() for name, data in originals.items()}
    assert all(path.read_bytes() == originals[name] for name, path in paths.items())
    assert all(not path.exists() for path in snapshot_paths)


def test_bom_hashes_match_decoded_text_but_receipt_preserves_raw_bytes(rehearsal, monkeypatch):
    paths, _, _ = rehearsal
    paths['suite'].write_bytes(b'\xef\xbb\xbf' + paths['suite'].read_bytes())
    async def fake(command, timeout, **kwargs):
        return ProcessResult(0, json.dumps(report_for(command)))
    monkeypatch.setattr(triggertangle, 'run_process', fake)
    result = invoke(rehearsal)
    assert result['status'] == 'review-required'
    assert result['evidence']['input_sha256']['suite'] != result['report']['evidence']['suiteTextSha256']


@pytest.mark.parametrize('defect', ['schema', 'status', 'executionAllowed', 'budget', 'hash', 'version',
                                  'inputs', 'cases', 'case_identity', 'case_review', 'observations', 'counts',
                                  'invalid_type', 'notes', 'truncated'])
def test_malformed_responses_fail_closed(rehearsal, monkeypatch, defect):
    async def fake(command, timeout, **kwargs):
        report = report_for(command)
        if defect == 'schema': report['schema'] = 'other/v1'
        elif defect == 'status': report['status'] = 'blocked'
        elif defect == 'executionAllowed': report['executionAllowed'] = True
        elif defect == 'budget': report['budget']['maxStates'] = 512
        elif defect == 'hash': report['evidence']['suiteTextSha256'] = '0' * 64
        elif defect == 'version': report['evidence']['runnerVersion'] = '0.2.0'
        elif defect == 'inputs': report['inputs']['candidate']['name'] = 'Unrelated'
        elif defect == 'cases': report['cases'] = []
        elif defect == 'case_identity': report['cases'][0]['id'] = 'other'
        elif defect == 'case_review': report['cases'][0]['candidate']['complete'] = 'yes'
        elif defect == 'observations': report['cases'][0]['candidate']['required'] = []
        elif defect == 'counts': report['cases'][0]['candidate']['stats']['states'] = 1000
        elif defect == 'invalid_type': report['cases'][0]['candidate']['analysisStatus'] = []
        elif defect == 'notes': report['notes'] = 'fine'
        output = '{"schema":' if defect == 'truncated' else json.dumps(report)
        return ProcessResult(0, output)
    monkeypatch.setattr(triggertangle, 'run_process', fake)
    result = invoke(rehearsal)
    assert result['status'] == 'failed' and result['authorizes_apply'] is False


@pytest.mark.parametrize(('original', 'replacement'), [(True, 1), (1, True), (False, 0), (0, False)])
@pytest.mark.parametrize('location', ['inputs', 'seed', 'required', 'forbidden', 'outcome_required', 'outcome_forbidden'])
def test_json_boolean_number_substitutions_are_rejected(rehearsal, monkeypatch, original, replacement, location):
    paths, _, _ = rehearsal
    for name, path in paths.items():
        value = json.loads(path.read_text())
        if name == 'suite':
            case = value['cases'][0]
            case['seed']['data']['flag'] = original
            case['required'][0]['data']['flag'] = original
            case['forbidden'] = [{'resource': 'invoice', 'event': 'sent', 'data': {'flag': original}}]
        else:
            value['seed']['data']['flag'] = original
        path.write_text(json.dumps(value))
    async def fake(command, timeout, **kwargs):
        report = report_for(command)
        case = report['cases'][0]
        if location == 'inputs': data = report['inputs']['candidate']['seed']['data']
        elif location == 'seed': data = case['seed']['data']
        elif location in ('required', 'forbidden'): data = case[location][0]['data']
        else: data = case['candidate'][location.removeprefix('outcome_')][0]['match']['data']
        data['flag'] = replacement
        return ProcessResult(0, json.dumps(report))
    monkeypatch.setattr(triggertangle, 'run_process', fake)
    result = invoke(rehearsal)
    assert result['status'] == 'failed' and result['authorizes_apply'] is False


def test_equivalent_integer_and_float_json_values_are_accepted(rehearsal, monkeypatch):
    path = rehearsal[0]['candidate']
    value = json.loads(path.read_text())
    value['seed']['data']['number'] = 1.0
    path.write_text(json.dumps(value))
    async def fake(command, timeout, **kwargs):
        report = report_for(command)
        report['inputs']['candidate']['seed']['data']['number'] = 1
        return ProcessResult(0, json.dumps(report))
    monkeypatch.setattr(triggertangle, 'run_process', fake)
    assert invoke(rehearsal)['status'] == 'review-required'


@pytest.mark.parametrize('defect', ['missing_required', 'forbidden_observed', 'loop', 'incomplete',
                                  'unjustified_block', 'aggregate', 'missing_regression', 'false_regression',
                                  'settled_incomplete', 'inconclusive_complete', 'zero_states', 'settled_null_counts',
                                  'loop_counts', 'incomplete_counts', 'missing_counts'])
def test_contradictory_outcomes_and_summaries_fail_closed(rehearsal, monkeypatch, defect):
    path = rehearsal[0]['suite']
    suite = json.loads(path.read_text())
    suite['cases'][0]['forbidden'] = [{'resource': 'invoice', 'event': 'sent'}]
    path.write_text(json.dumps(suite))
    async def fake(command, timeout, **kwargs):
        report = report_for(command)
        candidate = report['cases'][0]['candidate']
        exit_code = 0
        if defect == 'missing_required': candidate['required'][0]['observed'] = False
        elif defect == 'forbidden_observed': candidate['forbidden'][0]['observed'] = True
        elif defect == 'loop':
            candidate['analysisStatus'] = 'loop-found'
            candidate['stats'].update(workflowStarts=None, emittedEvents=None)
        elif defect == 'incomplete':
            candidate.update(analysisStatus='inconclusive', complete=False)
            candidate['stats'].update(workflowStarts=None, emittedEvents=None)
        elif defect in ('unjustified_block', 'aggregate', 'missing_regression'):
            candidate['status'] = 'blocked'
            if defect != 'unjustified_block': candidate['required'][0]['observed'] = False
            if defect != 'missing_regression': report['regressions'] = ['invoice-draft']
            if defect != 'aggregate':
                report['status'], exit_code = 'blocked', 1
        elif defect == 'false_regression': report['regressions'] = ['invoice-draft']
        elif defect == 'settled_incomplete': candidate['complete'] = False
        elif defect == 'inconclusive_complete': candidate['analysisStatus'] = 'inconclusive'
        elif defect == 'zero_states': candidate['stats']['states'] = 0
        elif defect == 'settled_null_counts': candidate['stats'].update(workflowStarts=None, emittedEvents=None)
        elif defect in ('loop_counts', 'incomplete_counts'):
            status = 'blocked' if defect == 'loop_counts' else 'inconclusive'
            report = report_for(command, status=status)
            report['cases'][0]['candidate']['stats'].update(workflowStarts='1', emittedEvents='1')
            exit_code = 1 if status == 'blocked' else 2
        elif defect == 'missing_counts': candidate['stats'].pop('emittedEvents')
        return ProcessResult(exit_code, json.dumps(report))
    monkeypatch.setattr(triggertangle, 'run_process', fake)
    result = invoke(rehearsal)
    assert result['status'] == 'failed' and result['authorizes_apply'] is False


@pytest.mark.parametrize('cause', ['missing', 'forbidden', 'partial_loop', 'partial_forbidden', 'incomplete'])
def test_valid_status_priority_and_regression_ids_are_preserved(rehearsal, monkeypatch, cause):
    path = rehearsal[0]['suite']
    suite = json.loads(path.read_text())
    suite['cases'][0]['forbidden'] = [{'resource': 'invoice', 'event': 'sent'}]
    path.write_text(json.dumps(suite))
    status = 'inconclusive' if cause == 'incomplete' else 'blocked'
    async def fake(command, timeout, **kwargs):
        report = report_for(command)
        candidate = report['cases'][0]['candidate']
        if cause in ('missing', 'incomplete'): candidate['required'][0]['observed'] = False
        if cause in ('forbidden', 'partial_forbidden'): candidate['forbidden'][0]['observed'] = True
        if cause in ('partial_loop', 'partial_forbidden', 'incomplete'):
            candidate.update(analysisStatus='loop-found' if cause == 'partial_loop' else 'inconclusive', complete=False)
            candidate['stats'].update(workflowStarts=None, emittedEvents=None)
        candidate['status'] = report['status'] = status
        report['regressions'] = ['invoice-draft']
        return ProcessResult(2 if status == 'inconclusive' else 1, json.dumps(report))
    monkeypatch.setattr(triggertangle, 'run_process', fake)
    result = invoke(rehearsal)
    assert result['status'] == status
    assert result['report']['regressions'] == ['invoice-draft']


@pytest.mark.parametrize('failure', ['timeout', 'output', 'exit', 'input_changed', 'snapshot_changed', 'runner_changed'])
def test_failed_or_changed_runs_never_produce_a_review_result(rehearsal, monkeypatch, failure):
    paths, _, runner = rehearsal
    async def fake(command, timeout, **kwargs):
        if failure == 'timeout': raise TimeoutError('Time limit reached')
        if failure == 'output': raise OutputLimitExceeded('Output limit reached')
        report = report_for(command)
        if failure == 'input_changed': paths['candidate'].write_text('{}')
        if failure == 'snapshot_changed': Path(command[command.index('--suite') + 1]).write_text('{}')
        if failure == 'runner_changed': runner.write_text('// replaced')
        return ProcessResult(3 if failure == 'exit' else 0, json.dumps(report))
    monkeypatch.setattr(triggertangle, 'run_process', fake)
    result = invoke(rehearsal)
    assert result['status'] == 'failed' and result['authorizes_apply'] is False


@pytest.mark.parametrize('missing', ['configuration', 'runner', 'node', 'relative_node'])
def test_unavailable_is_not_a_clean_rehearsal(rehearsal, monkeypatch, tmp_path, missing):
    if missing == 'configuration':
        monkeypatch.delenv('OMARCHY_TRIGGERTANGLE_ROOT')
        monkeypatch.setattr(integrations, 'SETTINGS', tmp_path / 'absent.json')
    elif missing == 'runner': rehearsal[2].unlink()
    elif missing == 'node': monkeypatch.setenv('OMARCHY_NODE_BINARY', '/missing/node')
    elif missing == 'relative_node': monkeypatch.setenv('OMARCHY_NODE_BINARY', 'node')
    assert invoke(rehearsal)['status'] == 'unavailable'


@pytest.mark.parametrize('defect', ['oversize', 'invalid_utf8', 'symlink', 'directory', 'nonfinite'])
def test_invalid_inputs_do_not_launch_a_process(rehearsal, monkeypatch, tmp_path, defect):
    path = rehearsal[0]['candidate']
    if defect == 'oversize': path.write_bytes(b' ' * (triggertangle.INPUT_LIMIT + 1))
    elif defect == 'invalid_utf8': path.write_bytes(b'\xff')
    elif defect == 'nonfinite': path.write_text('{"number":NaN}')
    else:
        target = tmp_path / 'target.json'
        target.write_bytes(path.read_bytes())
        path.unlink()
        if defect == 'symlink': path.symlink_to(target)
        else: path.mkdir()
    async def forbidden(*args, **kwargs):
        pytest.fail('Invalid input reached the runner')
    monkeypatch.setattr(triggertangle, 'run_process', forbidden)
    assert invoke(rehearsal)['status'] == 'failed'


@pytest.mark.parametrize('budget', [{'max_states': 0}, {'max_transitions': 8193}, {'max_states': True}])
def test_invalid_budgets_fail_closed(rehearsal, budget):
    assert invoke(rehearsal, **budget)['status'] == 'failed'


def test_configure_preserves_existing_integration_settings(rehearsal, tmp_path, monkeypatch, capsys):
    settings = tmp_path / 'settings.json'
    previous = {'ptrm': '/existing/ptrm', 'triad': '/existing/triad', 'future': {'value': 1}}
    settings.write_text(json.dumps(previous))
    monkeypatch.setattr(integrations, 'SETTINGS', settings)
    root = rehearsal[2].parents[1]
    assert workbench.main(['configure', '--triggertangle', str(root)]) == 0
    assert json.loads(settings.read_text()) == {**previous, 'triggertangle': str(root)}
    assert json.loads(capsys.readouterr().out)['triggertangle'] == str(root)


def test_rehearsal_cannot_validate_or_promote_a_staged_patch(rehearsal, project, monkeypatch):
    from app import patch_tasks
    source, project_id, base = project
    original = (source / 'module.py').read_bytes()
    task = asyncio.run(patch_tasks.propose(project_id, base,
        [{'path': 'module.py', 'before_sha256': patch_tasks.sha(original), 'after': 'VALUE = 2\n'}],
        [{'command': 'python.syntax', 'files': ['module.py']}]))
    async def fake(command, timeout, **kwargs):
        return ProcessResult(0, json.dumps(report_for(command)))
    monkeypatch.setattr(triggertangle, 'run_process', fake)
    assert invoke(rehearsal)['status'] == 'review-required'
    assert patch_tasks.load_task(task['id'])[1]['state'] == 'staged'
    assert (source / 'module.py').read_bytes() == original


@pytest.mark.parametrize(('status', 'exit_code'), [('review-required', 0), ('blocked', 1), ('inconclusive', 1), ('failed', 1)])
def test_operator_cli_preserves_advisory_outcomes(rehearsal, monkeypatch, capsys, status, exit_code):
    paths, collector, _ = rehearsal
    async def fake(*args, **kwargs):
        return {'status': status, **triggertangle.BOUNDARY}
    monkeypatch.setattr(triggertangle, 'rehearse', fake)
    result = workbench.main(['--store', str(collector.root), 'rehearse', *map(str, paths.values())])
    assert result == exit_code
    assert json.loads(capsys.readouterr().out)['authorizes_apply'] is False
