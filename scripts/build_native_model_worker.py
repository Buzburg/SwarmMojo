"""Build the Mojo model worker and bind it to the reviewed adapter/source identities."""
import argparse
import json
from pathlib import Path
import subprocess

from app.native_model_worker import ROOT, digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adapter', type=Path, default=ROOT / 'build/libomarchy_state.so')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    adapter = args.adapter.resolve()
    manifest = json.loads(adapter.with_suffix('.json').read_text())
    for field, path in [('source_sha256', ROOT / 'native/rwkv_state.cpp'),
                        ('header_sha256', ROOT / 'native/rwkv_state.h'), ('library_sha256', adapter)]:
        if digest(path) != manifest[field]:
            raise ValueError('Native adapter input changed: ' + field)
    for path, expected in manifest['runtime_libraries'].items():
        if digest(Path(path)) != expected:
            raise ValueError('Native runtime library changed')
    sources = ['app_mojo/native_model_worker.mojo', 'app_mojo/rwkv_engine.mojo',
               'app/native_model_worker.py', 'app/workbench/state.py', 'config/rwkv-user-assistant.jinja']
    before = {name: digest(ROOT / name) for name in sources}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['mojo', 'build', str(ROOT / sources[0]), '-I', str(ROOT),
                    '-Xlinker', str(adapter), '--Werror', '-o', str(args.output)], check=True)
    if any(digest(ROOT / name) != sha for name, sha in before.items()):
        raise ValueError('Worker source changed during compilation')
    args.output.with_suffix('.json').write_text(json.dumps({'version': 1, 'sha256': digest(args.output),
        'sources': before, 'adapter': str(adapter), 'adapter_sha256': manifest['library_sha256']}, indent=2) + '\n')
    print(args.output)


if __name__ == '__main__':
    main()
