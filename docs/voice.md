# Goose local voice

The experimental voice client connects Moonshine Tiny Streaming speech recognition, the existing Goose chat gateway, and Pocket TTS spoken replies. Speech runs on the CPU. The initial package targets Linux x86-64 and Python 3.12; other architectures require their own dependency lock and qualification.

Installed on the Omarchy WSL test machine on 6 October 2026. Eight common-word synthetic recognition checks, actual Goose arithmetic, playback, one-second microphone capture and cancellation/reuse passed. The original “Goose voice is ready” fixture is consistently recognized as “whose voice is ready”; its strict test remains failed. The evidence therefore distinguishes functional success from complete quality acceptance.

In the combined run, median warm first generated audio was 0.44s, median generation/audio-duration ratio was 1.16, the short model-answer/playback turn took 11.0s, and this voice process peaked near 1.23GB RSS. These are three warm speech samples and one model turn, excluding the separate model/gateway memory. Sustained realtime speech and human microphone intelligibility are not certified. Detailed reports are in the workspace's `review-artifacts/voice` directory.

See [verification results and reproduction](voice-verification.md) for exact scope, passing checks and the retained failure.

## Start talking

Open `Open Goose Voice.cmd` from the workspace, run `goose --voice` inside Omarchy, or type `/voice` in Goose text chat. Models load once when the voice session starts.

- Press **Enter** and wait for **Listening**. Speak, then press **Enter** again to send. Audio startup can take a moment in WSLg; each recording is limited to 30 seconds after audio starts.
- **Ctrl+C** stops the current recording or reply. `/exit` closes voice.
- `/type MESSAGE` asks a question using the keyboard and speaks the answer.
- `/reset` clears this voice session's conversation.
- `/system` and `/project` open the existing reviewed workshops. These commands must be typed; recognized speech is conversation text and cannot approve or execute a system change.

The microphone is closed between recordings and while Goose speaks. This first version uses push-to-talk, with no wake word or hands-free interruption. If you hear no audio, check the Windows output device and WSLg audio connection. If transcription is empty, check the selected Windows microphone and desktop-app microphone access, then use `/type` as a fallback.

## Runtime and privacy

The isolated environment lives at `/opt/goose-voice-env`; pinned model assets and their manifest live at `/opt/goose-voice-data`. The existing `/opt/roms-env`, RWKV weights, native worker and services are unchanged by the voice installer. It checks hashes and installs an exact CPU-only wheel inventory. Model loading and conversations use local files after setup.

Pocket TTS 3.3.0 uses the September English checkpoint without the voice-cloning encoder and a fixed CC0 Marius/Selfie voice embedding. Moonshine Voice 0.1.5 explicitly selects Tiny Streaming. The installer preserves the upstream notices in the data directory. [Pocket code](https://github.com/kyutai-labs/pocket-tts), [model](https://huggingface.co/kyutai/pocket-tts-without-voice-cloning), [voice licensing](https://huggingface.co/kyutai/tts-voices), [Moonshine](https://github.com/moonshine-ai/moonshine).

The voice client keeps microphone PCM and conversation history in memory and writes neither to disk. Raw PCM is released after transcription; `/reset` clears history. Terminal scrollback can retain displayed text, and OS swap or crash reporting can retain process memory. The gateway's separate recording setting still applies; see [chat privacy](chat-privacy.md). Voice sessions do not become training data automatically.

Speech and transcript text never supply executable commands. The client contacts only the authenticated loopback chat gateway and local Unix audio server. It filters hidden reasoning, fenced code and terminal control sequences, validates completed responses, and bounds audio/text buffers. Audio subprocesses receive no gateway credentials. A partial spoken answer can precede a later stream failure; the client reports the failure and does not add that turn to conversation history.

## Installation and verification

On this prepared Omarchy build, install the standard `libpulse` and `portaudio` packages, then run `scripts/install_voice_runtime.py --apply` as root using `/opt/roms-env/bin/python`. It creates the separate environment and pinned data directory; without `--apply` it only describes the plan. It is not a generic native-OS installer. Keep `config/voice-runtime.json` with the source.

The `scripts.voice_chat` module also accepts `--check`, `--say TEXT`, `--text TEXT` and `--input-wav PATH` for explicit checks. Run it with the isolated voice Python, this repository on `PYTHONPATH`, and the existing local gateway key supplied privately for chat. `--check` loads both models and checks audio connectivity without opening the microphone. WAV input must be uncompressed mono 16-bit PCM, 8–48kHz, at most 30 seconds.

Offline tests cover input limits, changed model files, cancellation/cleanup, stream parsing, terminal sanitization, history and the action boundary. The real-model verifier records synthetic-fixture results and timing separately from these mocked tests. Playback acceptance shows the audio server accepted and drained data; it does not prove a human heard the intended physical speaker. Human microphone intelligibility and headset/speaker feedback need listening checks.

Speed must be measured with RWKV running. Startup, speech recognition, first visible answer, first generated audio and completed playback are different costs. The first implementation submits a completed push-to-talk recording to the streaming recognizer; incremental transcription during recording and hands-free conversation remain future work. Model size and upstream benchmarks do not certify this PC or other hardware.
