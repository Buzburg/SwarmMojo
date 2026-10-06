"""Reconcile recorded validation containers without applying or deleting project work."""
import asyncio
import json
import os
from pathlib import Path
import re
import shutil
import stat
from time import monotonic

from app import patch_tasks
from app.container_runner import cleanup, confirmed_clean


def summary(report: dict | None) -> dict | None:
    if report is None:
        return None
    return {'counts': {key: len(value) for key, value in report.items()},
            'blocked': report['blocked'][:16], 'busy': report['busy'][:16],
            'report_file': str(patch_tasks.STORE / 'recovery.json')}


def private_directory(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('Recovery directory must be private, owned and not a symlink')


def candidates(root: Path, pattern: str) -> list[Path]:
    if not root.exists():
        return []
    result = []
    with os.scandir(root) as entries:
        for index, entry in enumerate(entries):
            if index >= 10000:
                raise ValueError('Recovery inventory exceeds 10000 entries')
            if re.fullmatch(pattern, entry.name):
                result.append(Path(entry.path))
                if len(result) > 1000:
                    raise ValueError('Recovery inventory exceeds 1000 task directories')
    return sorted(result)


async def recover_task(control: Path) -> bool:
    private_directory(control)
    with patch_tasks.task_lock(control):
        metadata = json.loads((control / 'task.json').read_text())
        if metadata['state'] not in {'validating', 'cleanup_required'}:
            return False
        _, task, patch = patch_tasks.load_task(control.name)
        try:
            for index in range(len(patch['checks'])):
                check = control / f'check-{index}'
                if check.exists():
                    private_directory(check)
                    journal = check / 'container.json'
                    if journal.exists():
                        if journal.is_symlink():
                            raise ValueError('Recovery journal cannot be a symlink')
                        state = json.loads(journal.read_text())
                        if state['workspace'] != str(control / 'stage'):
                            raise ValueError('Container journal does not belong to this stage')
                        await cleanup(check)
                        if not confirmed_clean(check):
                            raise RuntimeError('Container absence was not verified')
            patch_tasks.transition(control, task, 'interrupted',
                error='Validation was interrupted; recorded containers cleaned. Stage and evidence retained.')
            return True
        except BaseException as error:
            patch_tasks.transition(control, task, 'cleanup_required',
                                  error='Recovery incomplete: ' + type(error).__name__ + ': ' + str(error)[:512])
            raise


async def recover_probe(base: Path) -> str:
    private_directory(base)
    with patch_tasks.task_lock(base):
        marker = base / 'owner.json'
        control = base / 'control'
        if not marker.is_file():
            if (control / 'container.json').exists():
                raise ValueError('Unidentified probe has a container journal; manual inspection required')
            return 'retained_unidentified'
        if marker.is_symlink() or json.loads(marker.read_text()) != {'kind': 'capability', 'version': 1, 'id': base.name}:
            raise ValueError('Invalid capability ownership record')
        if control.exists():
            private_directory(control)
            journal = control / 'container.json'
            if journal.exists():
                if journal.is_symlink():
                    raise ValueError('Probe journal cannot be a symlink')
                state = json.loads(journal.read_text())
                if state['workspace'] != str(base / 'stage'):
                    raise ValueError('Probe container journal does not belong to this stage')
                await cleanup(control)
                if not confirmed_clean(control):
                    raise RuntimeError('Probe container absence was not verified')
        shutil.rmtree(base)
        return 'cleaned'


async def reconcile(workspaces: Path) -> dict:
    report = {'tasks_interrupted': [], 'probes_cleaned': [], 'busy': [], 'retained': [], 'blocked': []}
    deadline = monotonic() + 45
    try:
        async with asyncio.timeout(45):
            groups = [(candidates(patch_tasks.STORE / 'tasks', r'[a-f0-9]{32}'), False),
                      (candidates(workspaces, r'capability-[A-Za-z0-9_-]{6,64}'), True)]
            for paths, probe in groups:
                for path in paths:
                    if monotonic() >= deadline:
                        raise TimeoutError('Recovery inventory deadline exceeded')
                    try:
                        if probe:
                            result = await recover_probe(path)
                            report['probes_cleaned' if result == 'cleaned' else 'retained'].append(path.name)
                        elif await recover_task(path):
                            report['tasks_interrupted'].append(path.name)
                    except FileNotFoundError:
                        if path.exists():
                            report['blocked'].append({'id': path.name, 'reason': 'Required recovery record is missing'})
                    except RuntimeError as error:
                        if str(error) == 'Task is already being modified':
                            report['busy'].append(path.name)
                        else:
                            report['blocked'].append({'id': path.name, 'reason': str(error)[:512]})
                    except (OSError, ValueError, KeyError, TypeError) as error:
                        report['blocked'].append({'id': path.name, 'reason': str(error)[:512]})
    except (TimeoutError, OSError, ValueError) as error:
        report['blocked'].append({'id': 'inventory', 'reason': type(error).__name__ + ': ' + str(error)[:512]})
    patch_tasks.STORE.mkdir(parents=True, exist_ok=True, mode=0o700)
    patch_tasks.durable_json(patch_tasks.STORE / 'recovery.json', report)
    return report
