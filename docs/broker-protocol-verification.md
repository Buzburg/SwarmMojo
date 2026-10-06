# Broker protocol verification — October 5, 2026

The native broker now implements the R02 frame size, nesting and header-read limits: 65536 bytes before LF, 16 JSON containers and a five-second monotonic read deadline. The standard-library JSON decoder rejects duplicate keys and non-finite constants; a string-aware bounded nesting scan runs first. Only legacy `PING` and `STATUS` bypass the versioned request envelope, and both remain read-only.

V1 requires exactly `v`, `id`, `action` and `args`. Replies have exactly one `result` or structured `error` containing a stable code and safe message. Parsed valid request IDs are preserved; rejected envelopes and transport failures may use null. Unsupported actions return `NOT_IMPLEMENTED`. Large or invalid service responses become bounded errors instead of unframed data or serialization failures. Service exception details are not sent to the caller.

This changes the earlier provisional v1 response layout: status, worker and task fields now live under `result`. The installed worker verifier and broker integration tests were migrated; the private worker's own protocol and operator approval boundary are unchanged. Ordinary Goose status continues using its legacy read-only alias, and the existing chat result string keeps its shape under `result`.

## Evidence

The first compiled candidate passed **73 tests and 13 subtests** across strict protocol, action behavior and native transport. Tests include full-size valid input and one-byte overflow, invalid UTF-8, duplicate/unknown fields, version/type/ID errors, JSON depth, braces/escapes inside strings, concurrent callers with distinct IDs, incomplete/idle/disconnected clients, socket permissions, symlink/rename defenses and descriptor stability. An additional serialization regression covers non-finite backend data.

The candidate was built with the installed pinned Mojo environment, then installed explicitly at `/opt/roms-env/bin/omarchy-broker` and the service restarted. Installed SHA-256: `be748079de04e66e92b7739fbb9e0f083e5eaef5afe084209d62f6798d42edf6`. The previous executable is retained at workspace `deployment/backups/omarchy-broker-before-protocol`.

The complete installed profile passed **9/9 required groups**: 212 Python regressions, 24 actual native-broker tests, live Goose 2.9B/ROMS readiness, nine rootless-worker tests, 13 native/combined sandbox tests, 40 staging/promotion tests, 22 service/recovery tests, the installed worker boundary and 28 model-assisted workflow tests. No required live group was skipped. This includes the additional serialization regression, actual broker-to-worker validation and the real-model draft/apply/rollback fixture.

An additional installed `scripts/check_wsl_build.py` run reached the real model through the new broker envelope and preserved its request ID, but failed its exact-answer assertion: the model returned an empty `<think>` block before the correct `URGENT` word. The nine-group result above remains a passed profile; this extra generation-format check is a separate failure, not counted as passing or hidden by stripping tags in the test. Prompt/template handling and broader model quality still require follow-up under T08/T11. The protocol increment does not alter model text.

Follow-up: [completed-response decoding](goose-response-verification.md) subsequently resolved this formatting check while preserving original model output. The unchanged installed cutover assertion now passes. This later fix does not change the recorded outcome of the earlier failed run.

## Remaining protocol work

This increment completed strict parsing/framing and the structured envelope. A subsequent [durable replay increment](broker-replay-verification.md) binds `task.validate` IDs to durable intent/result records. Broker-forwarded generation/validation does not yet propagate socket loss as cancellation, and serial action handling can delay queued callers. Those R02 requirements remain open; the entire protocol milestone is not claimed complete. Direct-worker cancellation and task-level promotion recovery retain their separately verified behavior.
