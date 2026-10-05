"""Operator-authorized, journaled file promotion and conflict-preserving rollback."""
from contextlib import contextmanager
import difflib
import fcntl
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import stat
import time
from collections.abc import Callable

from app import patch_tasks as tasks
from app.container_runner import run_process
from app.git_workspace import safe_git


class Conflict(RuntimeError):
    pass


def review(task_id: str, *, rollback: bool = False) -> dict:
    control = tasks.task_directory(task_id)
    with tasks.task_lock(control):
        _, task, patch = tasks.load_task(task_id)
        if task.get('validated_patch_sha256') != task['patch_sha256']:
            raise ValueError('Only an exactly validated patch can be promoted')
        originals = json.loads((control / 'preimages.json').read_text())
        diff = []
        changes = []
        for change in patch['changes']:
            old, new = originals[change['path']]['text'], change['after']
            if rollback:
                old, new = new, old
            for line in difflib.unified_diff((old or '').splitlines(keepends=True),
                    (new or '').splitlines(keepends=True), fromfile='a/' + change['path'], tofile='b/' + change['path']):
                diff.append(line if line.endswith('\n') else line + '\n\\ No newline at end of file\n')
            changes.append({'path': change['path'], 'before_exists': old is not None, 'after_exists': new is not None,
                            'before_sha256': None if old is None else tasks.sha(old.encode('utf-8')),
                            'after_sha256': None if new is None else tasks.sha(new.encode('utf-8')),
                            'mode': oct(originals[change['path']]['mode'])})
        if task['state'] == 'validated' and not rollback:
            tasks.transition(control, task, 'awaiting_apply')
        return {'id': task_id, 'state': task['state'], 'source': task['source'],
                'base_commit': task['base_commit'], 'patch_sha256': task['patch_sha256'],
                'direction': 'rollback' if rollback else 'apply',
                'changes': changes,
                'diff': ''.join(diff)}


def authorize(task_id: str, digest: str, direction: str) -> str:
    """Trusted operator UI only. Never register this function as a model tool."""
    control = tasks.task_directory(task_id)
    with tasks.task_lock(control):
        _, task, _ = tasks.load_task(task_id)
        if (direction not in {'apply', 'rollback'} or not isinstance(digest, str)
                or digest != task['patch_sha256'] or digest != task.get('validated_patch_sha256')):
            raise ValueError('Authorization must name the exact validated patch')
        if direction == 'apply' and task['state'] not in {'awaiting_apply', 'applying', 'applied', 'failed'}:
            raise ValueError('Review the validated patch before authorizing apply')
        if direction == 'rollback' and task['state'] not in {'applying', 'applied', 'failed', 'rolling_back', 'rollback_failed', 'rolled_back'}:
            raise ValueError('Task has no promotion to roll back')
        token = secrets.token_hex(32)
        tasks.durable_json(control / ('approval-' + direction + '.json'), {
            'patch_sha256': digest, 'token_sha256': tasks.sha(token.encode()), 'direction': direction,
            'operator_uid': os.getuid(), 'approved_at': time.time(), 'expires_at': time.time() + 600})
        return token


def check_authorization(control: Path, task: dict, token: str, direction: str) -> None:
    approval = json.loads((control / ('approval-' + direction + '.json')).read_text())
    if (approval['direction'] != direction or approval['patch_sha256'] != task['patch_sha256']
            or approval['operator_uid'] != os.getuid() or time.time() > approval['expires_at']
            or not secrets.compare_digest(approval['token_sha256'], tasks.sha(token.encode()))):
        raise PermissionError('Missing, expired or mismatched concrete approval')


def open_root(path: Path) -> int:
    if not path.is_absolute():
        raise ValueError('Registered source must be absolute')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            if part in {'.', '..'}:
                raise ValueError('Invalid registered source path')
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


@contextmanager
def parent_fd(root: int, name: str):
    fd = os.dup(root)
    try:
        for part in PurePosixPath(name).parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def snapshot_at(parent: int, leaf: str) -> dict | None:
    try:
        fd = os.open(leaf, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=parent)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > tasks.MAX_FILE or info.st_mode & 0o7000:
            raise Conflict('Target is not an ordinary bounded file')
        if info.st_uid != os.getuid() or info.st_gid != os.getgid() or os.listxattr(stream.fileno()):
            raise Conflict('Target has ownership or extended metadata this policy cannot preserve')
        data = stream.read(tasks.MAX_FILE + 1)
        if len(data) > tasks.MAX_FILE:
            raise Conflict('Target grew during conflict check')
        return {'sha256': tasks.sha(data), 'mode': stat.S_IMODE(info.st_mode)}


