"""Package the integration's source and verify every packaged byte; no models or secrets."""
import argparse
import hashlib
import io
import json
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sources() -> list[Path]:
    files = [p for p in (ROOT / 'app/workbench').rglob('*') if p.is_file() and
             '__pycache__' not in p.parts and p.suffix != '.pyc']
    files += [ROOT / name for name in ['.gitattributes', 'native/rwkv_state.cpp', 'scripts/build_state_adapter.py',
        'scripts/workbench.py', 'scripts/verify_workbench.py', 'scripts/package_workbench.py',
        'scripts/project_workshop.py', 'requirements-workbench.txt', 'workbench.workflow.json', 'docs/repository-integrations.md']]
    files += list((ROOT / 'tests').glob('test_workbench_*.py'))
    return sorted(files)


def verify(path: Path) -> None:
    with tarfile.open(path, 'r:gz') as archive:
        members = archive.getmembers()
        if any(not item.isfile() or item.name.startswith('/') or '..' in Path(item.name).parts for item in members):
            raise ValueError('Package contains unsupported paths or file types')
        if len({item.name for item in members}) != len(members):
            raise ValueError('Package contains duplicate paths')
        manifest_stream = archive.extractfile('WORKBENCH-SHA256.json')
        if manifest_stream is None:
            raise ValueError('Missing package manifest')
        manifest = json.load(manifest_stream)
        if set(manifest) != {item.name for item in members} - {'WORKBENCH-SHA256.json'}:
            raise ValueError('Package membership differs from the manifest')
        for name, expected in manifest.items():
            stream = archive.extractfile(name)
            if stream is None:
                raise ValueError('Missing package entry: ' + name)
            data = stream.read()
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError('Package integrity failure: ' + name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if not args.verify:
        entries = {p.relative_to(ROOT).as_posix(): p.read_bytes() for p in sources()}
        entries['WORKBENCH-SHA256.json'] = json.dumps({name: hashlib.sha256(data).hexdigest()
            for name, data in entries.items()}, indent=2).encode()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(args.output, 'w:gz') as archive:
            for name, data in entries.items():
                info = tarfile.TarInfo(name)
                info.size, info.mode = len(data), 0o644
                archive.addfile(info, io.BytesIO(data))
    verify(args.output)
    print('Verified integration source package: ' + str(args.output))


if __name__ == '__main__':
    main()
