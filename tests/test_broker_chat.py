"""Project context through real MCP; controlled and live generation stay distinct."""
import asyncio
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
from threading import Thread
import time
from types import SimpleNamespace

import pytest

from app import broker_chat, broker_memory, broker_scheduler, memory
from app.broker_protocol import ProtocolError
from test_broker_memory import database, contents
from test_broker_concurrency import payload, response


def test_actual_context_preserves_scope_warning_and_receipts(database):
    path, ids, candidate = database
    before = contents(path)
    messages, context = asyncio.run(broker_chat.prepare({'prompt': 'timezone', 'project_id': 'memory-fixture'}))
    assert {row['id'] for row in context['records']} == set(ids[:2])
    assert context['warning_included'] and context['evidence_authority'] == 'caller-supplied'
    assert candidate not in json.dumps(context)
    assert messages[0]['role'] == 'system' and 'untrusted' in messages[0]['content']
    assert messages[1]['role'] == 'user' and ids[0] in messages[1]['content']
    assert len(messages) == 2 and messages[-1]['content'].endswith('\n\nQuestion:\ntimezone')
    assert all(row['verification']['evidence_ref'] == 'fixture:evidence' for row in context['records'])
    assert len(json.dumps(context, ensure_ascii=False, separators=(',', ':'))) <= broker_chat.CONTEXT_CHARS
    assert contents(path) == before
    memory.retract_memory('memory-fixture', ids[0], 'fixture retraction', db_path=path)
    _, changed = asyncio.run(broker_chat.prepare({'prompt': 'timezone', 'project_id': 'memory-fixture'}))
    assert {row['id'] for row in changed['records']} == {ids[1]}


@pytest.mark.parametrize('args', [
    {'prompt': 'x', 'revision': 'v1'}, {'prompt': 'x', 'project_id': '../escape'},
    {'prompt': '🙂' * 1025, 'project_id': 'valid'}, {'prompt': '\0'},
    {'prompt': 'x', 'project_id': 'valid', 'include_candidates': True},
])
def test_invalid_chat_never_starts_memory(args, monkeypatch):
    monkeypatch.setattr(broker_memory, 'parameters', lambda: pytest.fail('Invalid request started memory'))
    with pytest.raises(ValueError):
        asyncio.run(broker_chat.prepare(args))


def test_unscoped_chat_keeps_existing_contract(monkeypatch):
    monkeypatch.setattr(broker_memory, 'parameters', lambda: pytest.fail('Unscoped request searched project memory'))
    messages, context = asyncio.run(broker_chat.prepare({'prompt': 'hello'}))
    assert messages == [{'role': 'user', 'content': 'hello'}] and context is None
    assert broker_chat.result({'choices': [{'message': {'content': 'hi'}}]}, context) == 'hi'


@pytest.mark.parametrize('answer,finish', [('  \n', 'stop'), ('partial', 'length'), ('text', None)])
def test_scoped_chat_cannot_report_incomplete_generation_as_success(answer, finish):
    with pytest.raises(ProtocolError) as error:
        broker_chat.result({'choices': [{'message': {'content': answer}, 'finish_reason': finish}]}, {})
    assert error.value.code == 'GENERATION_INCOMPLETE'


@pytest.mark.parametrize('answer', ['<tool_call>{}</tool_call>', '{"answer":"a","answer":"b"}',
                                  '{"answer":""}', '{"answer":"x","run":"command"}',
                                  '{"answer":42}', json.dumps({'answer': 'x' * 1601})])
def test_scoped_reply_is_validated_even_if_runtime_ignores_schema(answer):
    with pytest.raises(ProtocolError) as error:
        broker_chat.result({'choices': [{'message': {'content': answer}, 'finish_reason': 'stop'}]}, {})
    assert error.value.code == 'GENERATION_INVALID'


