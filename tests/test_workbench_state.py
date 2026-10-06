import hashlib
import os
from pathlib import Path
from typing import ClassVar

import pytest
from app.workbench import state
from app.workbench.state import CheckpointStore, Runtime


class FixtureSession:
    compatibility: ClassVar[dict] = {'model': 'fixture', 'sampler': 'greedy', 'format': 1}
    turn = 2
    transcript: ClassVar[list] = ['fixture']
    def export(self):
        return b'opaque-runtime-state'


def test_checkpoint_integrity_compatibility_and_immutable_names(tmp_path):
    store = CheckpointStore(tmp_path / 'states', b'x' * 32)
    store.save('first', FixtureSession())
    record, data = store.read('first', FixtureSession.compatibility)
    assert data == b'opaque-runtime-state' and record['turn'] == 2
    with pytest.raises(FileExistsError):
        store.save('first', FixtureSession())
    with pytest.raises(ValueError, match='compatib'):
        store.read('first', {'model': 'another'})
    (store.root / 'first' / 'state.bin').write_bytes(b'corrupted')
    with pytest.raises(ValueError):
        store.read('first', FixtureSession.compatibility)
    with pytest.raises(ValueError):
        store.save('../escape', FixtureSession())


def test_interrupted_save_preserves_previous_checkpoint(tmp_path, monkeypatch):
    store = CheckpointStore(tmp_path / 'states', b'x' * 32)
    store.save('good', FixtureSession())
    def fail(source, target):
        raise OSError('interrupted final rename')
    monkeypatch.setattr(os, 'rename', fail)
    with pytest.raises(OSError):
        store.save('new', FixtureSession())
    assert not (store.root / 'new').exists()
    assert store.read('good', FixtureSession.compatibility)[1] == b'opaque-runtime-state'


def test_checkpoint_storage_limit_does_not_remove_previous_state(tmp_path):
    store = CheckpointStore(tmp_path / 'states', b'x' * 32, max_total_bytes=25)
    store.save('first', FixtureSession())
    with pytest.raises(ValueError, match='storage budget'):
        store.save('second', FixtureSession())
    assert store.read('first', FixtureSession.compatibility)[1] == b'opaque-runtime-state'


@pytest.mark.skipif(not os.getenv('OMARCHY_STATE_LIBRARY'), reason='Requires the compiled adapter and real GGUF')
def test_real_rwkv_continuation_restore_and_independent_fork(tmp_path, monkeypatch):
    model = Path(os.environ['OMARCHY_STATE_MODEL'])
    with Runtime(Path(os.environ['OMARCHY_STATE_LIBRARY']), model, model_key='2.9b') as runtime, runtime.session(persona='Answer briefly.', context=512) as first:
        first.prefill('User: Count from one.\n\nAssistant:')
        store = CheckpointStore(tmp_path / 'states', b'x' * 32)
        store.save('start', first)
        with first.fork() as fork:
            expected = first.generate(5)
            assert fork.generate(5) == expected
            original = first.export()
            fork.prefill('\n\nUser: A different question.\n\nAssistant:')
            assert first.export() == original
        first.restore(store, 'start')
        assert first.generate(5) == expected
        before = first.export()
        (store.root / 'start' / 'state.bin').write_bytes(b'truncated')
        with pytest.raises(ValueError):
            first.restore(store, 'start')
        assert first.export() == before
        template_root = tmp_path / 'template-root'
        (template_root / 'config').mkdir(parents=True)
        template = "{% for message in messages %}{{ message.content }}{% endfor %}Assistant:"
        (template_root / 'config/rwkv-user-assistant.jinja').write_text(template)
        monkeypatch.setattr(state, 'ROOT', template_root)
        with pytest.raises(ValueError, match='Template changed'):
            first.fork()
        assert first.export() == before
        with runtime.session(persona='custom persona') as custom:
            assert custom.compatibility['template_sha256'] == hashlib.sha256(template.encode()).hexdigest()
            rendered = []
            monkeypatch.setattr(custom, 'prefill', rendered.append)
            monkeypatch.setattr(custom, 'generate', lambda tokens: 'fixture answer')
            custom.chat('test prompt')
            assert rendered == ['custom personatest promptAssistant:', '\n\n']
