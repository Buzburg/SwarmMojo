# Voice verification — 6 October 2026

The installed Omarchy WSL voice client passed its functional checks. It remains experimental: the strict brand-name recognition check fails, and sustained faster-than-realtime synthesis is not established.

Later the same day, [prompt-cache tuning](voice-performance.md) reduced median first generated audio from 7.33s to 3.09s in a three-reply comparison. The initial qualification measurements below are retained as historical evidence.

## Actual installed runtime

Pocket TTS 3.3.0, September English weights without voice cloning, fixed CC0 Marius voice; Moonshine Voice 0.1.5, explicit Tiny Streaming; CPU-only Torch 2.8.0. The runtime is Linux x86-64/Python 3.12.14, separate from ROMS. Its wheel and model identities are pinned in `config/voice-runtime.json`.

Installed disk use: approximately 1.3GiB for the speech environment and 259MiB for model data. The tested host is the Ryzen 9 5980HX machine with a six-logical-CPU WSL allocation. This certifies neither native Windows speech nor other hardware.

## Evidence

| Check | Result |
|---|---|
| Linux voice, verifier logic, doctor and system-workshop regressions | 200 passed; one explicitly gated actual-model test skipped. Actual models were exercised separately below. |
| Expanded Windows release selection | 317 passed; 14 Linux-audio/host-restricted symlink skips. The initial run exposed an oversized pytest label; short fixed IDs resolved the Windows environment-variable limit. |
| Known common-word synthetic speech | 8/8 content checks passed across four phrases and two deterministic seeds. No human microphone accuracy claim. |
| Original “Goose voice is ready” fixture | Failed: recognized “whose voice is ready.” Padding, VAD bypass and a Goose keyterm did not correct it. Expected text remains unchanged. |
| Real Goose answer and speech | Arithmetic answer contained 42; first generated audio at 10.00s and playback complete at 11.00s in the combined run. |
| Warm synthesis only, three samples | Median first chunk 0.439s; median generation/audio-duration ratio 1.159. Values above one mean synthesis took longer than the audio duration. |
| Model loading in benchmark process | TTS 14.61s; STT 2.64s, including imports and integrity checks, without clearing OS file caches. |
| Voice process memory | Peak RSS about 1.23GB. Excludes the separate RWKV, gateway and desktop processes. |
| TTS cancellation | Before-first-chunk cancellation emitted nothing; after-first-chunk cancellation returned in 0.034s; the next request succeeded. |
| Playback | Audio server accepted and drained the generated phrase. Physical speaker audibility was not independently confirmed. |
| Microphone connection | 16,000 samples captured at 16kHz; audio immediately discarded, not transcribed or saved. Startup is given up to five seconds before the recording-duration timer begins. |
| Actual installed terminal launcher | Loaded both models, cancelled a turn, completed the next spoken reply, and exited with code zero. No microphone was opened during this terminal check. |
| Existing services | Model, ROMS, broker and user task worker remained active. |

Workspace evidence: `review-artifacts/voice/live-20261006-01.json` preserves the original failed first run; `live-20261006-02.json` records the full run; `launcher-20261006-01.json`, `linux-regressions.xml`, and `windows-release-final.xml` record terminal and regression checks. `prefill-review.md` separates model prompt-processing delay from speech synthesis and does not claim a cache speedup.

The full live report deliberately has `functional_success: true`, `success: false`, and `quality_failures: ["brand_roundtrip"]`. The verifier exits with code 1 for that unresolved quality failure. No fixture was weakened to turn the brand check green. The microphone's first one-second wall-clock attempt returned no samples; the subsequent fix separates WSLg connection startup from actual recording duration and has a regression test.

## Reproduce

Run the voice Python from the ROMS working directory, with `PYTHONPATH` pointing to ROMS and the existing gateway key loaded privately when testing chat:

```text
/opt/goose-voice-env/bin/python -m scripts.verify_voice --output NEW_REPORT.json --playback --chat --microphone
```

The default verifier without those three flags uses only synthetic speech and local models. Reports contain metrics and match results, not microphone audio, transcripts or credentials. `ROMS_LIVE_VOICE=1` enables the actual-model pytest case; it currently fails on the preserved brand-recognition expectation.

Public release still needs human listening/microphone checks, broader vocabulary/noise coverage, consistent realtime performance under concurrent load and native hardware qualification. Hands-free turn-taking and verbal authorization of OS changes are separate future capabilities.
