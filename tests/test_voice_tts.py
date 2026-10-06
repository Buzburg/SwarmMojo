import hashlib
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

import numpy as np
import pytest

from app import voice_tts as tts
from scripts import install_voice_runtime as installer


@pytest.fixture
def voice_files(tmp_path):
    assets = []
    for name in tts._TTS_FILES:
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b"test asset")
        assets.append({"path": name, "size": 10, "sha256": hashlib.sha256(b"test asset").hexdigest()})
    (tmp_path / "voice-runtime.json").write_text(json.dumps({"schema_version": 1, "assets": assets}))
    (tmp_path / "tts/pocket-english.yaml").write_text(json.dumps(tts.local_config(tmp_path)))
    return tmp_path


class Model:
    sample_rate = 24000

    def __init__(self, chunks=None):
        self.chunks = chunks if chunks is not None else [np.array([0.2, -0.3], dtype=np.float64)]
        self.drained = False
        self.calls = []
        self.state = object()

    def to(self, device):
        assert device == "cpu"
        return self

    def eval(self):
        return self

    def get_state_for_audio_prompt(self, path):
        assert path.name == "voice.safetensors"
        assert not self.has_voice_cloning
        return self.state

    def generate_audio_stream(self, state, text, *, copy_state, stop):
        assert state is self.state
        assert copy_state is True
        self.calls.append((text, stop))
        try:
            for chunk in self.chunks:
                yield chunk
        finally:
            self.drained = True


