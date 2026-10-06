# Broker-to-ROMS memory lookup

The installed native broker now accepts `memory.search` and calls the existing ROMS `memory_recall` tool over a real local MCP stdio connection. `app.memory_service` registers the shared memory tools directly; it does not start document ingestion, load custom tools or download an embedding model. Each lookup initializes the service, discovers and checks the recall schema, performs the call and shuts down its owned process.

This follows the installed SDK's [stdio lifecycle](https://py.sdk.modelcontextprotocol.io/client/transports/). MCP 2.2.0 and FastMCP 4.0.10 are already pinned in `pixi.lock`; no dependency or lockfile changed. Protocol aliases are used when inspecting SDK result models. The subprocess uses the configured Python prefix, explicit source directory and selected runtime/database environment variables, including paths with spaces. Gateway and model keys are not forwarded.

## Contract

Example broker request:

```json
{"v":1,"id":"lesson-lookup","action":"memory.search","args":{"project_id":"my-project","query":"timezone","limit":5,"max_chars":6000}}
```

Required fields are `project_id` and `query`. Optional fields are `limit` (1–20), `max_chars` (500–12000), `revision` and `include_candidates` (boolean). The result preserves the existing `memories` and `truncated` shape, record IDs, source references, revisions, verification metadata and recommendation eligibility. Oversized responses fail within the broker's encoded frame bound; they are not silently cut into invalid JSON.

Default recall omits candidates, expired, retracted and superseded records. Verified failed attempts remain warnings, not eligible recommendations. Candidate inspection must be requested explicitly. Verification metadata is caller-supplied evidence to inspect, not independent proof of correctness. Project scope prevents accidental cross-project recall; it is not a separate authentication boundary.

This endpoint searches project lessons with the existing SQLite keyword ranking. Imported-document semantic retrieval, automatic conversation context assembly and lesson creation are separate capabilities. Only the fixed recall call is forwarded by the broker; arbitrary tool names, commands, paths and memory mutations are not accepted by this action. The existing memory schema may be initialized additively on first use.

## Capacity and cleanup

The memory lane allows one active lookup and four waiters, with the existing five-second admission deadline. Each lookup has a 20-second execution deadline plus subprocess cleanup. Full client disconnection cancels it. The shared cancellation helper cancels owned work once and shields cleanup from repeated caller cancellation; capacity remains occupied until cleanup settles. Startup and service failures return safe `SERVICE_UNAVAILABLE` errors; the lookup deadline returns `REQUEST_TIMEOUT`.

The SDK owns stdio framing and bounded process shutdown. The endpoint is a fixed trusted local program, not a general remote MCP connector; this increment does not certify the SDK against arbitrary malicious stdout or infinite notification floods. Service status reports project memory as `not_probed`, because a status request does not perform a lookup.

## Evidence

The final offline/native profile passed **2/2 groups**: 273 offline regressions and 46 compiled-native/MCP tests plus 13 subtests. Fifteen memory tests exercise actual service initialization/discovery/call, populated temporary databases, project isolation, source/evidence preservation, failed-attempt labels, explicit candidates, truncation, invalid arguments, startup failure, inaccessible databases, timeout, repeated cancellation and native-client disconnection. Database dumps before and after retrieval/cancellation remain identical. Repeated cancellation must settle within eight seconds and leave no owned child process. The native disconnect test also obtains a separate ping reply while the lookup is active.

The separate existing `tests/test_mojo_protocol.py` passed against a freshly compiled `app_mojo/main.mojo`: native context selection/budget, shared memory lifecycle/scope, ticket lifecycle, seeded native search, resources/prompts, invalid-limit rejection and nonzero startup failure with clean stdout. This seeded-vector test is not evidence of live embedding quality. Verification artifact `/tmp/roms-mcp-memory-verification` SHA-256: `98beaec845973dc178330df97f21a7102961fc54c932e2f139845983cd2c440b`.

The installed broker was restarted and a request through `/run/omarchy-broker/broker.sock` completed the actual MCP lifecycle against its configured database, returning an empty result for the selected `omarchy-build` scope. No synthetic lessons were added to the installed database. The populated-data evidence comes from the isolated tests. The service remains active as `rryan` with `NoNewPrivileges=yes`.

The native broker binary is unchanged from the scheduling increment, SHA-256 `e98afc52498b9204648cfc9c38b2433aaf8148fd43bc299fbe5294e4048817c6`; it loads the updated shared Python dispatcher. This closes T07's first broker-to-memory lookup checkpoint. It does not complete R04's broader context/memory workflow, inference/state milestones or the full PDF roadmap. The 2.9B model remains active; training and the 7.2B upgrade remain deferred.
