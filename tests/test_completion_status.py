"""Incomplete generation never becomes successful evidence; proxy bytes stay intact."""
import json

import pytest

from app import broker_chat
from app.broker_protocol import ProtocolError
from app.completion_status import StreamCompletion, response_complete
from test_gateway_privacy import complete, recording


def event(delta=None, reason=None, index=0):
    return ('data: ' + json.dumps({'choices': [{'index': index, 'delta': delta or {},
                                               'finish_reason': reason}]}, ensure_ascii=False) + '\n\n').encode()


DONE = b'data: [DONE]\n\n'
TEXT = event({'role': 'assistant', 'content': 'Useful answer \U0001f642'})
STOP = event(reason='stop')


@pytest.mark.parametrize('fragments', [1, 2, 7, 65536])
def test_stream_tracks_split_utf8_crlf_comments_and_usage(fragments):
    wire = (b': heartbeat\n\n' + TEXT + STOP + b'data: {"choices":[],"usage":{"total_tokens":4}}\n\n' + DONE)
    wire = wire.replace(b'\n', b'\r\n')
    tracker = StreamCompletion()
    for offset in range(0, len(wire), fragments):
        tracker.feed(wire[offset:offset + fragments])
    assert tracker.complete()


@pytest.mark.parametrize('wire', [
    b'', TEXT, TEXT + STOP, TEXT + DONE, TEXT + event(reason='length') + DONE,
    TEXT + event(reason='content_filter') + DONE, TEXT + STOP + DONE + TEXT,
    b'data: {"choices":[]}\n\n' + TEXT + STOP + DONE,
    b'data: {"choices":[],"choices":[]}\n\n' + TEXT + STOP + DONE,
    b'data: {"choices":[],"usage":NaN}\n\n' + TEXT + STOP + DONE,
    b'data: not-json\n\n' + TEXT + STOP + DONE,
    b'event: error\ndata: {}\n\n' + TEXT + STOP + DONE,
    b'data: {"error":"backend failed"}\n\n' + TEXT + STOP + DONE,
    event({'content': 123}) + STOP + DONE,
    event({'tool_calls': [123]}) + event(reason='tool_calls') + DONE,
    event(reason='tool_calls') + DONE, event(reason='function_call') + DONE,
    event({'tool_calls': [{'index': 0, 'id': 'call_1', 'function': {'arguments': '{}'}}]})
        + event(reason='tool_calls') + DONE,
    event({'function_call': {'arguments': '{}'}}) + event(reason='function_call') + DONE,
    event({'function_call': {'arguments': '{}'}}) + STOP + DONE,
    event({'function_call': {'arguments': 123}}) + event(reason='function_call') + DONE,
    TEXT + event(reason='unknown') + DONE, TEXT + STOP + DONE + b'\xf0',
    TEXT + STOP + DONE + b'event: error\n',
    TEXT + STOP + b'data: [DONE]', b':' + b'x' * 262145 + b'\n\n' + TEXT + STOP + DONE,
], ids=lambda value: 'wire-' + str(len(value)))
def test_incomplete_or_malformed_stream_is_never_success(wire):
    tracker = StreamCompletion()
    tracker.feed(wire)
    assert not tracker.complete()


def test_all_requested_choices_must_finish_independently():
    tracker = StreamCompletion(2)
    tracker.feed(TEXT + event({'content': 'second'}, index=1) + STOP + DONE)
    assert not tracker.complete()
    tracker = StreamCompletion(2)
    tracker.feed(TEXT + event({'content': 'second'}, index=1) + STOP + event(reason='stop', index=1) + DONE)
    assert tracker.complete()
    missing = StreamCompletion(2)
    missing.feed(TEXT + STOP + DONE)
    assert not missing.complete()


