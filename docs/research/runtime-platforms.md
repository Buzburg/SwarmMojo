# Runtime platforms for the new SwarmMojo

Assessment note: this source review preceded the final integration. Three pinned Agency playbooks were subsequently added; see [the current evaluation](../UPSTREAM-EVALUATION.md) and [imported skills](../IMPORTED-SKILLS.md). Other runtimes remain uninstalled. Raw research snapshots are retained locally; pinned source links below are the portable evidence references.
Research captured 2026-10-07 UTC (2026-10-06 local time). Scope: public primary-source search, pinned GitHub metadata/source inspection, and read-only inspection of local archives/repositories. No external project was installed, imported, started, or tested. This is an integration assessment, not a security audit or runtime qualification.

## Recommendation

Keep the verified ROMS preparation and workshop boundaries. Implement small durable approval/recovery contracts; connect external agents through the existing MCP surface before adopting another runtime. The strongest concrete references are CopilotKit OpenMuse/OpenBot for action lifecycle, Goose for an external MCP consumer, and Deep Agents for bounded specialist delegation. Defer OpenClaw's channel gateway until there is a demonstrated channel requirement. Nanobot contributes recovery test cases; it does not need to become a second scheduler immediately.

The baseline examined is the ROMS baseline at `2d2e207bf2a97c1370971a5e34dbe3bf80ab7348`. Its preparation harness performs bounded evidence assembly, SQLite lexical retrieval, selected Markdown skill loading, and advisory heuristic decisions. Its preparation path cannot authorize execution. The separate workshop stages and verifies changes before hash-bound human approval. None of the candidates below proves RWKV recurrent-state branching, model quality, GPU acceleration, or a benefit on the future 128 GB machine.

## Preserve the two existing local projects

| Location | Verified identity and state | Required handling |
|---|---|---|
| `Harness Repos/Swarm Mojo` | Git origin is the private `Buzburg/swarm-mojo`; local and remote HEAD both `83bbd3b53785cce4305e39692b620ea66d4ebeed`. Python package version 0.11.0; Aeon lineage; MIT license. Local README is modified and `Context Window Handoff.txt` is untracked. | Preserve checkout, remote, history, and user changes. The new ROMS-derived SwarmMojo must have an explicitly distinct path/repository identity. |
| `Harness Repos/Swarmojo` | Separate research collection, no root Git repository or root license found. Contains `repo_stapler`, `msgl`, `holographic`, media experiments and archives. Its handoff references `gsh_core`, which is absent here. | Preserve as research. Do not treat its handoff's historical test/performance statements as present verification. Check each component's license individually before copying. |

The Aeon-lineage project's integration document already contains bounded AST maps, source hashes, advisory specialist roles and optional external mSGL access. Those are useful concepts to compare against the new code; they are not evidence that the old research collection provides a runnable integrated controller. Private repository identity was verified through authenticated GitHub API. [Existing private repository](https://github.com/Buzburg/swarm-mojo).

## Resolve names before choosing code

**OpenMuse:** the local `Harness Repos/openmuse-main.zip` explicitly points to **CopilotKit/openmuse**. ZIP comment commit `73a714963b57e5cd1747fd3fbc6833e09a36b81a` was verified upstream, dated 2026-10-05. Archive SHA-256: `6894ea7fc12aca6c6bb73270ebed9a586f3c4a71fa63e49d1d453179d3ac7eb6`. It contains an MIT license. This is stronger identity evidence than the bare name. **tahodev/openmuse** and **OpenMuseAgent/OpenMuse** are different projects; the latter was not assessed.

**OpenBot:** no matching top-level local checkout was found in the scoped Harness Repos/Github search. The primary assessed candidate is **CopilotKit/OpenBot**, because the identified OpenMuse explicitly integrates with it. **meetopenbot/openbot** is a separate Melony-based runtime, inspected briefly below. The user's intended OpenBot remains unconfirmed; do not silently substitute a similarly named repository. Other namesakes surfaced but were excluded.

**OpenClaw:** assessed canonical **openclaw/openclaw**. Local files named `openclaw.plugin.json` under the New Harness memory project's adapter folder indicate an adapter, not a verified upstream OpenClaw checkout.

**Nanobot:** local `Harness Repos/Final Harness\nanobot-main.zip` has comment commit `20f115bf4699bffcc786263cb999e7701986e179`, verified in **HKUDS/nanobot**, dated 2026-09-09. Archive SHA-256: `3ea3014bbb854a27e2f624978ea41d7af5e06ce6566445a46e20d7f9296fe07f`; actual archive license is MIT. The current upstream inspected below is newer; do not attribute its current recovery code to the older ZIP without a separate comparison.

