"""Real private service routing, confinement gating and disconnect recovery."""
import asyncio
import ctypes
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time

import pytest

from app import patch_tasks, task_worker, task_worker_client, validation_policy
from test_patch_staging import project, change, live


@pytest.fixture
def worker(project, tmp_path, monkeypatch, request):
    directory = tmp_path / 'endpoint'
    directory.mkdir(mode=0o700)
    endpoint = directory / 'worker.sock'
    monkeypatch.setenv('OMARCHY_TASK_WORKER_SOCKET', str(endpoint))
    monkeypatch.setattr(task_worker, 'WORKSPACES_DIR', tmp_path / 'workers')
    if getattr(request, 'param', None) == 'missing_image':
        monkeypatch.setattr(validation_policy, 'IMAGE_CONFIG', tmp_path / 'missing-image.json')
    pid = os.fork()
    if pid == 0:
        try:
            asyncio.run(task_worker.serve(endpoint))
        finally:
            os._exit(0)
    try:
        deadline = time.monotonic() + 5
        while not endpoint.exists():
            assert time.monotonic() < deadline, 'Worker failed to bind'
            time.sleep(0.02)
        yield endpoint
    finally:
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 20
        while True:
            result, status = os.waitpid(pid, os.WNOHANG)
            if result:
                assert os.waitstatus_to_exitcode(status) == 0
                break
            if time.monotonic() >= deadline:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
                pytest.fail('Worker failed to stop and settle cleanup')
            time.sleep(0.05)
        assert not endpoint.exists()


def raw_request(endpoint, frame):
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(50)
        client.connect(str(endpoint))
        client.sendall(frame)
        data = b''
        while not data.endswith(b'\n'):
            part = client.recv(4096)
            if not part:
                break
            data += part
        return json.loads(data)


def staged(project, changes=None, checks=None):
    source, project_id, base = project
    return asyncio.run(patch_tasks.propose(project_id, base, changes or [change(source, 'module.py', 'VALUE = 2\n')],
        checks or [{'command': 'python.syntax', 'files': ['module.py']}]))


@pytest.mark.parametrize('frame', [b'{"v":1,"v":1,"action":"ping","args":{}}\n',
    b'{"v":true,"action":"ping","args":{}}\n', b'{"v":1,"action":"apply","args":{}}\n',
    b'{"v":1,"action":"capabilities","args":{"image":"untrusted"}}\n',
    b'{"v":1,"action":"execute","args":{"command":"echo bad"}}\n',
    b'\xff\n', b'{' + b'x' * 5000 + b'\n'])
def test_malformed_or_unauthorized_requests_are_rejected(worker, frame):
    result = raw_request(worker, frame)
    assert result == {'ok': False, 'v': 1, 'error': 'invalid_request'}


def test_private_endpoint_and_status_lookup(worker, project):
    assert worker.stat().st_mode & 0o777 == 0o600
    assert task_worker_client.request('ping')['result'] == 'pong'
    task = staged(project)
    result = task_worker_client.request('task.status', {'task_id': task['id']})
    assert result['ok'] and result['task']['state'] == 'staged'
    assert 'preimages' not in result['task']


def test_existing_endpoint_is_never_replaced(tmp_path):
    target = tmp_path / 'worker.sock'
    target.write_text('preserve')
    with pytest.raises(FileExistsError):
        asyncio.run(task_worker.serve(target))
    assert target.read_text() == 'preserve'


