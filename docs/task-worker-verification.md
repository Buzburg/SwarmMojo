# Private validation service — October 5, 2026

The installed native Mojo broker can now route validation of an existing staged task to an independent same-user service. This completes the conditional isolation gate for that registered validation route. Model-generated proposals, conversational tool orchestration, MCP integration and arbitrary execution remain separate unfinished work. `STATUS` continues to report chat tool execution disabled; `worker_status` is the explicit, actively probed project-validation capability.

## Architecture and interface

`omarchy-task-worker.service` runs under the operator's systemd user manager. Its private endpoint is `/run/user/1000/omarchy-task-worker/worker.sock` in a mode-0700 service-managed directory; the socket is mode 0600. Both peers verify Unix credentials. The installer enables the existing user's lingering manager so the service can start without an interactive terminal. `install_wsl_services.py` includes this component, and `scripts/install_task_worker.py` can update it independently.

The worker starts through `env -i` with an explicit environment allowlist and does not read the model/gateway credential file. Its clean environment was verified from the actual running process without printing credential values. The broker and ROMS retain `NoNewPrivileges=1`. The dedicated user worker allows the rootless runtime's namespace-mapping helpers to operate; actual validation processes still run inside the existing capability-dropped, no-new-privileges, resource-limited, network-disabled container and native Landlock policy. No service was made root, and the broker cannot bypass confinement by falling back to a host command.

The worker accepts one bounded JSON request per connection, exact version/action/argument fields and unique keys. Requests are limited to 4096 bytes with a five-second read deadline; responses to 65536 bytes. At most 16 client handlers are retained and one capability/validation operation runs at a time, with a short busy response for contenders. Task status remains available while validation runs. Client disconnect or service termination cancels validation and waits for its existing explicit container cleanup lifecycle.

Accepted worker actions are `ping`, `capabilities`, `task.status` and `task.validate`. The latter two take only a validated `task_id`. There is no source-registration, shell, image-selection, approval, apply or rollback action. The native broker exposes the last two actions and maps `worker_status` to the capability probe; its existing 1024-byte transport frame remains sufficient for these ID-only requests.

Before validation changes task state, an actual registered syntax check runs through the installed container/native path. Missing image configuration or unavailable confinement leaves the task staged and returns an unavailable result. Each subsequent check independently uses the same no-fallback confinement path. Capability responses name the tested policy, immutable image ID, sandbox fingerprint and check time. A failed code check is reported as `validation_failed` with task state and retained evidence, not as a successful validation or a malformed request.

Operator commands:

```sh
goose --worker-status
goose --validate-patch TASK_ID
```

The existing validation command now requires this service and has no silent local fallback. Project registration, proposal staging, inspection and operator-approved apply/rollback retain their separate established interfaces.

## Evidence

The complete seven-group verifier passed: 142 Python regressions, 22 real native broker tests, live 2.9B/ROMS readiness, nine rootless worker lifecycle checks, 13 native/combined sandbox checks, 53 staged-patch/promotion/service checks, and the installed worker/broker boundary check.

The service suite exercised malformed/duplicate/oversized requests, protected endpoint ownership, preservation of a pre-existing endpoint file, actual broker routing with `NoNewPrivileges=1`, failure before task transition when isolation is unavailable, and actual container disappearance after client disconnect. A contender received `worker_busy`, and a subsequent real probe succeeded after cleanup released the slot.

The installed boundary verifier inspected both existing services' restrictions, verified the worker's environment allowlist, and ran real probes directly and through `/run/omarchy-broker/broker.sock`. Its optional `--lifecycle` check also passed graceful restart and recovery after killing the idle worker; systemd recreated its private runtime endpoint. These tests do not certify host death during an active container operation.

A check immediately after service restart exposed an application-startup race. The verifier now waits up to 15 seconds for an actual `ping` response, then performs the real capability probes. Re-running the installed boundary and lifecycle checks after this correction and the final worker restart passed.

After the final diagnostic refinement, the complete focused service suite passed **14/14** in 22.93 seconds. Its additional bad-syntax task returned `validation_failed`, retained the actual nonzero exit status and `SyntaxError` output, and left the source unchanged. This focused rerun follows the full-profile pass. All project mutations in integration tests were confined to disposable fixtures, with original source files unchanged.

## Remaining work

Startup reconciliation of recorded validation tasks and owned capability probes is now implemented and tested through forced process death. See [recovery verification](worker-recovery-verification.md). Unknown cleanup state still preserves the workspace and blocks new validation. Power-loss durability and legacy unidentified probe journals remain outside that certification.

Subsequent increments added model-assisted proposals through the project workshop and [asynchronous broker scheduling](broker-scheduling-verification.md). Broker status now remains responsive during validation; disconnected validation callers can retrieve the durable reply later. Explicit user-facing task cancellation controls and the full Checkpoint F conversation remain unfinished; this checkpoint does not claim them complete.
