"""Install an already built/verified model worker; never compile during installation."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

from app.native_model_worker import ROOT, digest, worker_manifest
from app.workbench.state import verify_inputs


def replace(path: Path, data: bytes, mode: int) -> None:
    staged = path.with_name(path.name + '.' + uuid.uuid4().hex + '.new')
    with staged.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    staged.chmod(mode)
    os.replace(staged, path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Install the prebuilt worker as root inside Omarchy')
    candidate = args.candidate.resolve()
    manifest = worker_manifest(candidate)
    model = ROOT.parent / 'rwkv7-g1g-2.9b-Q4_K_M.gguf'
    identity = verify_inputs(Path(manifest['adapter']), model, '2.9b')
    if identity['adapter_sha256'] != manifest['adapter_sha256']:
        raise ValueError('Candidate adapter changed')
    destination = Path('/opt/roms-env/bin/omarchy-model-worker')
    dropin = Path('/etc/systemd/system/omarchy-broker.service.d/native-chat.conf')
    previous = [path for path in (destination, destination.with_suffix('.json'), dropin) if path.exists()]
    backup = None
    if previous:
        backup = ROOT.parent / 'deployment/backups' / ('native-worker-before-' + uuid.uuid4().hex)
        backup.mkdir(parents=True, exist_ok=False)
        for path in previous:
            shutil.copy2(path, backup / path.name)
    dropin.parent.mkdir(parents=True, exist_ok=True)
    replace(destination, candidate.read_bytes(), 0o755)
    replace(destination.with_suffix('.json'), candidate.with_suffix('.json').read_bytes(), 0o644)
    content = ('[Service]\n' +
               'Environment=' + json.dumps('OMARCHY_NATIVE_CHAT_BINARY=' + str(destination)) + '\n' +
               'Environment=' + json.dumps('OMARCHY_NATIVE_MODEL=' + str(model)) + '\n')
    replace(dropin, content.encode(), 0o644)
    worker_manifest(destination)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'restart', 'omarchy-broker'], check=True)
    print(json.dumps({'worker': str(destination), 'sha256': digest(destination),
                      'backup': str(backup) if backup else None}))


if __name__ == '__main__':
    main()
