"""Real rootless worker tests; require an explicitly selected local test image."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import AsyncMock

import pytest

from app import container_runner as runner
from app import worker_tools

IMAGE = os.getenv('ROMS_LIVE_CONTAINER_IMAGE')
live = pytest.mark.skipif(not IMAGE, reason='Set ROMS_LIVE_CONTAINER_IMAGE to a reviewed local image')


def paths(tmp_path):
    workspace, control = tmp_path / 'work', tmp_path / 'control'
    workspace.mkdir()
    control.mkdir(mode=0o700)
    return workspace, control


def assert_absent(control):
    state = json.loads((control / 'container.json').read_text())
    assert state['state'] == 'cleaned', state
    result = subprocess.run(['podman', '--remote=false', '--log-level=error', 'ps', '-aq',
        '--filter', f"label={runner.LABEL}={state['task_id']}"], capture_output=True, text=True, check=True)
    assert not result.stdout.strip()


def worker_pid(control):
    state = json.loads((control / 'container.json').read_text())
    result = subprocess.run(['podman', '--remote=false', '--log-level=error', 'inspect',
                             '--format', '{{.State.Pid}}', state['container_id']],
                            capture_output=True, text=True, check=True)
    pid = int(result.stdout)
    assert pid > 1 and Path(f'/proc/{pid}').exists()
    return pid


@live
def test_real_worker_exit_status_and_cleanup(tmp_path):
    workspace, control = paths(tmp_path)
    result = asyncio.run(runner.execute(workspace, control, IMAGE,
        ['sh', '-c', 'printf "worker output"; echo preserved > /workspace/result; exit 7'], memory='64m'))
    assert result.returncode == 7, result
    assert 'worker output' in result.output
    assert (workspace / 'result').read_text().strip() == 'preserved'
    assert_absent(control)


@live
def test_timeout_stops_real_container_before_cleanup(tmp_path):
    workspace, control = paths(tmp_path)
    async def scenario():
        task = asyncio.create_task(runner.execute(workspace, control, IMAGE,
            ['sh', '-c', 'echo started > /workspace/started; exec sleep 60'], timeout=3, memory='64m'))
        async with asyncio.timeout(15):
            while not (workspace / 'started').exists():
                if task.done():
                    await task
                await asyncio.sleep(.05)
        pid = worker_pid(control)
        with pytest.raises(TimeoutError):
            await task
        assert not Path(f'/proc/{pid}').exists(), 'Worker host process survived container cleanup'
    asyncio.run(scenario())
    assert_absent(control)


@live
def test_repeated_cancel_stops_real_container(tmp_path):
    workspace, control = paths(tmp_path)
    async def scenario():
        task = asyncio.create_task(runner.execute(workspace, control, IMAGE,
            ['sh', '-c', 'echo started > /workspace/started; exec sleep 60'], memory='64m'))
        try:
            async with asyncio.timeout(15):
                while not (workspace / 'started').exists():
                    if task.done():
                        await task
                    await asyncio.sleep(.05)
            task.cancel()
            await asyncio.sleep(.02)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    asyncio.run(scenario())
    assert_absent(control)


@live
def test_cleanup_failure_retains_workspace_and_can_retry(tmp_path, monkeypatch):
    monkeypatch.setenv('ROMS_ENABLE_EXPERIMENTAL_EXECUTION', '1')
    monkeypatch.setattr(worker_tools, 'WORKSPACES_DIR', tmp_path)
    monkeypatch.setattr(worker_tools, 'TOOL_EXECUTION_TIMEOUT', 1)
    original = runner.run_process
    async def fail_remove(command, *args, **kwargs):
        if 'rm' in command:
            return runner.ProcessResult(125, 'injected cleanup failure')
        return await original(command, *args, **kwargs)
    monkeypatch.setattr(runner, 'run_process', fail_remove)
    try:
        result = asyncio.run(worker_tools.run_sandboxed_command.__wrapped__(IMAGE, 'sleep 60', memory='64m'))
        assert 'retained journal' in result, result
        controls = list(tmp_path.glob('task_*'))
        assert len(controls) == 1 and (controls[0] / 'work').is_dir()
        state = json.loads((controls[0] / 'container.json').read_text())
        assert state['state'] == 'cleanup_required'
        pid = worker_pid(controls[0])
    finally:
        monkeypatch.setattr(runner, 'run_process', original)
        for control in tmp_path.glob('task_*'):
            if (control / 'container.json').exists():
                asyncio.run(runner.cleanup(control))
    assert_absent(controls[0])
    assert not Path(f'/proc/{pid}').exists()


@pytest.mark.skipif(os.name != 'posix', reason='Linux process group lifecycle')
def test_output_limit_reaps_local_child(tmp_path):
    pid_path = tmp_path / 'pid'
    program = f'import os; open({str(pid_path)!r}, "w").write(str(os.getpid())); print("x" * 100000); import time; time.sleep(60)'
    with pytest.raises(runner.OutputLimitExceeded):
        asyncio.run(runner.run_process([sys.executable, '-c', program], 5, limit=1024))
    pid = int(pid_path.read_text())
    assert not Path(f'/proc/{pid}').exists()


def test_worker_network_override_rejected(monkeypatch):
    monkeypatch.setenv('ROMS_ENABLE_EXPERIMENTAL_EXECUTION', '1')
    with pytest.raises(ValueError, match='networking'):
        asyncio.run(worker_tools.run_sandboxed_command.__wrapped__('unused', 'unused', network='host'))


@live
def test_container_isolation_is_independent_of_landlock(tmp_path, monkeypatch):
    workspace, control = paths(tmp_path)
    secret = tmp_path / 'host-secret'
    secret.write_text('must stay on host')
    (workspace / 'escape').symlink_to(secret)
    monkeypatch.setenv('ROMS_TEST_HOST_SECRET', 'must-not-reach-container')
    command = r'''
set -eu
test -z "${ROMS_TEST_HOST_SECRET:-}"
test ! -e /run/podman/podman.sock
test ! -e /var/run/docker.sock
test ! -e /workspace/escape
if touch /etc/roms-write-probe 2>/dev/null; then exit 91; fi
test "$(cat /sys/fs/cgroup/memory.max)" = 67108864
test "$(cat /sys/fs/cgroup/pids.max)" = 128
test "$(cat /sys/fs/cgroup/cpu.max)" = '200000 100000'
grep -q '^CapEff:[[:space:]]*0000000000000000$' /proc/self/status
grep -q '^NoNewPrivs:[[:space:]]*1$' /proc/self/status
test "$(ls /sys/class/net)" = lo
echo bounded > /workspace/allowed
echo isolation-passed
'''
    result = asyncio.run(runner.execute(workspace, control, IMAGE, ['sh', '-c', command], memory='64m'))
    assert result.returncode == 0 and 'isolation-passed' in result.output, result
    assert secret.read_text() == 'must stay on host'
    assert (workspace / 'allowed').read_text().strip() == 'bounded'
    assert_absent(control)


@live
def test_real_tools_single_and_two_slot_lifecycles(tmp_path, monkeypatch):
    monkeypatch.setenv('ROMS_ENABLE_EXPERIMENTAL_EXECUTION', '1')
    monkeypatch.setattr(worker_tools, 'WORKSPACES_DIR', tmp_path)
    monkeypatch.setattr(worker_tools.tool_limiter, 'wait_for_headroom', AsyncMock())
    async def scenario():
        for slots in (1, 2):
            monkeypatch.setattr(worker_tools.tool_limiter, 'semaphore', asyncio.Semaphore(slots))
            results = await asyncio.wait_for(asyncio.gather(*[
                worker_tools.run_sandboxed_command(IMAGE, 'sh -c "sleep 0.2; echo finished"', memory='64m')
                for _ in range(slots)]), 20)
            assert all('Exit Code 0' in result and 'finished' in result for result in results), results
            assert not list(tmp_path.iterdir())
            assert worker_tools.tool_limiter.semaphore._value == slots
    asyncio.run(scenario())


@live
def test_worktree_timeout_preserves_user_changes_and_never_runs_filters(tmp_path, monkeypatch):
    base = tmp_path / 'repos'
    source = base / 'example'
    source.mkdir(parents=True)
    def git(*args):
        return subprocess.run(['git', '-C', str(source), *args], check=True, capture_output=True, text=True)
    git('init', '-q')
    (source / 'file.txt').write_text('original\n')
    (source / '.gitattributes').write_text('file.txt filter=fixture\n')
    git('add', '.')
    git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')
    marker = tmp_path / 'host-filter-ran'
    git('config', 'filter.fixture.smudge', f'touch {marker}; cat')
    git('config', 'filter.fixture.required', 'true')
    (source / 'file.txt').write_text('uncommitted user changes\n')
    workspaces = tmp_path / 'tasks'
    monkeypatch.setenv('ROMS_ENABLE_EXPERIMENTAL_EXECUTION', '1')
    monkeypatch.setattr(worker_tools, 'WORKSPACES_DIR', workspaces)
    monkeypatch.setattr(worker_tools, 'BASE_REPOS_DIR', base)
    result = asyncio.run(worker_tools.execute_tool_task_async.__wrapped__(
        'example', IMAGE, 'sh -c "echo changed > file.txt; exec sleep 60"', memory='64m', timeout=2))
    assert 'exceeded' in result, result
    assert (source / 'file.txt').read_text() == 'uncommitted user changes\n'
    assert not marker.exists()
    assert len([line for line in git('worktree', 'list', '--porcelain').stdout.splitlines()
                if line.startswith('worktree ')]) == 1
    assert not list(workspaces.iterdir())