@pytest.mark.parametrize('kind', ['tool_calls', 'function_call'])
def test_complete_tool_responses_and_fragments_are_preserved(recording, monkeypatch, kind):
    monkeypatch.setenv('ROMS_RECORD_CHAT_TRAJECTORIES', '1')
    function = {'name': 'lookup', 'arguments': '{"query":"invoice"}'}
    value = [dict(id='call_1', type='function', function=function)] if kind == 'tool_calls' else function
    response = {'choices': [{'index': 0, 'finish_reason': kind,
                             'message': {'role': 'assistant', 'content': None, kind: value}}]}
    assert response_complete(response)
    received, payload = complete(monkeypatch, upstream_json=response)
    assert received.status_code == 200 and json.loads(payload) == response
    first = {'name': 'lookup', 'arguments': '{"query":'}
    second = {'arguments': '"invoice"}'}
    if kind == 'tool_calls':
        first = [dict(index=0, id='call_1', type='function', function=first)]
        second = [dict(index=0, function=second)]
    wire = event({kind: first}) + event({kind: second}) + event(reason=kind) + DONE
    received, payload = complete(monkeypatch, stream=True, upstream_chunks=[wire[:63], wire[63:]])
    assert received.status_code == 200 and payload == wire
    connection, calls = recording
    assert [row[0] for row in connection.execute('SELECT success FROM agent_trajectories')] == [1, 1]
    assert len([name for name, _ in calls if name == 'finish_session']) == 2


@pytest.mark.parametrize('wire', [TEXT + STOP, TEXT + DONE, TEXT + event(reason='length') + DONE,
                                  b'data: bad-json\n\n' + TEXT + STOP + DONE], ids=['no-done', 'no-stop', 'length', 'malformed'])
def test_gateway_forwards_partial_stream_but_records_failure(recording, monkeypatch, wire):
    monkeypatch.setenv('ROMS_RECORD_CHAT_TRAJECTORIES', '1')
    _, payload = complete(monkeypatch, stream=True, upstream_chunks=[wire])
    assert payload == wire
    connection, calls = recording
    assert connection.execute('SELECT success FROM agent_trajectories').fetchone()[0] == 0
    assert 'incomplete or malformed' in calls[-1][1]['final_result']


@pytest.mark.parametrize('reason', ['length', 'content_filter', None])
def test_gateway_preserves_partial_nonstream_but_broker_refuses(recording, monkeypatch, reason):
    monkeypatch.setenv('ROMS_RECORD_CHAT_TRAJECTORIES', '1')
    response = {'choices': [{'message': {'content': 'partial answer'}, 'finish_reason': reason}]}
    _, payload = complete(monkeypatch, upstream_json=response)
    assert json.loads(payload) == response
    assert recording[0].execute('SELECT success FROM agent_trajectories').fetchone()[0] == 0
    with pytest.raises(ProtocolError, match='complete'):
        broker_chat.result(response, None)


@pytest.mark.parametrize('response', [
    {}, {'choices': []}, {'choices': [None]}, {'choices': [{'finish_reason': 'stop', 'message': []}]},
    {'choices': [{'finish_reason': 'stop', 'message': {'content': 'ok', 'refusal': 'refused'}}]},
    {'choices': [{'finish_reason': 'tool_calls', 'message': {'content': None,
        'tool_calls': [{'type': 'function', 'function': {'name': 'lookup', 'arguments': '{}'}}]}}]},
])
def test_text_broker_refuses_invalid_or_nontext_completions(response):
    with pytest.raises(ProtocolError):
        broker_chat.result(response, None)


def test_gateway_records_all_requested_choices(recording, monkeypatch):
    monkeypatch.setenv('ROMS_RECORD_CHAT_TRAJECTORIES', '1')
    wire = TEXT + STOP + DONE
    _, payload = complete(monkeypatch, stream=True, upstream_chunks=[wire], choices=2)
    assert payload == wire
    assert recording[0].execute('SELECT success FROM agent_trajectories').fetchone()[0] == 0
