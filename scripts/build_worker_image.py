"""Package the tested native sandbox and installed Python toolchain without network access."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    sandbox = Path('/opt/roms-env/bin/staging-sandbox')
    python = Path('/usr/bin/python3').resolve(strict=True)
    if os.geteuid() == 0 or not sandbox.is_file():
        raise SystemExit('Build as the normal Linux user after compiling staging-sandbox')
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(Path.home()), 'LANG': 'C.UTF-8'}
    for key in ('XDG_RUNTIME_DIR', 'DBUS_SESSION_BUS_ADDRESS'):
        if key in os.environ:
            env[key] = os.environ[key]
    version = subprocess.check_output([str(python), '-c', 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'],
                                      env=env, text=True).strip()
    stdlib = Path('/usr/lib') / ('python' + version)
    output = root.parent / 'deployment/packages/worker-image.manifest.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='omarchy-worker-build-') as temporary:
        context = Path(temporary)
        filesystem = context / 'rootfs'
        binaries, libraries = filesystem / 'usr/bin', filesystem / 'usr/lib'
        binaries.mkdir(parents=True)
        libraries.mkdir(parents=True)
        shutil.copy2(sandbox, binaries / 'omarchy-sandbox')
        shutil.copy2(python, binaries / 'python3')
        shutil.copytree(stdlib, libraries / stdlib.name,
                        ignore=shutil.ignore_patterns('__pycache__', 'site-packages', 'test', 'tests',
                                                     'idlelib', 'ensurepip', 'tkinter', 'turtledemo'))
        dependencies: dict[str, Path] = {}
        for binary in [sandbox, python, *stdlib.glob('lib-dynload/*.so')]:
            result = subprocess.run(['ldd', str(binary)], capture_output=True, text=True, check=True, env=env)
            for match in re.finditer(r'(?:=>\s+)?(/[^\n]*?)\s+\(0x[0-9a-f]+\)', result.stdout):
                dependency = Path(match[1].strip())
                # Prefer the current Arch library over an older embedded compiler search path.
                system = Path('/usr/lib') / dependency.name
                dependencies[dependency.name] = system if system.is_file() else dependency
        for name, dependency in dependencies.items():
            shutil.copy2(dependency.resolve(strict=True), libraries / name)
        (filesystem / 'lib').symlink_to('usr/lib')
        (filesystem / 'lib64').symlink_to('usr/lib')
        (filesystem / 'usr/lib64').symlink_to('lib')
        (filesystem / 'bin').symlink_to('usr/bin')
        (filesystem / 'etc').mkdir()
        (filesystem / 'etc/passwd').write_text('root:x:0:0:root:/nonexistent:/nonexistent\nworker:x:1000:1000:worker:/workspace:/nonexistent\n')
        (filesystem / 'etc/group').write_text('root:x:0:\nworker:x:1000:\n')
        for name in ('workspace', 'tmp', 'proc', 'dev'):
            (filesystem / name).mkdir()
        files = {str(path.relative_to(filesystem)): digest(path)
                 for path in sorted(filesystem.rglob('*')) if path.is_file() and not path.is_symlink()}
        (context / 'Containerfile').write_text(
            'FROM scratch\nCOPY rootfs/ /\nENV PATH=/usr/bin:/bin LANG=C.UTF-8\n'
            'ENTRYPOINT ["/usr/bin/omarchy-sandbox", "/workspace", "--"]\n')
        result = subprocess.run(['podman', '--remote=false', '--log-level=error', 'build', '--network=none',
            '--pull=never', '--no-cache', '--iidfile', str(context / 'image-id'),
            '-t', 'localhost/omarchy-worker:python', str(context)], env=env, capture_output=True, text=True, timeout=180)
        if result.returncode:
            raise RuntimeError(result.stderr[-3000:] + result.stdout[-3000:])
        identity = (context / 'image-id').read_text().strip()
        manifest = {'image_id': identity, 'python': version, 'sandbox_sha256': digest(sandbox),
                    'files': files, 'network_during_build': False}
        output.write_text(json.dumps(manifest, indent=2))
        (root / 'config/worker-image.local.json').write_text(json.dumps({
            'image_id': identity, 'sandbox_sha256': manifest['sandbox_sha256'],
            'policy_version': 'python-validation-v1'}, indent=2))
        print(json.dumps({'image_id': identity, 'files': len(files), 'manifest': str(output)}, indent=2))


if __name__ == '__main__':
    main()
