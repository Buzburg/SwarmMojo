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

Read-only/status actions are `ping`, `status`, `rwkv_status`, `mock`, `anchor`, `sandbox_status`, `landlock_probe`, `telemetry`, `os_controller`, `worker_status`, `worker_recovery` and `task.status`. `worker_status` performs a disposable actual enforcement probe; it does not approve or apply a project change. `chat` takes exactly `{"prompt":"text"}`. `task.status` and `task.validate` take exactly `{"task_id":"32 lowercase hex characters"}`; unknown task IDs do not create projects or tasks.

State save/restore/fork, memory MCP search, task stage/apply/rollback/cancel and unknown actions return `NOT_IMPLEMENTED`. Operator CLI staging and promotion are separate working interfaces; their existence does not make those broker actions implemented. Arbitrary shell/image/approval actions are not exposed.

Status aliases share a scoped feature inventory with reasons. Legacy `sandbox: disabled` describes arbitrary chat execution, not the separate registered validation worker. Kernel ABI probing sets `enforcement_verified: false`; only an actual worker probe can provide enforcement evidence. See [readiness evidence](readiness-verification.md).

## Native transport and service lifecycle

The socket directory must be private and owned by the service user. Native code opens each path component without following symlinks, pins the directory descriptor, and binds only the leaf name. It rejects pre-existing paths, validates peer UID with `SO_PEERCRED`, uses nonblocking close-on-exec descriptors and handles partial writes without SIGPIPE. Descriptor, concurrent-startup, path-preservation and directory-rename tests exercise the compiled binary.

The installed system unit provides `/run/omarchy-broker` with private permissions and owns its lifecycle. Standalone callers must supply an existing private directory through `OMARCHY_BROKER_SOCKET`; the binary never removes an existing socket or another file. Normal service restarts rely on systemd's managed runtime directory, not unchecked stale-path deletion.

The implementation remains serial. Read deadlines apply after acceptance, not time waiting in the listen queue. A long chat or validation delays later requests. Socket loss does not yet cancel broker-forwarded model generation or validation; the direct private worker already handles its own disconnected clients. Request IDs currently correlate responses, but do not yet provide a durable idempotency journal for mutating broker calls. These remaining R02 requirements must pass before the full protocol milestone is marked complete.

## Build and evidence

Build with the pinned Mojo environment using the `build-broker` task, or explicitly name an output artifact and supply it through `OMARCHY_BROKER_BINARY` to the native tests. There is no arbitrary `/tmp` fallback. The installed binary must be replaced explicitly after a tested build; recompiling source elsewhere does not update the service.

See [protocol verification](broker-protocol-verification.md), [worker service verification](task-worker-verification.md) and the [operating guide](wsl-test-build.md). The wider build roadmap remains separate from these transport checks.
