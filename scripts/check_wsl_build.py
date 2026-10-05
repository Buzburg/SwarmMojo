"""Real-process cutover checks using a known, non-private knowledge fixture."""
import json
import os
from pathlib import Path
import socket
import stat
import time
import urllib.error
import urllib.request


def request(payload: dict | str) -> dict:
    frame = payload if isinstance(payload, str) else json.dumps(payload)
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(150)
        client.connect('/run/omarchy-broker/broker.sock')
        client.sendall((frame + '\n').encode())
        result = bytearray()
        while not result.endswith(b'\n'):
            chunk = client.recv(4096)
            if not chunk:
                raise RuntimeError('Broker disconnected')
            result.extend(chunk)
        return json.loads(result)


def main() -> None:
    assert os.getuid() == 1000, 'Expected default unprivileged user'
    deadline = time.monotonic() + 120
    while True:
        try:
            status = request('STATUS')
            if status.get('rwkv7') == 'ready' and status.get('roms') == 'ready':
                break
        except OSError:
            pass
        if time.monotonic() >= deadline:
            raise TimeoutError('Services did not recover after WSL restart')
        time.sleep(1)
    assert not status['tool_execution']
    socket_info = Path('/run/omarchy-broker/broker.sock').stat()
    assert socket_info.st_uid == os.getuid()
    assert stat.S_IMODE(socket_info.st_mode) & 0o077 == 0
    try:
        urllib.request.urlopen('http://127.0.0.1:8844/v1/models', timeout=5)
    except urllib.error.HTTPError as error:
        assert error.code == 401
    else:
        raise AssertionError('Gateway accepted an unauthenticated request')
    response = request({'v': 1, 'id': 'cutover-check', 'action': 'chat', 'args': {
        'prompt': 'According to the local Customer Return & Replacement Terms, what ticket status applies to hardware failure replacement requests? Return only the single status word.'}})
    assert response.get('ok'), response
    assert response.get('id') == 'cutover-check'
    assert response['result'].strip().strip('"\'. ').upper() == 'URGENT', response
    print(json.dumps({'status': status, 'grounded_answer': response['result'],
                      'default_user_uid': os.getuid(), 'gateway_auth': 'passed',
                      'socket_permissions': 'passed', 'cold_restart': 'passed'}, indent=2))


if __name__ == '__main__':
    main()
