import asyncio
import json
import os
import socket
import sys

import pytest

from app import os_operator as operator
from app.container_runner import OutputLimitExceeded, ProcessResult

pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='The OS adapter targets Linux and WSL')


@pytest.fixture
def files(tmp_path, monkeypatch):
    apps, binaries = tmp_path / 'applications', tmp_path / 'bin'
    apps.mkdir()
    binaries.mkdir()
    monkeypatch.setattr(operator, 'APPLICATIONS', apps)
    monkeypatch.setattr(operator, 'SYSTEM_BIN', binaries)
    monkeypatch.setattr(operator, 'ROOT_UID', os.geteuid())
    # Fixtures stand in for root-owned system directories; leaf metadata is checked normally.
    monkeypatch.setattr(operator, '_trusted_directory', lambda path: path in {apps, binaries})
    gui = {'DISPLAY': ':0', 'XDG_RUNTIME_DIR': '/run/user/' + str(os.geteuid()),
           'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/run/user/' + str(os.geteuid()) + '/bus'}
    monkeypatch.setattr(operator, '_gui_environment', lambda uid: (dict(gui), 'wslg'))
    monkeypatch.setattr(operator, '_bus_environment', lambda uid: dict(gui))
    for name in ('demo', 'systemctl', 'systemd-run', 'gio', 'env'):
        executable = binaries / name
        executable.write_text('fixture, never execute\n')
        executable.chmod(0o755)
    def entry(name='demo.desktop', extra='', body=None):
        path = apps / name
        path.write_text(body if body is not None else '[Desktop Entry]\nType=Application\nName=Demo\nExec=demo %U\n' + extra)
        path.chmod(0o644)
        return path
    return apps, binaries, entry