@pytest.fixture
def loaded(voice_files, monkeypatch):
    model = Model()
    calls = []
    torch = SimpleNamespace(set_num_threads=lambda n: calls.append(("threads", n)))
    def load_model(**kwargs):
        assert kwargs == {"config": voice_files / "tts/pocket-english.yaml"}
        calls.append(("load", None))
        return model
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "pocket_tts", SimpleNamespace(TTSModel=SimpleNamespace(load_model=load_model)))
    monkeypatch.setattr(tts, "package_version", lambda name: "3.3.0")
    for name in ("HF_HUB_OFFLINE", "HF_HUB_DISABLE_IMPLICIT_TOKEN", "HF_HUB_DISABLE_TELEMETRY",
                 "DEBUG_MIMI", "POCKET_TTS_SAVE_WEIGHTS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        monkeypatch.delenv(name, raising=False)
    return tts.PocketSpeaker(voice_files), model, calls


def test_warm_cpu_model_fixed_voice_and_float32_contract(loaded):
    speaker, model, calls = loaded
    speaker.load()
    speaker.load()
    cancel = threading.Event()
    first = list(speaker.iter_audio("Hello.", cancel))
    second = list(speaker.iter_audio("Goodbye.", cancel))
    assert calls == [("threads", 2), ("load", None)]
    assert first[0].dtype == np.float32 and first[0].ndim == 1
    assert first[0].flags.owndata and np.allclose(first[0], [0.2, -0.3])
    assert len(second) == 1 and model.drained and not cancel.is_set()
    assert speaker.sample_rate == 24000


def test_precancel_never_loads_or_generates(tmp_path, monkeypatch):
    speaker = tts.PocketSpeaker(tmp_path)
    monkeypatch.setattr(speaker, "load", lambda: pytest.fail("must not load"))
    cancel = threading.Event()
    cancel.set()
    assert list(speaker.iter_audio("Hello", cancel)) == []


def test_cancel_drains_upstream_and_next_utterance_can_run(loaded):
    speaker, model, _ = loaded
    model.chunks *= 3
    cancel = threading.Event()
    stream = speaker.iter_audio("Hello", cancel)
    next(stream)
    cancel.set()
    assert list(stream) == [] and model.drained
    assert len(list(speaker.iter_audio("Again", threading.Event()))) == 3


def test_consumer_close_cancels_and_drains_threads(loaded):
    speaker, model, _ = loaded
    model.chunks *= 3
    cancel = threading.Event()
    stream = speaker.iter_audio("Hello", cancel)
    next(stream)
    stream.close()
    assert cancel.is_set() and model.drained


def test_parallel_utterances_refused(loaded):
    speaker, _, _ = loaded
    stream = speaker.iter_audio("First", threading.Event())
    next(stream)
    with pytest.raises(tts.VoiceTTSError, match="already in progress"):
        list(speaker.iter_audio("Second", threading.Event()))
    stream.close()


@pytest.mark.parametrize("chunk", [np.zeros((2, 10)), np.zeros((), dtype=float),
    np.array([1], dtype=np.int16), np.array([np.nan]), np.array([np.inf]),
    np.zeros(240001)], ids=["stereo", "scalar", "integer", "nan", "infinity", "oversized"])
def test_invalid_audio_cancels_and_cleans_up(loaded, chunk):
    speaker, model, _ = loaded
    model.chunks = [chunk]
    cancel = threading.Event()
    with pytest.raises(tts.VoiceTTSError, match="invalid audio"):
        list(speaker.iter_audio("Hello", cancel))
    assert cancel.is_set() and model.drained


def test_empty_chunk_skipped_and_amplitude_clipped(loaded):
    speaker, model, _ = loaded
    model.chunks = [np.array([], dtype=float), np.array([-2.0, 2.0])]
    chunks = list(speaker.iter_audio("Hello", threading.Event()))
    assert len(chunks) == 1 and np.array_equal(chunks[0], [-1.0, 1.0])


def test_empty_result_is_reported_as_failure(loaded):
    speaker, model, _ = loaded
    model.chunks = []
    with pytest.raises(tts.VoiceTTSError, match="no audio"):
        list(speaker.iter_audio("Hello", threading.Event()))


def test_generation_error_does_not_expose_user_text_or_raw_error(loaded):
    speaker, model, _ = loaded
    def fail(*args, **kwargs):
        raise RuntimeError("secret token and private spoken text")
    model.generate_audio_stream = fail
    with pytest.raises(tts.VoiceTTSError) as error:
        list(speaker.iter_audio("private spoken text", threading.Event()))
    assert str(error.value) == "Speech generation failed. Try another short reply."


@pytest.mark.parametrize("text", [None, "", "  ", "x" * 2001], ids=["none", "empty", "blank", "too-long"])
def test_invalid_text_before_loading(tmp_path, text):
    with pytest.raises(tts.VoiceTTSError, match="1 to 2000"):
        list(tts.PocketSpeaker(tmp_path).iter_audio(text, threading.Event()))


@pytest.mark.parametrize("change", ["missing", "bytes", "manifest", "remote-config"], ids=str)
def test_missing_or_tampered_assets_rejected_before_model_import(voice_files, change):
    if change == "missing":
        (voice_files / "tts/model.safetensors").unlink()
    elif change == "bytes":
        (voice_files / "tts/model.safetensors").write_bytes(b"evil asset")
    elif change == "manifest":
        (voice_files / "voice-runtime.json").write_text("invalid")
    else:
        config = tts.local_config(voice_files)
        config["weights_path"] = "https://example.invalid/model"
        (voice_files / "tts/pocket-english.yaml").write_text(json.dumps(config))
    with pytest.raises(tts.VoiceTTSError, match="missing or changed"):
        tts.PocketSpeaker(voice_files).load()


def test_loader_failure_is_safe_and_retry_does_not_cache_partial_model(loaded, monkeypatch):
    speaker, model, _ = loaded
    model.sample_rate = 16000
    with pytest.raises(tts.VoiceTTSError, match="could not load"):
        speaker.load()
    assert speaker._model is None and speaker._voice_state is None
    model.sample_rate = 24000
    speaker.load()
    assert speaker._model is model


def test_changed_installed_package_is_refused_before_model_load(loaded, monkeypatch):
    speaker, _, calls = loaded
    monkeypatch.setattr(tts, "package_version", lambda name: "3.4.0")
    with pytest.raises(tts.VoiceTTSError, match="could not load"):
        speaker.load()
    assert calls == []


def test_lock_has_only_exact_cpu_wheels_and_fixed_public_assets():
    lock, fingerprint = installer.read_lock(installer.LOCK)
    assert len(fingerprint) == 64
    assert len([a for a in lock["assets"] if a["path"].startswith("moonshine/")]) == 8
    assert not any(p["name"].startswith("nvidia-") for p in lock["packages"])
    assert lock["tts"]["voice"] == "marius" and lock["tts"]["voice_license"] == "CC0-1.0"


@pytest.mark.parametrize("bad_url", ["http://files.pythonhosted.org/a.whl", "https://evil.invalid/a.whl",
    "https://user:password@files.pythonhosted.org/a.whl", "https://files.pythonhosted.org/a.whl\n--evil"],
    ids=["http", "foreign-host", "credentials", "newline"])
def test_installer_rejects_untrusted_package_sources(tmp_path, bad_url):
    lock = json.loads(installer.LOCK.read_text())
    lock["packages"][0]["url"] = bad_url
    path = tmp_path / "lock.json"
    path.write_text(json.dumps(lock))
    with pytest.raises(ValueError):
        installer.read_lock(path)


def test_verified_download_is_atomic_bounded_and_disables_curl_config(tmp_path, monkeypatch):
    data = b"verified bytes"
    asset = {"path": "tts/model.safetensors", "size": len(data),
             "sha256": hashlib.sha256(data).hexdigest(), "url": "https://huggingface.co/official"}
    calls = []
    def fake_run(args, **kwargs):
        calls.append(args)
        assert args[:2] == ["/usr/bin/curl", "-q"]
        assert args[args.index("--max-filesize") + 1] == str(len(data))
        Path(args[args.index("--output") + 1]).write_bytes(data)
    monkeypatch.setattr(installer, "_run", fake_run)
    installer._download(asset, tmp_path)
    installer._download(asset, tmp_path)
    assert len(calls) == 1
    assert (tmp_path / asset["path"]).read_bytes() == data
    assert not list((tmp_path / "tts").glob(".voice-download-*"))


def test_failed_checksum_never_publishes_asset(tmp_path, monkeypatch):
    asset = {"path": "tts/model.safetensors", "size": 4, "sha256": "0" * 64,
             "url": "https://huggingface.co/official"}
    def fake_run(args, **kwargs):
        Path(args[args.index("--output") + 1]).write_bytes(b"bad!")
    monkeypatch.setattr(installer, "_run", fake_run)
    with pytest.raises(ValueError, match="checksum"):
        installer._download(asset, tmp_path)
    assert not (tmp_path / asset["path"]).exists()
    assert not list((tmp_path / "tts").glob(".voice-download-*"))


def test_installer_subprocess_environment_excludes_tokens_and_loader_variables(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "secret")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/wrong-runtime")
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    env = installer._environment()
    assert not any(name in env for name in ("HF_TOKEN", "LD_LIBRARY_PATH", "OPENAI_API_KEY"))
    assert env["PIP_CONFIG_FILE"] == installer.os.devnull