def test_failed_context_does_not_call_model(tmp_path, monkeypatch):
    monkeypatch.setenv('ROMS_PYTHON_PREFIX', str(tmp_path / 'missing-runtime'))
    async def unexpected(*args, **kwargs):
        pytest.fail('Model called without the requested memory')
    monkeypatch.setattr(broker_scheduler, 'gateway', unexpected)
    request = {'id': 'failed', 'action': 'chat', 'args': {'prompt': 'timezone', 'project_id': 'fixture'}}
    with pytest.raises(ProtocolError) as error:
        asyncio.run(broker_scheduler.dispatch(request, bytearray(), False))
    assert error.value.code == 'SERVICE_UNAVAILABLE'


def test_empty_project_returns_explicit_non_generated_notice(database, monkeypatch):
    async def unexpected(*args, **kwargs):
        pytest.fail('A model was called with no project evidence')
    monkeypatch.setattr(broker_scheduler, 'gateway', unexpected)
    request = {'id': 'empty', 'action': 'chat', 'args': {'prompt': 'timezone', 'project_id': 'empty-fixture'}}
    before = contents(database[0])
    reply = json.loads(asyncio.run(broker_scheduler.dispatch(request, bytearray(), False)))
    assert reply['ok'] and reply['result']['generated'] is False
    assert reply['result']['memory']['records'] == []
    assert reply['result']['answer'] == 'No usable project memory was found for this question.'
    assert contents(database[0]) == before


def test_inconsistent_evidence_is_rejected(database):
    _, context = asyncio.run(broker_chat.prepare({'prompt': 'timezone', 'project_id': 'memory-fixture'}))
    args = broker_chat.memory_args({'prompt': 'timezone', 'project_id': 'memory-fixture'})
    for mutation in ('scope', 'outcome', 'count', 'warning'):
        changed = deepcopy(context)
        if mutation == 'scope':
            changed['project_id'] = 'other'
        elif mutation == 'outcome':
            row = changed['records'][0]
            row['verification']['exit_code'] = 1 if row['outcome'] == 'success' else 0
        elif mutation == 'count':
            changed['candidates'] = 20
        else:
            changed['warning_included'] = False
        result = {'isError': False, 'content': [{'type': 'text', 'text': json.dumps(changed)}]}
        with pytest.raises(ValueError):
            broker_memory.decode_context(SimpleNamespace(model_dump=lambda **kw: result), args)


@pytest.fixture
def native_chat(tmp_path, database):
    processes = []
    def launch(port, key='fixture-key', prompt='timezone'):
        address = tmp_path / ('broker-' + str(len(processes)) + '.sock')
        binary = os.getenv('OMARCHY_BROKER_BINARY', '/opt/roms-env/bin/omarchy-broker')
        env = dict(os.environ, OMARCHY_BROKER_SOCKET=str(address), ROMS_GATEWAY_PORT=str(port),
                   ROMS_GATEWAY_API_KEY=key)
        process = subprocess.Popen([binary], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        processes.append(process)
        deadline = time.monotonic() + 10
        while not address.exists():
            assert process.poll() is None and time.monotonic() < deadline
            time.sleep(0.02)
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(120)
            client.connect(str(address))
            client.sendall(payload('chat', 'project-chat', {'prompt': prompt, 'project_id': 'memory-fixture'}))
            return response(client)
    yield launch
    for process in processes:
        process.terminate()
        process.communicate(timeout=8)


def test_compiled_broker_supplies_real_memory_to_controlled_model(native_chat, database):
    calls = []
    class HTTP(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append(body)
            data = json.dumps({'choices': [{'message': {'content': '{"answer":"controlled fixture response"}'},
                                           'finish_reason': 'stop'}]}).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    server = ThreadingHTTPServer(('127.0.0.1', 0), HTTP)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    before = contents(database[0])
    try:
        result = native_chat(server.server_port)
        assert result['ok'], result
        assert result['result']['answer'] == 'controlled fixture response'
        assert result['result']['generated'] is True
        assert calls[0]['roms_retrieval'] == 'disabled'
        assert calls[0]['messages'][1]['role'] == 'user'
        assert database[1][0] in calls[0]['messages'][1]['content']
        assert result['result']['memory']['warning_included']
        assert contents(database[0]) == before
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
