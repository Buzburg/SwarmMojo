"""Reviewed local-user OS operations; never a model-callable command runner."""
from __future__ import annotations

import asyncio
import configparser
import hashlib
import os
from pathlib import Path
import re
import stat
import sys
import unicodedata
import uuid

from app.container_runner import OutputLimitExceeded, run_process

APPLICATIONS = Path('/usr/share/applications')
SYSTEM_BIN = Path('/usr/bin')
RUNTIME_ROOT = Path('/run/user')
WSLG_ROOT = Path('/mnt/wslg')
X11_ROOT = Path('/tmp/.X11-unix')
ROOT_UID = 0
MAX_APPS = 32
MAX_ENTRIES = 2048
MAX_DESKTOP_BYTES = 32768
SERVICES = {
    'goose-model': ('system', 'goose-model.service'),
    'goose-roms': ('system', 'goose-roms.service'),
    'omarchy-broker': ('system', 'omarchy-broker.service'),
    'omarchy-task-worker': ('user', 'omarchy-task-worker.service'),
}
APP_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.desktop\Z')
EXECUTABLE = re.compile(r'(?:/[A-Za-z0-9_.+-]+)+\Z|[A-Za-z0-9][A-Za-z0-9_.+-]*\Z')


class OSOperatorError(RuntimeError):
    def __init__(self, code: str, message: str, *, unit: str | None = None):
        super().__init__(message)
        self.code, self.message, self.unit = code, message, unit


def _user() -> int:
    if sys.platform != 'linux' or os.geteuid() == 0:
        raise OSOperatorError('UNAVAILABLE', 'Use an unprivileged user inside the configured Linux environment.')
    return os.geteuid()


def _root_owned(info: os.stat_result) -> bool:
    return info.st_uid == ROOT_UID and not info.st_mode & 0o022


def _trusted_directory(path: Path) -> bool:
    try:
        return all(stat.S_ISDIR(info.st_mode) and _root_owned(info)
                   for info in (parent.lstat() for parent in (path, *path.parents)))
    except OSError:
        return False


def _trusted_executable(value: str) -> str | None:
    if len(value) > 512 or not EXECUTABLE.fullmatch(value) or '..' in value.split('/'):
        return None
    path = Path(value) if value.startswith('/') else SYSTEM_BIN / value
    if path.parent not in {SYSTEM_BIN, Path('/bin')}:
        return None
    try:
        info = path.lstat()
        if (not _trusted_directory(path.parent) or not stat.S_ISREG(info.st_mode)
                or not _root_owned(info) or not info.st_mode & 0o111 or not os.access(path, os.X_OK)):
            return None
        return str(path)
    except (OSError, RuntimeError):
        return None


