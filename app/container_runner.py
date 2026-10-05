"""Bounded rootless Podman workers with explicit, retryable cleanup ownership."""
import asyncio
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import signal
import uuid

OUTPUT_LIMIT = 512 * 1024
CONTROL_TIMEOUT = 20
LABEL = 'org.buzburg.roms.task'


class CleanupRequired(RuntimeError):
    pass


class OutputLimitExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    output: str


async def _settle(task: asyncio.Task) -> tuple[object, bool]:
    """Finish bounded ownership/cleanup operations despite repeated cancellation."""
    cancelled = False
    while True:
        try:
            return await asyncio.shield(task), cancelled
        except asyncio.CancelledError:
            if task.cancelled():
                raise
            cancelled = True


def runtime_environment() -> dict[str, str]:
    keys = ('HOME', 'USER', 'LOGNAME', 'XDG_RUNTIME_DIR', 'DBUS_SESSION_BUS_ADDRESS')
    return {**{key: os.environ[key] for key in keys if key in os.environ},
            'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'GIT_CONFIG_NOSYSTEM': '1',
            'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_NO_LAZY_FETCH': '1'}


async def run_process(command: list[str], timeout: float, limit: int = OUTPUT_LIMIT) -> ProcessResult:
    process, cancelled = await _settle(asyncio.create_task(asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        stdin=asyncio.subprocess.DEVNULL, env=runtime_environment(), start_new_session=True)))

    async def collect() -> ProcessResult:
        output = bytearray()
        while block := await process.stdout.read(16384):
            output.extend(block)
            if len(output) > limit:
                raise OutputLimitExceeded('Worker output exceeded the configured byte limit')
        return ProcessResult(await process.wait(), output.decode('utf-8', errors='replace'))

    async def reap() -> None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        async def discard() -> None:
            while await process.stdout.read(16384):
                pass
        await asyncio.wait_for(asyncio.gather(process.wait(), discard()), 5)

    try:
        if cancelled:
            raise asyncio.CancelledError
        return await asyncio.wait_for(collect(), timeout)
    finally:
        _, interrupted = await _settle(asyncio.create_task(reap()))
        if interrupted:
            raise asyncio.CancelledError


def write_state(path: Path, state: dict) -> None:
    temporary = path.with_suffix('.new')
    temporary.write_text(json.dumps(state, indent=2), encoding='utf-8')
    temporary.replace(path)


def _runtime() -> str:
    if os.name != 'posix' or os.geteuid() == 0:
        raise RuntimeError('Worker execution requires an unprivileged Linux account')
    runtime = shutil.which('podman')
    if not runtime:
        raise RuntimeError('Rootless Podman is required; host execution is unavailable')
    return str(Path(runtime).resolve())


async def cleanup(control: Path) -> None:
    """Retry only containers bearing this private journal's validated task label."""
    path = control / 'container.json'
    state = json.loads(path.read_text())
    task_id = state['task_id']
    if not re.fullmatch(r'[a-f0-9]{32}', task_id):
        raise ValueError('Invalid cleanup task identity')
    try:
        runtime = _runtime()
        command = [runtime, '--remote=false', '--log-level=error']
        query = [*command, 'ps', '-aq', '--no-trunc', '--filter', f'label={LABEL}={task_id}']
        listed = await run_process(query, CONTROL_TIMEOUT)
        if listed.returncode:
            raise RuntimeError('Cannot query owned containers: ' + listed.output[-1000:])
        identities = listed.output.split()
        if not all(re.fullmatch(r'[a-f0-9]{64}', identity) for identity in identities):
            raise RuntimeError('Container query returned an invalid identity')
        for identity in identities:
            removed = await run_process([*command, 'rm', '--force', '--time=1', identity], CONTROL_TIMEOUT)
            if removed.returncode:
                raise RuntimeError('Container removal failed: ' + removed.output[-1000:])
        remaining = await run_process(query, CONTROL_TIMEOUT)
        if remaining.returncode or remaining.output.strip():
            raise RuntimeError('Container absence could not be verified')
        state.update(state='cleaned', cleanup_error=None)
        write_state(path, state)
    except Exception as error:
        state.update(state='cleanup_required', cleanup_error=str(error))
        write_state(path, state)
        raise CleanupRequired(f'Cleanup requires retry; retained journal: {path}') from error


async def execute(workspace: Path, control: Path, image: str, argv: list[str], *,
                  cpus: str = '2.0', memory: str = '4g', timeout: float = 120) -> ProcessResult:
    runtime = _runtime()
    if not image or image.startswith('-') or len(image) > 512 or any(c.isspace() for c in image):
        raise ValueError('Invalid local container image reference')
    if not argv or len(argv) > 256 or any('\x00' in arg for arg in argv) or sum(map(len, argv)) > 16384:
        raise ValueError('Invalid or oversized worker command')
    if not 0 < float(cpus) <= 8 or not 0 < timeout <= 600:
        raise ValueError('CPU count or execution timeout exceeds the worker limits')
    memory_match = re.fullmatch(r'([1-9][0-9]*)([mg])', memory.lower())
    if not memory_match or not 16 <= int(memory_match[1]) * (1024 if memory_match[2] == 'g' else 1) <= 8192:
        raise ValueError('Worker memory must be between 16m and 8g')
    workspace = workspace.resolve(strict=True)
    control = control.resolve(strict=True)
    if control.is_relative_to(workspace):
        raise ValueError('Container journal must be outside the worker mount')
    command = [runtime, '--remote=false', '--log-level=error']
    info = await run_process([*command, 'info', '--format', '{{.Host.Security.Rootless}}'], CONTROL_TIMEOUT)
    if info.returncode or info.output.strip() != 'true':
        raise RuntimeError('Rootless Podman is unavailable: ' + info.output[-1000:])
    task_id = uuid.uuid4().hex
    path = control / 'container.json'
    if path.exists():
        raise ValueError('Control directory already belongs to a worker')
    state = {'task_id': task_id, 'workspace': str(workspace), 'state': 'creating'}
    write_state(path, state)
    try:
        created = await run_process([*command, 'create', '--pull=never', '--name=roms-' + task_id,
            '--label', f'{LABEL}={task_id}', '--network=none', '--cap-drop=all',
            '--security-opt=no-new-privileges', '--read-only', '--pids-limit=128',
            f'--cpus={cpus}', f'--memory={memory}', '--log-driver=none',
            '--tmpfs=/tmp:rw,nosuid,nodev,noexec,size=128m', '--userns=keep-id',
            '-v', f'{workspace}:/workspace:rw', '-w', '/workspace', image, *argv], CONTROL_TIMEOUT)
        if created.returncode:
            raise RuntimeError('Container creation failed: ' + created.output[-2000:])
        identity = created.output.strip()
        if not re.fullmatch(r'[a-f0-9]{64}', identity):
            raise RuntimeError('Container creation did not return a valid identity')
        state.update(state='running', container_id=identity)
        write_state(path, state)
        return await run_process([*command, 'start', '--attach', identity], timeout)
    except BaseException as error:
        state['outcome'] = type(error).__name__
        write_state(path, state)
        raise
    finally:
        _, interrupted = await _settle(asyncio.create_task(cleanup(control)))
        if interrupted:
            raise asyncio.CancelledError


def confirmed_clean(control: Path) -> bool:
    path = control / 'container.json'
    return path.is_file() and json.loads(path.read_text()).get('state') == 'cleaned'
