"""Durable proposed/staged/validated patches bound to a registered Git revision."""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import uuid

from app.config import DATA_DIR
from app.container_runner import CleanupRequired, run_process
from app.git_workspace import safe_git
from app.source_library import local_path
from app import validation_policy

STORE = DATA_DIR / 'patches'
FORBIDDEN = {'.git', '.gitmodules', '.gitattributes', '.agents', '.codex', '.ssh', '.aws',
             '.env', 'credentials.json', 'secrets.json', 'runtime.env', '__pycache__'}
MAX_FILE = 1024 * 1024


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def durable_json(path: Path, value: object) -> None:
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.journal-', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(canonical(value))
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        temporary.unlink(missing_ok=True)


def identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{32}', value):
        raise ValueError('Invalid project or task ID')
    return value


def patch_path(value: str) -> str:
    if (not isinstance(value, str) or not value or len(value) > 512 or '\\' in value
            or any(ord(char) < 32 or ord(char) == 127 for char in value) or ':' in value):
        raise ValueError('Invalid patch path')
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(part in {'.', '..'} for part in path.parts):
        raise ValueError('Patch paths must be canonical and relative')
    if any(part.lower() in FORBIDDEN or part.lower().startswith('.env') for part in path.parts):
        raise ValueError('Patch path is excluded by policy')
    return value


def read_file(root: Path, relative: str) -> bytes | None:
    """No-follow descriptor walk; None represents an absent leaf, never a symlink."""
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    parts = PurePosixPath(relative).parts
    try:
        for component in parts[:-1]:
            try:
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            except FileNotFoundError:
                return None
            os.close(directory)
            directory = child
        try:
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except FileNotFoundError:
            return None
    finally:
        os.close(directory)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE:
            raise ValueError('Patch input must be a regular file up to 1 MiB')
        content = stream.read(MAX_FILE + 1)
        if len(content) > MAX_FILE:
            raise ValueError('File grew beyond the patch limit')
        return content


def inventory(stage: Path) -> dict[str, dict]:
    result, total = {}, 0
    for directory, folders, files in os.walk(stage, followlinks=False):
        folders[:] = [name for name in folders if name != '__pycache__']
        if any((Path(directory) / name).is_symlink() for name in folders):
            raise ValueError('Staged directory symlinks are not permitted')
        for name in sorted(files):
            relative = (Path(directory) / name).relative_to(stage).as_posix()
            data = read_file(stage, relative)
            if data is None:
                raise ValueError('Staged file disappeared during inventory')
            total += len(data)
            if total > 32 * 1024 * 1024 or len(result) >= 2000:
                raise ValueError('Stage exceeds the 32 MiB / 2,000-file policy limit')
            result[relative] = {'sha256': sha(data), 'mode': stat.S_IMODE((stage / relative).stat().st_mode)}
    return result


async def register_project(value: str) -> dict:
    source = local_path(value)
    if not source.is_dir() or not (source / '.git').exists() or (source / '.git').is_symlink():
        raise ValueError('Select an existing local Git repository')
    git = await safe_git(source)
    top = await run_process([*git, 'rev-parse', '--show-toplevel'], 10)
    if top.returncode or Path(top.output.strip()).resolve() != source:
        raise ValueError('Select the repository root')
    registry = STORE / 'projects'
    registry.mkdir(parents=True, exist_ok=True, mode=0o700)
    for path in registry.glob('*.json'):
        existing = json.loads(path.read_text())
        if existing['source'] == str(source):
            return existing
    project = {'id': uuid.uuid4().hex, 'source': str(source)}
    durable_json(registry / (project['id'] + '.json'), project)
    return project


def task_directory(task_id: str) -> Path:
    return STORE / 'tasks' / identifier(task_id)


@contextmanager
def task_lock(control: Path):
    with (control / '.lock').open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Task is already being modified') from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def transition(control: Path, task: dict, state: str, **details) -> None:
    task.update(state=state, **details)
    task['history'].append({'state': state, 'time': datetime.now(timezone.utc).isoformat()})
    durable_json(control / 'task.json', task)


def load_task(task_id: str) -> tuple[Path, dict, dict]:
    control = task_directory(task_id)
    task = json.loads((control / 'task.json').read_text())
    patch = json.loads((control / 'patch.json').read_text())
    if sha(canonical(patch)) != task['patch_sha256']:
        raise ValueError('Patch content no longer matches the task digest')
    if task['base_commit'] != patch['base_commit']:
        raise ValueError('Task revision no longer matches the patch')
    if 'preimages_sha256' in task:
        preimages = json.loads((control / 'preimages.json').read_text())
        if sha(canonical(preimages)) != task['preimages_sha256']:
            raise ValueError('Preimage record no longer matches the task digest')
    return control, task, patch


