# ROMS GitHub readiness — September 27, 2026

## Recommendation

Ready to share as a **private, experimental Python developer preview**, with the boundaries below. **The Mojo bridge is now fixed and protocol-tested; this is still not a production-safe autonomous agent platform.** No GitHub repository was created or uploaded during this review.

Suggested repository: `buzburgai-arch/roms` (availability not checked). Suggested description: “Local document retrieval, MCP tools, and reusable skills for agents. Python developer preview with experimental Mojo components.” Keep it private while finishing broader deployment checks, especially if it will contribute to the competition harness.

## Completed changes

- Replaced unsupported latency, token-reduction, feature-parity and hallucination-prevention claims with a factual README and reproducible setup commands.
- Added portable filename validation to knowledge writes, skill writes/reads and trajectory-to-skill output. Traversal, device names and symlink escapes are rejected.
- Serialize knowledge metadata with the existing frontmatter library so quoted or multiline titles cannot inject new metadata keys.
- Removed completion reuse keyed only by chat messages. Each gateway request now reaches the backend, preserving changes to model, generation parameters and retrieved context.
- Validate text-message request shapes and default the gateway to localhost. Gateway startup initializes the database, tool registry and knowledge index.
- Send Python MCP startup and watcher diagnostics to stderr so they do not corrupt the stdout protocol stream.
- Disable experimental container execution by default. Its timeout handling does not yet establish reliable container termination; opting in is for trusted experiments only.
- Declare the gateway's direct dependencies explicitly; add offline regression tests and a Windows/Linux Python 3.11/3.12 CI matrix.
- Expand Git exclusions for credentials, environments, databases and generated datasets. Preserve Apache-2.0 LICENSE and Buzburg NOTICE.

## Verification performed

| Check | Result |
| --- | --- |
| Original integration suite before fixes, isolated runtime | 18 passed, 1 failed: health test depended on a pre-existing default database |
| Complete Python suite after fixes, Windows Python 3.11.16 | 43 passed, 1 skipped in 20.11 seconds |
| New offline regression suite, fresh Windows environment | 24 passed, 1 skipped in 11.06 seconds |
| Skip reason | Windows did not permit creation of a symlink for the escape test; Linux CI retains it |
| Installed package compatibility | `uv pip check`: 108 packages checked, all compatible |
| Existing environment vulnerability audit | `pip-audit`: no known vulnerabilities found at time of scan; this is not a guarantee of security |
| GitHub CI | Workflow added locally, not run on GitHub yet |
| Mojo toolchain | Existing project-local Mojo 1.1.0 identified through WSL |
| Mojo server compilation | Follow-up fix: passed with Mojo 1.1.0; explicit PythonModuleBuilder bindings replace raw Mojo function arguments |
| Mojo MCP interface | Passed live stdio handshake, ticket lifecycle, seeded retrieval, resource/prompt, invalid-limit and startup-failure checks |

Initial sandbox-only dependency loading failed with Windows DLL access denied. Running the same existing environment with permitted access allowed the tests to execute. No dependency reinstall was needed for that failure. A missing `pip` module in the existing uv-managed environment was handled by using `uv pip check`.

The full integration suite used the cached embedding model with offline mode enabled and temporary copies of knowledge/skills plus a temporary database directory. User documents and the existing runtime database were not used as test fixtures. The fresh environment validates only the lightweight offline suite, not a fresh full embedding-model installation.

## Local-memory follow-up

Added a shared Python/SQLite lesson store to both MCP servers: seven tools, a usage prompt/resource, project filters, evidence records, correction/retraction/deletion, expiry and bounded keyword recall. Automatic trajectory distillation now writes inactive candidate skills. The [memory guide](local-memory.md) explains use and the caller-supplied evidence boundary. No Hindsight service or runtime dependency was added.

| Check | Result |
| --- | --- |
| Complete Python suite, Windows Python 3.11.16 | 63 passed, 1 symlink-permission skip in 37.26 seconds |
| Offline safety and memory tests, fresh Windows environment | 44 passed, 1 symlink-permission skip in 5.27 seconds |
| Offline safety and memory tests, Linux/WSL Python 3.12.14 | 45 passed in 14.17 seconds, including the symlink check |
| Strict type check of the two new runtime modules | `mypy --strict --follow-imports=silent`: passed |
| Memory/draft suite after final type and message corrections | 20 passed in 3.91 seconds |
| Compiled Mojo 1.1.0 server, live MCP SDK | All seven memory tools, scope filtering, correction, resource/prompt and existing ticket/search/error checks passed; 14 tools advertised |

