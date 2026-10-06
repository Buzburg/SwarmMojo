"""Real MCP lifecycle and process cleanup against isolated project memory."""
import asyncio
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import time

import pytest
import psutil
from app import broker_memory, memory
from app.broker_protocol import ProtocolError

ARGS = {'project_id': 'memory-fixture', 'query': 'timezone'}


@pytest.fixture
def database(tmp_path, monkeypatch):
    path = tmp_path / 'roms.db'
    monkeypatch.setenv('ROMS_DB_PATH', str(path))
    monkeypatch.setenv('ROMS_DATA_DIR', str(tmp_path))
    records = []
    for scope, outcome in [('memory-fixture', 0), ('memory-fixture', 1), ('other-project', 0)]:
        row = memory.retain_memory(scope, 'Timezone: preserve the offset', 'fixture:source', db_path=path)
        memory.record_memory_verification(scope, row['id'], 'fixture: simulated check', outcome,
                                          'fixture:evidence', db_path=path)
        records.append(row['id'])
    candidate = memory.retain_memory('memory-fixture', 'Timezone candidate', 'fixture:candidate', db_path=path)
    return path, records, candidate['id']


def contents(path):
    with sqlite3.connect(path) as connection:
        return list(connection.iterdump())


def test_actual_mcp_discovery_recall_scope_bounds_and_no_writes(database):
    path, ids, candidate = database
    before = contents(path)
    async def verify():
        result = await broker_memory.search(ARGS)
        assert {row['id'] for row in result['memories']} == set(ids[:2])
        assert {row['outcome'] for row in result['memories']} == {'success', 'failure'}
        for row in result['memories']:
            assert row['source_ref'] == 'fixture:source'
            assert row['verification']['evidence_ref'] == 'fixture:evidence'
            assert row['recommendation_eligible'] == (row['outcome'] == 'success')
        bounded = await broker_memory.search(dict(ARGS, max_chars=500))
        assert bounded == {'memories': [], 'truncated': True}
        candidates = await broker_memory.search(dict(ARGS, include_candidates=True))
        row = next(row for row in candidates['memories'] if row['id'] == candidate)
        assert not row['recommendation_eligible'] and row['status'] == 'candidate'
    asyncio.run(verify())
    assert contents(path) == before


@pytest.mark.parametrize('args', [{}, dict(ARGS, project_id='../escape'), dict(ARGS, query='x' * 501),
    dict(ARGS, limit=True), dict(ARGS, max_chars=12001), dict(ARGS, revision='\x00'),
    dict(ARGS, include_candidates=1), dict(ARGS, command='unexpected')])
def test_bad_arguments_never_start_service(args, monkeypatch):
    monkeypatch.setattr(broker_memory, 'parameters', lambda: pytest.fail('Invalid request spawned a service'))
    with pytest.raises(ValueError):
        asyncio.run(broker_memory.search(args))


def test_unavailable_database_is_safe_error(tmp_path, monkeypatch):
    obstacle = tmp_path / 'file'
    obstacle.write_text('preserve')
    monkeypatch.setenv('ROMS_DB_PATH', str(obstacle / 'roms.db'))
    with pytest.raises(ProtocolError) as failure:
        asyncio.run(broker_memory.search(ARGS))
    assert failure.value.code == 'SERVICE_UNAVAILABLE'
    assert str(obstacle) not in str(failure.value)
    assert obstacle.read_text() == 'preserve'


def test_service_startup_failure_is_bounded_and_safe(tmp_path, monkeypatch):
    params = broker_memory.parameters()
    params.command = str(tmp_path / 'unavailable-python')
    monkeypatch.setattr(broker_memory, 'parameters', lambda: params)
    with pytest.raises(ProtocolError) as failure:
        asyncio.run(broker_memory.search(ARGS))
    assert failure.value.code == 'SERVICE_UNAVAILABLE'
    assert params.command not in str(failure.value)


