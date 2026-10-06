"""Admission, cancellation and durable replay through the asynchronous dispatcher."""
import asyncio
import json
import time

import pytest

from app import broker_requests, broker_scheduler as module


@pytest.fixture
def scheduler(tmp_path, monkeypatch):
    monkeypatch.setattr(broker_requests, 'STORE', tmp_path / 'requests')
    value = module.Scheduler()
    yield value
    value.close()


def frame(action='chat', request_id='fixture', args=None):
    return bytearray(json.dumps({'v': 1, 'id': request_id, 'action': action,
                                'args': {'prompt': request_id} if args is None else args}).encode())


def until(scheduler, condition, timeout=2):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, 'Scheduler did not settle'
        scheduler.tick()
        time.sleep(0.001)


def result(scheduler, token):
    until(scheduler, lambda: scheduler.ready(token))
    return json.loads(scheduler.take(token))


def test_cancel_before_first_tick_releases_admission_count(scheduler, monkeypatch):
    async def unexpected(*args, **kwargs):
        pytest.fail('A cancelled queued request reached the model')
    monkeypatch.setattr(module, 'gateway', unexpected)
    token, _ = scheduler.submit(frame())
    scheduler.detach(token)
    until(scheduler, lambda: not scheduler.jobs)
    assert scheduler.counts == {'chat': 0, 'validation': 0}


def test_one_chat_lane_has_bounded_queue_and_timeout_without_dispatch(scheduler, monkeypatch):
    monkeypatch.setattr(module, 'QUEUE_TIMEOUT', 0.05)
    calls = []
    async def slow(*args, **kwargs):
        calls.append('model')
        await asyncio.Event().wait()
    monkeypatch.setattr(module, 'gateway', slow)
    tokens = [scheduler.submit(frame(request_id=str(index)))[0] for index in range(5)]
    assert json.loads(scheduler.submit(frame(request_id='overflow'))[1])['error']['code'] == 'QUEUE_FULL'
    until(scheduler, lambda: len(calls) == 1)
    ping, _ = scheduler.submit(frame('ping', 'status-lane', {}))
    assert result(scheduler, ping)['result'] == 'pong'
    for token in tokens[1:]:
        assert result(scheduler, token)['error']['code'] == 'QUEUE_TIMEOUT'
    scheduler.detach(tokens[0])
    until(scheduler, lambda: not scheduler.jobs)
    assert calls == ['model'] and scheduler.counts['chat'] == 0


def test_client_departure_settles_upstream_before_freeing_capacity(scheduler, monkeypatch):
    entered, closed = [], []
    async def slow(*args, **kwargs):
        entered.append(True)
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0.01)
            closed.append(True)
    monkeypatch.setattr(module, 'gateway', slow)
    token, _ = scheduler.submit(frame())
    until(scheduler, lambda: bool(entered))
    scheduler.detach(token)
    assert scheduler.counts['chat'] == 1
    until(scheduler, lambda: not scheduler.jobs)
    assert closed == [True] and scheduler.counts['chat'] == 0


def test_completed_validation_replays_even_when_its_lane_is_full(scheduler, monkeypatch):
    calls = []
    async def worker(action, args, **kwargs):
        calls.append(args['task_id'])
        if args['task_id'] != 'a' * 32:
            await asyncio.Event().wait()
        return {'v': 1, 'ok': True, 'task': {'state': 'validated'}}
    monkeypatch.setattr(module, 'worker_request', worker)
    first = frame('task.validate', 'saved', {'task_id': 'a' * 32})
    token, _ = scheduler.submit(first)
    saved = result(scheduler, token)
    for index in range(5):
        assert scheduler.submit(frame('task.validate', str(index), {'task_id': 'b' * 32}))[0] > 0
    replay_token, replay = scheduler.submit(first)
    assert replay_token == -1 and json.loads(replay) == saved
    assert json.loads(scheduler.submit(frame('task.validate', 'saved', {'task_id': 'c' * 32}))[1])['error']['code'] == 'CONFLICT'
    assert calls == ['a' * 32]


def test_detached_durable_validation_finishes_and_records_result(scheduler, monkeypatch):
    entered, finished = [], []
    async def worker(*args, **kwargs):
        entered.append(True)
        await asyncio.sleep(0.03)
        finished.append(True)
        return {'v': 1, 'ok': True, 'task': {'state': 'validated'}}
    monkeypatch.setattr(module, 'worker_request', worker)
    request = frame('task.validate', 'durable', {'task_id': 'a' * 32})
    token, _ = scheduler.submit(request)
    until(scheduler, lambda: bool(entered))
    scheduler.detach(token)
    until(scheduler, lambda: not scheduler.jobs)
    assert finished == [True]
    token, cached = scheduler.submit(request)
    assert token == -1 and json.loads(cached)['result']['task']['state'] == 'validated'


def test_invalid_arguments_are_rejected_before_admission(scheduler):
    token, response = scheduler.submit(frame(args={'prompt': []}))
    assert token == -1 and json.loads(response)['error']['code'] == 'INVALID_REQUEST'
    assert not scheduler.jobs and not any(scheduler.counts.values())