Tests used isolated databases and sample evidence; no live lesson was created for the operator. The existing Mojo binary loads the updated Python bridge at runtime, so this change did not require rebuilding native code. GitHub CI now includes the memory suite; remote CI has not been run. Memory implementation files are shared Python code, not native Mojo kernels.

Backups of edited files are under `Github Gemini/output/roms-memory/before/`. The source-only preview and its explicit manifest were refreshed after this follow-up. Nothing was pushed to GitHub.

## Native context-selection follow-up

Added `memory_prepare_context` with a native Mojo selection kernel and a matching Python fallback. The tool packs complete, source-bearing records into a character budget, reserves a relevant failure warning when it fits, and discloses omissions and pool truncation. Both servers now expose eight memory tools; the compiled Mojo server advertises 15 tools total.

| Check | Result |
| --- | --- |
| Complete Windows Python suite | 80 passed, 1 symlink-permission skip in 25.89 seconds |
| Linux/WSL offline suites | 62 passed in 17.07 seconds, including symlink validation |
| Strict type checks | Passed for selector, context builder, memory tools, Mojo bridge and benchmark |
| Mojo 1.1.0 compilation | Server and benchmark compiled successfully |
| Native/reference equivalence | 400 seeded cases matched; five malformed native inputs rejected |
| Exact packing correctness | 150 small Python cases matched exhaustive subset search |
| Live compiled-server MCP | Native budget enforcement and failure warning preservation passed alongside existing memory, ticket, retrieval and error checks |
| Local context preparation fixture | Python 8.386957 ms, Mojo 1.951127 ms median, including SQLite and JSON; excludes MCP/model time |

The [native context guide](native-context.md) includes reproduction commands, raw benchmark data and the tiny all-fit case where Python was faster. These synthetic measurements do not establish a repair-success, token-use or competition advantage. The kernel is native; memory storage and transport remain Python. Evidence remains caller-supplied, and skills still default to inactive drafts.

Source backups and build/test outputs are under `Github Gemini/output/roms-native/`. The source-only preview was refreshed without publishing a repository. Compiler crash-reporting initialization emitted a warning, but both builds exited successfully and the resulting binaries passed their checks. GitHub CI now includes the context tests; remote CI has not been run.

## Remaining before a broader public launch

1. Complete real-model Mojo ingestion testing in a fully installed Pixi environment. The bridge now compiles and passes the live protocol fixture; the seven-check Mojo runner also compiles and now propagates failed checks. Its complete model-dependent run was not performed in this follow-up. See [Mojo verification](mojo-bridge-fix.md).
2. Verify the CI matrix on GitHub, a full clean Python install/model download, and broader MCP client integrations. The compiled Mojo server has passed a real MCP SDK handshake and tool calls. The offline suites passed locally on Windows 3.11 and Linux/WSL 3.12; the complete remote CI matrix and clean full-model installation remain unverified.
3. Exercise live gateway streaming, backend failures, tool-call compatibility and startup/shutdown. Current request validation deliberately accepts text messages only. The gateway has no authentication and must remain local.
4. Keep container tools disabled until subprocess cancellation, container cleanup and resource limits are tested. Review any Python plugin before loading it; plugins run as the host user.
5. Confirm authorship/licensing of externally sourced code and playbooks before public release. LICENSE and NOTICE exist, but this review is not an independent provenance audit.
6. Measure retrieval quality and latency on a documented workload before publishing performance comparisons. Experimental research/dataset helpers are not evidence of model training or factual verification.

Additional engineering limits: fixed 384-dimensional embeddings; model changes require a compatible model and rebuilt index. Local generated records can contain sensitive text. Mojo launchers now require Pixi in Linux/WSL and anchor execution to the project directory. The source tree is not currently its own Git repository; avoid Git commands that accidentally operate on an ancestor repository.

## Upload contents and recovery

The accompanying release archive contains an explicit source/documentation allowlist, not the entire working directory. Excluded: `.venv`, `.pixi`, runtime data, caches, reference PDFs, generated datasets, secrets and backups. Git ignores do not remove already tracked files; inspect the staged file list when initializing a new repository.

Original versions of edited existing files are backed up outside ROMS under `Github Gemini/output/roms-readiness/before/`. The publication file manifest, targeted credential scan and dependency audit are beside those backups. Do not upload the review-output directory wholesale. It includes local records and environments.

Use `ROMS-github-preview.zip` for a reviewed source snapshot. It includes the repaired experimental Mojo bridge and its protocol regression test; verification is limited to the documented scenarios. Review GitHub visibility and account ownership before publishing. No competition data is intentionally included.
