import json

import pytest
from app.workbench.builds import run_build
from app.workbench.receipts import Collector


def test_sealed_receipts_detect_edits_and_tail_removal(tmp_path):
    collector = Collector(tmp_path / 'private')
    receipt = collector.record('fixture', [{'step': 1}, {'step': 2}])
    assert collector.verify(receipt['id'])['valid']
    log = collector.root / 'runs' / receipt['id'] / 'events.jsonl'
    original = log.read_bytes()
    log.write_bytes(original.replace(b'"step":1', b'"step":9'))
    assert not collector.verify(receipt['id'])['valid']
    log.write_bytes(original.splitlines(keepends=True)[0])
    assert not collector.verify(receipt['id'])['valid']


def test_interrupted_receipt_has_no_verified_checkpoint(tmp_path):
    collector = Collector(tmp_path / 'private')
    def interrupted():
        yield {'step': 1}
        raise RuntimeError('collector interrupted')
    with pytest.raises(RuntimeError):
        collector.record('interrupted', interrupted())
    run = next((collector.root / 'runs').iterdir())
    assert not collector.verify(run.name)['valid']


def test_collector_rejects_symlink_and_public_storage(tmp_path):
    public = tmp_path / 'public'
    public.mkdir(mode=0o755)
    with pytest.raises(ValueError):
        Collector(public)
    (tmp_path / 'link').symlink_to(public, target_is_directory=True)
    with pytest.raises(ValueError):
        Collector(tmp_path / 'link')


def test_real_build_reuse_and_input_change_invalidation(tmp_path):
    workspace = tmp_path / 'build'
    workspace.mkdir()
    (workspace / 'input.txt').write_text('first')
    (workspace / 'build.py').write_text('from pathlib import Path\nPath("out.txt").write_text(Path("input.txt").read_text())\n')
    (workspace / 'verify.py').write_text('from pathlib import Path\nassert Path("out.txt").read_text() == Path("input.txt").read_text()\n')
    manifest = {'version': 1, 'max_seconds': 20, 'steps': [{'id': 'copy',
        'command': ['{python}', 'build.py'], 'verify': ['{python}', 'verify.py'],
        'needs': [], 'inputs': ['input.txt', 'build.py', 'verify.py'],
        'outputs': ['out.txt'], 'timeout_seconds': 5, 'cache': True}]}
    path = workspace / 'workflow.json'
    path.write_text(json.dumps(manifest))
    collector = Collector(tmp_path / 'private')
    first = run_build(path, collector)
    second = run_build(path, collector)
    assert first['workflow']['steps']['copy']['status'] == 'passed'
    assert second['workflow']['steps']['copy']['status'] == 'reused'
    (workspace / 'input.txt').write_text('second')
    third = run_build(path, collector)
    assert third['workflow']['steps']['copy']['status'] == 'passed'
    assert collector.verify(third['receipt']['id'])['valid']
