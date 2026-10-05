"""Git operations that cannot run repository hooks, filters or lazy fetches."""
from pathlib import Path

from app.container_runner import run_process


async def safe_git(source: Path) -> list[str]:
    command = ['git', '-c', f'safe.directory={source}', '-c', 'core.hooksPath=/dev/null',
               '-c', 'core.fsmonitor=false', '-c', 'submodule.recurse=false', '-C', str(source)]
    filters = await run_process([*command, 'config', '--name-only', '--get-regexp',
                                 r'^filter\..*\.(smudge|clean|process|required)$'], 10)
    if filters.returncode not in (0, 1):
        raise RuntimeError('Cannot inspect repository checkout filters')
    for key in filters.output.splitlines():
        command[1:1] = ['-c', key + ('=false' if key.endswith('.required') else '=')]
    return command
