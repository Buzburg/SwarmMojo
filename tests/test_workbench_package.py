"""Verify the actual source archive, including the adapter's build inputs."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

import pytest

from scripts import package_workbench


@pytest.fixture
def source_package(tmp_path: Path) -> Path:
    package = tmp_path / 'source package.tar.gz'
    subprocess.run([sys.executable, '-m', 'scripts.package_workbench', str(package)],
                   cwd=package_workbench.ROOT, check=True, capture_output=True, text=True, timeout=30)
    return package


def entries(package: Path) -> dict[str, bytes]:
    with tarfile.open(package, 'r:gz') as archive:
        return {member.name: archive.extractfile(member).read() for member in archive.getmembers()}


def rewrite(package: Path, contents: dict[str, bytes]) -> None:
    with tarfile.open(package, 'w:gz') as archive:
        for name, data in contents.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))


def test_archive_contains_adapter_rebuild_sources(source_package: Path) -> None:
    package_workbench.verify(source_package)
    contents = entries(source_package)
    required = {'native/rwkv_state.cpp', 'native/rwkv_state.h', 'scripts/build_state_adapter.py',
                'config/build-inputs.json', 'scripts/build_llama.py', 'config/llama-cancellation.patch'}
    assert required <= contents.keys()
    for name in required:
        assert contents[name] == (package_workbench.ROOT / name).read_bytes()
    inputs = json.loads(contents['config/build-inputs.json'])
    patch = inputs['runtime']['local_patch']
    assert hashlib.sha256(contents[patch['path']]).hexdigest() == patch['sha256']
    assert not any(name.startswith(('data/', 'packaging/')) or name.endswith(('.gguf', '.env'))
                   for name in contents)


@pytest.mark.parametrize('missing', ['native/rwkv_state.h', 'config/build-inputs.json'])
def test_complete_manifest_cannot_hide_missing_build_input(source_package: Path, missing: str) -> None:
    contents = entries(source_package)
    del contents[missing]
    manifest = json.loads(contents['WORKBENCH-SHA256.json'])
    del manifest[missing]
    contents['WORKBENCH-SHA256.json'] = json.dumps(manifest).encode()
    rewrite(source_package, contents)
    with pytest.raises(ValueError, match='missing required adapter build sources'):
        package_workbench.verify(source_package)


def test_archive_still_rejects_tampered_bytes(source_package: Path) -> None:
    contents = entries(source_package)
    contents['native/rwkv_state.h'] += b'\n/* tampered */\n'
    rewrite(source_package, contents)
    with pytest.raises(ValueError, match='integrity failure'):
        package_workbench.verify(source_package)


def test_archive_still_rejects_parent_paths(source_package: Path) -> None:
    contents = entries(source_package)
    contents['../outside'] = b'fixture'
    rewrite(source_package, contents)
    with pytest.raises(ValueError, match='unsupported paths'):
        package_workbench.verify(source_package)
