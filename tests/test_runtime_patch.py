"""Exact patch provenance and preservation of independently edited build sources."""
import hashlib
import subprocess

import pytest

from scripts import build_llama


@pytest.fixture
def source(tmp_path, monkeypatch):
    root = tmp_path / 'runtime'
    root.mkdir()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()
    git('init', '-q')
    git('remote', 'add', 'origin', build_llama.REPOSITORY)
    target = root / 'tools/server/server-queue.cpp'
    target.parent.mkdir(parents=True)
    target.write_text('before\n')
    (root / '.gitignore').write_text('build-cpu/\n')
    git('add', '.')
    git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'base')
    revision = git('rev-parse', 'HEAD')
    target.write_text('after\n')
    patch = tmp_path / 'fixture.patch'
    patch.write_text(git('diff') + '\n')
    target.write_text('before\n')
    spec = {'path': patch.name, 'target': 'tools/server/server-queue.cpp',
            'sha256': hashlib.sha256(patch.read_bytes()).hexdigest(),
            'before_sha256': hashlib.sha256(b'before\n').hexdigest(),
            'after_sha256': hashlib.sha256(b'after\n').hexdigest()}
    monkeypatch.setattr(build_llama, 'ROOT', tmp_path)
    monkeypatch.setattr(build_llama, 'REVISION', revision)
    monkeypatch.setattr(build_llama, 'INPUTS', {'runtime': {'local_patch': spec}})
    return root, target, patch


def test_exact_patch_is_isolated_and_reusable_with_ignored_build_outputs(source):
    root, original, _ = source
    prepared = build_llama.patched_source(root)
    assert original.read_text() == 'before\n'
    assert (prepared / 'tools/server/server-queue.cpp').read_text() == 'after\n'
    build_llama.verify_clean_source(root)
    (prepared / 'build-cpu').mkdir()
    (prepared / 'build-cpu/artifact').write_text('fixture output')
    assert build_llama.patched_source(root) == prepared


@pytest.mark.parametrize('changed', ['patch', 'preimage'])
def test_wrong_inputs_are_rejected_before_worktree_creation(source, changed):
    root, original, patch = source
    (patch if changed == 'patch' else original).write_text('changed input\n')
    with pytest.raises(RuntimeError, match='digest|preimage'):
        build_llama.patched_source(root)
    assert not list(root.parent.glob('llama.cpp-patched-*'))


@pytest.mark.parametrize('changed', ['target', 'untracked', 'symlink'])
def test_modified_prepared_tree_is_preserved_and_rejected(source, changed):
    root, _, _ = source
    prepared = build_llama.patched_source(root)
    if changed == 'symlink':
        moved = prepared.with_name('retained-tree')
        prepared.rename(moved)
        prepared.symlink_to(moved, target_is_directory=True)
    else:
        path = prepared / ('tools/server/server-queue.cpp' if changed == 'target' else 'unrelated.txt')
        path.write_text('preserve user edit\n')
    with pytest.raises(RuntimeError):
        build_llama.patched_source(root)
    if changed == 'symlink':
        assert prepared.is_symlink()
    else:
        assert path.read_text() == 'preserve user edit\n'


def test_reviewed_manifest_pins_patch_bytes():
    spec = build_llama.INPUTS['runtime']['local_patch']
    assert hashlib.sha256((build_llama.ROOT / spec['path']).read_bytes()).hexdigest() == spec['sha256']
    assert spec['before_sha256'] != spec['after_sha256']
