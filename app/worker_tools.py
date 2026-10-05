"""Opt-in tool wrappers around the owned container lifecycle."""
import asyncio
import json
import os
from pathlib import Path
import shlex
import shutil
import uuid

from app import container_runner
from app.config import BASE_REPOS_DIR, TOOL_EXECUTION_TIMEOUT, WORKSPACES_DIR
from app.throttle import tool_limiter

DISABLED = 'Container execution is disabled. See SECURITY.md for experimental limitations.'


def _task_paths() -> tuple[Path, Path]:
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    control = WORKSPACES_DIR / ('task_' + uuid.uuid4().hex)
    control.mkdir(mode=0o700)
    return control, control / 'work'


def _safe_to_remove(control: Path) -> bool:
    # Before a journal exists, no container has been created or started.
    return not (control / 'container.json').exists() or container_runner.confirmed_clean(control)


@tool_limiter.guard(timeout=60.0)
async def run_sandboxed_command(image: str, command: str, cpus: str = '2.0',
                                memory: str = '4g', network: str = 'none') -> str:
    if os.getenv('ROMS_ENABLE_EXPERIMENTAL_EXECUTION') != '1':
        return DISABLED
    if network != 'none':
        raise ValueError('Worker networking must remain disabled')
    argv = shlex.split(command)
    control, workspace = _task_paths()
    workspace.mkdir(mode=0o700)
    try:
        result = await container_runner.execute(workspace, control, image, argv, cpus=cpus,
                                                memory=memory, timeout=TOOL_EXECUTION_TIMEOUT)
        return f'Task [{control.name}] (Exit Code {result.returncode}):\n{result.output[:2500]}'
    except TimeoutError:
        detail = ('container removal verified' if container_runner.confirmed_clean(control)
                  else 'no container was created')
        return f'Task [{control.name}] exceeded its deadline; {detail}.'
    except Exception as error:
        return f'Task [{control.name}] failed: {error}'
    finally:
        if _safe_to_remove(control):
            shutil.rmtree(control)


@tool_limiter.guard(timeout=60.0)
async def execute_tool_task_async(repo_name: str, tool_image: str, command: str,
                                  cpus: str = '2.0', memory: str = '4g', timeout: int = 120) -> str:
    if os.getenv('ROMS_ENABLE_EXPERIMENTAL_EXECUTION') != '1':
        return DISABLED
    base = BASE_REPOS_DIR.resolve()
    source = (base / repo_name).resolve()
    if not repo_name or source == base or not source.is_relative_to(base):
        raise ValueError('Repository must be inside the configured repository folder')
    if not (source / '.git').exists():
        return 'Repository not found in the base library.'
    argv = shlex.split(command)
    control, workspace = _task_paths()
    git = ['git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
           '-c', 'submodule.recurse=false', '-C', str(source)]
    try:
        filters = await container_runner.run_process([*git, 'config', '--name-only', '--get-regexp',
                                                      r'^filter\..*\.(smudge|clean|process|required)$'], 10)
        if filters.returncode not in (0, 1):
            raise RuntimeError('Cannot inspect repository checkout filters')
        for key in filters.output.splitlines():
            git[1:1] = ['-c', key + ('=false' if key.endswith('.required') else '=')]
        created = await container_runner.run_process([*git, 'worktree', 'add', '--detach', str(workspace), 'HEAD'], 30)
        if created.returncode:
            raise RuntimeError('Worktree creation failed: ' + created.output[-1000:])
        workspace.chmod(0o700)
        result = await container_runner.execute(workspace, control, tool_image, argv, cpus=cpus,
                                                memory=memory, timeout=timeout)
        return f'Task [{control.name}] (Exit Code {result.returncode}):\n{result.output[:2500]}'
    except TimeoutError:
        return f'Task [{control.name}] exceeded its deadline; worker cleanup completed.'
    except Exception as error:
        return f'Task [{control.name}] failed: {error}'
    finally:
        if _safe_to_remove(control):
            async def remove_worktree() -> None:
                if workspace.exists():
                    removed = await container_runner.run_process([*git, 'worktree', 'remove', '--force', str(workspace)], 20)
                    if removed.returncode:
                        (control / 'worktree-cleanup.json').write_text(json.dumps({
                            'state': 'cleanup_required', 'source': str(source), 'workspace': str(workspace),
                            'error': removed.output[-1000:]}))
                        raise container_runner.CleanupRequired(f'Worktree retained for cleanup: {control}')
                shutil.rmtree(control)
            _, interrupted = await container_runner._settle(asyncio.create_task(remove_worktree()))
            if interrupted:
                raise asyncio.CancelledError


def execute_tool_task(repo_name: str, tool_image: str, command: str,
                      cpus: str = '2.0', memory: str = '4g', timeout: int = 120) -> str:
    if os.getenv('ROMS_ENABLE_EXPERIMENTAL_EXECUTION') != '1':
        return DISABLED
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(execute_tool_task_async(repo_name, tool_image, command, cpus, memory, timeout))
    raise RuntimeError('Use execute_tool_task_async inside an async caller')