async def propose(project_id: str, base_commit: str, changes: list[dict], checks: list[dict]) -> dict:
    if not re.fullmatch(r'(?:[a-f0-9]{40}|[a-f0-9]{64})', base_commit):
        raise ValueError('An explicit full base commit ID is required')
    if not isinstance(changes, list) or not 1 <= len(changes) <= 32 or not isinstance(checks, list) or not 1 <= len(checks) <= 4:
        raise ValueError('Require 1–32 changes and 1–4 registered validation checks')
    names = set()
    for change in changes:
        if type(change) is not dict or set(change) != {'path', 'before_sha256', 'after'}:
            raise ValueError('A change needs path, before_sha256 and after text (or null for deletion)')
        name = patch_path(change['path'])
        if name in names:
            raise ValueError('Duplicate patch path')
        names.add(name)
        if change['before_sha256'] is not None and (not isinstance(change['before_sha256'], str) or not re.fullmatch(r'[a-f0-9]{64}', change['before_sha256'])):
            raise ValueError('Invalid preimage digest')
        after = change['after']
        if after is not None and (not isinstance(after, str) or '\x00' in after or len(after.encode()) > MAX_FILE):
            raise ValueError('Replacement must be bounded UTF-8 text')
        if after is None and change['before_sha256'] is None:
            raise ValueError('Cannot delete an absent file')
    project = json.loads((STORE / 'projects' / (identifier(project_id) + '.json')).read_text())
    source = Path(project['source'])
    git = await safe_git(source)
    revision = await run_process([*git, 'rev-parse', '--verify', base_commit + '^{commit}'], 10)
    if revision.returncode or revision.output.strip() != base_commit:
        raise ValueError('Base commit does not exist in this project')
    tree = await run_process([*git, 'ls-tree', '-r', '-l', '-z', base_commit], 10)
    if tree.returncode:
        raise ValueError('Cannot inventory the requested base commit')
    entries = [entry for entry in tree.output.split('\x00') if entry]
    total = 0
    for entry in entries:
        metadata, _ = entry.split('\t', 1)
        mode, kind, _, size = metadata.split()
        if kind != 'blob' or mode not in {'100644', '100755'} or int(size) > MAX_FILE:
            raise ValueError('Base contains unsupported file types or oversized files')
        total += int(size)
    if len(entries) > 1999 or total > 32 * 1024 * 1024:
        raise ValueError('Base exceeds the staging inventory limits')
    patch = {'project_id': project_id, 'base_commit': base_commit, 'changes': changes, 'checks': checks,
             'policy_version': validation_policy.POLICY_VERSION}
    if len(canonical(patch)) > 512 * 1024:
        raise ValueError('Patch exceeds 512 KiB')
    task = {'id': uuid.uuid4().hex, 'source': str(source), 'base_commit': base_commit,
            'patch_sha256': sha(canonical(patch)), 'history': []}
    control = task_directory(task['id'])
    control.mkdir(parents=True, mode=0o700)
    stage = control / 'stage'
    with task_lock(control):
        durable_json(control / 'patch.json', patch)
        transition(control, task, 'proposed')
        try:
            created = await run_process([*git, 'worktree', 'add', '--detach', str(stage), base_commit], 30)
            if created.returncode:
                raise RuntimeError('Cannot create isolated worktree: ' + created.output[-1000:])
            stage.chmod(0o700)
            inventory(stage)  # Reject unsupported types/size before writing the proposed change.
            preimages = {}
            for change in changes:
                name = change['path']
                before = read_file(stage, name)
                observed = sha(before) if before is not None else None
                if observed != change['before_sha256']:
                    raise ValueError('Base preimage mismatch: ' + name)
                if read_file(source, name) != before:
                    raise ValueError('User working copy has a conflicting edit: ' + name)
                preimages[name] = {'text': before.decode('utf-8') if before is not None else None,
                                  'mode': stat.S_IMODE((source / name).stat().st_mode) if before is not None else 0o644}
                target = stage / name
                if change['after'] is None:
                    target.unlink()
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(change['after'], encoding='utf-8')
            for check in checks:
                validation_policy.command_for(check, stage)
            durable_json(control / 'preimages.json', preimages)
            transition(control, task, 'staged', stage_inventory=inventory(stage),
                       preimages_sha256=sha(canonical(preimages)))
        except BaseException as error:
            transition(control, task, 'cancelled' if isinstance(error, asyncio.CancelledError) else 'failed',
                       error=type(error).__name__ + ': ' + str(error))
            raise
    return task


async def validate_task(task_id: str) -> dict:
    control = task_directory(task_id)
    with task_lock(control):
        _, task, patch = load_task(task_id)
        if task['state'] != 'staged':
            raise ValueError('Only an unchanged staged task can be validated')
        stage = control / 'stage'
        if inventory(stage) != task['stage_inventory']:
            raise ValueError('Staged contents changed before validation')
        transition(control, task, 'validating', evidence=[])
        try:
            for index, check in enumerate(patch['checks']):
                check_dir = control / ('check-' + str(index))
                check_dir.mkdir(mode=0o700)
                result = await validation_policy.validate(stage, check_dir, check)
                task['evidence'].append({'command': check, 'exit_code': result.returncode,
                                         'output': result.output[:12000], 'policy': 'check-' + str(index) + '/policy.json'})
                if result.returncode:
                    raise ValueError('Registered validation failed')
                if inventory(stage) != task['stage_inventory']:
                    raise ValueError('Validation mutated staged contents; result is not bound to the proposed patch')
            transition(control, task, 'validated', validated_patch_sha256=task['patch_sha256'])
        except BaseException as error:
            state = ('cleanup_required' if isinstance(error, CleanupRequired) else
                     'cancelled' if isinstance(error, asyncio.CancelledError) else 'failed')
            transition(control, task, state, error=type(error).__name__ + ': ' + str(error))
            raise
    return task
