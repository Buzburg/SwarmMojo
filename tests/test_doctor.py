import json
import sys

import pytest

from app import doctor
from scripts import goose


def status():
    return {
        'ok': True, 'rwkv7': 'ready', 'roms': 'ready',
        'features': {
            'chat': {'state': 'ready'},
            'validation_worker': {'state': 'reachable'},
            'project_workshop': {'state': 'available'},
            'native_project_chat': {'state': 'idle'},
            'knowledge_library': {'state': 'not_probed'},
            'project_memory': {'state': 'not_probed'},
            'arbitrary_execution': {'state': 'disabled'},
        },
    }


class Socket:
    def __init__(self, payload=b'', error=None):
        self.payload = payload
        self.error = error
        self.sent = []
        self.closed = False
        self.timeouts = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def settimeout(self, value):
        self.timeouts.append(value)

    def connect(self, path):
        assert path == doctor.SOCKET_PATH
        if self.error:
            raise self.error

    def sendall(self, payload):
        self.sent.append(payload)

    def recv(self, size):
        result, self.payload = self.payload[:size], self.payload[size:]
        return result


def use_socket(monkeypatch, payload=b'', error=None):
    client = Socket(payload, error)
    monkeypatch.setattr(doctor, 'PLATFORM', 'linux')
    monkeypatch.setattr(doctor.socket, 'AF_UNIX', 1, raising=False)
    monkeypatch.setattr(doctor.socket, 'socket', lambda *_: client)
    return client


@pytest.mark.parametrize('platform, unix_family_present', [
    ('win32', False), ('win32', True), ('darwin', True), ('linux', False),
], ids=['windows-no-unix', 'windows-with-unix', 'macos', 'linux-no-unix'])
def test_unsupported_transport_is_reported_without_opening_socket(
        monkeypatch, capsys, platform, unix_family_present):
    monkeypatch.setattr(doctor, 'PLATFORM', platform)
    if unix_family_present:
        monkeypatch.setattr(doctor.socket, 'AF_UNIX', 1, raising=False)
    else:
        monkeypatch.delattr(doctor.socket, 'AF_UNIX', raising=False)
    def forbidden(*args, **kwargs):
        pytest.fail('Unsupported transport must not open a socket')
    monkeypatch.setattr(doctor.socket, 'socket', forbidden)
    assert doctor.run() == 1
    output = capsys.readouterr().out
    assert 'cannot access the Linux broker socket' in output
    assert 'On Windows, open Omarchy in WSL first' in output
    assert 'No connection or service change was attempted' in output


def test_ready_report_is_scoped_and_only_requests_status(monkeypatch, capsys):
    client = use_socket(monkeypatch, json.dumps(status()).encode() + b'\n')
    assert doctor.run() == 0
    output = capsys.readouterr().out
    assert 'chat ready; workshop prerequisites available' in output
    assert 'sandbox enforcement was not tested' in output
    assert 'no loaded model session verified' in output
    assert 'Library indexing: not tested' in output
    assert 'not a release certification' in output
    assert client.sent == [b'STATUS\n'] and client.closed
    assert all(0 < value <= doctor.TIMEOUT for value in client.timeouts)


@pytest.mark.parametrize('error, message', [
    (FileNotFoundError('SECRET'), 'broker is unavailable'),
    (ConnectionRefusedError('SECRET'), 'broker is unavailable'),
    (PermissionError('SECRET'), 'broker access denied'),
    (TimeoutError('SECRET'), 'broker status timed out'),
    (OSError('SECRET'), 'broker status could not be read'),
], ids=['missing', 'refused', 'denied', 'timeout', 'os-error'])
def test_unavailable_broker_gives_safe_advice(monkeypatch, capsys, error, message):
    client = use_socket(monkeypatch, error=error)
    assert doctor.run() == 1
    output = capsys.readouterr().out
    assert message in output and 'SECRET' not in output
    assert client.sent == [] and client.closed


