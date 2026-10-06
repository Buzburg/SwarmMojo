"""Compiled broker scheduling against real controlled HTTP and Unix endpoints."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import socketserver
import subprocess
from threading import Event, Thread
import time

import pytest


def wait_until(condition, timeout=3):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, 'Controlled service did not reach the expected state'
        time.sleep(0.01)


def payload(action, request_id, args):
    return json.dumps({'v': 1, 'id': request_id, 'action': action, 'args': args}).encode() + b'\n'


def response(client):
    raw = bytearray()
    while not raw.endswith(b'\n'):
        part = client.recv(4096)
        assert part and len(raw) + len(part) <= 65536
        raw.extend(part)
    return json.loads(raw)


class ControlledWork:
    def __init__(self):
        self.started = Event()
        self.release = Event()
        self.closed = Event()
        self.calls = []

    def hold(self, client, name):
        self.calls.append(name)
        self.started.set()
        client.settimeout(0.02)
        while not self.release.is_set():
            try:
                if client.recv(1) == b'':
                    self.closed.set()
                    return False
            except TimeoutError:
                continue
        return True


@pytest.fixture
def broker(tmp_path):
    chat, worker = ControlledWork(), ControlledWork()
    class HTTP(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def reply(self, data):
            raw = json.dumps(data).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        def do_GET(self):
            self.reply({'status': 'ready', 'upstream_ready': True, 'model': 'fixture'})
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            prompt = body['messages'][0]['content']
            if prompt == 'oversized':
                self.reply({'choices': [{'message': {'content': 'x' * 65536}}]})
                return
            if prompt != 'quick' and not chat.hold(self.connection, prompt):
                return
            self.reply({'choices': [{'message': {'content': 'ready'}}]})
    class Unix(socketserver.StreamRequestHandler):
        def handle(self):
            request = json.loads(self.rfile.readline(4097))
            action = request['action']
            if action == 'task.validate':
                if not worker.hold(self.connection, request['args']['task_id']):
                    return
                data = {'task': {'state': 'validated'}}
            elif action == 'task.status':
                data = {'task': {'state': 'validating'}}
            else:
                data = {'result': 'pong'}
            self.wfile.write(json.dumps({'v': 1, 'ok': True, **data}).encode() + b'\n')
    http = ThreadingHTTPServer(('127.0.0.1', 0), HTTP)
    endpoint = tmp_path / 'worker.sock'
    unix = socketserver.ThreadingUnixStreamServer(str(endpoint), Unix)
    unix.daemon_threads = True
    endpoint.chmod(0o600)
    threads = [Thread(target=server.serve_forever, daemon=True) for server in (http, unix)]
    for thread in threads:
        thread.start()
    binary = Path(os.getenv('OMARCHY_BROKER_BINARY', str(Path(os.getenv('ROMS_PYTHON_PREFIX', '/opt/roms-env')) / 'bin/omarchy-broker')))
    assert binary.is_file(), 'An explicitly built native broker is required'
    path = tmp_path / 'broker.sock'
    env = dict(os.environ, OMARCHY_BROKER_SOCKET=str(path), ROMS_GATEWAY_PORT=str(http.server_port),
               OMARCHY_TASK_WORKER_SOCKET=str(endpoint), ROMS_DATA_DIR=str(tmp_path))
    process = subprocess.Popen([str(binary)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    @contextmanager
    def connect(frame=None):
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(8)
            client.connect(str(path))
            if frame is not None:
                client.sendall(frame)
            yield client
    def call(frame):
        with connect(frame) as client:
            return response(client)
    try:
        wait_until(lambda: path.exists())
        assert call(payload('ping', 'warm', {}))['result'] == 'pong'
        yield connect, call, chat, worker, tmp_path
        assert process.poll() is None, process.communicate()[1].decode()
    finally:
        process.terminate()
        process.communicate(timeout=5)
        chat.release.set()
        worker.release.set()
        for server in (http, unix):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=3)


def test_incomplete_client_does_not_block_status(broker):
    connect, call, *_ = broker
    with connect(b'{"v":1'):
        start = time.monotonic()
        assert call(payload('status', 'status', {}))['result']['rwkv7'] == 'ready'
        assert time.monotonic() - start < 1


def test_connection_capacity_is_bounded_and_recovers(broker):
    from contextlib import ExitStack
    connect, call, *_ = broker
    with ExitStack() as stack:
        clients = [stack.enter_context(connect()) for _ in range(16)]
        assert call(payload('ping', 'overflow', {}))['error']['code'] == 'QUEUE_FULL'
        clients[0].sendall(payload('ping', 'accepted', {}))
        assert response(clients[0])['result'] == 'pong'
        assert call(payload('ping', 'recovered', {}))['result'] == 'pong'


def test_oversized_gateway_reply_is_bounded_without_killing_broker(broker):
    _, call, *_ = broker
    reply = call(payload('chat', 'oversized-reply', {'prompt': 'oversized'}))
    assert reply['id'] == 'oversized-reply' and reply['error']['code'] == 'RESPONSE_TOO_LARGE'
    assert call(payload('ping', 'still-alive', {}))['result'] == 'pong'


def test_active_chat_keeps_status_responsive_and_disconnect_closes_upstream(broker):
    connect, call, chat, *_ = broker
    with connect(payload('chat', 'slow', {'prompt': 'hold'})):
        assert chat.started.wait(3)
        start = time.monotonic()
        assert call(payload('status', 'status', {}))['result']['rwkv7'] == 'ready'
        assert time.monotonic() - start < 1
    assert chat.closed.wait(3)
    assert call(payload('chat', 'next', {'prompt': 'quick'}))['result'] == 'ready'


def test_write_half_close_can_still_receive_its_response(broker):
    connect, _, chat, *_ = broker
    with connect(payload('chat', 'half-close', {'prompt': 'hold'})) as client:
        assert chat.started.wait(3)
        client.shutdown(socket.SHUT_WR)
        time.sleep(0.1)
        assert not chat.closed.is_set()
        chat.release.set()
        assert response(client)['result'] == 'ready'


def test_chat_queue_limit_and_deadline_never_dispatch_waiters(broker):
    from contextlib import ExitStack
    connect, call, chat, *_ = broker
    with connect(payload('chat', 'active', {'prompt': 'hold'})):
        assert chat.started.wait(3)
        with ExitStack() as stack:
            waiters = [stack.enter_context(connect(payload('chat', str(i), {'prompt': 'queued'}))) for i in range(4)]
            assert call(payload('ping', 'barrier', {}))['result'] == 'pong'
            rejected = call(payload('chat', 'overflow', {'prompt': 'overflow'}))
            assert rejected['id'] == 'overflow' and rejected['error']['code'] == 'QUEUE_FULL'
            for client in waiters:
                assert response(client)['error']['code'] == 'QUEUE_TIMEOUT'
            assert chat.calls == ['hold']
    assert chat.closed.wait(3)
    assert call(payload('chat', 'recovered', {'prompt': 'quick'}))['result'] == 'ready'


def test_detached_validation_keeps_status_live_and_saves_result(broker):
    connect, call, _, worker, root = broker
    frame = payload('task.validate', 'durable', {'task_id': 'a' * 32})
    with connect(frame):
        assert worker.started.wait(3)
        start = time.monotonic()
        assert call(payload('task.status', 'query', {'task_id': 'a' * 32}))['result']['task']['state'] == 'validating'
        assert time.monotonic() - start < 1
    assert not worker.closed.wait(0.15)
    worker.release.set()
    journal = root / 'broker-requests/durable.json'
    wait_until(lambda: json.loads(journal.read_text())['response'] is not None)
    saved = json.loads(json.loads(journal.read_text())['response'])
    assert call(frame) == saved and worker.calls == ['a' * 32]
