"""Automatic chat recording is opt-in; manual trajectory tools remain explicit."""
import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path

import httpx
import pytest
from starlette.requests import Request

from app import db, gateway, trajectory_recorder as recorder
from app.request_lifecycle import ClientDisconnected

PROMPT = 'fixture-private-prompt-274be1'
COMPLETION = 'fixture-private-completion-42f196'


@pytest.fixture
def recording(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / 'trajectories.db'
    db.init_database(path)
    connection = db.get_connection(path)
    calls = []
    monkeypatch.delenv('ROMS_RECORD_CHAT_TRAJECTORIES', raising=False)
    monkeypatch.setattr(recorder, '_ACTIVE_SESSIONS', {})
    monkeypatch.setattr(recorder, 'get_connection', lambda db_path=None: connection)
    for name in ('start_session', 'finish_session'):
        original = getattr(recorder, name)

        def tracked(*, _name=name, _original=original, **kwargs):
            calls.append((_name, kwargs))
            return _original(**kwargs)

        monkeypatch.setattr(gateway, name, tracked)
    try:
        yield connection, calls
    finally:
        connection.close()


def complete(monkeypatch: pytest.MonkeyPatch, *, stream=False, outcome='success', prompt=PROMPT,
             upstream_json=None, upstream_chunks=None, choices=1):
    body = {'messages': [{'role': 'user', 'content': prompt}],
            'stream': stream, 'roms_retrieval': 'disabled', 'n': choices}
    status = 503 if outcome == 'rejected' else 200

    def fail_if_requested():
        if outcome == 'error':
            raise httpx.ConnectError('fixture backend failure')
        if outcome == 'cancelled':
            raise asyncio.CancelledError()

    class Backend:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, *args, **kwargs):
            fail_if_requested()
            value = upstream_json if upstream_json is not None else {
                'choices': [{'message': {'content': COMPLETION}, 'finish_reason': 'stop'}]}
            return httpx.Response(status, json=value)

        @asynccontextmanager
        async def stream(self, *args, **kwargs):
            yield self

        def raise_for_status(self):
            if status != 200:
                raise httpx.HTTPStatusError('fixture upstream rejection',
                                           request=httpx.Request('POST', 'http://fixture.invalid'),
                                           response=httpx.Response(status))

        async def aiter_bytes(self):
            fail_if_requested()
            if upstream_chunks is not None:
                for chunk in upstream_chunks:
                    yield chunk
                return
            yield ('data: ' + json.dumps({'choices': [{'delta': {'content': COMPLETION}}]}) + '\n\n').encode()
            yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
            yield b'data: [DONE]\n\n'

    async def connected(request, generate):
        if outcome == 'disconnected':
            raise ClientDisconnected()
        return await generate()

    monkeypatch.setattr(gateway.httpx, 'AsyncClient', Backend)
    monkeypatch.setattr(gateway, 'while_connected', connected)

    async def run():
        async def receive():
            return {'type': 'http.request', 'body': json.dumps(body).encode(), 'more_body': False}

        response = await gateway.chat_completions(Request({'type': 'http', 'method': 'POST', 'headers': []}, receive))
        if stream:
            payload = b''.join([piece async for piece in response.body_iterator])
        else:
            payload = response.body
        return response, payload

    return asyncio.run(run())


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize(('stream', 'outcome'), [
    (False, 'success'), (True, 'success'), (False, 'error'), (True, 'error'),
    (False, 'rejected'), (True, 'rejected'), (False, 'cancelled'),
    (True, 'cancelled'), (False, 'disconnected'),
])
def test_automatic_recording_is_explicit(recording, monkeypatch, enabled, stream, outcome):
    connection, calls = recording
    if enabled:
        monkeypatch.setenv('ROMS_RECORD_CHAT_TRAJECTORIES', '1')
    else:
        def forbidden_uuid():
            pytest.fail('Disabled recording must not allocate a trajectory session')
        monkeypatch.setattr(gateway.uuid, 'uuid4', forbidden_uuid)
    if outcome == 'cancelled':
        with pytest.raises(asyncio.CancelledError):
            complete(monkeypatch, stream=stream, outcome=outcome)
    else:
        response, payload = complete(monkeypatch, stream=stream, outcome=outcome)
        if not enabled:
            assert 'X-ROMS-Session' not in response.headers
        if outcome == 'success':
            assert COMPLETION.encode() in payload
            assert response.status_code == 200
            if enabled:
                assert response.headers['X-ROMS-Session'] == calls[0][1]['session_id']
        elif not stream:
            assert response.status_code == {'error': 502, 'rejected': 503, 'disconnected': 499}[outcome]
    rows = connection.execute('SELECT session_id, goal, success, final_result FROM agent_trajectories').fetchall()
    if enabled:
        assert len(rows) == 1
        assert rows[0][1] == PROMPT
        assert rows[0][2] == (outcome == 'success')
        assert [name for name, _ in calls] == ['start_session', 'finish_session']
        assert all(values['session_id'] == rows[0][0] for _, values in calls)
        assert COMPLETION not in str(rows) + str(calls)
    else:
        assert rows == [] and calls == [] and recorder._ACTIVE_SESSIONS == {}
        dump = '\n'.join(connection.iterdump())
        assert PROMPT not in dump and COMPLETION not in dump


@pytest.mark.parametrize('value', ['', '0', 'true', 'yes', ' 1'])
def test_only_exact_opt_in_enables_recording(recording, monkeypatch, value):
    connection, calls = recording
    monkeypatch.setenv('ROMS_RECORD_CHAT_TRAJECTORIES', value)
    response, _ = complete(monkeypatch)
    assert 'X-ROMS-Session' not in response.headers
    assert calls == []
    assert connection.execute('SELECT COUNT(*) FROM agent_trajectories').fetchone()[0] == 0


@pytest.mark.parametrize('stream', [False, True])
def test_opt_in_without_user_text_does_not_invent_a_session(recording, monkeypatch, stream):
    _, calls = recording
    monkeypatch.setenv('ROMS_RECORD_CHAT_TRAJECTORIES', '1')
    response, _ = complete(monkeypatch, prompt='', stream=stream)
    assert 'X-ROMS-Session' not in response.headers
    assert calls == []


def test_manual_trajectory_tools_remain_available_with_automatic_recording_off(recording):
    from app.tools import start_trajectory_session, record_trajectory_step, finish_trajectory_session
    connection, automatic_calls = recording
    start_trajectory_session('manual-fixture', 'Explicitly record this fixture')
    record_trajectory_step('manual-fixture', 'fixture-check', {}, 'passed')
    finish_trajectory_session('manual-fixture', True, 'Explicit result')
    row = connection.execute('SELECT goal, steps_json, success, final_result FROM agent_trajectories').fetchone()
    assert row[0] == 'Explicitly record this fixture' and 'fixture-check' in row[1]
    assert row[2:] == (1, 'Explicit result')
    assert automatic_calls == []