@pytest.mark.parametrize('payload', [
    b'', b'{"ok":true}', b'SECRET\n', b'[]\n', b'{}\n',
    b'{"ok":false,"error":"SECRET","features":{}}\n',
    b'{"ok":true,"features":[]}\n',
    b'{"ok":true,"ok":true,"features":{}}\n',
    b'{"ok":true,"features":{},"value":NaN}\n',
    b'{"ok":true,"features":{}}\nSECRET\n',
    b'\xff\n', b'[' * 1500 + b']' * 1500 + b'\n', b'x' * (doctor.MAX_FRAME + 1),
], ids=['empty', 'truncated', 'non-json', 'array', 'missing-fields', 'error-response',
        'invalid-features', 'duplicate-key', 'non-finite', 'multiple-frames', 'invalid-utf8',
        'deep-json', 'oversized'])
def test_bad_responses_fail_without_echoing_contents(monkeypatch, capsys, payload):
    client = use_socket(monkeypatch, payload)
    assert doctor.run() == 1
    output = capsys.readouterr().out
    assert 'invalid or incomplete status' in output and 'SECRET' not in output
    assert client.sent == [b'STATUS\n'] and client.closed


def test_deadline_is_total_not_reset_per_receive(monkeypatch, capsys):
    client = use_socket(monkeypatch, b'partial')
    ticks = iter([0.0, 0.1, doctor.TIMEOUT + 1])
    monkeypatch.setattr(doctor.time, 'monotonic', lambda: next(ticks))
    assert doctor.run() == 1
    assert 'timed out' in capsys.readouterr().out
    assert client.closed


def test_degraded_report_does_not_upgrade_reachability_or_contradictory_chat():
    payload = status()
    payload['rwkv7'] = 'not_connected'
    payload['roms'] = 'degraded'
    report, code = doctor.explain(payload)
    assert code == 1
    assert 'Local model: not connected' in report
    assert 'Knowledge service: degraded' in report
    assert 'Chat: not ready' in report
    assert 'Project workshop: unavailable' in report
    assert 'allow up to 90 seconds' in report
    assert 'sandbox enforcement was not tested' in report


def test_unknown_or_missing_states_and_arbitrary_fields_are_not_echoed():
    payload = {'ok': True, 'features': {'chat': {'state': 'SECRET\x1b[2J', 'reason': 'SECRET'},
                                      'validation_worker': []},
               'roms': {'secret': 'SECRET'}, 'model': 'SECRET', 'error': 'SECRET'}
    report, code = doctor.explain(payload)
    assert code == 1 and 'SECRET' not in report and '\x1b' not in report
    assert 'Local model: not reported or unrecognized' in report
    assert 'Validation worker: not reported or unrecognized' in report


def test_native_cleanup_blocks_healthy_overall_result():
    payload = status()
    payload['features']['native_project_chat']['state'] = 'cleanup_required'
    report, code = doctor.explain(payload)
    assert code == 1 and 'new native requests are blocked' in report
    assert 'Stop submitting native requests' in report


def test_goose_doctor_works_without_chat_credentials_or_starting_helpers(monkeypatch, capsys):
    monkeypatch.delenv('ROMS_GATEWAY_API_KEY', raising=False)
    monkeypatch.setattr(sys, 'argv', ['goose', '--doctor'])
    client = use_socket(monkeypatch, json.dumps(status()).encode() + b'\n')
    def forbidden(*args, **kwargs):
        pytest.fail('Doctor must not start a helper or call model HTTP endpoints')
    monkeypatch.setattr(goose.subprocess, 'run', forbidden)
    monkeypatch.setattr(goose.urllib.request, 'urlopen', forbidden)
    with pytest.raises(SystemExit) as result:
        goose.main()
    assert result.value.code == 0
    assert client.sent == [b'STATUS\n']
    assert 'read-only readiness' in capsys.readouterr().out


@pytest.mark.parametrize('arguments', [
    ['--status'], ['a question'], ['--library'], ['--project-workshop'], ['--preview'],
], ids=['status', 'chat', 'library', 'workshop', 'preview'])
def test_doctor_cannot_be_combined_with_another_operation(monkeypatch, arguments):
    monkeypatch.setattr(sys, 'argv', ['goose', '--doctor', *arguments])
    with pytest.raises(SystemExit) as result:
        goose.main()
    assert result.value.code == 2


def test_status_remains_json(monkeypatch, capsys):
    payload = status()
    monkeypatch.setattr(sys, 'argv', ['goose', '--status'])
    client = use_socket(monkeypatch, json.dumps(payload).encode() + b'\n')
    goose.main()
    assert json.loads(capsys.readouterr().out) == payload
    assert client.sent == [b'STATUS\n']
