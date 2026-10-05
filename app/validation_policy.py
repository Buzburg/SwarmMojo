"""Typed validation commands; models cannot select an image, shell or executable."""
import json
from pathlib import Path
import re

from app.config import BASE_DIR
from app.container_runner import execute, ProcessResult, write_state

POLICY_VERSION = 'python-validation-v1'
IMAGE_CONFIG = BASE_DIR / 'config/worker-image.local.json'


def command_for(request: dict, workspace: Path) -> list[str]:
    if (type(request) is not dict or type(request.get('command')) is not str
            or request['command'] not in {'python.syntax', 'python.tests'}):
        raise ValueError('Unknown registered validation command')
    if request['command'] == 'python.tests':
        if set(request) != {'command'}:
            raise ValueError('python.tests does not accept arbitrary arguments')
        target = workspace / 'tests'
        if not target.is_dir() or target.is_symlink():
            raise ValueError('A real tests directory is required')
        tests = list(target.glob('test_*.py'))
        if not tests or len(tests) > 64 or any(path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024 for path in tests):
            raise ValueError('Expected 1–64 regular test_*.py files in the tests directory')
        return ['/usr/bin/python3', '-I', '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py']
    if set(request) != {'command', 'files'} or type(request['files']) is not list or not 1 <= len(request['files']) <= 64:
        raise ValueError('python.syntax requires a bounded files list')
    files = request['files']
    for name in files:
        if not isinstance(name, str) or len(name) > 512 or not re.fullmatch(r'[A-Za-z0-9_.\-/]+', name):
            raise ValueError('Invalid validation path')
        path = Path(name)
        if path.is_absolute() or path.suffix != '.py' or any(part in {'', '.', '..'} or part.startswith('-') for part in name.split('/')):
            raise ValueError('Validation requires relative Python file paths, not options')
        current = workspace
        for part in path.parts:
            current /= part
            if current.is_symlink():
                raise ValueError('Symlinks are forbidden in validation paths')
        if not current.is_file() or current.stat().st_size > 1024 * 1024:
            raise ValueError('Validation input must be a Python file up to 1 MiB')
    return ['/usr/bin/python3', '-I', '-B', '-m', 'py_compile', '--', *files]


async def validate(workspace: Path, control: Path, request: dict) -> ProcessResult:
    argv = command_for(request, workspace)
    image = json.loads(IMAGE_CONFIG.read_text())
    if (image.get('policy_version') != POLICY_VERSION
            or not re.fullmatch(r'sha256:[a-f0-9]{64}', image.get('image_id', ''))
            or not re.fullmatch(r'[a-f0-9]{64}', image.get('sandbox_sha256', ''))):
        raise ValueError('A compatible locally built sandbox image is required')
    policy_path = control / 'policy.json'
    if policy_path.exists():
        raise ValueError('Validation journal already exists')
    write_state(policy_path, {'version': POLICY_VERSION, 'request': request, 'argv': argv,
                             'image_id': image['image_id'], 'sandbox_sha256': image['sandbox_sha256'],
                             'network': 'none', 'cpus': '2', 'memory': '256m', 'timeout_seconds': 30})
    return await execute(workspace, control, image['image_id'], argv, cpus='2', memory='256m', timeout=30)