## Pinned upstream identities

GitHub default-branch commit API and actual LICENSE text were inspected. These are research pins, not a promise that a moving main branch is production-ready. Dependency, asset, service, and trademark terms still require review when adopting a specific component.

| Repository | Commit inspected | License |
|---|---|---|
| [CopilotKit/openmuse](https://github.com/CopilotKit/openmuse/tree/1ac68f3909f2478ab6280883f1ab5ea65eb5719d) | `1ac68f3909f2478ab6280883f1ab5ea65eb5719d` | [MIT](https://github.com/CopilotKit/openmuse/blob/1ac68f3909f2478ab6280883f1ab5ea65eb5719d/LICENSE) |
| [CopilotKit/OpenBot](https://github.com/CopilotKit/OpenBot/tree/17831b2415b3f764cdb07110ca68fdab18fe8b2d) | `17831b2415b3f764cdb07110ca68fdab18fe8b2d` | [MIT](https://github.com/CopilotKit/OpenBot/blob/17831b2415b3f764cdb07110ca68fdab18fe8b2d/LICENSE) |
| [tahodev/openmuse](https://github.com/tahodev/openmuse/tree/e96d76aafcc538706b61b56f48649df128fca983) | `e96d76aafcc538706b61b56f48649df128fca983` | [MIT](https://github.com/tahodev/openmuse/blob/e96d76aafcc538706b61b56f48649df128fca983/LICENSE) |
| [meetopenbot/openbot](https://github.com/meetopenbot/openbot/tree/276c20ee2f171ddeb0622d349e59d71a77f086ad) | `276c20ee2f171ddeb0622d349e59d71a77f086ad` | [MIT](https://github.com/meetopenbot/openbot/blob/276c20ee2f171ddeb0622d349e59d71a77f086ad/LICENSE) |
| [openclaw/openclaw](https://github.com/openclaw/openclaw/tree/078ca8950dbcb65b47d74a494b64f5aed8376180) | `078ca8950dbcb65b47d74a494b64f5aed8376180` | [MIT](https://github.com/openclaw/openclaw/blob/078ca8950dbcb65b47d74a494b64f5aed8376180/LICENSE) |
| [aaif-goose/goose](https://github.com/aaif-goose/goose/tree/f9c18a81952e8895b6f2d88b0f4569f3975034af) | `f9c18a81952e8895b6f2d88b0f4569f3975034af` | [Apache-2.0](https://github.com/aaif-goose/goose/blob/f9c18a81952e8895b6f2d88b0f4569f3975034af/LICENSE) |
| [langchain-ai/deepagents](https://github.com/langchain-ai/deepagents/tree/16e84d927e7e13c41a10c071380c875af6a562f5) | `16e84d927e7e13c41a10c071380c875af6a562f5` | [MIT](https://github.com/langchain-ai/deepagents/blob/16e84d927e7e13c41a10c071380c875af6a562f5/LICENSE) |
| [HKUDS/nanobot](https://github.com/HKUDS/nanobot/tree/d6ddceed997b53c4adcd56e8b302bd124bfa0c71) | `d6ddceed997b53c4adcd56e8b302bd124bfa0c71` | [MIT](https://github.com/HKUDS/nanobot/blob/d6ddceed997b53c4adcd56e8b302bd124bfa0c71/LICENSE) |

`block/goose` now redirects to `aaif-goose/goose`; preserve the actual resolved identity in attribution and pinning.

## Ranked integrations and acceptance checks

### 1. Reimplement a narrow durable action lifecycle — OpenMuse/OpenBot reference

**What exists:** OpenMuse's `ActionService` hashes prepared input, connection, target and version; expiry and account changes invalidate approval. It atomically claims an action before dispatch and distinguishes an uncertain external outcome from ordinary failure. Its worker uses compare-and-swap leases, renewable ownership and guarded checkpoints. These are actual code paths, not just a roadmap. [Action lifecycle](https://github.com/CopilotKit/openmuse/blob/1ac68f3909f2478ab6280883f1ab5ea65eb5719d/apps/server/src/actions.ts), [worker](https://github.com/CopilotKit/openmuse/blob/1ac68f3909f2478ab6280883f1ab5ea65eb5719d/apps/server/src/engine/worker.ts).

OpenBot's resume service revalidates actor and action digest, consumes approval before executing, and records an unknown result when a consumed action has no saved outcome after interruption. Its policy also supports automatic allowances and model review; those policy choices must not become SwarmMojo authority. [Resume implementation](https://github.com/CopilotKit/OpenBot/blob/17831b2415b3f764cdb07110ca68fdab18fe8b2d/server/src/approvals/service.ts), [policy](https://github.com/CopilotKit/OpenBot/blob/17831b2415b3f764cdb07110ca68fdab18fe8b2d/server/src/approvals/policy.ts).

**Fit:** ROMS already has evidence-bound approval for project promotion. Reuse that boundary; add external-action records only for a concrete business connector. An approval should bind actor, tenant/account, exact arguments, target version, policy version, expiry and intended adapter. Worker leases prevent competing ownership, but cannot guarantee exactly-once remote effects.

**Acceptance:** changed arguments/account/target fail; expired and replayed approvals fail; concurrent dispatch executes once; crash before dispatch is distinguishable from crash after dispatch; uncertain remote results never auto-retry; a revoked/cancelled task cannot start another action; a model's positive review never authorizes execution.

**Do not transplant the platform:** OpenMuse configuration requires an Intelligence key. Its OpenBot adapter is disabled by default and pinned to a different OpenBot contract commit (`a96d88c6...`); current upstream compatibility needs requalification. Native identity/session bridging remains incomplete. [Required service configuration](https://github.com/CopilotKit/openmuse/blob/1ac68f3909f2478ab6280883f1ab5ea65eb5719d/apps/server/src/config.ts), [adapter](https://github.com/CopilotKit/openmuse/blob/1ac68f3909f2478ab6280883f1ab5ea65eb5719d/packages/backends/src/openbot.ts), [integration limits](https://github.com/CopilotKit/openmuse/blob/1ac68f3909f2478ab6280883f1ab5ea65eb5719d/docs/OPENBOT-INTEGRATION.md).

### 2. External MCP consumer recipe — Goose

**What exists:** Goose's permission inspector distinguishes Auto, Approve and SmartApprove; Auto allows tools at that layer, while SmartApprove can trust read-only annotations or model classification. Unknown tools in Approve require approval. It also has recipe validation. This makes it a useful interoperating client, not a replacement authority. [Permission implementation](https://github.com/aaif-goose/goose/blob/f9c18a81952e8895b6f2d88b0f4569f3975034af/crates/goose/src/permission/permission_inspector.rs), [recipe validation](https://github.com/aaif-goose/goose/blob/f9c18a81952e8895b6f2d88b0f4569f3975034af/crates/goose/src/recipe/validate_recipe.rs).

**Fit:** a pinned, optional recipe connecting to SwarmMojo's existing preparation MCP tool is smaller than embedding Rust/Electron or duplicating its agent loop. The consumer may suggest a next step; the server keeps authority. This is unrelated to the old ROMS heuristic classes formerly named Goose and is not RWKV state integration.

**Acceptance:** real MCP handshake/schema/cancellation tests; preparation succeeds with no tool execution; unknown tools unavailable; a client in Auto mode still cannot promote or approve; protocol errors produce explicit failures; recipes cannot smuggle server root/DB configuration through model-supplied arguments.

### 3. Bounded specialist jobs — Deep Agents pattern, optional adapter

**What exists:** isolated subagents receive the delegated task by default; forked context is an explicit experimental choice. The graph supports skills, filesystem backends, and interruption/checkpoint infrastructure. Declarative child permissions can replace inherited rules; compiled and remote children do not automatically inherit the parent's interruption policy. Filesystem rules apply to built-in tool wrappers, not arbitrary direct backend use, and unmatched paths are allowed. [Subagent implementation](https://github.com/langchain-ai/deepagents/blob/16e84d927e7e13c41a10c071380c875af6a562f5/libs/deepagents/deepagents/middleware/subagents.py), [graph assembly and permission contract](https://github.com/langchain-ai/deepagents/blob/16e84d927e7e13c41a10c071380c875af6a562f5/libs/deepagents/deepagents/graph.py).

**Fit:** preserve the small core and create bounded role requests/results: role, selected evidence hashes, input/output limits, deadline, cancellation, and explicit advisory status. Use an optional Deep Agents adapter only if a concrete LangGraph consumer needs it. Do not replace the deterministic preparation engine with a mandatory model/provider framework.

**Acceptance:** independent role contexts cannot read sibling secrets; total context/output limits enforced; duplicate and late results rejected; child/remote tools get explicit least-privilege policy; refusal survives checkpoint resume; child “approved” text remains untrusted; no interpretation of conversation forks as recurrent model-state forks.

### 4. Channel gateway later — OpenClaw

**What exists:** a layered policy pipeline progressively filters tools and preserves the layer's diagnostic provenance. Its documentation correctly separates sandbox placement, tool availability and elevated execution. Blocking file-write tools does not make a permitted shell read-only; sandbox-off runs on the host, and ordinary elevated execution can leave the sandbox. [Policy code](https://github.com/openclaw/openclaw/blob/078ca8950dbcb65b47d74a494b64f5aed8376180/src/agents/tool-policy-pipeline.ts), [runtime boundaries](https://github.com/openclaw/openclaw/blob/078ca8950dbcb65b47d74a494b64f5aed8376180/docs/gateway/sandbox-vs-tool-policy-vs-elevated.md).

**Fit:** borrow clear “why blocked” diagnostics now; consider a separate channel ingress adapter later. Importing its whole gateway would duplicate conversation, tools, skills, scheduling and approval surfaces, with a much larger maintenance burden.

**Acceptance:** authenticated channel identity maps to the correct operator; forwarded model text cannot grant capabilities; read-only ingress cannot execute host commands; fail closed if a required sandbox cannot start; deny rules cannot be broadened by plugins/subagents; channel delivery success is distinct from approved action completion.

### 5. Recovery observations and test cases — Nanobot

**What exists:** `restore_runtime_checkpoint` converts unfinished tool calls into explicit interrupted results rather than replaying them. It preserves completed observations and avoids duplicate history tails. The scheduler records skipped/error outcomes and bounded run history; subagent tasks track ownership, cancellation and cleanup. [Recovery](https://github.com/HKUDS/nanobot/blob/d6ddceed997b53c4adcd56e8b302bd124bfa0c71/nanobot/session/recovery.py), [scheduler](https://github.com/HKUDS/nanobot/blob/d6ddceed997b53c4adcd56e8b302bd124bfa0c71/nanobot/cron/service.py), [subagents](https://github.com/HKUDS/nanobot/blob/d6ddceed997b53c4adcd56e8b302bd124bfa0c71/nanobot/agent/subagent.py).

**Fit:** translate recovery scenarios into SwarmMojo tests before adding a second scheduler/session store. The subagent constructor's `restrict_to_workspace=False` is another reason not to copy defaults blindly.

**Acceptance:** terminated runs remain interrupted, never successful; completed results remain deduplicated; cancelled work cannot publish a new successful result; stale recovery requests fail; uncertain side effects require reconciliation; restart and DST/clock tests precede any scheduled business action.

## Other namesakes: selective reference or reject

- **tahodev/openmuse:** useful minimal Python illustration of HMAC-bound, expiring approvals. The inspected `ApprovalAuthority` keeps consumed tokens in an in-memory set; that class alone is not a durable replay ledger across restarts. Its policy can enable writes for a whole run. Use test ideas, not these defaults or an assumption that this is the locally archived OpenMuse. [Approval class](https://github.com/tahodev/openmuse/blob/e96d76aafcc538706b61b56f48649df128fca983/src/openmuse/approvals.py), [policy](https://github.com/tahodev/openmuse/blob/e96d76aafcc538706b61b56f48649df128fca983/src/openmuse/policy.py).
- **meetopenbot/openbot:** real event-based runtime: pending tool batches are persisted and tool execution is handled outside the single model call. However, server gateway authentication is conditional on an environment token, and this is not CopilotKit/OpenBot's approval implementation. Defer; adopting it would add another conversation/runtime stack without a proven gap. [Runtime](https://github.com/meetopenbot/openbot/blob/276c20ee2f171ddeb0622d349e59d71a77f086ad/src/plugins/openbot/runtime.ts), [server boundary](https://github.com/meetopenbot/openbot/blob/276c20ee2f171ddeb0622d349e59d71a77f086ad/src/app/server.ts).
- **Reject wholesale vendoring and branding-based integrations.** A matching project name, feature list, handoff claim, or large star count does not establish interoperability. Do not put external executors, secrets, cloud telemetry, or browser profiles inside the read-only preparation process.

## Delivery sequence

1. Preserve the old local checkouts; document the new repository's ROMS lineage and retained protocol names.
2. Add a minimal interoperable MCP consumer example, then verify it against an actual pinned client before advertising compatibility.
3. Add durable jobs and external-action approval only when the first concrete connector requires them; use the crash/replay/account-switch acceptance cases above.
4. Add bounded specialist execution behind the existing proposal boundary.
5. Evaluate channel/UI adapters in separate optional packages. Require measured task benefit, platform support and cost/dependency disclosure before adoption.

Evidence snapshots are under `runtime-source/`: pinned metadata/tree JSON and only the selected source/license files cited above. The fetch helper downloads text only and does not execute it. No copied upstream code was integrated into SwarmMojo during this research.

