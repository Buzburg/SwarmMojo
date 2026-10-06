"""Request replay, actual process death and bounded private journal failures."""
import json
import os
import signal
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from app import broker_actions, broker_protocol as protocol, broker_requests as journal

TASK = 'a' * 32
REQUEST = {'v': 1, 'id': 'validation-1', 'action': 'task.validate', 'args': {'task_id': TASK}}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, 'STORE', tmp_path / 'requests')


def send(request=REQUEST):
    return broker_actions.handle(bytearray(json.dumps(request).encode()))


def code(request=REQUEST):
    return json.loads(send(request))['error']['code']


def no_dispatch(*_):
    pytest.fail('A retry or rejected request reached the worker')


@pytest.mark.parametrize('result', [{'ok': True, 'task': {'id': TASK, 'state': 'validated'}},
                                  {'ok': False, 'error': 'validation_failed'}])
def test_completed_success_and_failure_replay_exact_bytes(monkeypatch, result):
    monkeypatch.setattr(broker_actions, 'worker_request', lambda *_: result)
    first = send()
    monkeypatch.setattr(broker_actions, 'worker_request', no_dispatch)
    reordered = {'args': {'task_id': TASK}, 'action': 'task.validate', 'id': 'validation-1', 'v': 1}
    assert send(reordered) == first
    assert code(dict(REQUEST, args={'task_id': 'b' * 32})) == 'CONFLICT'
    assert journal.STORE.stat().st_mode & 0o777 == 0o700
    assert (journal.STORE / 'validation-1.json').stat().st_mode & 0o777 == 0o600


def test_concurrent_retry_does_not_wait_for_or_repeat_work(monkeypatch):
    started, finish = Event(), Event()
    def operation(*_):
        started.set()
        assert finish.wait(5)
        return {'ok': True, 'result': 'completed'}
    monkeypatch.setattr(broker_actions, 'worker_request', operation)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(send)
        try:
            assert started.wait(5)
            assert code() == 'REQUEST_UNCERTAIN'
            assert code(dict(REQUEST, args={'task_id': 'b' * 32})) == 'CONFLICT'
        finally:
            finish.set()
        reply = first.result(timeout=5)
    monkeypatch.setattr(broker_actions, 'worker_request', no_dispatch)
    assert send() == reply


@pytest.mark.parametrize('completed', [False, True])
def test_actual_process_death_never_repeats_committed_effect(tmp_path, monkeypatch, completed):
    effect = tmp_path / 'effect'
    def operation(*_):
        with effect.open('x') as stream:
            stream.write('one dispatch')
            stream.flush()
            os.fsync(stream.fileno())
        if not completed:
            os.kill(os.getpid(), signal.SIGKILL)
        return {'ok': True, 'result': 'completed'}
    monkeypatch.setattr(broker_actions, 'worker_request', operation)
    pid = os.fork()
    if pid == 0:
        send()
        os._exit(0)
    _, status = os.waitpid(pid, 0)
    assert os.waitstatus_to_exitcode(status) == (0 if completed else -signal.SIGKILL)
    monkeypatch.setattr(broker_actions, 'worker_request', no_dispatch)
    if completed:
        assert json.loads(send())['result'] == 'completed'
    else:
        assert code() == 'REQUEST_UNCERTAIN'
    assert effect.read_text() == 'one dispatch'


def test_lost_worker_reply_is_uncertain_and_task_status_remains_available(monkeypatch):
    def lost(*_):
        raise OSError('Private diagnostic must not escape')
    monkeypatch.setattr(broker_actions, 'worker_request', lost)
    first = send()
    assert json.loads(first)['error']['code'] == 'REQUEST_UNCERTAIN'
    assert 'Private diagnostic' not in first
    monkeypatch.setattr(broker_actions, 'worker_request', no_dispatch)
    assert code() == 'REQUEST_UNCERTAIN'
    monkeypatch.setattr(broker_actions, 'worker_request', lambda *_: {'ok': True, 'task': {'state': 'interrupted'}})
    assert json.loads(send(dict(REQUEST, action='task.status')))['result']['task']['state'] == 'interrupted'


