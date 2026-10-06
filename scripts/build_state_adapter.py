"""Build the opaque RWKV state adapter against the verified installed runtime."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path.home() / '.local/share/omarchy-harness/llama.cpp')
    parser.add_argument('--runtime', type=Path, default=Path('/opt/goose-runtime/bin'))
    parser.add_argument('--output', type=Path, default=ROOT / 'build/libomarchy_state.so')
    args = parser.parse_args()
    inputs = json.loads((ROOT / 'config/build-inputs.json').read_text())
    installed = json.loads((args.runtime / 'omarchy-runtime.json').read_text())
    if (installed['revision'] != inputs['runtime']['revision'] or
            installed.get('local_patch_sha256') != inputs['runtime']['local_patch']['sha256']):
        raise ValueError('Installed runtime is not the pinned revision')
    revision = subprocess.check_output(['git', '-C', str(args.source), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != installed['revision']:
        raise ValueError('Runtime headers do not match installed runtime revision')
    header_changes = subprocess.check_output(['git', '-C', str(args.source), 'status', '--porcelain',
                                              '--untracked-files=all', '--', 'include', 'ggml/include'], text=True)
    if header_changes:
        raise ValueError('Runtime public include trees contain local changes')
    libraries = {}
    for name, expected in installed['artifacts'].items():
        if '.so' in name:
            path = args.runtime / name
            if digest(path) != expected:
                raise ValueError('Installed runtime library changed: ' + name)
            libraries[str(path.resolve())] = expected
    for name in ['include/llama.h', 'ggml/include/ggml.h', 'ggml/include/ggml-backend.h']:
        pinned = subprocess.check_output(['git', '-C', str(args.source), 'show', revision + ':' + name])
        if (args.source / name).read_bytes() != pinned:
            raise ValueError('Local runtime header changed: ' + name)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'native/rwkv_state.cpp'
    subprocess.run(['c++', '-std=c++17', '-O2', '-fPIC', '-shared', str(source),
        '-I' + str(args.source / 'include'), '-I' + str(args.source / 'ggml/include'),
        '-L' + str(args.runtime), '-Wl,-rpath,' + str(args.runtime), '-lllama', '-lggml',
        '-o', str(args.output)], check=True)
    args.output.with_suffix('.json').write_text(json.dumps({'abi': 1, 'revision': revision,
        'source_sha256': digest(source), 'library_sha256': digest(args.output),
        'header_sha256': digest(ROOT / 'native/rwkv_state.h'),
        'runtime_libraries': libraries}, indent=2) + '\n')
    print(args.output)


if __name__ == '__main__':
    main()
