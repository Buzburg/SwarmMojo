"""Verify the installed worker/broker boundary without modifying any project."""
import json
import argparse
import os
from pathlib import Path
import socket
import subprocess
import time

from app.task_worker_client import request


def wait_for_worker() -> None:
    deadline = time.monotonic() + 15
    while True:
        try:
            assert request('ping', timeout=1)['ok']
            return
        except (FileNotFoundError, ConnectionError, TimeoutError):
            if time.monotonic() >= deadline:
                raise TimeoutError('Worker did not become ready within 15 seconds') from None
            time.sleep(0.1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lifecycle', action='store_true', help='Also exercise graceful restart and idle crash recovery')
    args = parser.parse_args()
    environment = dict(os.environ, XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}',
                       DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{os.getuid()}/bus')
    manager = ['systemctl', '--user']
    def worker_pid() -> str:
        return subprocess.check_output([*manager, 'show', 'omarchy-task-worker', '-p', 'MainPID', '--value'],
                                       text=True, env=environment).strip()
    wait_for_worker()
    if args.lifecycle:
        assert request('capabilities', timeout=45)['ok'], 'Do not restart an unavailable or busy worker'
        subprocess.run([*manager, 'restart', 'omarchy-task-worker'], env=environment, check=True)
        wait_for_worker()
        previous = worker_pid()
        subprocess.run([*manager, 'kill', '--kill-whom=main', '--signal=SIGKILL', 'omarchy-task-worker'],
                       env=environment, check=True)
        deadline = time.monotonic() + 15
        while True:
            try:
                current = worker_pid()
                if current not in {'0', previous} and request('ping', timeout=1)['ok']:
                    break
            except OSError:
                pass
            assert time.monotonic() < deadline, 'Worker did not recover after its idle process was killed'
            time.sleep(0.1)
    capabilities = request('capabilities', timeout=45)
    assert capabilities['ok'] and capabilities['capabilities']['available'], capabilities
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(45)
        client.connect('/run/omarchy-broker/broker.sock')
        client.sendall(b'{"v":1,"id":"service-check","action":"worker_status","args":{}}\n')
        raw = b''
        while not raw.endswith(b'\n'):
            part = client.recv(4096)
            assert part and len(raw) + len(part) <= 65536
            raw += part
    routed = json.loads(raw)
    assert routed['ok'] and routed['id'] == 'service-check' and routed['result']['capabilities']['available'], routed
    protected = {}
    for unit in ('omarchy-broker', 'goose-roms'):
        pid = subprocess.check_output(['systemctl', 'show', unit, '-p', 'MainPID', '--value'], text=True).strip()
        protected[unit] = 'NoNewPrivs:\t1' in Path(f'/proc/{int(pid)}/status').read_text()
        assert protected[unit], unit
    pid = worker_pid()
    keys = {item.split(b'=', 1)[0].decode() for item in Path(f'/proc/{int(pid)}/environ').read_bytes().split(b'\0') if item}
    allowed = {'HOME', 'USER', 'LOGNAME', 'PATH', 'LANG', 'XDG_RUNTIME_DIR', 'DBUS_SESSION_BUS_ADDRESS',
               'ROMS_PYTHON_PREFIX', 'ROMS_DATA_DIR', 'ROMS_WORKSPACES_DIR', 'PYTHONUNBUFFERED',
               'PYTHONHOME', 'PYTHONPATH', 'MOJO_PYTHON_LIBRARY', 'MODULAR_HOME', 'LD_LIBRARY_PATH'}
    assert keys <= allowed, 'Worker inherited an unexpected environment field'
    print(json.dumps({'worker_available': True, 'broker_route_verified': True,
                      'service_restrictions_retained': protected, 'worker_environment_allowlist_verified': True,
                      'policy': routed['result']['capabilities']['policy_version'], 'lifecycle_checked': args.lifecycle}, indent=2))


if __name__ == '__main__':
    main()
