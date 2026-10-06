import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import verify_all


def test_empty_artifact_directory_cannot_pass_offline_profile(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('ROMS_PYTHON_PREFIX', str(tmp_path))
    monkeypatch.delenv('OMARCHY_BROKER_BINARY', raising=False)
    monkeypatch.setattr(sys, 'argv', ['verify_all.py', '--offline'])
    commands = []
    def passed_regressions(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, 'Fixture regression pass', '')
    monkeypatch.setattr(verify_all.subprocess, 'run', passed_regressions)
    with pytest.raises(SystemExit) as error:
        verify_all.main()
    assert error.value.code == 1
    assert len(commands) == 1 and 'pytest' in commands[0]
    output = capsys.readouterr().out
    assert 'INCOMPLETE: Compiled native broker' in output
    assert '1/2 required checks passed' in output


def test_readiness_waits_for_both_services(monkeypatch):
    statuses = iter([{'rwkv7': 'ready', 'roms': 'degraded'}, {'rwkv7': 'ready', 'roms': 'ready'}])
    monkeypatch.setattr(verify_all.subprocess, 'run', lambda *a, **k:
                        subprocess.CompletedProcess(a[0], 0, json.dumps(next(statuses)), ''))
    monkeypatch.setattr(verify_all.time, 'sleep', lambda _: None)
    result = verify_all.wait_for_services(['goose', '--status'], Path('.'), {})
    assert json.loads(result.stdout)['roms'] == 'ready'


def test_readiness_deadline_fails_instead_of_certifying_degraded_service(monkeypatch):
    clock = iter([0, 0, 1, 2])
    monkeypatch.setattr(verify_all.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(verify_all.time, 'sleep', lambda _: None)
    monkeypatch.setattr(verify_all.subprocess, 'run', lambda *a, **k:
                        subprocess.CompletedProcess(a[0], 0, '{"rwkv7":"not_connected","roms":"degraded"}', ''))
    with pytest.raises(TimeoutError, match='startup deadline'):
        verify_all.wait_for_services(['goose', '--status'], Path('.'), {}, timeout=1)