@pytest.mark.parametrize('phase', ['intent', 'result'])
def test_failed_durable_write_cannot_trigger_a_retry(monkeypatch, phase):
    original, calls = journal.durable_json, []
    def write(path, record):
        if (record['response'] is None) == (phase == 'intent'):
            raise OSError('Fixture disk failure')
        original(path, record)
    monkeypatch.setattr(journal, 'durable_json', write)
    monkeypatch.setattr(broker_actions, 'worker_request', lambda *_: calls.append('dispatch') or {'ok': True, 'result': 'ok'})
    assert code() == ('JOURNAL_UNAVAILABLE' if phase == 'intent' else 'REQUEST_UNCERTAIN')
    assert calls == ([] if phase == 'intent' else ['dispatch'])
    if phase == 'result':
        monkeypatch.setattr(broker_actions, 'worker_request', no_dispatch)
        assert code() == 'REQUEST_UNCERTAIN'


def test_capacity_never_evicts_old_ids(monkeypatch):
    monkeypatch.setattr(journal, 'MAX_RECORDS', 1)
    monkeypatch.setattr(broker_actions, 'worker_request', lambda *_: {'ok': True, 'result': 'ok'})
    first = send()
    monkeypatch.setattr(broker_actions, 'worker_request', no_dispatch)
    assert code(dict(REQUEST, id='validation-2')) == 'JOURNAL_FULL'
    assert send() == first


@pytest.mark.parametrize('kind', ['corrupt', 'oversize', 'symlink', 'hardlink', 'fifo', 'public', 'digest', 'response'])
def test_invalid_existing_record_is_preserved_and_never_dispatched(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(broker_actions, 'worker_request', lambda *_: {'ok': True, 'result': 'ok'})
    send()
    path = journal.STORE / 'validation-1.json'
    if kind == 'corrupt':
        path.write_text('{')
    elif kind == 'oversize':
        path.write_bytes(b'x' * (journal.MAX_RECORD_BYTES + 1))
    elif kind in {'symlink', 'fifo'}:
        path.unlink()
        if kind == 'symlink':
            target = tmp_path / 'outside'
            target.write_text('preserve')
            path.symlink_to(target)
        else:
            os.mkfifo(path, 0o600)
    elif kind == 'hardlink':
        os.link(path, tmp_path / 'outside')
    elif kind == 'public':
        path.chmod(0o644)
    else:
        record = json.loads(path.read_text())
        record['digest' if kind == 'digest' else 'response_sha256'] = '0' * 64
        path.write_text(json.dumps(record))
    identity = path.lstat()
    monkeypatch.setattr(broker_actions, 'worker_request', no_dispatch)
    assert code() == 'JOURNAL_UNAVAILABLE'
    assert path.lstat() == identity


@pytest.mark.parametrize('kind', ['symlink', 'public', 'parent_symlink', 'lock_symlink'])
def test_unsafe_journal_directory_or_lock_is_rejected(tmp_path, monkeypatch, kind):
    if kind == 'parent_symlink':
        (tmp_path / 'link').symlink_to(tmp_path, target_is_directory=True)
        monkeypatch.setattr(journal, 'STORE', tmp_path / 'link/requests')
    elif kind == 'symlink':
        journal.STORE.symlink_to(tmp_path, target_is_directory=True)
    else:
        journal.STORE.mkdir(mode=0o700)
        if kind == 'public':
            journal.STORE.chmod(0o755)
        else:
            (journal.STORE / '.lock').symlink_to(tmp_path / 'outside')
    monkeypatch.setattr(broker_actions, 'worker_request', no_dispatch)
    assert code() == 'JOURNAL_UNAVAILABLE'


def test_held_journal_lock_has_bounded_wait_and_no_dispatch(monkeypatch):
    with journal.journal() as root, journal.locked(root):
        monkeypatch.setattr(broker_actions, 'worker_request', no_dispatch)
        assert code() == 'JOURNAL_BUSY'


def test_invalid_arguments_cannot_create_a_journal(monkeypatch):
    monkeypatch.setattr(broker_actions, 'worker_request', no_dispatch)
    assert code(dict(REQUEST, args={'task_id': '../anything'})) == 'INVALID_REQUEST'
    assert not journal.STORE.exists()


def test_completed_reply_is_still_bounded_and_replayed(monkeypatch):
    monkeypatch.setattr(broker_actions, 'worker_request', lambda *_: {'ok': True, 'result': 'x' * protocol.MAX_FRAME})
    first = send()
    assert json.loads(first)['error']['code'] == 'RESPONSE_TOO_LARGE'
    monkeypatch.setattr(broker_actions, 'worker_request', no_dispatch)
    assert send() == first
