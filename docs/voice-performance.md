# Voice latency tuning — 6 October 2026

The installed CPU Goose 2.9B gateway now keeps its precise current timestamp after
the final user message. This preserves the earlier prompt prefix and allows the
pinned RWKV server to restore its user-boundary checkpoint. Memory retrieval,
model weights, context/output limits, and action restrictions remain intact.
Assistant-ending continuation requests retain their previous message ordering.
Voice now uses deterministic sampling (temperature zero) for more consistent
short answers. It still rejects incomplete or reasoning-only output; this does
not disable the model's reasoning or grant any tool permissions.

## Measured effect on this PC

Three actual streamed voice replies were measured before and after the clock
placement change, with normal retrieval, the same arithmetic question, temperature
0.3, and a warmed Pocket TTS process. The microphone was never opened; these
times start when text is submitted, so they exclude recording and transcription.

| Measurement | Before | Clock placement change |
|---|---:|---:|
| First generated audio, all three runs | 21.63 / 7.33 / 6.50 s | 12.27 / 3.09 / 2.92 s |
| Median first generated audio | 7.33 s | 3.09 s |
| Median completed playback | 8.28 s | 5.00 s |

That is a 58% reduction in median time to generated audio in this small sample.
The answer wording and host load varied; this is not a universal latency promise.
First requests and cache misses remain slower. First generated audio is not a
measurement of the physical speaker's first sound.

A separate deterministic varied-question check passed all four expected answers.
Three requests restored 318 prompt tokens and processed only 44, giving first
visible text at 0.87, 1.32 and 0.80 seconds. The fourth required different retrieved
context, reused zero tokens and took 6.67 seconds. This demonstrates both useful
reuse across questions and the remaining retrieval-cache limitation. Retrieval
was neither disabled nor replaced with stale results.

The live HTTP cancellation check passed: disconnect during actual generation
released the slot within its five-second bound. Focused gateway regressions
passed 59 checks. The added first-visible-text timing and stream-cleanup tests
passed six checks on both Windows and Linux.

## Evidence and reproduction

Workspace `review-artifacts/voice` contains `benchmark_latency.py`,
`benchmark_gateway.py`, `speed-baseline.json`, `speed-clock-ready.json`,
`speed-clock-varied.json`, and `speed-cancellation.xml`. Reports save metrics and
known-fixture match flags, not chat answers, microphone audio or credentials.
The first comparison attempt (`speed-clock.json`) hit the gateway before startup
finished and contains no successful runs; it is excluded from the comparison.

The voice verifier now distinguishes first visible answer text, first complete
speakable text, first generated audio, and playback completion. These stages make
future delays attributable without storing conversations.

## Reliability follow-up

After restoring the original CPU configuration, a further check completed its
first cold reply in 13.98s, with first generated audio at 12.37s, then rejected a
reasoning-only reply. `speed-final.json` contains only the first successful row;
it is **not** a passing series and its median must not be used as one. The server
finished normally after 65 generated tokens on the failed reply, but supplied no
visible answer. The existing rejection was retained.

A voice-only temperature-zero experiment then passed four spoken replies:
first generated audio 2.58 / 2.29 / 2.32 / 2.00s, median 2.31s. These were warm
requests, so they do not establish improved cold-start performance. An additional
eight checks covered arithmetic, a conversational follow-up, a bug explanation,
and honest statements about file access, each with prompt caching enabled and
disabled. All returned correct, visible answers; their full responses were
reviewed transiently and only match/timing metadata was saved. These small checks
support the new default but cannot guarantee that every future reply succeeds.
See `speed-greedy-experiment.json` and `speed-greedy-quality.json`.

The final check using the installed default, without experimental overrides,
passed all three real spoken replies (`speed-installed-final.json`). The first
uncached reply produced audio at 8.90s and finished playback at 10.59s; the two
warm replies produced audio at **2.62s and 2.49s**, finishing playback at 4.52s
and 4.36s. These times still exclude microphone capture and transcription.

The combined focused regression selection passed 120 checks, with the unrelated
full-model speech-recognition test explicitly deselected. Its known brand-name
failure remains recorded in the original voice verification report.
After installing temperature zero, 61 focused voice checks passed on Linux and
65 gateway/voice checks passed on Windows; each deselected the same full speech
model test. Windows fixture setup initially encountered sandbox temporary-folder
permissions; the unchanged tests passed with a fresh approved workspace directory.

## Attempt ledger

| Candidate | Decision | Evidence |
|---|---|---|
| Move changing clock behind the user checkpoint | Kept | Actual cache reuse and lower median voice latency; precision retained. |
| Voice temperature zero | Kept | Four spoken replies and eight varied cached/uncached correctness checks passed after a reasoning-only failure at 0.3. No automatic retry or weakened answer validation. |
| Explicit `cache_prompt=true` | No change | Already the server default; earlier probe found no gain by itself. |
| Additional audio queue or early filler | Not implemented | Most delay preceded speakable text; current output already streams. |
| Lower checkpoint spacing alone | Not implemented | Pinned server skips ordinary middle-of-prompt checkpoints; this does not solve changing retrieval prefixes. |
| Larger CPU batches / six prompt threads | Rejected | Confirmed 128/6 median first visible text 3.31s versus original 64/4 at 3.11s; no repeatable improvement. Original service settings restored. |

The CPU comparison used the exact pinned server/model/template, three fixed
arithmetic questions per configuration, temperature zero, seed 17 and disabled
prompt reuse to isolate computation. All six answers passed after explicitly
checking both digits and spelled-out numbers. `speed-cpu-pair.json` records the
successful confirmation and service restoration. The earlier exploratory report
`speed-cpu-default-ready.json` is preserved: its baseline failed before recording
startup/request timings and its digit-only checker marked spelled-out replies false, so it
cannot support a speedup. The confirmation allowed 120 seconds for startup and
reversed the configuration order. Checkpoint and RAM-cache limits were unchanged.
Both confirmation configurations took about 67 seconds to start their fresh model
process; model startup is separate from the retained-service response timings.

The original voice qualification limits still apply: brand-name recognition,
human microphone intelligibility, sustained real-time synthesis, and broader
hardware support need further testing. See [voice verification](voice-verification.md).
