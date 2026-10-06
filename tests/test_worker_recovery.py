"""Recovery after actual worker death, plus preservation and retry boundaries."""
import asyncio
from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import subprocess
import time

import pytest

from app import patch_tasks as tasks, task_worker, task_worker_client, validation_policy, worker_recovery
from app.container_runner import CONTROL_TIMEOUT, CleanupRequired, cleanup
from test_patch_staging import project, change, live
from test_task_worker import staged


@contextmanager
def running_worker(endpoint):
    pid = os.fork()
    if pid == 0:
        try:
            asyncio.run(task_worker.serve(endpoint))
        finally:
            os._exit(0)
    try:
        deadline = time.monotonic() + 20
        while not endpoint.exists():
            assert time.monotonic() < deadline, 'Recovery worker failed to bind'
            time.sleep(0.02)
        yield pid
    finally:
        try:
            result, _ = os.waitpid(pid, os.WNOHANG)
            if not result:
                os.kill(pid, signal.SIGTERM)
                deadline = time.monotonic() + 20
                while not os.waitpid(pid, os.WNOHANG)[0]:
                    if time.monotonic() >= deadline:
                        os.kill(pid, signal.SIGKILL)
                        os.waitpid(pid, 0)
                        pytest.fail('Worker shutdown did not settle')
                    time.sleep(0.05)
        except ChildProcessError:
            pass  # The test deliberately killed and reaped this process.


def interrupted(project):
    task = staged(project)
    control, task, _ = tasks.load_task(task['id'])
    tasks.transition(control, task, 'validating', evidence=[])
    return control, task


def test_recovery_preserves_stage_and_is_idempotent(project, tmp_path):
    control, task = interrupted(project)
    original = (control / 'stage/module.py').read_bytes()
    first = asyncio.run(worker_recovery.reconcile(tmp_path / 'workers'))
    assert first['tasks_interrupted'] == [task['id']] and not first['blocked']
    assert tasks.load_task(task['id'])[1]['state'] == 'interrupted'
    assert (control / 'stage/module.py').read_bytes() == original
    assert (project[0] / 'module.py').read_text() == 'VALUE = 1\n'
    assert not asyncio.run(worker_recovery.reconcile(tmp_path / 'workers'))['tasks_interrupted']


def test_active_task_lease_is_never_recovered(project, tmp_path):
    control, task = interrupted(project)
    with tasks.task_lock(control):
        result = asyncio.run(worker_recovery.reconcile(tmp_path / 'workers'))
    assert result['busy'] == [task['id']] and not result['blocked']
    assert tasks.load_task(task['id'])[1]['state'] == 'validating'


def test_unknown_and_symlinked_probe_directories_are_preserved(project, tmp_path):
    workers = tmp_path / 'workers'
    workers.mkdir(mode=0o700)
    unknown = workers / ('capability-' + 'a' * 32)
    unknown.mkdir(mode=0o700)
    (unknown / 'user.txt').write_text('preserve')
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'keep').write_text('outside')
    (workers / ('capability-' + 'b' * 32)).symlink_to(outside, target_is_directory=True)
    result = asyncio.run(worker_recovery.reconcile(workers))
    assert result['retained'] == [unknown.name] and len(result['blocked']) == 1
    assert (unknown / 'user.txt').read_text() == 'preserve'
    assert (outside / 'keep').read_text() == 'outside'


def test_cleanup_failure_blocks_new_work_and_remains_retryable(project, tmp_path, monkeypatch):
    control, task = interrupted(project)
    check = control / 'check-0'
    check.mkdir(mode=0o700)
    tasks.durable_json(check / 'container.json', {'task_id': 'f' * 32, 'workspace': str(control / 'stage'), 'state': 'running'})
    async def fail(_):
        raise CleanupRequired('fixture cleanup failure')
    monkeypatch.setattr(worker_recovery, 'cleanup', fail)
    result = asyncio.run(worker_recovery.reconcile(tmp_path / 'workers'))
    assert result['blocked'] and tasks.load_task(task['id'])[1]['state'] == 'cleanup_required'
    worker = task_worker.Worker()
    worker.recovery = result
    response = asyncio.run(worker.dispatch({'v': 1, 'action': 'capabilities', 'args': {}}))
    assert not response['ok'] and response['error'] == 'recovery_required'
    assert (control / 'stage/module.py').exists()
    async def complete(path):
        state = json.loads((path / 'container.json').read_text())
        tasks.durable_json(path / 'container.json', dict(state, state='cleaned'))
    monkeypatch.setattr(worker_recovery, 'cleanup', complete)
    retry = asyncio.run(worker_recovery.reconcile(tmp_path / 'workers'))
    assert not retry['blocked'] and retry['tasks_interrupted'] == [task['id']]


def test_capability_probe_lease_and_owned_cleanup(project, tmp_path):
    workers = tmp_path / 'workers'
    base = workers / ('capability-' + 'c' * 32)
    base.mkdir(parents=True, mode=0o700)
    tasks.durable_json(base / 'owner.json', {'kind': 'capability', 'version': 1, 'id': base.name})
    with tasks.task_lock(base):
        result = asyncio.run(worker_recovery.reconcile(workers))
    assert result['busy'] == [base.name] and base.exists()
    result = asyncio.run(worker_recovery.reconcile(workers))
    assert result['probes_cleaned'] == [base.name] and not base.exists()


