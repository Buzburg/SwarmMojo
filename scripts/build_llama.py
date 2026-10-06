"""Build the pinned GGUF runtime on Linux without installing a service."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]
INPUTS = json.loads((ROOT / 'config/build-inputs.json').read_text())
REVISION = INPUTS['runtime']['revision']
REPOSITORY = INPUTS['runtime']['repository']


def verify_clean_source(root: Path) -> None:
    if subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain']):
        raise RuntimeError('Runtime source has local changes; refusing to build or checkout')
    origin = subprocess.check_output(['git', '-C', str(root), 'remote', 'get-url', 'origin'], text=True).strip()
    if origin != REPOSITORY:
        raise RuntimeError('Runtime source origin does not match the pinned input record')


def patched_source(root: Path) -> Path:
    spec = INPUTS['runtime']['local_patch']
    patch = ROOT / spec['path']
    if hashlib.sha256(patch.read_bytes()).hexdigest() != spec['sha256']:
        raise RuntimeError('Runtime patch does not match its reviewed digest')
    target = spec['target']
    if hashlib.sha256((root / target).read_bytes()).hexdigest() != spec['before_sha256']:
        raise RuntimeError('Runtime patch preimage does not match the pinned source')
    prepared = root.with_name('llama.cpp-patched-' + spec['sha256'][:12])
    if prepared.is_symlink():
        raise RuntimeError('Runtime build source cannot be a symlink')
    if not prepared.exists():
        subprocess.run(['git', '-C', str(root), 'worktree', 'add', '--detach', str(prepared), REVISION], check=True)
        subprocess.run(['git', '-C', str(prepared), 'apply', '--check', str(patch)], check=True)
        subprocess.run(['git', '-C', str(prepared), 'apply', str(patch)], check=True)
    head = subprocess.check_output(['git', '-C', str(prepared), 'rev-parse', 'HEAD'], text=True).strip()
    changes = subprocess.check_output(['git', '-C', str(prepared), 'status', '--porcelain', '--untracked-files=all'], text=True)
    if (head != REVISION or changes != f' M {target}\n'
            or hashlib.sha256((prepared / target).read_bytes()).hexdigest() != spec['after_sha256']):
        raise RuntimeError('Runtime build source differs from the exact reviewed patch')
    return prepared


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=('cpu', 'vulkan'), default='cpu')
    backend = parser.parse_args().backend
    root = Path.home() / ".local/share/omarchy-harness/llama.cpp"
    root.parent.mkdir(parents=True, exist_ok=True)
    if not root.exists():
        subprocess.run(["git", "init", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "remote", "add", "origin",
                        REPOSITORY], check=True)
    verify_clean_source(root)
    actual = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                            capture_output=True, text=True)
    if actual.stdout.strip() != REVISION:
        subprocess.run(["git", "-C", str(root), "fetch", "--depth=1", "origin", REVISION], check=True)
        subprocess.run(["git", "-C", str(root), "checkout", "--detach", REVISION], check=True)
    verified = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    if verified != REVISION:
        raise RuntimeError('Runtime source revision does not match the pinned input record')
    verify_clean_source(root)
    root = patched_source(root)
    build = root / ('build-' + backend)
    if any(path.exists() or path.is_symlink() for path in (root / 'tools/ui/dist', build / 'tools/ui/dist')):
        raise RuntimeError('Preserve and relocate existing UI assets before building the headless runtime')
    subprocess.run(["cmake", "-S", str(root), "-B", str(build),
                    "-DCMAKE_BUILD_TYPE=Release", '-DGGML_VULKAN=' + ('ON' if backend == 'vulkan' else 'OFF'),
                    "-DLLAMA_CURL=OFF", "-DLLAMA_BUILD_TESTS=OFF",
                    "-DLLAMA_BUILD_UI=OFF", "-DLLAMA_USE_PREBUILT_UI=OFF"], check=True)
    subprocess.run(["cmake", "--build", str(build), "--target", "llama-server",
                    "llama-cli", "-j", "3"], check=True)
    artifacts = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in sorted((build / 'bin').iterdir()) if path.is_file() and path.name != 'omarchy-runtime.json'}
    (build / 'bin/omarchy-runtime.json').write_text(json.dumps({
        'schema_version': 1, 'revision': REVISION, 'local_patch_sha256': INPUTS['runtime']['local_patch']['sha256'],
        'backend': backend, 'embedded_ui': False, 'artifacts': artifacts}, indent=2) + '\n')
    print(f"Built pinned runtime {REVISION}: {build / 'bin'}", flush=True)


if __name__ == "__main__":
    main()
