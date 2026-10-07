"""PTRM evidence/coverage boundary; fixtures do not invoke the external worker."""
import asyncio
import copy
import hashlib
import json

import pytest

pytest.importorskip('fcntl', reason='PTRM uses the Linux workshop adapter')

from app.container_runner import ProcessResult
from app.workbench import integrations


SOURCE = {'a.py': b'exec(code)\n', 'notes.md': b'Not a supported language\n'}
DIGEST = hashlib.sha256(SOURCE['a.py']).hexdigest()


def report(*, skipped=False, truncated=False):
    files = [{'path': 'a.py', 'status': 'reviewed', 'sha256': DIGEST,
              'possibly_truncated': truncated}]
    if skipped:
        files.append({'path': 'notes.md', 'status': 'skipped', 'reason': 'Unsupported language'})
    return {'schema_version': 1, 'mode': 'advisory_static_rules', 'files': files,
            'coverage': {'requested': len(files), 'reviewed': 1, 'skipped': int(skipped)},
            'findings': [{'path': 'a.py', 'start_line': 1, 'end_line': 1,
                          'source_sha256': DIGEST, 'verified': False, 'title': 'Dynamic execution'}]}


def test_complete_review_preserves_findings_but_cannot_authorize_changes():
    value = report()
    value.update(advisory_only=False, authorizes_apply=True, execution_allowed=True,
                 approval_required=False, verified=True, status='passed', receipt={'valid': True})
    result = integrations._review_report(value, {'a.py': SOURCE['a.py']})
    assert result['status'] == 'reviewed' and result['coverage_status'] == 'complete'
    assert result['findings'] == value['findings']
    assert result['source_sha256'] == {'a.py': DIGEST}
    assert result['advisory_only'] is True and result['authorizes_apply'] is False
    assert not {'execution_allowed', 'approval_required', 'verified', 'receipt'} & result.keys()


@pytest.mark.parametrize('skipped,truncated', [(True, False), (False, True), (True, True)])
def test_incomplete_coverage_is_visible_even_with_no_findings(skipped, truncated):
    value = report(skipped=skipped, truncated=truncated)
    value['findings'] = []
    sources = SOURCE if skipped else {'a.py': SOURCE['a.py']}
    result = integrations._review_report(value, sources)
    assert result['status'] == result['coverage_status'] == 'partial'
    assert result['possibly_truncated'] is truncated
    assert 'files scanned' in result['reason']
    assert ('truncated' in result['reason']) is truncated


def test_all_skipped_is_not_a_review_and_preserves_each_reason():
    value = report()
    value['files'] = [{'path': 'notes.md', 'status': 'skipped', 'reason': 'Unsupported language'},
                      {'path': 'missing.py', 'status': 'skipped', 'reason': 'Missing file'}]
    value['findings'] = []
    value['coverage'] = {'requested': 2, 'reviewed': 0, 'skipped': 2}
    result = integrations._review_report(value, {'notes.md': SOURCE['notes.md'], 'missing.py': None})
    assert result['status'] == 'not_reviewed' and result['coverage_status'] == 'none'
    assert result['files'] == value['files']
    assert result['source_sha256']['missing.py'] is None
    assert result['reason'] == '0 of 2 files scanned; 2 skipped.'


@pytest.mark.parametrize('case', ['schema', 'mode', 'missing_file', 'duplicate_file', 'unexpected_file',
    'source_hash', 'truncation', 'unexplained_skip', 'coverage', 'bool_count',
    'finding_file', 'finding_hash', 'verified', 'start_line', 'end_line', 'too_many'])
def test_malformed_or_stale_evidence_is_rejected(case):
    value = report()
    if case == 'schema': value['schema_version'] = True
    elif case == 'mode': value['mode'] = 'verified'
    elif case == 'missing_file': value['files'] = []
    elif case == 'duplicate_file': value['files'].append(copy.deepcopy(value['files'][0]))
    elif case == 'unexpected_file': value['files'][0]['path'] = 'other.py'
    elif case == 'source_hash': value['files'][0]['sha256'] = '0' * 64
    elif case == 'truncation': value['files'][0]['possibly_truncated'] = 'false'
    elif case == 'unexplained_skip': value['files'][0]['status'] = 'skipped'
    elif case == 'coverage': value['coverage']['skipped'] = 1
    elif case == 'bool_count': value['coverage']['reviewed'] = True
    elif case == 'finding_file': value['findings'][0]['path'] = 'other.py'
    elif case == 'finding_hash': value['findings'][0]['source_sha256'] = '0' * 64
    elif case == 'verified': value['findings'][0]['verified'] = True
    elif case == 'start_line': value['findings'][0]['start_line'] = True
    elif case == 'end_line': value['findings'][0]['end_line'] = 2
    elif case == 'too_many': value['findings'] *= 201
    with pytest.raises(ValueError):
        integrations._review_report(value, {'a.py': SOURCE['a.py']})


def test_findings_cannot_be_attached_to_skipped_files():
    value = report(skipped=True)
    value['findings'][0]['path'] = 'notes.md'
    with pytest.raises(ValueError, match='unreviewed'):
        integrations._review_report(value, SOURCE)


@pytest.mark.parametrize('changed_worker', [False, True])
def test_adapter_checks_worker_identity_and_applies_coverage_contract(tmp_path, monkeypatch, changed_worker):
    dependency = tmp_path / 'ptrm'
    worker = dependency / 'bin/ptrm-review-worker'
    worker.parent.mkdir(parents=True)
    worker.write_bytes(b'fixture executable identity; never executed')
    monkeypatch.setenv('OMARCHY_PTRM_ROOT', str(dependency))
    monkeypatch.setattr(integrations.patch_tasks, 'read_file', lambda root, name: SOURCE.get(name))

    async def fake(command, timeout, **kwargs):
        if changed_worker:
            worker.write_bytes(b'different worker')
        return ProcessResult(0, json.dumps(report(skipped=True)))

    monkeypatch.setattr(integrations, 'run_process', fake)
    if changed_worker:
        with pytest.raises(ValueError, match='worker changed'):
            asyncio.run(integrations.review_files(tmp_path, list(SOURCE)))
    else:
        result = asyncio.run(integrations.review_files(tmp_path, list(SOURCE)))
        assert result['status'] == 'partial' and result['coverage']['skipped'] == 1
        assert result['worker_sha256'] == hashlib.sha256(worker.read_bytes()).hexdigest()
