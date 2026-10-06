# Bounded broker scheduling and disconnect propagation

The installed native Mojo broker now services slow clients and asynchronous gateway/worker requests concurrently. Status remains available while a chat generates or a project validation runs. Native code retains socket ownership, peer-UID checks, descriptor-pinned paths, frame bounds and write handling. Python's existing asyncio and HTTPX facilities handle local service I/O; no new dependency or per-request process is introduced.

## Behavior and limits

- At most 16 accepted connections and 16 tracked jobs; acceptance is bounded per loop iteration so arriving traffic cannot starve existing clients.
- Five seconds to receive a complete frame after acceptance and two seconds to transmit a ready response. These are cooperative deadlines, not hard real-time guarantees or deadlines for connections still in the kernel backlog.
- Independent chat and validation lanes each allow one active request and four waiters. Worker capability probes share the validation lane. Waiting expires after five seconds with `QUEUE_TIMEOUT`, before action dispatch or new durable intent. Capacity rejection returns `QUEUE_FULL`.
- Chat dispatch has a 120-second outer budget; validation has 180 seconds. Local worker status/recovery calls use shorter timeouts. HTTP and private-worker response sizes remain bounded.
- Full chat-client disconnection closes the owned upstream operation. Cancellation cleanup settles before lane capacity is released. A write-half-close still permits receiving the response.
- Accepted validations continue after their caller leaves, including queued requests that have not yet expired. Completed replies are durably saved. Matching replay bypasses a full validation lane; conflicting IDs and pending intents preserve their prior rejection behavior. Broker process death still requires inspecting uncertain work rather than automatically dispatching it again.

Journal access and pure local actions remain synchronous. A contended journal lock may delay the cooperative loop by up to its one-second lock budget, and storage synchronization has no hard latency guarantee. These limits apply to broker admission, not every direct HTTP caller. Sequenced streaming, explicit task cancellation, the direct native C model adapter and recurrent-state lifecycle remain unfinished.

## Installed artifact

Installed binary: `/opt/roms-env/bin/omarchy-broker`.

SHA-256: `e98afc52498b9204648cfc9c38b2433aaf8148fd43bc299fbe5294e4048817c6`.

Prior binary retained at `deployment/backups/omarchy-broker-before-scheduling` in the Windows project, SHA-256 `be748079de04e66e92b7739fbb9e0f083e5eaef5afe084209d62f6798d42edf6`. The service was restarted after installing the candidate and updating its shared Python source. Its ordinary-user identity and `NoNewPrivileges` restrictions remain in place. Runtime/model identities are unchanged from the [gateway cancellation increment](gateway-cancellation-verification.md).

## Verification

The complete installed profile passed eight groups: 273 offline regressions; 31 compiled-native tests plus 13 subtests; live 2.9B/ROMS readiness; nine container lifecycle tests; 13 sandbox tests; 40 staging/promotion tests; 22 worker/recovery tests; and the installed worker boundary. The ninth group initially reported 32 passes and one failure: the model spent its 256-token budget reasoning about a simple arithmetic prompt and returned `finish_reason: length`. Its unchanged targeted test passed immediately afterward.

A repeat of the entire model-workflow group with the installed native worker image enabled passed all 33 tests, with no skips, in 28.78 seconds. An earlier diagnostic repeat without the worker-image setting passed 31 and skipped two; that run is not used as live workshop evidence. The original full-profile result remains **8/9**, with the failed group passing separately afterward. This is evidence of an intermittent bounded-answer failure, not proof that general model quality is solved. No prompt, sampler, answer assertion or token budget was relaxed to make the repeat pass.

New tests cover cancellation before dispatch, cleanup before capacity release, queue expiry without upstream dispatch, completed replay under saturation, detached validation durability, connection saturation/recovery, oversized service output, half-close behavior and responsive status during actual socket I/O. Scheduler unit fixtures are distinct from the compiled broker tests and installed-model checks.

Both actual-model cancellation checks observe generated tokens before closing the caller and require the slot to become idle within five seconds while repeatedly querying status. The broker variant also obtains a separate status reply within two seconds while generation is active. This exercises the installed native broker through the authenticated gateway to the actual 2.9B runtime.

The 2.9B model remains the test-build model. No 7.2B activation or training occurred. This increment does not complete the full PDF roadmap.