@pytest.mark.parametrize('cancel', [False, True])
def test_timeout_and_cancellation_reap_real_child_without_changing_memory(database, tmp_path, monkeypatch, cancel):
    path, _, _ = database
    before = contents(path)
    marker = tmp_path / 'child.json'
    opened = tmp_path / 'opened'
    original = broker_memory.parameters
    def parameters():
        value = original()
        value.args = ['-c', 'import json, os, sqlite3; from pathlib import Path; ' +
            f'Path({str(marker)!r}).write_text(json.dumps({{"pid":os.getpid(),"secret": "ROMS_GATEWAY_API_KEY" in os.environ}})); ' +
            'original = sqlite3.connect; ' +
            f'sqlite3.connect = lambda *a, **kw: (Path({str(opened)!r}).touch(), original(*a, **kw))[1]; ' +
            'from app.memory_service import main; main()']
        return value
    monkeypatch.setattr(broker_memory, 'parameters', parameters)
    monkeypatch.setenv('ROMS_GATEWAY_API_KEY', 'fixture-secret-must-not-reach-memory')
    monkeypatch.setattr(broker_memory, 'TIMEOUT', 5.0)
    with sqlite3.connect(path) as locked:
        locked.execute('BEGIN EXCLUSIVE')
        async def verify():
            task = asyncio.create_task(broker_memory.search(ARGS))
            deadline = time.monotonic() + 4
            while not marker.exists():
                assert time.monotonic() < deadline
                await asyncio.sleep(0.01)
            data = json.loads(marker.read_text())
            assert data['secret'] is False
            pid = data['pid']
            # Wait until the real child opened this locked database.
            while not opened.exists():
                assert time.monotonic() < deadline
                await asyncio.sleep(0.01)
            if cancel:
                started = time.monotonic()
                task.cancel()
                await asyncio.sleep(0.03)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert time.monotonic() - started < 8
            else:
                with pytest.raises(ProtocolError) as failure:
                    await task
                assert failure.value.code == 'REQUEST_TIMEOUT'
            assert not Path(f'/proc/{pid}').exists(), 'MCP subprocess survived lookup cleanup'
        asyncio.run(verify())
        locked.rollback()
    assert contents(path) == before


@pytest.mark.parametrize('cancel', [False, True])
def test_native_broker_search_uses_real_mcp_service(database, tmp_path, cancel):
    path, ids, _ = database
    before = contents(path)
    runtime = tmp_path / 'runtime'
    runtime.mkdir(mode=0o700)
    address = runtime / 'broker.sock'
    binary = os.getenv('OMARCHY_BROKER_BINARY', '/opt/roms-env/bin/omarchy-broker')
    process = subprocess.Popen([binary], cwd=broker_memory.ROOT,
        env=dict(os.environ, OMARCHY_BROKER_SOCKET=str(address)), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 10
        while not address.exists():
            assert process.poll() is None
            assert time.monotonic() < deadline
            time.sleep(0.02)
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(25)
            client.connect(str(address))
            client.sendall(json.dumps({'v': 1, 'id': 'memory-check', 'action': 'memory.search', 'args': ARGS}).encode() + b'\n')
            if cancel:
                deadline = time.monotonic() + 5
                while not (children := psutil.Process(process.pid).children()):
                    assert time.monotonic() < deadline
                    time.sleep(0.01)
                with socket.socket(socket.AF_UNIX) as ping:
                    ping.settimeout(1)
                    ping.connect(str(address))
                    ping.sendall(b'PING\n')
                    assert json.loads(ping.recv(4096))['result'] == 'pong'
                client.close()
                deadline = time.monotonic() + 8
                while any(child.is_running() for child in children):
                    assert time.monotonic() < deadline, 'Disconnected broker lookup left an MCP child'
                    time.sleep(0.02)
                assert contents(path) == before
                return
            raw = bytearray()
            while not raw.endswith(b'\n'):
                part = client.recv(4096)
                assert part and len(raw) + len(part) <= 65536
                raw.extend(part)
        response = json.loads(raw)
        assert response['ok'], response
        assert response['id'] == 'memory-check'
        assert {row['id'] for row in response['result']['memories']} == set(ids[:2])
        assert contents(path) == before
    finally:
        process.terminate()
        process.communicate(timeout=10)
