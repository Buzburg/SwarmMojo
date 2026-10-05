"""Retry recorded worker-container cleanup, preserving the retained workspace."""
import argparse
import asyncio
from pathlib import Path
import re

from app.config import WORKSPACES_DIR
from app.container_runner import cleanup


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task', help='task_ followed by the ID reported by the tool')
    args = parser.parse_args()
    if not re.fullmatch(r'task_[a-f0-9]{32}', args.task):
        parser.error('Expected a task ID, not an arbitrary path')
    base = WORKSPACES_DIR.resolve()
    control = (base / args.task).resolve(strict=True)
    if control.parent != base:
        parser.error('Task journal must remain inside the configured workspace directory')
    asyncio.run(cleanup(control))
    print(f'Container absence verified. Retained files remain available at {control}.')


if __name__ == '__main__':
    main()