def never_run(monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail('Operation must be rejected before dispatch')
    monkeypatch.setattr(operator, 'run_process', forbidden)


def test_inventory_returns_only_bounded_snapshot_fields(files):
    _, _, entry = files
    entry()
    result = operator.inventory()
    assert result['supported'] and result['launch_available']
    assert result['gui']['backend'] == 'wslg'
    assert result['interaction_supported'] is False
    assert result['apps'][0]['id'] == 'demo.desktop'
    assert set(result['apps'][0]) == {'id', 'name', 'file_sha256'}
    assert len(result['apps'][0]['file_sha256']) == 64
    assert 'Exec' not in json.dumps(result)


@pytest.mark.parametrize('extra', [
    'Hidden=true\n', 'NoDisplay=true\n', 'Terminal=true\n', 'DBusActivatable=true\n',
    'OnlyShowIn=GNOME;\n', 'NotShowIn=KDE;\n', 'Path=/tmp\n', 'Hidden=unknown\n',
    'TryExec=missing\n', 'TryExec=demo --unsafe\n',
], ids=['hidden', 'no-display', 'terminal', 'dbus', 'only-desktop', 'not-desktop',
        'working-directory', 'invalid-boolean', 'missing-try-exec', 'try-exec-arguments'])
def test_ineligible_entries_are_skipped(files, extra):
    _, _, entry = files
    entry(extra=extra)
    assert operator.inventory()['apps'] == []


@pytest.mark.parametrize('command', ['"demo" %U', 'missing', '/tmp/demo', 'demo;touch /tmp/file',
                                    'demo\n continuation', '../demo', 'demo\t--arg'],
                         ids=['quoted', 'missing', 'outside-system', 'shell-delimiter',
                              'multiline', 'traversal', 'control-character'])
def test_exec_eligibility_is_conservative(files, command):
    _, _, entry = files
    entry(body='[Desktop Entry]\nType=Application\nName=Demo\nExec=' + command + '\n')
    assert operator.inventory()['apps'] == []


def test_bad_types_duplicate_keys_and_private_user_entries_are_excluded(files):
    apps, _, entry = files
    entry('bad.desktop', body='[Desktop Entry]\nType=Link\nName=Demo\nExec=demo\n')
    entry('duplicate.desktop', extra='Name=Other\n')
    entry('with space.desktop')
    private = apps.parent / 'private'
    private.mkdir()
    (private / 'secret.desktop').write_text('[Desktop Entry]\nType=Application\nName=Private\nExec=demo\n')
    assert operator.inventory()['apps'] == []


@pytest.mark.parametrize('kind', ['writable', 'symlink', 'directory', 'fifo', 'oversized'],
                         ids=['writable', 'symlink', 'directory', 'fifo', 'oversized'])
def test_launcher_must_be_bounded_readonly_regular_file(files, kind):
    apps, _, entry = files
    path = entry()
    if kind == 'writable':
        path.chmod(0o666)
    elif kind == 'oversized':
        path.write_text('x' * (operator.MAX_DESKTOP_BYTES + 1))
    else:
        path.unlink()
        if kind == 'symlink':
            target = entry('target.txt')
            path.symlink_to(target)
        elif kind == 'directory':
            path.mkdir()
        else:
            os.mkfifo(path)
    assert operator.inventory()['apps'] == []


def test_wrong_file_owner_or_untrusted_parent_is_rejected(files, monkeypatch):
    _, _, entry = files
    entry()
    monkeypatch.setattr(operator, 'ROOT_UID', os.geteuid() + 1)
    assert operator.inventory()['apps'] == []
    monkeypatch.setattr(operator, 'ROOT_UID', os.geteuid())
    monkeypatch.setattr(operator, '_trusted_directory', lambda path: False)
    assert operator.inventory()['apps'] == []


def test_real_temporary_directory_is_not_a_trusted_root_directory(tmp_path):
    assert operator._trusted_directory(tmp_path) is False


def test_executable_cannot_resolve_outside_trusted_system_tree(files):
    _, binaries, entry = files
    entry()
    target = binaries.parent / 'outside'
    target.write_text('not executed')
    target.chmod(0o755)
    (binaries / 'demo').unlink()
    (binaries / 'demo').symlink_to(target)
    assert operator.inventory()['apps'] == []


def test_executable_symlinks_are_conservatively_excluded(files):
    _, binaries, entry = files
    entry()
    (binaries / 'demo').unlink()
    (binaries / 'demo').symlink_to(binaries / 'gio')
    assert operator.inventory()['apps'] == []


def test_names_and_inventory_are_bounded(files):
    _, _, entry = files
    for number in range(35):
        entry(f'app{number:02}.desktop', body='[Desktop Entry]\nType=Application\nName=' + '\u202e' + 'X' * 200 + '\nExec=demo\n')
    result = operator.inventory()
    assert len(result['apps']) == 32 and result['truncated']
    assert [item['id'] for item in result['apps']] == [f'app{number:02}.desktop' for number in range(32)]
    assert all(item['name'] == 'X' * 160 for item in result['apps'])


def test_missing_tools_disable_launch_and_fail_before_dispatch(files, monkeypatch):
    _, binaries, entry = files
    entry()
    item = operator.inventory()['apps'][0]
    (binaries / 'gio').unlink()
    assert operator.inventory()['launch_available'] is False
    never_run(monkeypatch)
    with pytest.raises(operator.OSOperatorError) as error:
        asyncio.run(operator.launch(item['id'], item['file_sha256']))
    assert error.value.code == 'UNAVAILABLE'


def test_changed_launcher_cannot_be_launched(files, monkeypatch):
    _, _, entry = files
    entry()
    item = operator.inventory()['apps'][0]
    entry(extra='Comment=changed after review\n')
    never_run(monkeypatch)
    with pytest.raises(operator.OSOperatorError) as error:
        asyncio.run(operator.launch(item['id'], item['file_sha256']))
    assert error.value.code == 'APP_CHANGED'


@pytest.mark.parametrize('app_id, digest', [('../../secret', 'a' * 64), ('--run.desktop', 'a' * 64),
                                         ('demo.desktop', 'SECRET'), ([], 'a' * 64)],
                         ids=['traversal', 'option', 'hash', 'wrong-type'])
def test_injected_launch_arguments_are_rejected(files, monkeypatch, app_id, digest):
    never_run(monkeypatch)
    with pytest.raises(operator.OSOperatorError) as error:
        asyncio.run(operator.launch(app_id, digest))
    assert error.value.code == 'INVALID_APP' and 'SECRET' not in str(error.value)


def test_launch_uses_exact_snapshot_clean_environment_and_never_parses_exec(files, monkeypatch):
    apps, binaries, entry = files
    entry(extra='Comment=SECRET-EXEC-COMMENT\n')
    item = operator.inventory()['apps'][0]
    for name in ('ROMS_GATEWAY_API_KEY', 'LD_LIBRARY_PATH', 'PYTHONHOME', 'HOME'):
        monkeypatch.setenv(name, 'SECRET-ENV-VALUE')
    commands = []
    async def capture(command, timeout, limit):
        commands.append(command)
        assert timeout == 10 and limit == 4096
        return ProcessResult(0, 'SECRET-OUTPUT')
    monkeypatch.setattr(operator, 'run_process', capture)
    result = asyncio.run(operator.launch(item['id'], item['file_sha256']))
    command, = commands
    assert command[:4] == [str(binaries / 'systemd-run'), '--user', '--collect', '--quiet']
    assert '--property=Type=exec' in command and '--property=ExitType=cgroup' in command
    assert '--property=UnsetEnvironment=LD_PRELOAD LD_LIBRARY_PATH LD_AUDIT LD_DEBUG LD_DEBUG_OUTPUT LD_PROFILE LD_PROFILE_OUTPUT GLIBC_TUNABLES PYTHONHOME PYTHONPATH' in command
    assert '--setenv=DISPLAY=:0' in command
    clean = command[command.index('--') + 1:]
    assert clean[:2] == [str(binaries / 'env'), '-i']
    assert 'PATH=/usr/bin:/bin' in clean and 'LANG=C.UTF-8' in clean
    assert clean[-3:] == [str(binaries / 'gio'), 'launch', str(apps / 'demo.desktop')]
    assert 'demo %U' not in json.dumps(command)
    assert 'SECRET' not in json.dumps(command) + json.dumps(result)
    assert result['status'] == 'request_accepted' and result['window_verified'] is False
    assert result['app'] == item and result['unit'].startswith('goose-app-')


@pytest.mark.parametrize('failure', [TimeoutError('SECRET'), OutputLimitExceeded('SECRET'),
                                    OSError('SECRET'), asyncio.CancelledError()],
                         ids=['timeout', 'output-limit', 'os-error', 'cancelled'])
def test_uncertain_launch_carries_unit_and_is_not_retried(files, monkeypatch, failure):
    _, _, entry = files
    entry()
    item = operator.inventory()['apps'][0]
    calls = []
    async def fail(command, *args):
        calls.append(command)
        raise failure
    monkeypatch.setattr(operator, 'run_process', fail)
    with pytest.raises(operator.OSOperatorError) as error:
        asyncio.run(operator.launch(item['id'], item['file_sha256']))
    assert error.value.code == 'OUTCOME_UNKNOWN'
    assert error.value.unit.startswith('goose-app-') and 'SECRET' not in str(error.value)
    assert len(calls) == 1


def test_nonzero_launch_is_not_reported_as_a_window(files, monkeypatch):
    _, _, entry = files
    entry()
    item = operator.inventory()['apps'][0]
    async def rejected(*args):
        return ProcessResult(1, 'SECRET')
    monkeypatch.setattr(operator, 'run_process', rejected)
    with pytest.raises(operator.OSOperatorError) as error:
        asyncio.run(operator.launch(item['id'], item['file_sha256']))
    assert error.value.code == 'OUTCOME_UNKNOWN' and error.value.unit


@pytest.mark.parametrize('service_id', list(operator.SERVICES), ids=list(operator.SERVICES))
def test_service_status_uses_only_fixed_unit_and_properties(files, monkeypatch, service_id):
    _, binaries, _ = files
    scope, unit = operator.SERVICES[service_id]
    commands = []
    async def capture(command, timeout, limit):
        commands.append(command)
        assert timeout == 5 and limit == 4096
        return ProcessResult(0, 'LoadState=loaded\nActiveState=active\nSubState=running\n')
    monkeypatch.setattr(operator, 'run_process', capture)
    result = asyncio.run(operator.service_status(service_id))
    assert commands == [[str(binaries / 'systemctl'), *(['--user'] if scope == 'user' else []),
                         'show', '--no-pager', '--property=LoadState', '--property=ActiveState',
                         '--property=SubState', '--', unit]]
    assert result == {'service': service_id, 'scope': scope, 'unit': unit, 'load_state': 'loaded',
                      'active_state': 'active', 'sub_state': 'running'}


@pytest.mark.parametrize('service_id', ['sshd', '--all', 'goose-model; reboot', []],
                         ids=['unknown', 'option', 'injection', 'wrong-type'])
def test_unknown_service_never_runs(files, monkeypatch, service_id):
    never_run(monkeypatch)
    with pytest.raises(operator.OSOperatorError) as error:
        asyncio.run(operator.service_status(service_id))
    assert error.value.code == 'INVALID_SERVICE'


def test_service_error_and_unrecognized_values_do_not_expose_output(files, monkeypatch):
    async def unknown(*args):
        return ProcessResult(0, 'LoadState=loaded\nActiveState=SECRET\nSubState=SECRET\n')
    monkeypatch.setattr(operator, 'run_process', unknown)
    result = asyncio.run(operator.service_status('goose-model'))
    assert result['active_state'] == result['sub_state'] == 'unknown'
    async def malformed(*args):
        return ProcessResult(1, 'SECRET-DIAGNOSTICS\n')
    monkeypatch.setattr(operator, 'run_process', malformed)
    with pytest.raises(operator.OSOperatorError) as error:
        asyncio.run(operator.service_status('goose-model'))
    assert error.value.code == 'STATUS_UNAVAILABLE' and 'SECRET' not in str(error.value)


def test_real_socket_checks_recognize_wslg_without_claiming_desktop(tmp_path, monkeypatch):
    uid = os.geteuid()
    runtime = tmp_path / 'run' / str(uid)
    runtime.mkdir(parents=True, mode=0o700)
    wslg = tmp_path / 'wslg'
    (wslg / 'runtime-dir').mkdir(parents=True)
    bus, wayland = socket.socket(socket.AF_UNIX), socket.socket(socket.AF_UNIX)
    try:
        bus.bind(str(runtime / 'bus'))
        wayland.bind(str(wslg / 'runtime-dir' / 'wayland-0'))
        (runtime / 'wayland-0').symlink_to(wslg / 'runtime-dir' / 'wayland-0')
        monkeypatch.setattr(operator, 'RUNTIME_ROOT', runtime.parent)
        monkeypatch.setattr(operator, 'WSLG_ROOT', wslg)
        monkeypatch.setenv('XDG_RUNTIME_DIR', str(runtime))
        monkeypatch.setenv('DBUS_SESSION_BUS_ADDRESS', 'unix:path=' + str(runtime / 'bus'))
        monkeypatch.setenv('WAYLAND_DISPLAY', 'wayland-0')
        monkeypatch.setenv('DISPLAY', 'remote.example:0')
        environment, backend = operator._gui_environment(uid)
        assert backend == 'wslg' and 'DISPLAY' not in environment
        assert environment['WAYLAND_DISPLAY'] == 'wayland-0'
        monkeypatch.delenv('DBUS_SESSION_BUS_ADDRESS')
        assert operator._gui_environment(uid) == ({}, 'unavailable')
        monkeypatch.setenv('DBUS_SESSION_BUS_ADDRESS', 'tcp:host=example.com,port=1234')
        assert operator._gui_environment(uid) == ({}, 'unavailable')
    finally:
        bus.close()
        wayland.close()


def test_environment_strings_without_sockets_are_not_gui_capability(tmp_path, monkeypatch):
    monkeypatch.setattr(operator, 'RUNTIME_ROOT', tmp_path)
    monkeypatch.setenv('DISPLAY', ':0')
    monkeypatch.setenv('WAYLAND_DISPLAY', 'wayland-0')
    assert operator._gui_environment(os.geteuid()) == ({}, 'unavailable')


def test_missing_gui_rejects_launch_before_dispatch(files, monkeypatch):
    _, _, entry = files
    entry()
    item = operator.inventory()['apps'][0]
    monkeypatch.setattr(operator, '_gui_environment', lambda uid: ({}, 'unavailable'))
    never_run(monkeypatch)
    with pytest.raises(operator.OSOperatorError) as error:
        asyncio.run(operator.launch(item['id'], item['file_sha256']))
    assert error.value.code == 'GUI_UNAVAILABLE'


def test_user_service_requires_the_same_available_local_bus(files, monkeypatch):
    monkeypatch.setattr(operator, '_bus_environment', lambda uid: {})
    never_run(monkeypatch)
    with pytest.raises(operator.OSOperatorError) as error:
        asyncio.run(operator.service_status('omarchy-task-worker'))
    assert error.value.code == 'UNAVAILABLE'
