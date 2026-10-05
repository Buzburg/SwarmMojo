"""Verify the WSL test-build profile; unavailable required checks fail closed."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def wait_for_services(command: list[str], root: Path, env: dict[str, str], timeout: float = 90) -> subprocess.CompletedProcess:
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Local model and ROMS did not become ready within the startup deadline')
        try:
            result = subprocess.run(command, cwd=root, env=env, text=True, capture_output=True,
                                    timeout=min(10, remaining))
            if result.returncode == 0:
                status = json.loads(result.stdout)
                if status.get('rwkv7') == 'ready' and status.get('roms') == 'ready':
                    return result
        except subprocess.TimeoutExpired:
            pass
        time.sleep(min(1, max(0, deadline - time.monotonic())))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true', help='Check code only, without running services')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    prefix = Path(os.getenv('ROMS_PYTHON_PREFIX', str(root / '.pixi/envs/default')))
    binary = Path(os.getenv('OMARCHY_BROKER_BINARY', str(prefix / 'bin/omarchy-broker')))
    suites = ['release_safety', 'memory', 'context', 'retrieval_quality', 'ingestion_quality',
              'tools_quality', 'throttle', 'broker_actions', 'document_identity', 'source_library', 'build_readiness']
    checks = [
        ('ROMS offline regressions', [sys.executable, '-m', 'pytest',
            *[f'tests/test_{name}.py' for name in suites], '-q', '--tb=short']),
        ('Compiled native broker', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests',
                                    '-p', 'test_omarchy_broker.py', '-q']),
    ]
    if not args.offline:
        checks.append(('Live model and ROMS', ['/usr/local/bin/goose', '--status']))
    failed = 0
    env = dict(os.environ, OMARCHY_BROKER_BINARY=str(binary))
    print('WSL test build. Tool execution, training and full desktop are not certified.')
    for name, command in checks:
        try:
            if name == 'Compiled native broker' and not binary.is_file():
                raise FileNotFoundError(f'Required current-build artifact missing: {binary}')
            result = (wait_for_services(command, root, env) if name == 'Live model and ROMS' else
                      subprocess.run(command, cwd=root, env=env, text=True, capture_output=True, timeout=180))
            passed = result.returncode == 0
            if name == 'Live model and ROMS' and passed:
                status = json.loads(result.stdout)
                passed = status.get('rwkv7') == 'ready' and status.get('roms') == 'ready'
            print(f'{"PASS" if passed else "FAIL"}: {name}')
            print((result.stdout + result.stderr)[-6000:])
            failed += not passed
        except (OSError, subprocess.TimeoutExpired, ValueError) as error:
            print(f'INCOMPLETE: {name}: {error}')
            failed += 1
    print(f'{len(checks) - failed}/{len(checks)} required checks passed')
    raise SystemExit(1 if failed else 0)


if __name__ == '__main__':
    main()