def snapshot(root: int, name: str) -> dict | None:
    try:
        with parent_fd(root, name) as parent:
            return snapshot_at(parent, PurePosixPath(name).name)
    except FileNotFoundError:
        return None


def image(text: str | None, mode: int) -> dict | None:
    return None if text is None else {'sha256': tasks.sha(text.encode('utf-8')), 'mode': mode}


def expected_images(patch: dict, originals: dict) -> dict:
    return {change['path']: (image(originals[change['path']]['text'], originals[change['path']]['mode']),
                            image(change['after'], originals[change['path']]['mode'])) for change in patch['changes']}


def save_operation(control: Path, task: dict) -> None:
    tasks.durable_json(control / 'task.json', task)


def create_parents(root: int, name: str, control: Path, task: dict) -> None:
    fd = os.dup(root)
    parts = []
    try:
        for part in PurePosixPath(name).parts[:-1]:
            parts.append(part)
            relative = '/'.join(parts)
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                task.setdefault('directories', {}).setdefault(relative, None)
                save_operation(control, task)
                os.mkdir(part, 0o755, dir_fd=fd)
                os.fsync(fd)
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                info = os.fstat(child)
                task['directories'][relative] = [info.st_dev, info.st_ino]
                save_operation(control, task)
            os.close(fd)
            fd = child
    finally:
        os.close(fd)


