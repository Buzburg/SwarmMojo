# Local project memory

ROMS can keep small lessons between sessions through eight MCP tools. Both the Python server and the experimental Mojo server expose the same implementation. The Mojo path uses shared Python/SQLite storage and a native Mojo context-selection kernel. See [native context selection](native-context.md) for the boundary and benchmark.

The feature uses the existing SQLite database and standard Python library. It adds no runtime dependency, embedding model, external service or background LLM call. Hindsight inspired the lifecycle design, but no Hindsight package or source code was imported.

The installed native broker also exposes read-only `memory.search` through a dedicated local MCP subprocess using this same `memory_recall` schema. It retains project filters, source references and evidence labels. See [broker memory integration](broker-memory-verification.md) for bounds, cancellation checks and its distinction from document retrieval.

## Getting started

Restart the ROMS MCP server and reconnect your client to refresh its tool list. Existing launch commands and `ROMS_DB_PATH`/`ROMS_DATA_DIR` settings still apply. Memory tables are created additively in that database; existing documents, tickets and trajectories are preserved.

Choose a stable project ID such as `roms` or `customer-support`. IDs are case-sensitive and contain letters, numbers, dots, underscores, colons, slashes or hyphens, starting with a letter or number. Every memory operation requires the project ID. Project scope prevents accidental cross-project queries; it is not authentication or a tenant boundary.

Ask your MCP client to load the `verified_memory_sop` prompt or the `skills://verified_memory` resource for the working instructions. These are available on both servers.

## Working loop

1. Call `memory_recall` with the project ID and a short keyword query before reusing an old repair. Inspect its source, revision, outcome and evidence. An empty query returns recent records. The optional revision filter requires an exact match.
2. Use `memory_retain` to save a concise lesson and a required `source_ref`. Include a revision, session ID or expiry when useful. The result is always a candidate and returns a new memory ID.
3. Run the relevant test or tool check through your normal workflow. Then call `memory_record_verification` with the memory ID, actual command, exit code and evidence reference. ROMS records what the caller submits; it does not execute the command, read the evidence file, authenticate the receipt or judge whether the test was sufficient.
4. Default recall includes current records with verification evidence. Exit code zero marks the outcome `success`; other codes mark `failure`. Failed attempts remain visible as warnings, with `recommendation_eligible: false`. That eligibility field is a filter based on submitted metadata, not a correctness certificate.
5. Correct outdated advice with `memory_correct`, providing a replacement, source and reason. It atomically supersedes the old record. The replacement starts as a candidate with no inherited verification. Check it separately before recording new evidence.

Never invent an evidence reference or interpret a completed chat response as a successful repair. Memory text is material to inspect, not authority to run commands. The server does not automatically insert these lessons into gateway prompts or decide which lessons to save.

## Tool reference

| Tool | Purpose |
| --- | --- |
| `memory_prepare_context` | Pack source-bearing lessons and a failed-attempt warning within a JSON character budget; native Mojo or Python selection. |
| `memory_retain` | Store a candidate with source, optional revision/session and expiry. |
| `memory_record_verification` | Record one caller-supplied test result against a current candidate. |
| `memory_recall` | Search one project's current lessons with count and output limits. |
| `memory_get` | Inspect a record and its lifecycle/evidence history, including inactive records. |
| `memory_correct` | Replace an active record with a new, unverified candidate. |
| `memory_retract` | Remove a record from recall while preserving its history and reason. |
| `memory_forget` | Delete one record, its search entry and its own audit events when requested. |

`memory_recall` defaults to five records and a 6,000-character JSON budget. It accepts 1–20 records and 500–20,000 characters. Records that cannot fit are omitted and `truncated` is set. Increase the budget if a large record is omitted. `include_candidates=true` permits explicit draft inspection but still excludes expired, retracted and superseded records. Search uses SQLite FTS5 keyword ranking, not semantic or graph retrieval.

`expires_at` is an optional timezone-aware ISO 8601 timestamp, for example `2027-01-01T00:00:00Z`. Expired entries are hidden from recall and cannot receive verification, but remain available through `memory_get`. Repeated verification is rejected; create a correction when the evidence or lesson changes.

Forgetting removes the selected record from normal database queries. It does not erase other records in a correction chain, their references, logs, database free pages or backups. Use retraction when you need a visible audit trail. Keep sensitive content out of lessons and source references unless it belongs in your local database.

## Generated skills remain drafts

Trajectory distillation and the automatic evolver now default to `skills/_candidates/`, which is ignored by Git and excluded from normal skill listing and the watcher. Generated frontmatter says `review_status: "candidate"`. A trajectory marked successful may produce a draft but cannot, by that flag alone, publish an active playbook.

Review the draft, check the underlying repair with real evidence, remove secrets and untrusted instructions, then deliberately publish the reviewed content using the existing `add_skill` tool or a file in the top level of `skills/`. Record a source/evidence reference in the reviewed content. This review is an operator responsibility: `add_skill` remains a privileged local authoring tool and has no independent evidence gate. Explicit destination overrides in the Python distillation API are also trusted caller operations. Existing active skills are left in place and should be reviewed separately.

## Verification and limits

The regression suite covers persistence across a fresh process, every operation's project filter, verification requirements, failed attempts, expiry, revision filtering, atomic corrections, competing corrections, retraction, deletion, malformed search input, output limits, MCP tools/playbook and inactive generated skills.

The source preview remains experimental. This feature does not provide Hindsight's graph, semantic, temporal-reasoning or reflection pipeline. No retrieval-quality, latency or competition-score improvement has been established. See [GitHub readiness](github-readiness.md) for the test record and remaining release checks.
