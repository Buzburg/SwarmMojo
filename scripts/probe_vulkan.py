"""Run an isolated, authenticated Vulkan candidate and retain placement/failure evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import time

import httpx
from scripts.download_rwkv7 import MANIFEST, verify_file
from scripts.verify_model_compatibility import ROOT, verify


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-bin', type=Path, required=True)
    parser.add_argument('--device', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    inputs = json.loads(MANIFEST.read_text())
    build = json.loads((args.runtime_bin / 'omarchy-runtime.json').read_text())
    assert build['revision'] == inputs['runtime']['revision'] and build['backend'] == 'vulkan'
    assert build['local_patch_sha256'] == inputs['runtime']['local_patch']['sha256']
    for name, expected in build['artifacts'].items():
        assert Path(name).name == name
        assert hashlib.sha256((args.runtime_bin / name).read_bytes()).hexdigest() == expected
    spec = inputs['models']['2.9b']
    model = ROOT.parent / spec['filename']
    report = {'runtime': build, 'device_requested': args.device, 'model_identity': verify_file(model, spec), 'passed': False}
    log = args.output.with_suffix('.log')
    with socket.socket() as address:
        address.bind(('127.0.0.1', 0))
        port = address.getsockname()[1]
    key = secrets.token_hex(32)
    env = dict(os.environ, LLAMA_API_KEY=key, LD_LIBRARY_PATH=str(args.runtime_bin))
    command = [str(args.runtime_bin / 'llama-server'), '-m', str(model), '--host', '127.0.0.1', '--port', str(port),
               '--device', args.device, '-ngl', '999', '-c', '4096', '-np', '1', '-b', '64', '-ub', '64', '-t', '4', '-lv', '4',
               '--no-warmup', '--jinja', '--reasoning', 'auto', '--reasoning-format', 'deepseek',
               '--chat-template-file', str(ROOT / 'config/rwkv-user-assistant.jinja'), '--alias', 'goose-2.9b']
    with log.open('x') as output:
        process = subprocess.Popen(command, env=env, stdout=output, stderr=subprocess.STDOUT)
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}', headers={'Authorization': 'Bearer ' + key},
                              trust_env=False, timeout=90) as client:
                deadline = time.monotonic() + 180
                while True:
                    if process.poll() is not None:
                        raise RuntimeError(f'Candidate exited during startup: {process.returncode}')
                    try:
                        if client.get('/health', timeout=2).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Candidate did not become ready within 180 seconds')
                    time.sleep(0.2)
                report['compatibility'] = verify(client)
        except (OSError, ValueError, RuntimeError, TimeoutError, AssertionError, httpx.HTTPError) as error:
            report['failure'] = str(error)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
            report['process_reaped'] = process.poll() is not None
            report['exit_code'] = process.returncode
    diagnostic = log.read_text(errors='replace')
    placement = re.findall(r'offloaded (\d+)/(\d+) layers to GPU', diagnostic)
    report['placement'] = [{'offloaded': int(a), 'layers': int(b)} for a, b in placement]
    report['passed'] = (report.get('compatibility', {}).get('passed') is True and bool(placement) and
                        int(placement[-1][0]) == int(placement[-1][1]) > 0 and report['process_reaped'])
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report.get(key) for key in ('passed', 'failure', 'placement', 'process_reaped', 'exit_code')}))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
