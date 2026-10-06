# Omarchy native broker contract

The installed Mojo broker owns the private Unix socket and native framing. Python performs bounded JSON parsing and delegates only explicit actions to the authenticated ROMS gateway or private validation worker. It runs as the ordinary `rryan` user with `NoNewPrivileges`; it is a userspace coordinator, not an OS hypervisor.

## Request and response

Protocol v1 accepts one UTF-8 JSON object followed by LF per connection. All four request fields are required:

```json
{"v":1,"id":"request-1","action":"ping","args":{}}
```

`v` must be integer 1, including rejection of booleans. `id` must contain 1–64 ASCII letters, digits, underscores or hyphens. `action` is an allowlisted string and `args` is an action-specific object. Unknown fields, duplicate keys, non-finite numbers, invalid UTF-8 and excessive nesting fail before service dispatch. Whitespace and key order do not change meaning.

Success has exactly `v`, `id`, `ok` and `result`; failure has exactly `v`, `id`, `ok` and `error`. Error objects contain stable uppercase `code` and a safe `message`. Valid parsed request IDs are echoed; malformed envelopes may return `id: null`. Action data formerly placed at the top level is now inside `result`. For example, worker capability data is at `result.capabilities`.

```json
{"v":1,"id":"request-1","ok":true,"result":"pong"}
```

Legacy `PING` and `STATUS` remain read-only aliases with their existing unversioned reply shapes. Legacy `MOCK` and `ANCHOR` text commands are no longer accepted; use v1 `mock` and `anchor`. These changes replace the earlier provisional v1 envelope. The repository's broker consumers were migrated together; the private worker's separate protocol is unchanged.

## Bounds and actions

Frames may contain at most 65536 bytes before LF. JSON may nest at most 16 containers, counting the root. The native header-read deadline is five seconds measured with the monotonic clock. Responses are also capped at 65536 encoded bytes; oversize output becomes `RESPONSE_TOO_LARGE`. Only one frame is accepted per connection; extra frames already received alongside the first are rejected. Later input cannot trigger a second action after connection closure.

Read-only/status actions are `ping`, `status`, `rwkv_status`, `mock`, `anchor`, `sandbox_status`, `landlock_probe`, `telemetry`, `os_controller`, `worker_status`, `worker_recovery` and `task.status`. `worker_status` performs a disposable actual enforcement probe; it does not approve or apply a project change. `chat` takes `{"prompt":"text"}` with optional `project_id` and `revision` (revision requires a project). `task.status` and `task.validate` take exactly `{"task_id":"32 lowercase hex characters"}`; unknown task IDs do not create projects or tasks.

Plain chat retains its text result. Project chat returns `{"answer":"text","memory":{...}}`, with the complete bounded ROMS context receipt. It calls the existing MCP `memory_prepare_context` tool, excludes candidates/inactive records, preserves failure warnings and disables the gateway's unscoped document retrieval. Its prompt is limited to 4096 UTF-8 bytes; the first 500 characters form the memory query, and the context tool has a 2048-character budget. The result records omissions and truncation. Generation is uncached, temperature zero, at most 512 tokens, and constrained to a validated answer object. Blank/unfinished output returns `GENERATION_INCOMPLETE`; malformed output returns `GENERATION_INVALID`. This is ephemeral one-turn chat, not a saved session. See [grounded-chat evidence](broker-chat-verification.md).

`memory.search` requires `project_id` and `query`, with optional `limit` (1–20), `max_chars` (500–12000), `include_candidates` (boolean) and `revision`. It calls the existing ROMS `memory_recall` tool through MCP and returns its bounded `memories` and `truncated` fields, including source references and evidence status. This is keyword search over project lessons; it does not search imported document embeddings. Default recall excludes candidates and inactive records. See [memory integration evidence](broker-memory-verification.md).

Project replies also contain `generated`: true for a validated model answer, false for a system notice when no usable records fit the query and context budget. Empty evidence never invokes the model. The notice does not claim no records exist elsewhere; inspect the receipt's omission/truncation fields.

State save/restore/fork, task stage/apply/rollback/cancel and unknown actions return `NOT_IMPLEMENTED`. Operator CLI staging and promotion are separate working interfaces; their existence does not make those broker actions implemented. Arbitrary shell/image/approval actions are not exposed.

Status aliases share a scoped feature inventory with reasons. Legacy `sandbox: disabled` describes arbitrary chat execution, not the separate registered validation worker. Kernel ABI probing sets `enforcement_verified: false`; only an actual worker probe can provide enforcement evidence. See [readiness evidence](readiness-verification.md).

