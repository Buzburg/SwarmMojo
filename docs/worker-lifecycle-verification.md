# Rootless worker lifecycle — October 5, 2026

T05's timeout/cancellation milestone is implemented and verified in the installed Omarchy WSL distribution. This does not enable assistant command execution: the service setting remains `ROMS_ENABLE_EXPERIMENTAL_EXECUTION=0`. Native Landlock enforcement, broker action authorization, reviewed patch promotion and complete confinement verification remain separate gates.

## Implemented behavior

- A single capacity guard surrounds each asynchronous tool call. The registered MCP handler delegates to that guard. Queue waits remain bounded and permits release after cleanup, including cancellation.
- A rootless, local Podman worker receives a random task label and a private journal outside its writable mount. Creation and attached execution are separate, so cleanup can find the task's exact containers even if creation is interrupted before the caller receives an ID.
- Timeout, cancellation and output overflow kill/reap the client process group, force-remove owned containers, and verify their absence before deleting a temporary workspace. Repeated caller cancellation cannot interrupt the bounded cleanup sequence.
- Cleanup failure reports `cleanup_required` and retains both journal and workspace. Retry with `goose --cleanup-worker task_ID`, using the exact ID from the failure. This command removes remaining owned containers and verifies absence; it preserves retained files for inspection. Worktree cleanup failure also retains an explicit record.
- The worker environment excludes host API keys and Git/remote-container overrides. Workers use preinstalled images (`--pull=never`), no network, dropped capabilities, no new privileges, a read-only container root, a writable task mount, a bounded temporary filesystem, 128 processes, configured CPU/memory limits, 512 KiB captured output, and bounded execution/control deadlines. Missing rootless support returns an error; no host execution fallback exists.
- Detached temporary worktrees leave the source branch and uncommitted user files untouched. Checkout hooks, fsmonitor and configured filters are disabled; lazy fetching and global/system Git configuration are disabled. The compatibility synchronous helper must be called outside an event loop; asynchronous callers use `execute_tool_task_async`.

## Machine prerequisites and provenance

Installed from signed Arch repositories: Podman `6.1.3-1`, crun `1.30.1-1` and their package dependencies. Rootless UID/GID mappings already existed for `rryan` (`100000:65536`). The imported WSL image lacked helper file capabilities; reinstalling signed package `shadow 4.20.0.arch1-1` restored them. This follows the [Arch WSL rootless-container guidance](https://wiki.archlinux.org/title/Install_Arch_Linux_on_WSL). Worker execution ran as UID 1000, not root.

The controlled test image was pulled from `docker.io/library/alpine:3.22`, then tests used its immutable local image ID:

`sha256:c83674e1999044d33d751661371b873539f47e5b5c5ca3320c7e0377acca6238`

Reported manifest digest: `sha256:3e9b4b680bfc9fb5269227cffbd6d42be39fbf7c0b908123913864aa4447e764`.

The installed environment now selects native private worker storage at `~/.local/share/omarchy-harness/workspaces`. The service installer records the same setting. Secrets and the disabled-execution setting were preserved.

## Verification

`scripts/verify_all.py --containers`, with `ROMS_LIVE_CONTAINER_IMAGE` set to the image ID above, passed all four required groups:

| Group | Result |
|---|---|
| ROMS Python regression inventory | 131 passed |
| Compiled native broker | 22 passed |
| Live model and ROMS | ready; `goose-2.9b`; execution disabled |
| Real rootless container lifecycle | 8 passed |

The live tests exercise normal nonzero exit, timeout, repeated cancellation, one-/two-slot tool calls, deliberate cleanup failure and retry, bounded process output, forbidden network override, and temporary-worktree cleanup. Timeout and retry tests inspect the actual worker host PID and verify it is absent afterward. The failure test confirms that the worker is still alive and its workspace retained when removal is deliberately failed, then confirms process death after retry. The worktree test preserves an uncommitted source edit and proves a configured host checkout filter was not executed. Final enumeration found no ROMS-labeled containers.

Passing lifecycle tests does not prove all sandbox boundaries. `--containers` refuses to certify execution when the required local image setting is missing rather than counting skipped live tests as success. Runtime design follows [Podman creation](https://docs.podman.io/en/latest/markdown/podman-create.1.html) and [forced removal](https://docs.podman.io/en/latest/markdown/podman-rm.1.html) contracts.

DEBT(pointdexter): forced host/process death can leave a recoverable journal and worker; revisit before enabling autonomous execution; upgrade to startup reconciliation and service-managed worker ownership. The current retry command supports operator recovery but does not automatically remove retained worktrees.

DEBT(pointdexter): the existing protected gateway service has no-new-privileges enabled and is not yet the supported rootless-worker launch context; revisit during broker execution integration; upgrade to a separate user worker service rather than weakening the gateway's protections.