def _desktop(app_id: str) -> dict[str, str] | None:
    if not APP_ID.fullmatch(app_id) or not _trusted_directory(APPLICATIONS):
        return None
    try:
        fd = os.open(APPLICATIONS / app_id, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as source:
            before = os.fstat(source.fileno())
            if (not stat.S_ISREG(before.st_mode) or not _root_owned(before)
                    or before.st_size > MAX_DESKTOP_BYTES):
                return None
            content = source.read(MAX_DESKTOP_BYTES + 1)
            after = os.fstat(source.fileno())
        if (len(content) > MAX_DESKTOP_BYTES or before.st_size != len(content)
                or (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
            return None
        parser = configparser.ConfigParser(interpolation=None, strict=True, delimiters=('=',),
                                           comment_prefixes=('#',), empty_lines_in_values=False)
        parser.optionxform = str
        parser.read_string(content.decode('utf-8'))
        if parser.defaults() or 'Desktop Entry' not in parser:
            return None
        entry = parser['Desktop Entry']
        if entry.get('Type') != 'Application':
            return None
        for key in ('Hidden', 'NoDisplay', 'Terminal', 'DBusActivatable'):
            if entry.get(key, 'false') != 'false':
                return None
        if entry.get('Path') or entry.get('OnlyShowIn') or entry.get('NotShowIn'):
            return None
        if any(ord(character) < 32 for character in entry.get('Exec', '') + entry.get('TryExec', '')):
            return None
        # Only identify an uncomplicated first executable for eligibility. GIO owns Exec parsing.
        executable = re.match(r'([^\s]+)(?:[ \t]|$)', entry.get('Exec', ''))
        if not executable or not _trusted_executable(executable[1]):
            return None
        if 'TryExec' in entry and not _trusted_executable(entry['TryExec']):
            return None
        name = ' '.join(''.join(c for c in unicodedata.normalize('NFKC', entry.get('Name', ''))
                               if c.isprintable()).split())[:160]
        if not name:
            return None
        return {'id': app_id, 'name': name, 'file_sha256': hashlib.sha256(content).hexdigest()}
    except (OSError, ValueError, configparser.Error):
        return None


def _socket(path: Path, uid: int, targets: set[Path]) -> Path | None:
    try:
        resolved = path.resolve(strict=True)
        info = resolved.stat()
        return resolved if resolved in targets and stat.S_ISSOCK(info.st_mode) and info.st_uid in {0, uid} else None
    except (OSError, RuntimeError):
        return None


def _bus_environment(uid: int) -> dict[str, str]:
    runtime = RUNTIME_ROOT / str(uid)
    try:
        info = runtime.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != uid or info.st_mode & 0o077
                or os.environ.get('XDG_RUNTIME_DIR') != str(runtime)):
            return {}
        bus = runtime / 'bus'
        address = 'unix:path=' + str(bus)
        if (os.environ.get('DBUS_SESSION_BUS_ADDRESS') != address
                or not _socket(bus, uid, {bus})):
            return {}
        return {'XDG_RUNTIME_DIR': str(runtime), 'DBUS_SESSION_BUS_ADDRESS': address}
    except OSError:
        return {}


def _gui_environment(uid: int) -> tuple[dict[str, str], str]:
    runtime = RUNTIME_ROOT / str(uid)
    result = _bus_environment(uid)
    if not result:
        return {}, 'unavailable'
    try:
        backend = 'local-display'
        wayland = os.environ.get('WAYLAND_DISPLAY', '')
        if re.fullmatch(r'wayland-[0-9]{1,3}', wayland):
            native = runtime / wayland
            wslg = WSLG_ROOT / 'runtime-dir' / wayland
            resolved = _socket(native, uid, {native, wslg})
            if resolved:
                result['WAYLAND_DISPLAY'] = wayland
                if resolved == wslg:
                    backend = 'wslg'
        display = os.environ.get('DISPLAY', '')
        match = re.fullmatch(r':([0-9]{1,3})(?:\.[0-9]{1,2})?', display)
        if match:
            filename = 'X' + match[1]
            native = X11_ROOT / filename
            wslg = WSLG_ROOT / '.X11-unix' / filename
            resolved = _socket(native, uid, {native, wslg})
            if resolved:
                result['DISPLAY'] = display
                try:
                    if resolved == wslg or resolved.samefile(wslg):
                        backend = 'wslg'
                except OSError:
                    pass
        return (result, backend) if 'DISPLAY' in result or 'WAYLAND_DISPLAY' in result else ({}, 'unavailable')
    except OSError:
        return {}, 'unavailable'


def inventory() -> dict:
    """List eligible system launchers and actual local display-socket availability."""
    try:
        uid = _user()
    except OSOperatorError:
        return {'supported': False, 'apps': [], 'skipped_count': 0, 'truncated': False,
                'gui': {'available': False, 'backend': 'unavailable', 'reason': 'An unprivileged Linux session is required.'},
                'launch_available': False, 'interaction_supported': False}
    gui, backend = _gui_environment(uid)
    apps, skipped, truncated = [], 0, False
    if _trusted_directory(APPLICATIONS):
        try:
            with os.scandir(APPLICATIONS) as entries:
                names = []
                for index, entry in enumerate(entries):
                    if index >= MAX_ENTRIES:
                        truncated = True
                        break
                    names.append(entry.name)
            for name in sorted(names):
                item = _desktop(name)
                if item is None:
                    skipped += 1
                elif len(apps) < MAX_APPS:
                    apps.append(item)
                else:
                    truncated = True
        except OSError:
            pass
    tools = all(_trusted_executable(str(SYSTEM_BIN / name)) for name in ('systemd-run', 'gio', 'env'))
    return {'supported': True, 'apps': apps, 'skipped_count': skipped, 'truncated': truncated,
            'gui': {'available': bool(gui), 'backend': backend,
                    'reason': 'Local display and user-bus sockets found; window interaction is unverified.' if gui
                    else 'A supported local display and private user-bus socket are required.'},
            'launch_available': bool(gui) and tools, 'interaction_supported': False}


async def service_status(service_id: str) -> dict[str, str]:
    uid = _user()
    if not isinstance(service_id, str) or service_id not in SERVICES:
        raise OSOperatorError('INVALID_SERVICE', 'Choose one of the four registered service IDs.')
    executable = _trusted_executable(str(SYSTEM_BIN / 'systemctl'))
    if not executable:
        raise OSOperatorError('UNAVAILABLE', 'The trusted system status tool is unavailable.')
    scope, unit = SERVICES[service_id]
    if scope == 'user' and not _bus_environment(uid):
        raise OSOperatorError('UNAVAILABLE', 'The private local user service bus is unavailable.')
    command = [executable, *(['--user'] if scope == 'user' else []), 'show', '--no-pager',
               '--property=LoadState', '--property=ActiveState', '--property=SubState', '--', unit]
    try:
        result = await run_process(command, 5, 4096)
        values = {}
        for line in result.output.splitlines():
            key, separator, value = line.partition('=')
            if not separator or key not in {'LoadState', 'ActiveState', 'SubState'} or key in values:
                raise ValueError('Invalid status fields')
            values[key] = value
        if set(values) != {'LoadState', 'ActiveState', 'SubState'} or (result.returncode and values['LoadState'] != 'not-found'):
            raise ValueError('Incomplete status')
    except (OSError, ValueError, TimeoutError, OutputLimitExceeded) as error:
        raise OSOperatorError('STATUS_UNAVAILABLE', 'Service status could not be read safely; no change was requested.') from error
    allowed = {
        'LoadState': {'loaded', 'not-found', 'error', 'masked', 'bad-setting', 'stub', 'merged'},
        'ActiveState': {'active', 'reloading', 'inactive', 'failed', 'activating', 'deactivating', 'maintenance', 'refreshing'},
        'SubState': {'running', 'dead', 'exited', 'failed', 'start-pre', 'start', 'start-post', 'auto-restart',
                     'stop', 'stop-sigterm', 'stop-sigkill', 'stop-post', 'final-sigterm', 'final-sigkill', 'reload'},
    }
    return {'service': service_id, 'scope': scope, 'unit': unit,
            **{field: values[key] if values[key] in allowed[key] else 'unknown'
               for field, key in (('load_state', 'LoadState'), ('active_state', 'ActiveState'), ('sub_state', 'SubState'))}}


async def launch(app_id: str, file_sha256: str) -> dict:
    """Launch only a reviewed launcher snapshot; the caller must obtain approval."""
    uid = _user()
    if (not isinstance(app_id, str) or not APP_ID.fullmatch(app_id)
            or not isinstance(file_sha256, str) or not re.fullmatch(r'[a-f0-9]{64}', file_sha256)):
        raise OSOperatorError('INVALID_APP', 'Provide a registered application ID and its reviewed SHA-256.')
    gui, _ = _gui_environment(uid)
    if not gui:
        raise OSOperatorError('GUI_UNAVAILABLE', 'No supported local graphical session is available.')
    if not all(_trusted_executable(str(SYSTEM_BIN / name)) for name in ('systemd-run', 'gio', 'env')):
        raise OSOperatorError('UNAVAILABLE', 'Trusted application-launch tools are unavailable.')
    import pwd
    home = pwd.getpwuid(uid).pw_dir
    if not home.startswith('/') or any(ord(character) < 32 for character in home):
        raise OSOperatorError('UNAVAILABLE', 'The local account home directory is invalid.')
    unit = 'goose-app-' + uuid.uuid4().hex + '.service'
    clean = {'HOME': home, 'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', **gui}
    command = [str(SYSTEM_BIN / 'systemd-run'), '--user', '--collect', '--quiet', '--unit=' + unit,
               '--property=Type=exec', '--property=ExitType=cgroup',
               '--property=UnsetEnvironment=LD_PRELOAD LD_LIBRARY_PATH LD_AUDIT LD_DEBUG LD_DEBUG_OUTPUT LD_PROFILE LD_PROFILE_OUTPUT GLIBC_TUNABLES PYTHONHOME PYTHONPATH',
               *('--setenv=' + key + '=' + value for key, value in gui.items()),
               '--', str(SYSTEM_BIN / 'env'), '-i', *(key + '=' + value for key, value in clean.items()),
               str(SYSTEM_BIN / 'gio'), 'launch', str(APPLICATIONS / app_id)]
    item = _desktop(app_id)
    if item is None:
        raise OSOperatorError('APP_UNAVAILABLE', 'The application launcher is no longer eligible.')
    if item['file_sha256'] != file_sha256:
        raise OSOperatorError('APP_CHANGED', 'The launcher changed after review; obtain a fresh inventory and review.')
    try:
        result = await run_process(command, 10, 4096)
        if result.returncode:
            raise OSOperatorError('OUTCOME_UNKNOWN', 'Application launch was not confirmed. Inspect the displayed unit before deciding what to do next.', unit=unit)
    except (OSError, TimeoutError, OutputLimitExceeded, asyncio.CancelledError) as error:
        raise OSOperatorError('OUTCOME_UNKNOWN', 'Application launch was interrupted or unconfirmed. Inspect the displayed unit; do not automatically retry.', unit=unit) from error
    return {'status': 'request_accepted', 'unit': unit, 'app': item, 'window_verified': False}
