# Interrupted validation recovery — October 5, 2026

The validation service now reconciles recorded work before opening its endpoint after startup. An interrupted validation is never marked successful or automatically re-executed. The operator can retry reconciliation with `goose --recover-workers`; the broker's read-only `worker_recovery` action returns the latest bounded summary.

## Recovery contract

Recovery inventories registered task directories and reserved capability-probe directories. Each inventory is bounded to 10000 entries and 1000 matching directories, with a 45-second reconciliation deadline. Reports are written atomically to the private `ROMS_DATA_DIR/patches/recovery.json`; responses include counts and at most 16 blocked/busy entries plus the report path.

A task can be recovered only after taking its nonblocking task lock and verifying its stored proposal/preimage digests. Active locked tasks are skipped. Only `validating` and `cleanup_required` states are reconciled. Each existing check directory must be private, owned and not a symlink. Its container journal must identify the expected stage. Cleanup uses the existing exact random task label, stops only matching recorded containers, and queries again to establish their absence.

After successful reconciliation the task becomes `interrupted`; its patch, stage, original-file records and evidence remain available. No source checkout is changed, and no apply or rollback is performed. The interrupted task does not reuse old validation evidence: an operator must stage a fresh task from the proposal before re-running checks.

Capability probes now hold a lifetime file lock and a durable ownership marker in a UUID-named private directory. Startup skips active probes. For an abandoned owned probe it cleans any recorded container, verifies absence and removes only that probe's disposable directory. Unidentified directories without a container journal are retained. An unidentified directory with a journal, a symlink, corrupt required record, mismatched stage or cleanup failure is reported as blocked instead of being removed.

Any unresolved cleanup blocks new capability probes and task validation; ping, task inspection and recovery reporting remain available. `goose --recover-workers` retries the same reconciliation after the underlying problem is corrected. It does not accept arbitrary paths. The broker exposes reporting only; it has no recovery mutation, apply or approval action.

## Evidence

The initial combined service/recovery run passed 20 tests. The completed focused recovery suite passed 7/7, covering preserved stage/source files and idempotence; active task locks; unidentified and symlinked probe folders; retained cleanup failure, launch blocking and retry; capability ownership/locks; and two real process-death scenarios.

In the active-validation scenario, a real test container and its host process were observed before killing the validation service process. The task remained `validating` across the forced death. A fresh service instance recovered its journal, removed the container, verified the process disappeared, marked the task `interrupted`, preserved its staged files and restored usable validation capacity. No successful result was fabricated.

In the capability scenario, a deliberately delayed real probe container existed when its service was killed. A fresh instance removed the recorded container and its owned temporary probe directory; a subsequent ordinary native/container probe succeeded.

The installed user service and native broker were restarted with the new code. The live boundary verifier passed, and the installed `goose --recover-workers` returned a clear report with no outstanding, busy, retained or blocked work. These checks used the private native Linux journal location, the existing pinned native image and Goose 2.9B.

The expanded fixed verifier separates staged-patch tests from service/recovery tests, retaining bounded per-group execution. Its first run passed seven of eight groups: 142 Python regressions, 22 native broker checks, live 2.9B/ROMS readiness, nine rootless worker checks, 13 native/combined checks, 40 staging/promotion checks and the installed boundary check. The service/recovery group had one failure because the new fixture used a two-second inspection timeout, shorter than the production control deadline; its cleanup completed and no running containers remained.

The fixture now uses the existing 20-second production control deadline and explicitly waits for a real running container process before injecting death. After that correction and a check proving scan-deadline exhaustion preserves unprocessed work, the entire affected service/recovery group passed **22/22** in 20.95 seconds. The other passing groups were unchanged and were not rerun. This is a targeted recovery from the failed profile run, not a claim that its original exit status was zero.

## Limits

This evidence covers process death and restart, not power-loss persistence certification. Launches record their container journal before creation; recovery relies on those private records remaining intact. Missing or corrupt required task records block recovery, and legacy/unidentified probe journals require inspection. The service does not enumerate and delete arbitrary containers or infer ownership from their contents. Recovery of interrupted proposal creation, automatic stale-worktree removal, asynchronous conversational jobs and user cancellation controls remain separate work.
