# Omarchy RWKV-7 build readiness

This is a custom Arch/Omarchy **WSL test build**, using the supplied Goose 2.9B model and ROMS. Ubuntu has been removed after a verified recovery export. This is not a completed native Omarchy desktop or a production-certified release. The 7.2B upgrade and fine-tuning are deferred to the new computer.

## Working entry points

The workspace contains `Open Omarchy.cmd`, `Open Goose.cmd`, `Open Knowledge Library.cmd` and `Open Project Workshop.cmd`. The [operating guide](wsl-test-build.md) records installation paths and limits. `goose --status` checks the live gateway/model and worker reachability; `goose --worker-status` performs the actual combined confinement probe. A reachable worker is not an enforcement pass.

| Area | Current evidence | Limit |
|---|---|---|
| Local inference and ROMS | Real Goose 2.9B chat, local-policy retrieval and cold-start checks | Broader generation quality remains unmeasured |
| Knowledge library | [Actual embeddings, indexing, refresh and removal](source-intake-verification.md) | Supported text files only; no PDF/Office intake |
| Native broker | Compiled-process socket/protocol tests; live gateway and worker routes | Serial requests; direct native model C adapter and MCP integration unfinished |
| Confinement | [Actual Mojo Landlock plus rootless-container tests](native-sandbox-verification.md) | Registered Python validation commands only |
| Editing | [Real model draft, validation, apply and rollback](project-assistant-verification.md) | Four selected files / 4 KiB; explicit operator approval |
| Validation recovery | [Forced service death and recorded-worker cleanup](worker-recovery-verification.md) | Process-death evidence, not power-loss certification |
| Recurrent state and fork | Unavailable | Prototype buffers are not real model state |
| Desktop control, web evidence, guest delegation | Unavailable | Adapters/providers are not integrated |
| Training and native image release | Unfinished | No trained checkpoint or tested custom boot image |

## Verification contract

`scripts/verify_all.py` verifies a named test-build profile, not every item in the original PDF. Its base checks are offline ROMS regressions, the current compiled native broker and live model/ROMS readiness. `--offline` explicitly omits live readiness. `--containers`, `--sandbox`, `--staging` and `--drafts` add required groups; missing selected artifacts/prerequisites produce an incomplete result and nonzero exit.

The installed nine-group profile uses all four flags and the pinned worker images recorded in the linked evidence. It passed with 142 offline tests, 22 native-broker tests, nine container tests, 13 confinement tests, 40 staging/promotion tests, 22 service/recovery tests and 28 project-workflow tests, plus live readiness and installed boundary checks. That evidence predates the additional status-contract tests; the new focused results are recorded in [readiness verification](readiness-verification.md).

The verifier and native tests resolve an explicitly supplied executable or the configured environment's current build. They do not accept an unrelated `/tmp` binary. An empty-artifact regression proves that passing Python checks cannot make a missing native executable count as success.

`STATUS`, v1 `status` and `rwkv_status` share one feature inventory with reasons. Legacy `sandbox: disabled` and `tool_execution: false` refer to arbitrary chat execution, identified by `sandbox_scope`. The separate validation worker may be reachable while its enforcement remains unprobed. `landlock_probe` / `sandbox_status` report the kernel ABI only and explicitly set `enforcement_verified: false`; they never substitute for `worker_status`.

## Completion requirements

The [original task list](../../tasks/todo.md) remains authoritative for the broader build. Missing state, desktop, web, delegation, packaging and evaluation work is not waived by passing the test-build profile. Earlier prototype performance projections and claims of working recurrent-state serialization have been removed from this guide because they were not supported by real runtime evidence. Use the supplied models and pinned runtime already installed; the old downloader/native-library instructions are not certified.