def replace_entry(parent: int, leaf: str, expected: dict | None, content: str | None,
                  mode: int, operation: dict, persist: Callable[[], None]) -> None:
    if snapshot_at(parent, leaf) != expected:
        raise Conflict('Target changed immediately before promotion: ' + leaf)
    if content is None:
        os.unlink(leaf, dir_fd=parent)
        os.fsync(parent)
        return
    temporary = operation['temporary']
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
    with os.fdopen(descriptor, 'wb') as stream:
        info = os.fstat(stream.fileno())
        operation['temporary_identity'] = [info.st_dev, info.st_ino]
        os.fsync(parent)
        persist()
        stream.write(content.encode('utf-8'))
        stream.flush()
        os.fchmod(stream.fileno(), mode)
        os.fsync(stream.fileno())
        if stat.S_IMODE(os.fstat(stream.fileno()).st_mode) != mode:
            raise Conflict('Filesystem cannot preserve the required file mode: ' + leaf)
    # Refuse inherited metadata we cannot restore before publishing the new file.
    snapshot_at(parent, temporary)
    if snapshot_at(parent, leaf) != expected:
        raise Conflict('Target changed while preparing replacement: ' + leaf)
    if expected is None:
        # Link publishes a new inode without overwriting a concurrently created file.
        os.link(temporary, leaf, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
        os.unlink(temporary, dir_fd=parent)
    else:
        os.replace(temporary, leaf, src_dir_fd=parent, dst_dir_fd=parent)
    os.fsync(parent)


def clean_temporary(parent: int, operation: dict, desired: dict | None) -> None:
    temporary = operation.get('temporary')
    if temporary is None:
        return
    existing = snapshot_at(parent, temporary)
    if existing is not None:
        info = os.stat(temporary, dir_fd=parent, follow_symlinks=False)
        identity = operation.get('temporary_identity')
        owned = [info.st_dev, info.st_ino] == identity if identity is not None else existing == desired
        if not owned:
            raise Conflict('Retained replacement file changed; preserving it: ' + temporary)
        os.unlink(temporary, dir_fd=parent)
        os.fsync(parent)


def clean_directories(root: int, task: dict) -> list[str]:
    retained = []
    for name, identity in sorted(task.get('directories', {}).items(), key=lambda item: len(item[0]), reverse=True):
        try:
            with parent_fd(root, name) as parent:
                leaf = PurePosixPath(name).name
                info = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
                if identity != [info.st_dev, info.st_ino] or not stat.S_ISDIR(info.st_mode):
                    retained.append(name)
                    continue
                os.rmdir(leaf, dir_fd=parent)
                os.fsync(parent)
        except FileNotFoundError:
            continue
        except OSError:
            retained.append(name)
    return retained


async def promote(task_id: str, token: str, *, rollback: bool = False) -> dict:
    direction = 'rollback' if rollback else 'apply'
    control = tasks.task_directory(task_id)
    with tasks.task_lock(control):
        _, task, patch = tasks.load_task(task_id)
        check_authorization(control, task, token, direction)
        final_state = 'rolled_back' if rollback else 'applied'
        if task['state'] == final_state:
            return task  # Idempotent retry must never overwrite later user edits.
        if task.get('validated_patch_sha256') != task['patch_sha256']:
            raise ValueError('Validation is not bound to this exact patch')
        if tasks.inventory(control / 'stage') != task['stage_inventory']:
            raise Conflict('Validated staging content has changed')
        states = {'applying', 'applied', 'failed', 'rolling_back', 'rollback_failed'} if rollback else {'awaiting_apply', 'applying', 'failed'}
        if task['state'] not in states:
            raise ValueError('Task state does not permit this operation')
        project = json.loads((tasks.STORE / 'projects' / (patch['project_id'] + '.json')).read_text())
        if project['source'] != task['source']:
            raise Conflict('Project registration changed')
        with (tasks.STORE / 'projects' / (patch['project_id'] + '.lock')).open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Conflict('Another task is changing this project') from None
            root = open_root(Path(task['source']))
            try:
                info = os.fstat(root)
                if [info.st_dev, info.st_ino] != [project.get('device'), project.get('inode')]:
                    raise Conflict('Registered repository directory has been replaced')
                git = await safe_git(Path(task['source']))
                head = await run_process([*git, 'rev-parse', 'HEAD'], 10)
                if head.returncode or head.output.strip() != patch['base_commit']:
                    raise Conflict('Source HEAD changed since validation')
                originals = json.loads((control / 'preimages.json').read_text())
                images = expected_images(patch, originals)
                interrupted = task.get('transaction') is not None
                # Check the whole change set before the first write.
                for name, (before, after) in images.items():
                    current = snapshot(root, name)
                    allowed = (before, after) if interrupted else ((after,) if rollback else (before,))
                    if current not in allowed:
                        raise Conflict('Conflicting user edit: ' + name)
                if rollback and not interrupted:
                    raise ValueError('Task has no recorded application to reverse')
                tasks.transition(control, task, 'rolling_back' if rollback else 'applying',
                                 transaction=task.get('transaction', {'apply': {}, 'rollback': {}}))
                operations = task['transaction'][direction]
                try:
                    for index, change in enumerate(patch['changes']):
                        name = change['path']
                        before, after = images[name]
                        expected, desired = (after, before) if rollback else (before, after)
                        text = originals[name]['text'] if rollback else change['after']
                        mode = originals[name]['mode']
                        if rollback and name in task['transaction']['apply']:
                            try:
                                with parent_fd(root, name) as parent:
                                    clean_temporary(parent, task['transaction']['apply'][name], after)
                            except FileNotFoundError:
                                pass  # An interrupted new-file operation may not have created its parent.
                        current = snapshot(root, name)
                        # Resume an operation that reached disk before its completion record.
                        if current == desired:
                            if operations.get(name, {}).get('temporary') is not None:
                                with parent_fd(root, name) as parent:
                                    clean_temporary(parent, operations[name], desired)
                            operations[name] = {**operations.get(name, {}), 'phase': 'done'}
                            save_operation(control, task)
                            continue
                        if current != expected:
                            raise Conflict('Target changed during transaction: ' + name)
                        create_parents(root, name, control, task)
                        operation = operations.setdefault(name, {'phase': 'intent',
                            'temporary': f'.omarchy-{task_id}-{direction}-{index}.tmp'})
                        save_operation(control, task)
                        with parent_fd(root, name) as parent:
                            clean_temporary(parent, operation, desired)
                            replace_entry(parent, PurePosixPath(name).name, expected, text, mode, operation,
                                          lambda: save_operation(control, task))
                            if snapshot_at(parent, PurePosixPath(name).name) != desired:
                                raise Conflict('Unexpected result after replacement: ' + name)
                        operation['phase'] = 'done'
                        save_operation(control, task)
                    retained = clean_directories(root, task) if rollback else []
                    tasks.transition(control, task, final_state, retained_directories=retained)
                except BaseException as error:
                    tasks.transition(control, task, 'rollback_failed' if rollback else 'failed',
                                     error=type(error).__name__ + ': ' + str(error))
                    raise
            finally:
                os.close(root)
    return task
