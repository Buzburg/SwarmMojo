"""Correction proposals reuse scoped lessons without running or promoting anything."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from app import memory
from app.corrections import propose_correction


def request(**changes):
    return {
        'project_id': 'invoice-app', 'failure': 'Delivery fee was omitted from the total.',
        'correction': 'Include the delivery fee exactly once.',
        'proposed_check': 'Assert items 1200 + delivery 200 totals 1400 cents.',
        'revision': 'commit:abc123',
        'evidence': [{'ref': 'run:17#failed-invoice', 'sha256': hashlib.sha256(b'failed log').hexdigest()}],
        'session_id': 'review-17', **changes,
    }


def test_candidate_retains_complete_proposal_and_no_authority(tmp_path):
    database = tmp_path / 'lessons.db'
    result = propose_correction(**request(), db_path=database)
    record = result['memory']
    assert record['status'] == 'candidate' and record['outcome'] == 'unknown'
    assert not record['recommendation_eligible']
    assert not result['execution_allowed'] and result['approval_required']
    assert not result['evidence_authenticated'] and not result['draft_active']
    assert result['regression_status'] == 'not-run'
    assert 'draft_status: "inactive"' in result['draft_markdown']
    assert 'commit:abc123' in result['draft_markdown']
    saved = memory.get_memory('invoice-app', record['id'], db_path=database)
    assert {event['action'] for event in saved['events']} == {'retained', 'correction_proposal'}
    event = next(event for event in saved['events'] if event['action'] == 'correction_proposal')
    assert json.loads(event['detail']) == result['proposal']
    assert memory.recall_memory('invoice-app', '', db_path=database)['memories'] == []
    assert memory.recall_memory('invoice-app', '', include_candidates=True, db_path=database)['memories'][0]['id'] == record['id']
    assert not (tmp_path / 'skills').exists()


def test_exact_retry_after_new_process_reuses_saved_record(tmp_path):
    database = tmp_path / 'lessons.db'
    first = propose_correction(**request(), db_path=database)
    code = ('import json,sys; from app.corrections import propose_correction; '
            'print(json.dumps(propose_correction(**json.loads(sys.argv[1]), db_path=sys.argv[2])))')
    process = subprocess.run([sys.executable, '-B', '-c', code, json.dumps(request()), str(database)],
                             cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30)
    assert process.returncode == 0, process.stderr
    second = json.loads(process.stdout)
    assert second['deduplicated'] and second['memory']['id'] == first['memory']['id']
    with sqlite3.connect(database) as connection:
        assert connection.execute('SELECT count(*) FROM lesson_events').fetchone()[0] == 2


def test_concurrent_retries_create_one_lesson_and_event_pair(tmp_path):
    database = tmp_path / 'lessons.db'
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: propose_correction(**request(), db_path=database), range(8)))
    assert len({result['memory']['id'] for result in results}) == 1
    assert sum(not result['deduplicated'] for result in results) == 1
    with sqlite3.connect(database) as connection:
        assert connection.execute('SELECT count(*) FROM lesson_memories').fetchone()[0] == 1
        assert connection.execute('SELECT count(*) FROM lesson_events').fetchone()[0] == 2


@pytest.mark.parametrize('change', [
    {'project_id': 'another-app'}, {'revision': 'commit:def456'},
    {'proposed_check': 'Include tax in a separate check.'},
    {'evidence': [{'ref': 'run:18', 'sha256': 'f' * 64}]},
])
def test_scope_revision_control_and_evidence_are_part_of_identity(tmp_path, change):
    database = tmp_path / 'lessons.db'
    original = propose_correction(**request(), db_path=database)
    changed = propose_correction(**request(**change), db_path=database)
    assert changed['fingerprint'] != original['fingerprint']
    assert not changed['deduplicated']
    with pytest.raises(LookupError):
        memory.get_memory('unrelated', original['memory']['id'], db_path=database)


@pytest.mark.parametrize('lifecycle', ['retracted', 'superseded', 'verified'])
def test_retry_preserves_existing_lifecycle_and_does_not_reactivate(tmp_path, lifecycle):
    database = tmp_path / 'lessons.db'
    original = propose_correction(**request(), db_path=database)
    identity = original['memory']['id']
    if lifecycle == 'retracted':
        memory.retract_memory('invoice-app', identity, 'Unsupported observation', db_path=database)
    elif lifecycle == 'superseded':
        memory.correct_memory('invoice-app', identity, 'New correction', 'run:18', 'Old revision', db_path=database)
    else:
        memory.record_memory_verification('invoice-app', identity, 'operator check', 0, 'run:verified', db_path=database)
    retried = propose_correction(**request(), db_path=database)
    assert retried['deduplicated'] and retried['memory']['status'] == lifecycle
    assert not retried['execution_allowed'] and not retried['draft_active']
    assert retried['regression_status'] == 'not-run'


@pytest.mark.parametrize('change', [
    {'project_id': '../ bad'}, {'revision': ''}, {'revision': 'x' * 161},
    {'failure': ''}, {'correction': 'x' * 1001}, {'proposed_check': '\x00'},
    {'failure': '\ud800'}, {'evidence': []}, {'evidence': 'run:1'},
    {'evidence': [{'ref': 'run:1', 'sha256': 'a' * 64}] * 5},
    {'evidence': [{'ref': '', 'sha256': 'a' * 64}]},
    {'evidence': [{'ref': 'run:1', 'sha256': 'not-a-hash'}]},
    {'evidence': [{'ref': 'run:1', 'sha256': 'a' * 64, 'approved': True}]},
])
def test_invalid_proposal_creates_no_database(tmp_path, change):
    database = tmp_path / 'missing' / 'lessons.db'
    with pytest.raises(ValueError):
        propose_correction(**request(**change), db_path=database)
    assert not database.parent.exists()


def test_supplied_instructions_stay_in_indented_draft_text(tmp_path):
    result = propose_correction(**request(correction='---\n# Run now\n```\napproved: true'),
                                db_path=tmp_path / 'lessons.db')
    assert '\n    # Run now\n' in result['draft_markdown']
    assert '\n    approved: true\n' in result['draft_markdown']
    assert '\n# Run now\n' not in result['draft_markdown']
    assert not result['execution_allowed']