def test_recovery_deadline_preserves_unprocessed_work(project, tmp_path, monkeypatch):
    _, task = interrupted(project)
    clock = iter([0, 50])
    monkeypatch.setattr(worker_recovery, 'monotonic', lambda: next(clock))
    report = asyncio.run(worker_recovery.reconcile(tmp_path / 'workers'))
    assert report['blocked'][0]['id'] == 'inventory'
    assert 'deadline' in report['blocked'][0]['reason']
    assert tasks.load_task(task['id'])[1]['state'] == 'validating'


@live
def test_restart_recovers_a_real_container_after_active_worker_is_killed(project, tmp_path, monkeypatch):
    import socket
    workers = tmp_path / 'workers'
    monkeypatch.setattr(task_worker, 'WORKSPACES_DIR', workers)
    text = 'import time, unittest\nclass Wait(unittest.TestCase):\n    def test_wait(self): time.sleep(29)\n'
    task = staged(project, [change(project[0], 'tests/test_value.py', text)], [{'command': 'python.tests'}])
    control = tasks.task_directory(task['id']) / 'check-0'
    journal = control / 'container.json'
    endpoint = tmp_path / 'first.sock'
    try:
        with running_worker(endpoint) as pid, socket.socket(socket.AF_UNIX) as client:
            client.connect(str(endpoint))
            client.sendall(json.dumps({'v': 1, 'action': 'task.validate', 'args': {'task_id': task['id']}}).encode() + b'\n')
            deadline = time.monotonic() + 20
            while not journal.exists() or json.loads(journal.read_text())['state'] != 'running':
                assert time.monotonic() < deadline
                time.sleep(0.02)
            identity = json.loads(journal.read_text())['container_id']
            deadline = time.monotonic() + CONTROL_TIMEOUT
            while True:
                remaining = deadline - time.monotonic()
                assert remaining > 0, 'Container never entered actual execution'
                container_pid = int(subprocess.check_output(['podman', 'inspect', '--format', '{{.State.Pid}}', identity], text=True, timeout=remaining))
                if container_pid > 0:
                    break
                assert time.monotonic() < deadline, 'Container never entered actual execution'
                time.sleep(0.05)
            assert container_pid > 0 and Path(f'/proc/{container_pid}').exists()
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
            assert tasks.load_task(task['id'])[1]['state'] == 'validating'
            assert subprocess.run(['podman', 'container', 'exists', identity], capture_output=True).returncode == 0
        replacement = tmp_path / 'replacement.sock'
        monkeypatch.setenv('OMARCHY_TASK_WORKER_SOCKET', str(replacement))
        with running_worker(replacement):
            record = tasks.load_task(task['id'])[1]
            assert record['state'] == 'interrupted'
            assert subprocess.run(['podman', 'container', 'exists', identity], capture_output=True).returncode == 1
            assert not Path(f'/proc/{container_pid}').exists()
            assert json.loads(journal.read_text())['state'] == 'cleaned'
            assert (tasks.task_directory(task['id']) / 'stage/tests/test_value.py').read_text() == text
            assert (project[0] / 'module.py').read_text() == 'VALUE = 1\n'
            recovery = task_worker_client.request('recovery')['recovery']
            assert recovery['counts']['tasks_interrupted'] == 1 and not recovery['blocked']
            assert task_worker_client.request('capabilities')['capabilities']['available']
            assert task_worker_client.request('recover')['recovery']['counts']['tasks_interrupted'] == 0
    finally:
        if journal.exists():
            asyncio.run(cleanup(control))


@live
def test_restart_cleans_an_interrupted_real_capability_probe(project, tmp_path, monkeypatch):
    import socket
    workers = tmp_path / 'workers'
    monkeypatch.setattr(task_worker, 'WORKSPACES_DIR', workers)
    original = validation_policy.validate
    async def delayed_probe(workspace, control, request):
        if workspace.parent.name.startswith('capability-'):
            (workspace / 'tests').mkdir()
            (workspace / 'tests/test_wait.py').write_text(
                'import time, unittest\nclass Wait(unittest.TestCase):\n    def test_wait(self): time.sleep(29)\n')
            request = {'command': 'python.tests'}
        return await original(workspace, control, request)
    monkeypatch.setattr(validation_policy, 'validate', delayed_probe)
    endpoint = tmp_path / 'probe.sock'
    journal = None
    try:
        with running_worker(endpoint) as pid, socket.socket(socket.AF_UNIX) as client:
            client.connect(str(endpoint))
            client.sendall(b'{"v":1,"action":"capabilities","args":{}}\n')
            deadline = time.monotonic() + 20
            while True:
                matches = list(workers.glob('capability-*/control/container.json'))
                if matches and json.loads(matches[0].read_text())['state'] == 'running':
                    journal = matches[0]
                    break
                assert time.monotonic() < deadline
                time.sleep(0.02)
            identity = json.loads(journal.read_text())['container_id']
            assert subprocess.run(['podman', 'container', 'exists', identity], capture_output=True).returncode == 0
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
        monkeypatch.setattr(validation_policy, 'validate', original)
        replacement = tmp_path / 'replacement.sock'
        monkeypatch.setenv('OMARCHY_TASK_WORKER_SOCKET', str(replacement))
        with running_worker(replacement):
            result = task_worker_client.request('recovery')['recovery']
            assert result['counts']['probes_cleaned'] == 1 and not result['blocked']
            assert not journal.parent.parent.exists()
            assert subprocess.run(['podman', 'container', 'exists', identity], capture_output=True).returncode == 1
            assert task_worker_client.request('capabilities')['capabilities']['available']
    finally:
        if journal is not None and journal.exists():
            asyncio.run(cleanup(journal.parent))
