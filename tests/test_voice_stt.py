"""Offline STT contract tests using a fake Moonshine runtime, never a microphone."""
import hashlib
import json
import struct
import sys
from types import ModuleType, SimpleNamespace

import pytest

from app import voice_stt


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    model_dir = tmp_path / 'moonshine'
    model_dir.mkdir()
    sizes, assets = {}, []
    for name in voice_stt.MODEL_FILES:
        data = f'fixture:{name}'.encode()
        (model_dir / name).write_bytes(data)
        sizes[name] = len(data)
        assets.append({'path': f'moonshine/{name}', 'size': len(data),
                       'sha256': hashlib.sha256(data).hexdigest(),
                       'url': voice_stt.MODEL_URL + name})
    monkeypatch.setattr(voice_stt, 'MODEL_FILES', sizes)
    manifest = {'schema_version': 1, 'stt': {'model_arch': 'tiny_streaming',
                 'model_dir': 'moonshine'}, 'assets': assets}
    manifest_path = tmp_path / 'voice-runtime.json'
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    state = SimpleNamespace(constructors=[], streams=[], closes=0, fail=None,
                            result=SimpleNamespace(lines=[
                                SimpleNamespace(text=' Open  hardware viewer. ', is_complete=True)]))

    class Stream:
        def __init__(self, **kwargs):
            self.kwargs, self.closed, self.started = kwargs, False, False
            self.samples, self.sample_rate = None, None
            state.streams.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.closed = True

        def start(self):
            self.started = True

        def add_audio(self, samples, sample_rate):
            assert self.started
            self.samples, self.sample_rate = samples, sample_rate
            if state.fail:
                raise state.fail

        def stop(self):
            return state.result

    class Transcriber:
        def __init__(self, **kwargs):
            state.constructors.append(kwargs)

        def create_stream(self, **kwargs):
            return Stream(**kwargs)

        def close(self):
            state.closes += 1

    package = ModuleType('moonshine_voice')
    api = ModuleType('moonshine_voice.moonshine_api')
    api.ModelArch = SimpleNamespace(TINY_STREAMING=2)
    transcriber = ModuleType('moonshine_voice.transcriber')
    transcriber.Transcriber = Transcriber
    for module in (package, api, transcriber):
        monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr(voice_stt.metadata, 'version', lambda name: '0.1.5')
    return SimpleNamespace(root=tmp_path, model_dir=model_dir, manifest=manifest,
                           manifest_path=manifest_path, state=state,
                           recognizer=voice_stt.TinyRecognizer(tmp_path))


def test_load_is_offline_tiny_cpu_and_idempotent(runtime):
    runtime.recognizer.load()
    runtime.recognizer.load()
    assert len(runtime.state.constructors) == 1
    options = runtime.state.constructors[0]
    assert options['model_path'] == runtime.model_dir
    assert options['model_arch'] == 2
    assert options['options']['ort_providers'] == 'CPU'
    assert options['options']['save_input_wav_path'] == ''
    for key in ('return_audio_data', 'log_output_text', 'log_api_calls', 'log_ort_run',
                'identify_speakers', 'word_timestamps'):
        assert options['options'][key] == 'false'
    assert sorted(path.name for path in runtime.root.iterdir()) == ['moonshine', 'voice-runtime.json']


def test_pcm_conversion_final_text_and_stream_cleanup(runtime):
    runtime.recognizer.load()
    result = runtime.recognizer.transcribe(struct.pack('<hhhh', -32768, -1, 0, 32767), 24000)
    assert result == 'Open hardware viewer.'
    stream = runtime.state.streams[0]
    assert stream.samples == [-1.0, -1 / 32768, 0.0, 32767 / 32768]
    assert stream.sample_rate == 24000 and stream.closed
    assert stream.kwargs['update_interval'] > voice_stt.MAX_AUDIO_SECONDS


def test_each_utterance_gets_a_fresh_stream(runtime):
    runtime.recognizer.load()
    runtime.recognizer.transcribe(b'\0\0')
    runtime.state.result = SimpleNamespace(lines=[SimpleNamespace(text='Second.', is_complete=True)])
    assert runtime.recognizer.transcribe(b'\0\0') == 'Second.'
    assert len(runtime.state.streams) == 2
    assert all(stream.closed for stream in runtime.state.streams)


@pytest.mark.parametrize('pcm,rate', [(b'\0', 16000), ('audio', 16000),
    (bytearray(2), 16000), (b'\0\0', True), (b'\0\0', 16000.0),
    (b'\0\0', 0), (b'\0\0', 7999), (b'\0\0', 48001),
    (b'\0\0' * 480001, 16000)], ids=['odd', 'text', 'mutable', 'bool-rate',
    'float-rate', 'zero-rate', 'low-rate', 'high-rate', 'over-duration'])
def test_invalid_audio_never_reaches_model(runtime, pcm, rate):
    runtime.recognizer.load()
    with pytest.raises(ValueError):
        runtime.recognizer.transcribe(pcm, rate)
    assert runtime.state.streams == []


