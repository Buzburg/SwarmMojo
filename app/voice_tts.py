"""Offline, fixed-voice Pocket TTS output. No audio devices or conversation files.

Call load() before recording starts to pay the model/hash initialization cost once.
Cancellation is cooperative: the current native operation finishes, then the upstream
stream is drained so its worker threads finish before another utterance starts.
"""
from __future__ import annotations

import hashlib
from importlib.metadata import version as package_version
import json
import logging
import os
from pathlib import Path
import threading
from typing import Any, Iterator, TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

MAX_TEXT_CHARS = 2000
SAMPLE_RATE = 24000
_TTS_FILES = ("tts/model.safetensors", "tts/tokenizer.json", "tts/voice.safetensors")


class VoiceTTSError(RuntimeError):
    """A bounded, user-safe speech output failure."""


def local_config(data_dir: Path) -> dict[str, Any]:
    """Pocket 3.3.0 English architecture, with every asset reference local."""
    return {
        "weights_path": str(data_dir / "tts/model.safetensors"),
        "default_temperature": 0.3,
        "flow_lm": {
            "insert_bos_before_voice": True, "dtype": "float32",
            "flow": {"depth": 6, "dim": 512},
            "transformer": {"d_model": 1024, "hidden_scale": 4, "max_period": 10000,
                            "num_heads": 16, "num_layers": 6},
            "lookup_table": {"dim": 1024, "n_bins": 4000, "tokenizer": "tokenizers",
                             "tokenizer_path": str(data_dir / "tts/tokenizer.json")},
        },
        "mimi": {
            "dtype": "float32", "sample_rate": SAMPLE_RATE, "inner_dim": 32,
            "outer_dim": 512, "channels": 1, "frame_rate": 12.5,
            "seanet": {"dimension": 512, "channels": 1, "n_filters": 64,
                       "n_residual_layers": 1, "ratios": [6, 5, 4], "kernel_size": 7,
                       "residual_kernel_size": 3, "last_kernel_size": 3,
                       "dilation_base": 2, "pad_mode": "constant", "compress": 2},
            "transformer": {"d_model": 512, "num_heads": 8, "num_layers": 2,
                            "layer_scale": 0.01, "context": 250, "dim_feedforward": 2048,
                            "input_dimension": 512, "output_dimensions": [512]},
            "quantizer": {"dimension": 32, "output_dimension": 512},
        },
    }


def _verified_assets(data_dir: Path) -> Path:
    try:
        manifest_path = data_dir / "voice-runtime.json"
        if manifest_path.is_symlink() or manifest_path.stat().st_size > 131072:
            raise ValueError("manifest")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["schema_version"] != 1 or len(manifest["assets"]) > 64:
            raise ValueError("manifest")
        assets = {entry["path"]: entry for entry in manifest["assets"]}
        if len(assets) != len(manifest["assets"]):
            raise ValueError("duplicates")
        for name in _TTS_FILES:
            path = data_dir / name
            entry = assets[name]
            if (path.is_symlink() or not path.is_file()
                    or not path.resolve().is_relative_to(data_dir)
                    or path.stat().st_size != entry["size"]):
                raise ValueError("asset")
            with path.open("rb") as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
            if digest != entry["sha256"]:
                raise ValueError("checksum")
        config = data_dir / "tts/pocket-english.yaml"
        if (config.is_symlink() or config.stat().st_size > 16384
                or json.loads(config.read_text(encoding="utf-8")) != local_config(data_dir)):
            raise ValueError("local config")
        return config
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise VoiceTTSError("Speech files are missing or changed. Run the voice runtime installer.") from None


class PocketSpeaker:
    sample_rate = SAMPLE_RATE

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir).resolve()
        self._model: Any = None
        self._voice_state: Any = None
        self._load_lock = threading.Lock()
        self._generation_lock = threading.Lock()

    def load(self) -> None:
        with self._load_lock:
            if self._model is not None:
                return
            config = _verified_assets(self.data_dir)
            os.environ.update(HF_HUB_OFFLINE="1", HF_HUB_DISABLE_IMPLICIT_TOKEN="1",
                              HF_HUB_DISABLE_TELEMETRY="1", DEBUG_MIMI="0",
                              POCKET_TTS_SAVE_WEIGHTS="0", OMP_NUM_THREADS="2",
                              MKL_NUM_THREADS="2")
            try:
                if package_version("pocket-tts") != "3.3.0":
                    raise ValueError("unsupported Pocket TTS version")
                import torch
                from pocket_tts import TTSModel

                torch.set_num_threads(2)
                # This dedicated runtime must not record text via upstream debug logs.
                for name in list(logging.Logger.manager.loggerDict):
                    if name == "pocket_tts" or name.startswith("pocket_tts."):
                        logging.getLogger(name).disabled = True
                model = TTSModel.load_model(config=config)
                model.to("cpu").eval()
                model.has_voice_cloning = False
                if model.sample_rate != SAMPLE_RATE:
                    raise ValueError("sample rate")
                state = model.get_state_for_audio_prompt(self.data_dir / "tts/voice.safetensors")
                self._voice_state = state
                self._model = model
            except Exception:
                raise VoiceTTSError("Speech model could not load. Check the isolated voice runtime.") from None

    def iter_audio(self, text: str, cancel: threading.Event) -> Iterator[np.ndarray]:
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARS:
            raise VoiceTTSError("Speech text must contain 1 to 2000 characters.")
        if cancel.is_set():
            return
        if not self._generation_lock.acquire(blocking=False):
            raise VoiceTTSError("Speech output is already in progress.")
        stream = None
        complete = False
        try:
            self.load()
            if cancel.is_set():
                return
            import numpy as np

            stream = self._model.generate_audio_stream(
                self._voice_state, text, copy_state=True, stop=cancel)
            samples = 0
            for chunk in stream:
                if cancel.is_set():
                    break
                if hasattr(chunk, "detach"):
                    chunk = chunk.detach().cpu().numpy()
                chunk = np.asarray(chunk)
                if (chunk.ndim != 1 or chunk.dtype.kind != "f"
                        or chunk.size > SAMPLE_RATE * 10 or not np.isfinite(chunk).all()):
                    raise VoiceTTSError("Speech model returned invalid audio.")
                samples += chunk.size
                if samples > SAMPLE_RATE * 180:
                    raise VoiceTTSError("Speech output exceeded the utterance limit.")
                if chunk.size:
                    yield np.clip(chunk, -1.0, 1.0).astype(np.float32, copy=True)
            if samples == 0 and not cancel.is_set():
                raise VoiceTTSError("Speech model returned no audio.")
            complete = not cancel.is_set()
        except VoiceTTSError:
            raise
        except Exception:
            raise VoiceTTSError("Speech generation failed. Try another short reply.") from None
        finally:
            try:
                if stream is not None and not complete:
                    cancel.set()
                    # Closing upstream early skips its join; draining lets it clean up.
                    for _ in stream:
                        pass
            except Exception:
                # A failing stream is discarded; it is never reused or retried.
                self._model = None
                self._voice_state = None
            finally:
                self._generation_lock.release()