@live
def test_real_validation_through_native_broker_keeps_no_new_privileges(worker, project, tmp_path):
    task = staged(project)
    broker_socket = tmp_path / 'broker.sock'
    binary = Path(os.getenv('ROMS_PYTHON_PREFIX', '/opt/roms-env')) / 'bin/omarchy-broker'
    def restrict_broker():
        libc = ctypes.CDLL(None)
        if libc.prctl(38, 1, 0, 0, 0):
            os._exit(88)
    process = subprocess.Popen([str(binary)], env=dict(os.environ, OMARCHY_BROKER_SOCKET=str(broker_socket)),
                               preexec_fn=restrict_broker, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 5
        while not broker_socket.exists():
            assert process.poll() is None and time.monotonic() < deadline
            time.sleep(0.02)
        assert 'NoNewPrivs:\t1' in Path(f'/proc/{process.pid}/status').read_text()
        request = {'v': 1, 'id': 'fixture', 'action': 'task.validate', 'args': {'task_id': task['id']}}
        result = raw_request(broker_socket, json.dumps(request).encode() + b'\n')
        assert result['ok'], result
        assert result['id'] == 'fixture' and result['task']['state'] == 'validated'
        assert result['capabilities']['available'] and not result['capabilities']['apply']
        assert (project[0] / 'module.py').read_text() == 'VALUE = 1\n'
    finally:
        process.terminate()
        process.communicate(timeout=10)


def test_unavailable_isolation_prevents_task_transition(project, tmp_path, monkeypatch):
    task = staged(project)
    monkeypatch.setattr(task_worker, 'WORKSPACES_DIR', tmp_path / 'workers')
    monkeypatch.setattr(validation_policy, 'IMAGE_CONFIG', tmp_path / 'missing-image.json')
    with pytest.raises(FileNotFoundError):
        asyncio.run(task_worker.Worker().dispatch({'v': 1, 'action': 'task.validate', 'args': {'task_id': task['id']}}))
    assert patch_tasks.load_task(task['id'])[1]['state'] == 'staged'
    assert list((tmp_path / 'workers').iterdir()) == []


@pytest.mark.parametrize('worker', ['missing_image'], indirect=True)
def test_broker_route_fails_closed_when_worker_cannot_enforce_policy(worker, project):
    from app.broker_actions import handle
    task = staged(project)
    payload = {'v': 1, 'action': 'task.validate', 'args': {'task_id': task['id']}}
    response = json.loads(handle(bytearray(json.dumps(payload).encode())))
    assert not response['ok'] and response['error'] == 'worker_unavailable'
    assert patch_tasks.load_task(task['id'])[1]['state'] == 'staged'
    assert (project[0] / 'module.py').read_text() == 'VALUE = 1\n'


@live
def test_failed_check_reports_validation_failure_with_retained_evidence(worker, project):
    task = staged(project, [change(project[0], 'module.py', 'def broken(:\n')])
    response = task_worker_client.request('task.validate', {'task_id': task['id']})
    assert not response['ok'] and response['error'] == 'validation_failed'
    assert response['task']['state'] == 'failed'
    record = patch_tasks.load_task(task['id'])[1]
    assert record['evidence'][0]['exit_code'] != 0
    assert 'SyntaxError' in record['evidence'][0]['output']
    assert (project[0] / 'module.py').read_text() == 'VALUE = 1\n'


@live
def test_disconnect_cancels_real_worker_and_releases_slot(worker, project):
    source = project[0]
    text = 'import time, unittest\nclass Sleep(unittest.TestCase):\n    def test_wait(self): time.sleep(25)\n'
    task = staged(project, [change(source, 'tests/test_value.py', text)], [{'command': 'python.tests'}])
    journal = patch_tasks.task_directory(task['id']) / 'check-0/container.json'
    with socket.socket(socket.AF_UNIX) as client:
        client.connect(str(worker))
        client.sendall(json.dumps({'v': 1, 'action': 'task.validate', 'args': {'task_id': task['id']}}).encode() + b'\n')
        deadline = time.monotonic() + 20
        while not journal.exists() or json.loads(journal.read_text())['state'] != 'running':
            assert time.monotonic() < deadline, 'Validation did not start'
            time.sleep(0.05)
        busy = task_worker_client.request('capabilities')
        assert busy['error'] == 'worker_busy'
    deadline = time.monotonic() + 15
    while patch_tasks.load_task(task['id'])[1]['state'] != 'cancelled':
        assert time.monotonic() < deadline, 'Disconnected validation was not cancelled'
        time.sleep(0.05)
    assert json.loads(journal.read_text())['state'] == 'cleaned'
    identity = json.loads(journal.read_text())['container_id']
    check = subprocess.run(['podman', 'container', 'exists', identity], capture_output=True)
    assert check.returncode == 1
    assert task_worker_client.request('capabilities')['capabilities']['available']