def test_duration_boundary_empty_and_silence(runtime):
    runtime.recognizer.load()
    assert runtime.recognizer.transcribe(b'') == ''
    assert runtime.state.streams == []
    runtime.state.result = SimpleNamespace(lines=[])
    assert runtime.recognizer.transcribe(b'\0\0' * 240000, 8000) == ''


def test_load_required_and_close_idempotent(runtime):
    runtime.recognizer.close()
    with pytest.raises(RuntimeError, match='Load'):
        runtime.recognizer.transcribe(b'\0\0')
    runtime.recognizer.load()
    runtime.recognizer.close()
    runtime.recognizer.close()
    assert runtime.state.closes == 1
    runtime.recognizer.load()
    assert len(runtime.state.constructors) == 2


def test_runtime_failure_closes_stream(runtime):
    runtime.recognizer.load()
    runtime.state.fail = RuntimeError('native failure')
    with pytest.raises(RuntimeError, match='native failure'):
        runtime.recognizer.transcribe(b'\0\0')
    assert runtime.state.streams[0].closed


@pytest.mark.parametrize('result', [None, SimpleNamespace(lines=None),
    SimpleNamespace(lines=[SimpleNamespace(text='unfinished', is_complete=False)]),
    SimpleNamespace(lines=[SimpleNamespace(text=None, is_complete=True)]),
    SimpleNamespace(lines=[SimpleNamespace(text='bad\x1b[31m', is_complete=True)]),
    SimpleNamespace(lines=[SimpleNamespace(text='x' * 4097, is_complete=True)])])
def test_invalid_native_results_rejected(runtime, result):
    runtime.recognizer.load()
    runtime.state.result = result
    with pytest.raises(RuntimeError):
        runtime.recognizer.transcribe(b'\0\0')
    assert runtime.state.streams[0].closed


@pytest.mark.parametrize('change', ['hash', 'size', 'url', 'missing', 'duplicate',
    'extra', 'architecture', 'directory', 'schema'])
def test_unverified_inventory_never_loads(runtime, change):
    manifest = runtime.manifest
    if change == 'hash':
        manifest['assets'][0]['sha256'] = '0' * 64
    elif change == 'size':
        manifest['assets'][0]['size'] += 1
    elif change == 'url':
        manifest['assets'][0]['url'] = 'https://untrusted.example/model'
    elif change == 'missing':
        manifest['assets'].pop()
    elif change == 'duplicate':
        manifest['assets'].append(manifest['assets'][0])
    elif change == 'extra':
        manifest['assets'].append(dict(manifest['assets'][0], path='moonshine/../outside'))
    elif change == 'architecture':
        manifest['stt']['model_arch'] = 'medium_streaming'
    elif change == 'directory':
        manifest['stt']['model_dir'] = '../outside'
    else:
        manifest['schema_version'] = True
    runtime.manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError):
        runtime.recognizer.load()
    assert runtime.state.constructors == []


def test_modified_asset_rejected(runtime):
    path = runtime.model_dir / 'adapter.ort'
    path.write_bytes(b'x' * path.stat().st_size)
    with pytest.raises(ValueError, match='verification'):
        runtime.recognizer.load()
    assert runtime.state.constructors == []


@pytest.mark.parametrize('extra', [False, True], ids=['missing', 'unlisted'])
def test_exact_model_files_required(runtime, extra):
    if extra:
        (runtime.model_dir / 'frontend.onnx').write_bytes(b'unverified alternate')
    else:
        (runtime.model_dir / 'adapter.ort').unlink()
    with pytest.raises(ValueError, match='unexpected or missing'):
        runtime.recognizer.load()
    assert runtime.state.constructors == []


@pytest.mark.parametrize('data', ['{"schema_version":1,"schema_version":1}', ' ' * 65537],
                         ids=['duplicate-keys', 'oversized'])
def test_duplicate_or_oversized_manifest_rejected(runtime, data):
    runtime.manifest_path.write_text(data, encoding='utf-8')
    with pytest.raises(ValueError):
        runtime.recognizer.load()
    assert runtime.state.constructors == []


def test_wrong_runtime_version_rejected(runtime, monkeypatch):
    monkeypatch.setattr(voice_stt.metadata, 'version', lambda name: '0.1.4')
    with pytest.raises(RuntimeError, match='0.1.5'):
        runtime.recognizer.load()
    assert runtime.state.constructors == []


def test_missing_runtime_reports_setup_error(runtime, monkeypatch):
    def missing(name):
        raise voice_stt.metadata.PackageNotFoundError(name)
    monkeypatch.setattr(voice_stt.metadata, 'version', missing)
    with pytest.raises(RuntimeError, match='Install the pinned'):
        runtime.recognizer.load()


def test_symlink_asset_rejected(runtime):
    path = runtime.model_dir / 'adapter.ort'
    data = path.read_bytes()
    path.unlink()
    target = runtime.root / 'external.ort'
    target.write_bytes(data)
    try:
        path.symlink_to(target)
    except OSError:
        pytest.skip('Symlinks unavailable on this host')
    with pytest.raises(ValueError, match='unsafe'):
        runtime.recognizer.load()
    assert runtime.state.constructors == []