## Native transport and service lifecycle

The socket directory must be private and owned by the service user. Native code opens each path component without following symlinks, pins the directory descriptor, and binds only the leaf name. It rejects pre-existing paths, validates peer UID with `SO_PEERCRED`, uses nonblocking close-on-exec descriptors and handles partial writes without SIGPIPE. Descriptor, concurrent-startup, path-preservation and directory-rename tests exercise the compiled binary.

The installed system unit provides `/run/omarchy-broker` with private permissions and owns its lifecycle. Standalone callers must supply an existing private directory through `OMARCHY_BROKER_SOCKET`; the binary never removes an existing socket or another file. Normal service restarts rely on systemd's managed runtime directory, not unchecked stale-path deletion.

The native loop services up to 16 accepted connections without waiting for a slow header or an asynchronous service response. Read deadlines start at acceptance; writes have a two-second budget. Chat and validation each admit one active request and four queued requests, with a five-second queue deadline. Excess work receives `QUEUE_FULL`; expired queued work receives `QUEUE_TIMEOUT` before dispatch. Status can proceed during generation or validation. Local journal operations remain synchronous and can briefly delay this cooperative loop.

Memory lookup has its own one-active/four-waiter lane and the same queue deadline. Each dispatched lookup owns a local stdio MCP subprocess, initializes it, discovers `memory_recall`, calls it and shuts it down. The lookup deadline is 20 seconds plus process cleanup; disconnection cancels it and keeps its lane occupied until cleanup settles. API keys are not forwarded. Status reports project memory as `not_probed` rather than claiming a lookup succeeded.

A fully disconnected chat caller cancels its upstream request and waits for cleanup before releasing the lane. Write-half-closed callers can still receive replies. Accepted `task.validate` requests continue after caller disconnection so their durable reply can be retrieved with the same request ID. Completed replay bypasses a full validation lane. Broker process death retains the existing uncertain-intent safeguards. See [scheduling and live cancellation evidence](broker-scheduling-verification.md). Sequenced streaming, explicit task cancellation and the remaining unimplemented actions still prevent claiming the full R02 milestone complete.

## Durable validation requests

`task.validate` reserves its request ID and canonical request digest in `ROMS_DATA_DIR/broker-requests` before contacting the worker. Completed replies, including worker rejection/failure replies, are persisted before transmission. A matching retry returns the exact saved reply; different arguments with an already-bound ID return `CONFLICT`. JSON whitespace and key order do not affect this binding. Read-only calls and ephemeral chat use IDs for correlation only.

`REQUEST_UNCERTAIN` means an intent exists without a confirmed completed reply. This includes an in-progress request, a disconnected worker, or a broker killed between dispatch and recording the result. The broker never repeats that dispatch. Query `task.status` with the original task ID to inspect retained work; task cleanup/recovery remains the worker's responsibility. A saved success is historical evidence, not a fresh task-status query. There is no automatic intent reset, expiry or eviction. Pending intents currently require operator inspection; their original replies cannot always be reconstructed after a crash.

The journal uses a private owned directory, descriptor-pinned paths, no-follow regular-file reads, a bounded cross-process lock, and atomic file replacement with file/directory synchronization. Bad ownership, links, malformed records and digest mismatches fail closed with `JOURNAL_UNAVAILABLE`; a held lock returns `JOURNAL_BUSY` after at most one second of lock waiting. After possible dispatch, journal failures instead report `REQUEST_UNCERTAIN`. Directory scans stop at the fixed inventory bound. Up to 1,000 request records are retained, each bounded to twice the response limit plus 4 KiB; leftover temporary files count toward capacity. `JOURNAL_FULL` blocks new IDs while existing records remain replayable. Deleting request records is not a supported cleanup operation because doing so could permit duplicate execution.

See [replay verification](broker-replay-verification.md). Process-death tests exercise durable recovery; they do not certify physical power-loss behavior of the underlying storage.

## Build and evidence

Build with the pinned Mojo environment using the `build-broker` task, or explicitly name an output artifact and supply it through `OMARCHY_BROKER_BINARY` to the native tests. There is no arbitrary `/tmp` fallback. The installed binary must be replaced explicitly after a tested build; recompiling source elsewhere does not update the service.

See [protocol verification](broker-protocol-verification.md), [worker service verification](task-worker-verification.md) and the [operating guide](wsl-test-build.md). The wider build roadmap remains separate from these transport checks.
