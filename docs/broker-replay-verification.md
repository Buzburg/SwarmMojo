# Durable broker validation replay

`task.validate` now binds a request ID to a canonical request digest, persists intent before contacting the private worker, and saves the exact bounded reply before sending it. Matching completed requests replay that reply; different arguments return `CONFLICT`. Pending intents return `REQUEST_UNCERTAIN` and never dispatch again automatically. The retained task remains queryable through `task.status`.

This is at-most-once broker dispatch, not a claim that every interrupted operation completes or that every lost reply can be reconstructed. Existing worker task journals and cleanup recovery continue to own validation state. Read-only actions and ephemeral chat do not reserve durable IDs. The private worker protocol and operator approval/apply boundary are unchanged.

## Evidence

The fixed offline profile includes 24 request-journal tests. They cover exact success/failure replay, equivalent JSON, conflicts, concurrent retries, actual child-process death after a durable fixture side effect, restart after a completed reply, lost worker replies, failed intent/result writes, record capacity without eviction, corrupt/oversized records, digest mismatches, symlinks/hardlinks/FIFOs, ownership/permission checks, bounded lock waiting, invalid arguments and oversized backend replies.

The live native-broker service test validates a real staged fixture through the actual confined worker. Repeating the request returns the same capability timestamp and reply; changing its task ID returns `CONFLICT`. The test then kills the compiled broker, starts a new process using the same journal and a new private socket, and verifies exact replay. Task history contains one validation transition, and the original source remains unchanged. The broker retains `NoNewPrivileges=1`.

The installed `omarchy-broker` service was restarted to load the updated Python action module; its compiled transport did not change. An installed-socket check used a fresh nonexistent task ID to verify a private durable failure reply, exact retry, conflicting-ID rejection and absence of implicit task creation. The synthetic request record is deliberately retained; deleting it would discard its replay binding.

The final full profile passed **9/9 required groups** with no required live group skipped:

| Check | Result |
| --- | --- |
| Offline ROMS regressions | 253 passed |
| Compiled native broker | 24 passed |
| Installed 2.9B model and ROMS | Ready |
| Rootless worker lifecycle | 9 passed |
| Native and combined sandbox | 13 passed |
| Staged validation and promotion | 40 passed |
| Project worker and recovery | 22 passed |
| Installed worker boundary | Passed |
| Model-assisted workflow and prompt contract | 31 passed |

This includes the previous completed-answer formatting increment. Validation used the already pinned native worker and generic worker images; no model weights, inference settings, compiler dependencies or user project files were changed by this increment.

## Limits

The owned native journal directory retains up to 1,000 request records. Pending records and interrupted atomic-write temporaries consume capacity; new IDs fail closed when it is full. Records have bounded reads and response integrity digests. There is no automatic pruning, expiry, reset or repair interface. A pending request may represent ongoing work or interrupted work; use the original task ID for status and operator recovery. A new request ID is a new request, not a retry.

Cross-process locking protects the short journal transactions, not the duration of validation. Process-death tests are real; physical power-loss durability remains dependent on the underlying filesystem/storage and was not tested. Same-user filesystem tampering is outside the isolation boundary, although invalid records, links and unsafe permissions are rejected.

Broker generation cancellation, queued-request deadlines, asynchronous jobs and the remaining unimplemented R02 actions still need work. This increment does not complete the full protocol or PDF roadmap. See the [broker contract](omarchy-broker.md) and [implementation checklist](../../tasks/todo.md).
