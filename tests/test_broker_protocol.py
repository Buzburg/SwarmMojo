"""Strict framing, request identity and bounded structured broker responses."""
import json

import pytest

from app import broker_actions, broker_protocol as protocol

REQUEST = {'v': 1, 'id': 'fixture-1', 'action': 'ping', 'args': {}}


def send(value):
    raw = value if isinstance(value, bytes) else json.dumps(value).encode()
    return json.loads(broker_actions.handle(bytearray(raw)))


@pytest.mark.parametrize('value', [[], None, dict(REQUEST, v=True), dict(REQUEST, v=1.0),
    dict(REQUEST, v=2), dict(REQUEST, id=None), dict(REQUEST, id=''), dict(REQUEST, id='x' * 65),
    dict(REQUEST, id='not/allowed'), dict(REQUEST, id='é'), dict(REQUEST, action=[]),
    dict(REQUEST, args=[]), dict(REQUEST, extra='field'), {'v': 1, 'action': 'ping'},
    b'{"v":1,"v":1,"id":"x","action":"ping","args":{}}',
    b'{"v":1,"id":"x","action":"chat","args":{"prompt":NaN}}',
    b'\xff', b'{} {}', b'MOCK', b'ANCHOR'])
def test_malformed_requests_cannot_reach_services(monkeypatch, value):
    monkeypatch.setattr(broker_actions, 'gateway', lambda *_: pytest.fail('Malformed request reached a service'))
    monkeypatch.setattr(broker_actions, 'worker_request', lambda *_: pytest.fail('Malformed request reached a worker'))
    response = send(value)
    assert set(response) == {'v', 'id', 'ok', 'error'}
    assert response['ok'] is False and response['id'] is None
    assert set(response['error']) == {'code', 'message'}


def test_depth_limit_counts_containers_but_not_string_contents(monkeypatch):
    nested = 0
    for _ in range(14):
        nested = [nested]
    request = dict(REQUEST, action='state.save', args={'nested': nested})
    assert protocol.parse(json.dumps(request).encode()) == request  # root + args + 14 arrays
    request['args']['nested'] = [nested]
    assert send(request)['error']['code'] == 'INVALID_REQUEST'
    monkeypatch.setattr(broker_actions, 'gateway', lambda *_: {
        'choices': [{'message': {'content': 'ok'}, 'finish_reason': 'stop'}]})
    assert send(dict(REQUEST, action='chat', args={'prompt': 'escaped "\\ brackets ' + '[{' * 100}))['result'] == 'ok'


def test_args_error_preserves_valid_request_id():
    response = send(dict(REQUEST, args={'shell': 'anything'}))
    assert response['id'] == REQUEST['id'] and response['error']['code'] == 'INVALID_REQUEST'


@pytest.mark.parametrize('action', ['state.save', 'state.restore', 'state.fork',
                                   'task.stage', 'task.apply', 'task.rollback', 'task.cancel', 'unknown'])
def test_unimplemented_actions_are_honest_and_have_no_side_effects(monkeypatch, action):
    monkeypatch.setattr(broker_actions, 'worker_request', lambda *_: pytest.fail('Unimplemented action reached worker'))
    response = send(dict(REQUEST, action=action, args={'untrusted': 'data'}))
    assert response['id'] == REQUEST['id']
    assert response['error']['code'] == 'NOT_IMPLEMENTED' and 'result' not in response


def test_memory_search_requires_scope_before_service_start(monkeypatch):
    from app import broker_memory
    monkeypatch.setattr(broker_memory, 'parameters', lambda: pytest.fail('Invalid memory request spawned a process'))
    response = send(dict(REQUEST, action='memory.search', args={'query': 'unscoped'}))
    assert response['id'] == REQUEST['id'] and response['error']['code'] == 'INVALID_REQUEST'


def test_oversized_response_fails_with_safe_bounded_error(monkeypatch):
    monkeypatch.setattr(broker_actions, 'gateway', lambda *_: {
        'choices': [{'message': {'content': 'x' * 65536}, 'finish_reason': 'stop'}]})
    response = send(dict(REQUEST, action='chat', args={'prompt': 'fixture'}))
    assert response['error']['code'] == 'RESPONSE_TOO_LARGE'
    assert response['id'] == REQUEST['id'] and len(json.dumps(response)) < 256


def test_service_error_does_not_expose_exception_text(monkeypatch):
    def unavailable(*_):
        raise OSError('private path and secret diagnostic')
    monkeypatch.setattr(broker_actions, 'gateway', unavailable)
    response = send(dict(REQUEST, action='chat', args={'prompt': 'fixture'}))
    assert response['error']['code'] == 'SERVICE_UNAVAILABLE'
    assert 'private path' not in json.dumps(response)


def test_frame_size_is_measured_in_bytes():
    with pytest.raises(protocol.ProtocolError, match='65536'):
        protocol.parse(('é' * 32769).encode())


def test_nonfinite_service_data_cannot_break_response_serialization():
    response = json.loads(protocol.encode({'v': 1, 'id': 'fixture', 'ok': True, 'result': float('nan')}))
    assert response['error']['code'] == 'SERVICE_FAILURE' and response['id'] == 'fixture'
