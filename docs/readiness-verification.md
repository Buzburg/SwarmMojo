# Readiness contract verification — October 5, 2026

The installed broker distinguishes arbitrary chat execution (disabled), the operator-guided project workshop, and the private validation worker. All status aliases derive their model/gateway facts from live health, reject malformed or incomplete readiness claims, and attach reasons to unsupported features. Status uses a one-second read-only worker ping; it neither starts a container nor certifies confinement. The actual enforcement probe remains `worker_status` and is repeated before validation.

Kernel ABI availability is separately reported against the native sandbox's ABI-3 minimum. An ABI result never sets `enforcement_verified` true. Knowledge-library indexing is explicitly `not_probed` because a status request does not perform an import or embedding computation. Workshop availability also requires configured gateway authentication.

The native socket tests now isolate their worker endpoint and resolve the current build explicitly, removing their historical `/tmp/omarchy-broker` fallback. The empty-artifact regression supplies a successful Python-regression result but no broker executable and requires a nonzero incomplete profile. Existing framing, peer identity, socket ownership and restart protections remain exercised by the actual compiled binary.

The focused broker/readiness/compiled-process run passed **40 tests and nine subtests**. It covers all status aliases, disconnected and malformed model health, worker failure, the ABI boundary and empty-artifact refusal, alongside existing native transport checks. The full nine-group workflow passed before these status-only changes; its results are preserved in [project workshop verification](project-assistant-verification.md).

The actual verifier was then run with a new empty environment directory and no executable override. All **154 Python regressions passed**, but the missing compiled broker was reported `INCOMPLETE` and the process exited **1**, with only one of two required groups passing. The full output is retained at workspace `tmp/readiness-empty-artifacts.log`. This is the intended negative gate, not an unresolved build failure.

After restarting the installed broker, `goose --status` reported live `goose-2.9b` and ROMS readiness, a reachable private worker and available workshop. It explicitly reported unsupported desktop/state/web/delegation/training features and did not certify the unprobed knowledge index or enforcement.

This contract certifies reporting and selected verification behavior only. It does not turn missing integrations into complete features. The deployment guide now links concrete evidence and removes old unsupported performance/state claims; the broader roadmap remains open.
