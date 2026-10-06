import asyncio
import json
import sys
from types import SimpleNamespace

import httpx
import pytest

from scripts import os_workshop as workshop
from scripts import goose


APPS = [{'id': 'viewer.desktop', 'name': 'Hardware viewer', 'file_sha256': 'a' * 64}]


def planner(monkeypatch, payload):
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, content=payload)
    client = httpx.AsyncClient
    monkeypatch.setenv('ROMS_GATEWAY_API_KEY', 'fixture-secret')
    monkeypatch.setattr(workshop.httpx, 'AsyncClient', lambda **kwargs:
                        client(transport=httpx.MockTransport(respond), **kwargs))
    return requests


def test_local_plan_only_sends_catalog_labels_not_hashes_or_executable_paths(monkeypatch):
    requests = planner(monkeypatch, b'{"plan":{"action":"launch_app","app_id":"viewer.desktop"}}')
    result = asyncio.run(workshop.request_plan('Open the hardware viewer', APPS))
    assert result == {'action': 'launch_app', 'app_id': 'viewer.desktop'}
    assert requests[0].url.host == '127.0.0.1'
    assert requests[0].headers['authorization'] == 'Bearer fixture-secret'
    assert json.loads(requests[0].content) == {'instruction': 'Open the hardware viewer',
                                             'apps': [{'id': 'viewer.desktop', 'name': 'Hardware viewer'}]}


@pytest.mark.parametrize('payload', [
    b'{"plan":{"action":"launch_app","app_id":"unknown.desktop"}}',
    b'{"plan":{"action":"shell","app_id":null}}',
    b'{"plan":{"action":"inspect_services","app_id":"viewer.desktop"}}',
    b'{"plan":{"action":"launch_app","app_id":null}}',
    b'{"plan":{"action":"none","app_id":null,"command":"rm"}}',
    b'{"plan":{"action":"none","action":"inspect_services","app_id":null}}',
    b'{"plan":[]}', b'[]', b'x' * 16385,
], ids=['unknown-app', 'unknown-action', 'extra-target', 'missing-target', 'extra-key',
        'duplicate-key', 'array-plan', 'array-response', 'oversized'])
def test_invalid_remote_plan_never_reaches_execution(monkeypatch, payload):
    planner(monkeypatch, payload)
    with pytest.raises(ValueError):
        asyncio.run(workshop.request_plan('Open an app', APPS))


def test_launch_proposal_needs_exact_confirmation_and_uses_original_hash(monkeypatch):
    calls = []
    async def launch(app_id, digest):
        calls.append((app_id, digest))
        return {'status': 'request_accepted', 'window_verified': False}
    monkeypatch.setattr(workshop.os_operator, 'launch', launch)
    plan = {'action': 'launch_app', 'app_id': 'viewer.desktop'}
    monkeypatch.setattr('builtins.input', lambda _: '')
    asyncio.run(workshop.review_plan(plan, APPS))
    assert calls == []
    monkeypatch.setattr('builtins.input', lambda _: 'OPEN viewer.desktop')
    asyncio.run(workshop.review_plan(plan, APPS))
    assert calls == [('viewer.desktop', 'a' * 64)]


def test_read_only_plan_checks_all_registered_services_without_launch(monkeypatch):
    calls = []
    async def inspect(name):
        calls.append(name)
        return {'service': name, 'active_state': 'active'}
    monkeypatch.setattr(workshop.os_operator, 'service_status', inspect)
    monkeypatch.setattr(workshop.os_operator, 'launch', lambda *_: pytest.fail('Read-only plan launched an app'))
    asyncio.run(workshop.review_plan({'action': 'inspect_services', 'app_id': None}, []))
    assert calls == ['goose-model', 'goose-roms', 'omarchy-broker', 'omarchy-task-worker']


def test_interactive_controls_reject_piped_model_output(monkeypatch):
    monkeypatch.setattr(workshop.sys, 'stdin', SimpleNamespace(isatty=lambda: False))
    with pytest.raises(ValueError, match='interactive terminal'):
        asyncio.run(workshop.workshop())


def test_display_escapes_terminal_controls(capsys):
    workshop.display({'name': '\x1b[2Jfake ready'})
    assert '\x1b' not in capsys.readouterr().out


def test_goose_routes_system_mode_to_explicit_workshop(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, 'argv', ['goose', '--system'])
    monkeypatch.setattr(goose.subprocess, 'run', lambda command, **kwargs:
                        calls.append(command) or SimpleNamespace(returncode=0))
    with pytest.raises(SystemExit) as stopped:
        goose.main()
    assert stopped.value.code == 0 and calls[0][-2:] == ['-m', 'scripts.os_workshop']


@pytest.mark.parametrize('options', [['--system', '--doctor'], ['--system', 'hello'],
                                    ['--system', '--preview'], ['--system', '--status']])
def test_system_management_mode_rejects_ambiguous_commands(monkeypatch, options):
    monkeypatch.setattr(sys, 'argv', ['goose', *options])
    monkeypatch.setattr(goose.subprocess, 'run', lambda *_args, **_kwargs: pytest.fail('Ambiguous command executed'))
    with pytest.raises(SystemExit) as stopped:
        goose.main()
    assert stopped.value.code == 2
