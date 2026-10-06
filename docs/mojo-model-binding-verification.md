# Real Mojo model binding

`app_mojo/rwkv_engine.mojo` now calls the verified opaque C adapter. The old module had no model inference: its state was a zero-filled array, its library check only opened a shared object, and its date anchor used a literal year. Those demonstration interfaces had no consumers and were removed. This increment does not introduce checkpoint persistence or a replacement temporal policy.

`RWKV7Session` exclusively owns a native CPU session. It releases the temporary model handle after session creation because the C adapter retains the underlying model. Moving the Mojo value transfers ownership; copying is forbidden. Explicit close is idempotent and destruction releases an open handle. Calls after close fail before entering C. Callers must serialize operations and must not share the internal handle.

Construction validates path, context and thread bounds. Prefill counts UTF-8 bytes and enforces the C prompt limit. Generation returns one raw byte piece plus an end marker, preserving token boundaries that might split a Unicode character. A short output buffer can grow within a fixed 64 KiB limit without advancing generation twice. Native error codes propagate as Mojo exceptions. Cancellation/reset reach the actual adapter; resetting an interrupted decode does not repair invalid state.

The binding deliberately does not claim a conversation template, verified model identity, memory context assembly, deadlines, streaming or authenticated checkpoint restore. These remain caller responsibilities. It uses the Linux x86-64 ABI and the CPU backend; other platforms and GPU cancellation were not tested. The native adapter's existing in-flight cancellation tests remain the evidence for CPU abort. Mojo checks cancellation between calls here; a cross-thread Mojo ownership/cancellation interface is not supplied.

## Verified with the supplied 2.9B model

Eleven binding tests passed against the actual installed `build/libomarchy_state.so` and `rwkv7-g1g-2.9b-Q4_K_M.gguf`:

- A probe compiles with the installed Mojo 1.1.0 compiler and warnings treated as errors. Its executable and working paths include spaces.
- A moved session produces the exact same first twelve token pieces as direct C calls for the same prompt and settings. The comparison also covers a multilingual/emoji prompt and cancellation reset before decode.
- Invalid context, embedded-NUL path, closed session, generation before prefill, empty prompt, sticky cancellation and missing model all exit with an error rather than fabricated output or a native crash.
- A negative compilation check rejects an attempted copy into two session owners.

The existing three C-adapter tests and three build-readiness tests also passed. These focused checks are not a new full-roadmap or full live-service certification. `verify_all.py --native-adapter` now includes the compiled binding tests; a missing Mojo compiler fails the selected group instead of skipping it.

The probe links the verified library by absolute path. Model/service/broker binaries and adapter source were not changed. Existing adapter identity and CPU cancellation evidence remain in [native adapter verification](native-adapter-verification.md). No 7.2B model was loaded and no training was performed.

Subsequent increment: [native answer-format verification](native-answer-verification.md) adds `answer_format()` and one additional real Mojo JSON-answer check. The original eleven binding checks remain in the required native profile.

Design reference: Modular documents move-only ownership and foreign calls in [Mojo structs](https://docs.modular.com/mojo/manual/structs/) and [C interoperability](https://mojolang.static.modular.com/docs/manual/c-ffi/). Actual signatures were checked against the pinned installed compiler, which requires `__deinit__` rather than the older documentation's `__del__` spelling.
