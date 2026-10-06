# Omarchy Mojo RWKV7: native broker milestone

## Installed WSL build update — October 5, 2026

The earlier milestone notes below are historical. The installed broker now handles real local chat through ROMS and Goose 2.9B, with a strict JSON v1 parser. It also supports `worker_status`, `task.status` and `task.validate`; task actions take exactly `{"task_id":"32 lowercase hex characters"}` in `args`. Validation is delegated to the private same-user service and never falls back to a host command. Apply/rollback stay in the explicit operator workflow. See [current worker architecture, limits and evidence](task-worker-verification.md). General chat-driven tool execution remains disabled.

## Objective and scope
Build a Linux x86-64 userspace broker on top of Omarchy/Arch, using the existing
ROMS Mojo 1.1.0 toolchain. This is not a new kernel, bootable image, inference
engine, or secured tool executor. The first milestone has no model, network
service, ROMS database access, shell execution, or filesystem tools.

## Protocol v0
One ASCII command followed by LF per Unix-stream connection; one JSON response
followed by LF, then connection close. Maximum 1024 bytes before LF. Commands:

- `PING`: `{"ok":true,"result":"pong"}`
- `STATUS`: reports native Mojo transport and explicitly unavailable RWKV/tools.
- `MOCK`: returns a fixed, clearly labeled mock response; never invokes a model.
- All other commands: `{"ok":false,"error":"unsupported_command"}`.
- Oversized, incomplete/timed-out, and pipelined frames are rejected.

This deliberately small framing contract is not JSON-RPC or MCP. Structured tool
requests will require a versioned contract in a later milestone.

## Safety boundaries
- Require `OMARCHY_BROKER_SOCKET` to name a socket in an existing, private,
  user-owned Linux directory (e.g. a `mktemp -d` directory or XDG runtime dir).
  Do not use shared `/tmp` directly or a Windows-mounted socket directory.
- Resolve runtime directories component-by-component using Linux `openat` with
  O_DIRECTORY, O_NOFOLLOW, and O_CLOEXEC. Reject symlinks and dot components.
  Validate the opened directory via `/proc/self/fd`, then pin it using `fchdir`
  and bind only the socket leaf name. Renaming ancestors cannot redirect bind.
  This requires a mounted procfs and changes the broker's working directory.
- Socket creation uses umask 077. Existing paths are never unlinked or replaced.
- Only connections with the broker's UID are accepted (Linux SO_PEERCRED).
- Listener and accepted sockets are nonblocking and close-on-exec.
- Retry socket operations only for EINTR and EAGAIN/EWOULDBLOCK. Fatal receive
  errors reject the client, fatal sends stop immediately, and fatal accept errors
  terminate with a nonzero exit (including descriptor exhaustion).
- A client is bounded to 100 polling iterations of 20 ms and 1025 input bytes.
  Service is serial; this is a prototype, not a denial-of-service resistant server.
- No permissions/ownership changes, privileged install, disk changes, dependency
  installs, or model downloads. Never report an absent compiler as passing.
- SIGTERM exits via the OS and leaves the socket path; explicit cleanup of the
  private runtime directory is the caller's responsibility. No systemd unit yet.

## Implementation and style
`app_mojo/omarchy_broker.mojo`: native Mojo with libc FFI (no Python transport).
`tests/test_omarchy_broker.py`: standard-library unittest socket tests launching a
real compiled process with an isolated Linux temporary directory. Follow existing
Mojo `def main() raises` and explicit C ABI types; keep borrowed buffers alive
across synchronous calls and close every accepted descriptor.

## Commands (Linux/WSL, from ROMS)
```sh
export MODULAR_HOME="$PWD/.pixi/envs/default/share/max"
export LD_LIBRARY_PATH="$PWD/.pixi/envs/default/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
.pixi/envs/default/bin/mojo build app_mojo/omarchy_broker.mojo -o .pixi/envs/default/bin/omarchy-broker
OMARCHY_BROKER_BINARY="$PWD/.pixi/envs/default/bin/omarchy-broker" .pixi/envs/default/bin/python -m unittest discover -s tests -p test_omarchy_broker.py -v
runtime=$(mktemp -d)
OMARCHY_BROKER_SOCKET="$runtime/broker.sock" .pixi/envs/default/bin/omarchy-broker
```
With an activated, correctly located Pixi environment, the equivalent tasks are
`pixi run build-broker`, then `pixi run test-broker`; `pixi run broker` requires
`OMARCHY_BROKER_SOCKET`. Copied environments can contain absolute paths from the
original location: this copy's ignored `share/max/modular.cfg` was relocated to
this directory. Recreate the environment if other relocated packages fail.
The test suite fails if its compiled binary is absent. Tests must cover actual
socket traffic, fragmented input, invalid requests, bounded clients, existing
path preservation, permissions, disconnect recovery, and concurrent startup.

## Build order
1. Native socket broker and offline protocol tests (this milestone).
2. Versioned structured requests, ROMS memory/retrieval integration, sandboxed
   dry-run workspaces. Landlock must be independently verified before execution.
3. Verify an actual RWKV-7 runtime and checkpoint ABI; add state lifecycle tests.
   Do not assume a library named `librwkv.so` supports RWKV-7.
4. Omarchy desktop integration and reproducible image packaging.

## Verification record
2026-10-04, Ubuntu WSL, Mojo 1.1.0:
- Native Linux binary recompiled with Protocol v1 structured JSON support and temporal anchor.
- 21 real-process protocol tests passed (6.6 seconds); 0 failures.
  Added coverage for `ANCHOR`, `{"v":1,"action":"ping"}`, `{"v":1,"action":"status"}`,
  `{"v":1,"action":"mock"}`, `{"v":1,"action":"anchor"}`, `{"v":1,"action":"sandbox_status"}`,
  and rejection of unsupported v1 actions.

2026-10-02, Ubuntu WSL, Mojo 1.1.0:
- Native Linux binary compiled to `.pixi/envs/default/bin/omarchy-broker`.
- 19 real-process protocol tests passed (6.3 seconds); no model or downloads.
  Added regression coverage for symlinked directories/ancestors, invalid leaf
  names, runtime-directory rename isolation, and 40-client descriptor stability.
  The symlink-directory test failed against the previous binary before the fix.
- Existing Windows offline ROMS suites: 61 passed, 1 existing symlink-privilege
  skip (4.1 seconds in the latest run). No tests were removed or disabled.
- Compiler reports missing Crashpad handler (crash reporter), but compilation and
  actual socket tests succeed. No production-readiness claim.
- Existing model-dependent integration and full Mojo ROMS tests were not run.
- Peer UID enforcement is implemented but cross-UID rejection is not yet tested.
- Graceful signal cleanup, concurrent clients, cross-UID testing, errno fault
  injection, and adversarial resource tests remain before deployment or adding
  any execution capabilities. Directory pinning does not isolate malicious
  same-UID processes or root; no sandbox claim is made. Pipelined bytes already read
  are rejected; bytes sent after a completed first frame are not processed.

References: Mojo 1.1.0 official `std.ffi.external_call`, `std.os.fstat.stat_result`,
and pointer lifetime documentation at https://mojolang.org/docs/std/ffi/external_call/
and https://mojolang.org/docs/manual/pointers/using-pointers/.
