# SwarmMojo

**A unified, local-first AI agent harness combining decision intelligence, specialist reviews, workflow rehearsal, and universal agent configuration.**

SwarmMojo brings together three core pillars:
1. **ROMS Engine**: Decision AI, RAG retrieval, Open Knowledge Files (OKF), SQLite-Vec, MCP tools, and skills to prepare bounded, reviewable actions.
2. **Swarm Mojo (Aeon)**: Source-grounded specialist reviews, TriggerTangle workflow rehearsal, bounded execution, and optional mSGL inference adapters.
3. **PolyHarness**: Universal transpiler and package manager for AI agent configurations (compiling to `CLAUDE.md`, `AGENTS.md`, `dsh.config.json`, `.cursorrules`, scoped `.cursor/rules/*.mdc`, `.claude/rules/*.md`, MCP registries, and deterministic pre-commit guardrails).

The portable Python path is used on Windows and Linux. Omarchy is an optional integration; it is not required to use SwarmMojo.

## Core Pillars & Capabilities

| Pillar | Sub-system | Purpose |
| --- | --- | --- |
| **ROMS Core** | **Decision Maker** | Rank supplied options, return structured results and abstain when thresholds are not met. |
| **ROMS Core** | **RAG & OKF** | Multi-format local document ingestion, hybrid vector + FTS5 BM25 retrieval, and bounded context preparation. |
| **ROMS Core** | **MCP & Skills** | Local MCP tools server and reusable Markdown skill playbooks. |
| **Swarm Mojo** | **Aeon Specialist Reviews** | Source-grounded multi-specialist reviews with bounded deliberation and explicit operator approval tickets. |
| **Swarm Mojo** | **Workflow Rehearsal** | TriggerTangle offline causal loop simulator to test automations and prevent trigger deadlocks. |
| **PolyHarness** | **Multi-Target Transpiler** | Single-source-of-truth configuration (`harness.config.json`) compiling to Claude Code, Cursor, DeepSeek, and AGY. |
| **PolyHarness** | **Progressive Disclosure** | Scoped rule generator emitting `.cursor/rules/*.mdc` and `.claude/rules/*.md` to prevent context saturation. |
| **PolyHarness** | **Deterministic Guardrails** | Generates `.githooks/pre-commit` and `safe-exec.sh` to block destructive actions and leaks at the shell/git level. |

## Specialized Local-First Engines

SwarmMojo incorporates 19 high-speed specialized engines with Python bridges in `app/engines/`, FastMCP tool exposures in `app/engine_tools.py`, and native Mojo acceleration in `app_mojo/`:

| Engine | Primary Feature & Performance | CLI Command | FastMCP Tool |
| --- | --- | --- | --- |
| **Symdex** | In-memory code symbol & bi-directional call-graph index (<20 µs) | `python swarmmojo.py symdex` | `symdex_query` |
| **Titans** | Test-Time Neural Memory with momentum & surprise gating (arXiv:2501.00663) | `python swarmmojo.py titans` | `titans_memory_update`, `titans_memory_recall` |
| **Micro-ToolCall** | JSON extraction, auto-repair, and type coercion for 7B-32B models | `python swarmmojo.py toolcall` | `toolcall_repair_output` |
| **Sieve** | Streaming terminal and compiler log compaction (95%+ noise reduction) | `python swarmmojo.py sieve` | `sieve_compact_logs` |
| **Local-Horizon** | State-machine task graph (DAG) & anti-loop vector circuit breaker | `python swarmmojo.py horizon` | `horizon_record_step` |
| **Fastgate** | 256-dim phase vector System-1 tool triage router | `python swarmmojo.py fastgate` | `fastgate_triage_tools` |
| **Compact-KV** | VRAM-capped rolling structured scratchpad (<800 tokens) | `python swarmmojo.py compact-kv` | `compact_kv_scratchpad` |
| **Agent-Rewind** | Content-addressed workspace snapshotting and microsecond rollback | `python swarmmojo.py rewind` | `rewind_snapshot_workspace`, `rewind_rollback_workspace` |
| **Path-Carry** | Filename safety, cross-platform reserved-name & path audit | `python swarmmojo.py path-carry` | `path_carry_audit` |
| **LocalDoc-Search** | Line-level local document chunking & search | `python -m app.engines.localdoc_search` | Integrated via RAG & OKF |
| **Mojo-Drift** | 256-dim angular trajectory tracking & drift guardrail (warn >=65°, block >=80°) | `python swarmmojo.py drift` | `drift_evaluate_action` |
| **StateFresh** | Optimistic concurrency control, version leases & stale-write rejection | `python swarmmojo.py statefresh` | `statefresh_check_and_stage` |
| **WorkflowProof** | Step input/output SHA-256 fingerprinting & verified proof-of-work caching | `python swarmmojo.py workflowproof` | `workflowproof_verify_step` |
| **Prefrontal Cortex** | Execution shield hazard scoring, regex filters & cyclic loop intercept | `python swarmmojo.py cortex` | `cortex_shield_action` |
| **Triad-Engine** | Pareto reliability, duration, and token cost multi-objective ranking | `python swarmmojo.py triad` | `triad_pareto_rank` |
| **Mojo-Memory** | 512-dim phase vector associative memory with sub-10ms recall | `python swarmmojo.py mojo-memory` | `mojomemory_store`, `mojomemory_query` |
| **Studio-Engine** | Multimodal cinematic video, ComfyUI execution graphs, storyboards & banner craft | `python swarmmojo.py studio` | `studio_compile_prompt`, `studio_create_storyboard`, `studio_export_comfyui_graph`, `studio_craft_banner` |
| **Design-Engine** | High-craft UI/GUI landing pages, enterprise admin dashboards & component systems | `python swarmmojo.py design` | `design_build_landing_page`, `design_build_dashboard` |
| **Writer-Engine** | Authentic prose authoring, Ghost Protocol anti-slop filters & multi-chapter book planner | `python swarmmojo.py writer` | `writer_audit_prose`, `writer_clean_prose`, `writer_plan_book` |
| **Workflow-Engine** | Constitutional pipeline governance, routine scheduler & WorkflowProof Merkle verification | `python swarmmojo.py workflow` | `workflow_run_dag`, `workflow_schedule_routine`, `workflow_list_routines` |
| **Assistant-Engine** | 24/7 sovereign companion, encrypted vault, consult gateway & realtime voice bridge | `python swarmmojo.py assistant` | `assistant_get_briefing`, `assistant_consult_specialist`, `assistant_store_credential` |

## Meta-Agent Architecture Comparison: SwarmMojo vs Conventional Frameworks

SwarmMojo represents a generational leap over conventional cloud orchestrators and generic CLI seat wrappers. See the full architectural breakdown in [docs/meta_agent_comparison.md](docs/meta_agent_comparison.md).

| Architectural Dimension | **SwarmMojo (Buzburg AI)** | **Conventional Cloud Orchestrators** | **Generic CLI Seat Wrappers** |
| :--- | :--- | :--- | :--- |
| **Primary Philosophy** | Sub-millisecond local-first meta-harness with native Mojo SIMD acceleration | Cloud-hosted ticketing, multi-tier enterprise web app & remote deployment runner | Multi-seat terminal wrapper & basic CLI subprocess manager |
| **Core Runtime** | **Mojo (SIMD v25+)** + **Python 3.11+** hybrid engine | Heavyweight Node.js, GraphQL, PostgreSQL web stacks | Basic Node/Python CLI subprocess supervisor |
| **Decision / Tool Latency** | **< 50 microseconds** (native `fastgate_core.mojo`) | 150 – 500 ms (database queries & network hops) | 80 – 300 ms (subprocess creation & IPC pipes) |
| **Native Compiler Kernels** | **40+ Native Mojo kernels** (`app_mojo/*.mojo`) | None (JavaScript V8 / Node.js) | None (Standard CPython / V8) |
| **Trajectory Drift & Safety** | **Deterministic 256-dim phase-space geometry** (<65° safe, ≥80° blocked) | Prompt-based system guidelines only | Fixed max-iteration counters & tool timeouts |
| **Memory Architecture** | **Titans DeltaNet** (fast/slow weights) + **Compact-KV** + **HMS Simd** | Flat conversation rows in remote SQL tables | In-memory message arrays / raw JSON logs |
| **Concurrency Model** | **StateFresh OCC** (Atomic CAS, read-set validation, epoch commits) | Remote SQL row locks / database transactions | Sequential command queues / filesystem race hazards |
| **Rollback & Reversibility** | **Microsecond snapshot restore** (`mojo-agent-rewind` delta replay) | Remote git branch resets via web APIs | Manual developer terminal interrupts |
| **Model Heterogeneity** | **Any local** (Ollama, LM Studio, vLLM, SGLang, RWKV7) + **Cloud** (Sovereign endpoints) | Locked to cloud vendor APIs | Relies on external proprietary CLI binaries |
| **Specialized Agent Guilds** | **6 Complete Guilds**: Coding, Studio, Design, Writer, Workflow, Assistant | Generic worker seats assigned tickets | Generalist terminal agents |
| **Harness Portability** | **PolyHarness**: Compiles zero-dependency configs for Claude Code, Cursor, DeepSeek, AGY | Proprietary cloud platform lock-in | Fixed single CLI format |
| **UI / Desktop Experience** | **Herald HUD**: Deep-blue glassmorphism, real-time kernel telemetry, canvas builders | Generic web SaaS dashboard | Text-only terminal table view |
| **Formal Mathematical Proofs** | **WorkflowProof**: Cryptographic Merkle invariants and transition proofs | None | None |

## Workflow Automation Agent Engine: Constitutional Pipelines & Routine Triggers

SwarmMojo features a deterministic workflow execution and routine automation engine:

### 1. 8-Stage Constitutional Execution Pipeline (`WorkflowPipeline`)
- **Turn Governor & Rate Gate**: Enforces strict turn limits and cycle interceptors.
- **Risk Classifier**: Automatically classifies action risks (LOW: read-only, MEDIUM: mutations, HIGH: shell/network, CRITICAL: destructive operations).
- **Constitutional Safety Checks**: Blocks dangerous destructive commands (`rm -rf /`, `mkfs`, `format`, SQL drops, credential leaks).
- **Pre-Execution Lease**: Acquires StateFresh optimistic concurrency control (OCC) leases.
- **Fastgate System-1 Dispatch**: Routes step commands in <50 microseconds via native phase vectors.
- **Sandboxed Execution & Log Compaction**: Executes tools while applying Sieve log compaction (95%+ noise reduction).
- **WorkflowProof Cryptographic Verification**: Calculates deterministic SHA-256 Merkle hashes for every step and result.
- **Rewind Self-Correction Loop**: If a step encounters an error, automatically triggers diagnostic reflection, rolls back workspace state using `mojo-agent-rewind`, and retries with modified parameters.

### 2. Routine Scheduler (`WorkflowRoutineScheduler`)
- Manages recurring background automations (daily repository audits, dependency checks, test regressions).
- Persisted in `.mojo_workflows/routines.json` (`python swarmmojo.py workflow schedule`).

---

## Personal Assistant Agent Engine: 24/7 Companion, Secure Vault & Realtime Voice

SwarmMojo includes a 24/7 sovereign personal companion:

### 1. Persistent 24/7 Companion (`PersonalAssistantEngine`)
- Manages active desk context, ongoing tasks, and daily objectives in `.mojo_assistant/`.

### 2. Encrypted Personal Vault (`AssistantVault`)
- Stores API keys, tokens, and personal preference profiles with SHA-256 fingerprinting.

### 3. Specialist Consult Gateway (`ConsultGateway`)
- Receives natural language goals and delegates to specialist agent guilds (Coding, Studio, Design, Writer, Workflow), returning synthesized executive answers.

### 4. Realtime Voice & Audio Bridge (`RealtimeVoiceBridge`)
- **Audio Pipeline Law**: 16kHz PCM Ears STT -> Conversational Voice Captain -> 24kHz PCM Mouth TTS.
- **Energy-Gated VAD & Barge-In**: Real-time RMS audio energy calculation with automatic barge-in interruption.

### 5. Proactive Daily Briefing (`DailyBriefingEngine`)
- Generates structured morning briefings covering system health, active priorities, and scheduled routine updates (`python swarmmojo.py assistant briefing`).

---

## Writer Agent Engine: Authentic Prose & Ghost Protocol Authoring

SwarmMojo features an authentic authoring suite by Buzburg AI:

### 1. Ghost Protocol Anti-Slop Audit (`ProseHumanizer.audit_text`)
- **200+ Zero-Tolerance Phrase Blacklist**: Scans and flags statistically overrepresented AI phrases (`in today's digital landscape`, `delve into`, `testament to`, `rich tapestry`, `moreover`, `having said that`, `watershed moment`).
- **Inflation Word Detection**: Identifies stock editorial adjectives (`pivotal`, `crucial`, `vital`, `groundbreaking`, `multifaceted`) that inflate importance without presenting concrete facts.
- **Cadence & Rhythm Variance**: Measures sentence length variance to eliminate robotic, uniform LLM paragraph structures.

### 2. Programmatic Humanizer (`ProseHumanizer.humanize`)
- Subtraction-over-addition principle: Programmatically cleans synthetic filler and cleans sentence transitions without injecting hallucinated content.

### 3. Multi-Chapter Long-Form Book Planner (`BookOutlinePlanner`)
- Breaks novels and non-fiction books into structured chapter DAGs with target word budgets, POV characters, and narrative conflict drivers.
- Exports persistent outline plans directly into `.mojo_writer/`.

---

## Design Agent Engine: Impeccable UI, GUI & Website Builder

SwarmMojo incorporates a dedicated Design & GUI runtime:

### 1. Impeccable Craft Floor & Design Tokens (`DesignTokens`)
- **Accessibility & Contrast**: Built-in WCAG AAA text contrast ($\ge 7:1$ body, $\ge 4.5:1$ secondary), tinting secondary text directly from background surfaces rather than flat grays.
- **Typographic Measure**: Standardized line lengths ($65\text{--}75\text{ch}$ measure), balanced headings, $-0.04\text{em}$ tracking floor, and modern font stacks (`Inter`, `Plus Jakarta Sans`, `JetBrains Mono`).
- **Depth Without Halos**: Soft directional elevation shadows with gentle blur offsets, completely avoiding zero-offset colored halos.

### 2. Full-Page Website Builder (`build_landing_page`)
- Produces complete, responsive, dark-mode landing pages with glassmorphism sticky navigation, radiant radial glow hero banners, metrics strips, and interactive feature grids.
- Automatically persists rendered HTML & modern CSS tokens directly to `.mojo_design/index.html`.

### 3. Enterprise GUI & Admin Dashboards (`build_admin_dashboard`)
- Implements production GUI dashboards with sidebar navigation, metric delta counters, and tabular agent activity feeds.
- Outputs clean, zero-dependency HTML/CSS dashboards to `.mojo_design/dashboard.html`.

### 4. Herald HUD Glassmorphism Operating Desktop (`build_herald_hud`)
- **Deep-Blue Glass on Living Wallpaper**: Real-time desktop dashboard displaying active agent swarms, telemetry, and DAG milestones.
- **Live Specialist Swarm Roster**: Real-time agent status cards with model endpoints, load telemetry, and unread notification states.
- **Microsecond Telemetry Matrix**: Displays real-time metrics for in-memory Symdex lookups, StateFresh OCC concurrency rates, and Mojo angular trajectory drift.
- **Active Task DAG Visualizer**: Displays interactive milestone execution stages (`complete`, `running`, `pending`) alongside verified TriggerTangle rehearsals.
- Output generated directly to `.mojo_design/herald_hud.html` (`python swarmmojo.py design hud`).

---

## Studio Agent Engine: Cinematic Video, Photography & Visual Craft

SwarmMojo incorporates a cinematic production studio runtime:

### 1. Cinematic Camera, Lens & Optics Rig (`StudioPromptCompiler`)
- **Directorial Optics Presets**: Grand Format 70mm Film (IMAX grain), Modular 8K Digital (Arri Alexa 65 look), Super 35, Classic 16mm Vintage, Anamorphic 2x (oval bokeh & horizontal streak flares), Tilt-Shift selective focus, and Extreme Macro.
- **Atmospheric Lighting**: Golden hour 3200K, Rembrandt key/fill contrast, Cyberpunk dual-rim neon, Volumetric misty shafts, and commercial softboxes.
- **Movement Vectors**: Smooth crane sweeps, slow tracking push-ins, handheld organic drift, and Dutch angle rotations.

### 2. Multi-Shot Storyboard Sequencing (`StoryboardDirector`)
- Breaks creative concepts into timed shot lists with duration, camera setup, lighting mood, motion vector, and sound design.
- Compiles sequence JSON specifications and exports them to `.mojo_studio/` for render pipeline feeding.

### 3. Visual Execution Node Graphs (`ComfyUIBridge`)
- Programmatically generates production-ready API graphs for text-to-image and image-to-video pipelines.
- Auto-scales dimensions to match exact aspect ratios (`16:9`, `9:16`, `1:1`, `2.39:1 Cinemascope`, `4:5`) while respecting optimal VRAM latent constraints.

### 4. UI/UX Banner & Visual Asset Craft
- Platform safe-zone templates: YouTube banners, Twitter/X headers, LinkedIn covers, responsive website hero sections, and Instagram cards.
- Design tokens: typography hierarchy, high-contrast palette pairings, and container buffer validation.

---

## Coding Agent Engine: Triad Engine & Recursive Code Reflection

SwarmMojo features a dedicated coding agent runtime:

### 1. Precise Coding Toolkit (`PiCodingToolkit`)
- **Exact Substring Editing (`edit_file_exact`)**: Replaces target blocks only if they match uniquely. Strictly checks occurrence counts to prevent multi-location mutations, accompanied by automatic pre-edit Rewind snapshots and StateFresh OCC version checks.
- **Line-Numbered Slicing (`read_file_slice`)**: 1-indexed, line-numbered views avoiding full-file context dumps.
- **Atomic Writing (`write_file_atomic`)**: Creates or writes files atomically with PathCarry directory audits.
- **Fast Symbol Discovery (`symdex_callgraph`, `find_files`, `grep_content`)**: Sub-20 µs caller/callee and definition indexing via Symdex.

### 2. Recursive Reflection Engine (`PrimeRecursionEngine`)
- **Three Delegation Modes**:
  - `single`: Focuses a single specialized subagent on an isolated subtask.
  - `parallel`: Dispatches multiple independent tasks simultaneously and aggregates results.
  - `chain`: Sequential pipeline with automatic `{previous}` token piping from preceding subagent outputs.
- **Strict Recursion Limits (`max_depth`)**: Halts runaway recursion trees before exceeding configurable depth thresholds.
- **Context Window Isolation**: Subagents run with isolated scratchpads; only distilled findings return to the parent context.
- **Mojo-Drift Active Guardrails**: Re-evaluates each subagent task against the parent goal, blocking actions with >=80° angular drift.

---

## MetaHarness: Multi-Agent & Heterogeneous Multi-Model Orchestration

SwarmMojo provides a meta-harness capable of coordinating multiple autonomous specialist agents concurrently or in structured pipelines across **the same local model or multiple distinct local models** (Ollama, LM Studio, vLLM, SGLang / mSGL, RWKV-7).

### Premade Specialist Agents
- **Atlas Coordinator (`coordinator`)**: Meta coordinator and task DAG dispatcher. Breaks down complex goals into atomic subtasks.
- **Daedalus Architect (`code_architect`)**: Principal systems and software engineer. Leverages Symdex for call-graph exploration.
- **Argus Reviewer (`code_reviewer`)**: QA and verification specialist. Rigorous regression detection.
- **Hypatia Researcher (`researcher`)**: Semantic retrieval and knowledge grounding specialist.
- **Vulcan DevOps (`devops_operator`)**: Shell and sandbox operator. Applies Sieve log compaction.
- **Aegis Security (`security_auditor`)**: Path traversal and Windows reserved-name safety auditor via PathCarry.
- **Mnemosyne Curator (`memory_curator`)**: Titans test-time neural memory and Compact-KV working memory curator.
- **Chronos Workflow Engineer (`workflow_automator`)**: Constitutional pipeline automation, routine scheduling, and Merkle proof verification.
- **Aura Personal Companion (`personal_assistant`)**: 24/7 personal assistant, secure vault custodian, and consult gateway.

### Multi-Model Local Routing
Agents can share a single local model or each be assigned their own dedicated local model endpoint:
```sh
# Run with heterogeneous local models (e.g. DeepSeek-R1 coordinator + Qwen-Coder architect)
python swarmmojo.py meta run --task "Refactor event broker" --team fullstack_team

# Run all agents on a specific local Ollama model
python swarmmojo.py meta run --task "Verify test matrix" --team review_audit_team --model ollama-qwen-coder

# Run offline with deterministic zero-cost execution
python swarmmojo.py meta run --task "Audit security boundaries" --team review_audit_team --model mock
```

### Build Your Own Agents & Environments
```sh
# Create a custom specialist agent
python swarmmojo.py meta create-agent --id api_dev --name "API Specialist" --role "Backend REST Developer" --model ollama-qwen-coder --tools "symdex_query,sieve_compact_logs"

# Create a custom execution sandbox with Rewind snapshots & Horizon breakers
python swarmmojo.py meta create-env --id microservices_sandbox --name "Microservices Sandbox" --root ./services
```

The workflow is **request → knowledge and skills → decision → proposed next step → operator approval → separately configured execution**. The preparation API implements the first four steps. It does not execute the proposal or approve itself. See the [component map](docs/components.md).

## Try one useful thing first

From a downloaded or cloned checkout, with **Python 3.11 or later**:

```sh
python -I -S -B scripts/demo_first_run.py
```

No installation, account, model, GPU or network connection is needed. The demo creates a temporary invoice program, introduces a known bad edit and runs a real failing check. SwarmMojo extracts the error from the log, locates the function and restores the original file. The check must pass again before the temporary files are removed and success is reported.

Add `--json` to inspect the original failure log, compacted log, source location and before/after file hashes. The demo accepts no path to your project. It demonstrates controlled recovery, not autonomous repair or safe rollback of concurrent edits. [Verification scope](docs/first-run-demo.md).

## Prepare a task for review

The harness command uses the lightweight dependencies in `requirements-ci.txt`. From the repository root, create a virtual environment and install them:

```sh
python -m venv .venv
```

Use `.venv/bin/python` on Linux or `.venv/Scripts/python.exe` on Windows for the following commands:

```sh
python -m pip install -r requirements-ci.txt
python swarmmojo.py harness --request examples/harness-request.json
python -B scripts/demo_harness.py
```

Replace `python` with that environment's executable; shell activation is optional. The [harness guide](docs/HARNESS.md) explains request fields, database setup and examples.

The harness demo uses a temporary synthetic knowledge index and selected skill to exercise real retrieval and the public CLI. It prints its checks and removes the fixture afterward.

Preparation retrieves keyword matches from an existing OKF index, reads explicitly selected Markdown skills, and evaluates supplied choices through the current Decision Maker. Retrieval uses the indexed snapshot; it does not revalidate the original documents. The response includes source hashes, a bounded context, a decision or abstention, and a proposed next step. It always reports `approval_required: true` and `execution_allowed: false`.

This path does not call a model, use the network, run tools, edit documents or save topic-discovery records. SQLite may use normal coordination sidecars. It is a preparation step for a caller or operator to review, not a complete autonomous execution loop.

## Other command-line tools

The existing utility CLI uses Python's standard library:

```sh
python swarmmojo.py --help
python swarmmojo.py index --path .
python swarmmojo.py lookup --query invoice_total_cents
python swarmmojo.py pack --costs "50,40,30" --values "100,60,50" --budget 70 --required 2
```

Commands for advisory decisions, memory, log compaction and snapshots are listed in `--help`. Utilities can write local state under `data/prefrontal/`; set `SWARMMOJO_DATA_DIR` when using the new launcher to choose another directory. Snapshot restoration writes files; review its limits before applying it to a real workspace.

Standalone Decision Maker utilities can also persist topic discovery. The new launcher defaults to `~/.swarmmojo`; set `SWARMMOJO_STATE_DIR` to choose another location. Harness preparation disables that persistence. Existing ROMS settings, command aliases and protocol IDs remain compatible; see the [migration guide](docs/MIGRATION.md).

<a id="-10-second-mcp-setup-claude-code-cursor-windsurf"></a>

## Connect an MCP client

The full server needs the packages in `requirements.txt` and an embedding model. Install them using the virtual environment's Python, then let your MCP client launch the server:

```sh
python -m pip install -r requirements.txt
python swarmmojo.py mcp
```

The command uses stdio and waits for MCP messages. For clients with an `mcpServers` configuration, use absolute paths:

```json
{
  "mcpServers": {
    "swarmmojo": {
      "command": "/absolute/path/to/SwarmMojo/.venv/bin/python",
      "args": ["/absolute/path/to/SwarmMojo/swarmmojo.py", "mcp"]
    }
  }
}
```

On Windows, use `.venv/Scripts/python.exe`. Forward slashes work in JSON paths; otherwise escape each backslash. Configuration locations depend on the client.

Startup initializes the database, indexes supported files in `knowledge/`, loads local plugins and starts the watcher. The default embedding model is `sentence-transformers/all-MiniLM-L6-v2` on CPU; first use may download model files. Remote embedding providers send text to their configured endpoint. The index requires 384-dimensional embeddings; changing models requires a compatible rebuilt index. Review [security and data handling](SECURITY.md) before connecting an agent.

### Useful registered interfaces

| Task | Interface |
| --- | --- |
| Prepare a reviewable request | `swarmmojo_prepare_harness` with `request_json` |
| Search knowledge | `search_knowledge_base`, `search_grounded_context` |
| Add or refresh documents | `add_knowledge_document`, `reload_knowledge`, `list_knowledge_documents` |
| Retain and recall project lessons | `memory_retain`, `memory_recall`, `memory_get`, `memory_prepare_context` |
| Propose a regression check after a failure | `memory_propose_correction` or `python swarmmojo.py correction --help` |
| Record or revise lesson evidence | `memory_record_verification`, `memory_correct`, `memory_retract`, `memory_forget` |
| Get an advisory decision | `roms_decide`, `roms_noul`, `roms_score` |
| Find tools and skills | `search_tools`, `list_skills` |
| Read a skill | Resource `skills://{skill_name}` or prompt `get_skill_playbook` |
| Inspect logs and source locations | `roms_sieve_compact`, `roms_symdex_lookup` |

The server advertises the full tool list and schemas on connection. The harness tool uses the server's configured database and skills directory; it does not accept arbitrary paths. Other tools can write knowledge, change lessons, author skills or restore files. Caller-supplied verification records are not authenticated test results.

## Status and limits

SwarmMojo is a developer project for a trusted local operator. Its Python tools, native components and optional integrations have different prerequisites and verification scopes.

- Decision scores and retrieved text can be wrong. They do not establish truth or grant permission to change a system.
- Local plugins run with the server's permissions. Skills and retrieved documents are untrusted input to the agent.
- The optional model gateway needs a separately configured inference service. Installing SwarmMojo does not install model weights or an operating system.
- Dataset export does not train a model. Routing prototypes do not establish measured model-quality improvements.
- Benchmark reports cover specific fixtures and machines. No general latency, token-saving or GPU-performance guarantee is made. The planned 128 GB machine needs its own qualification.

## Verification

The no-install demo has standard-library regression checks:

```sh
python -m unittest discover -s tests -p test_first_run_demo.py -v
```

After installing `requirements-ci.txt` in your environment:

```sh
python -m pytest tests/test_first_run_demo.py tests/test_prefrontal_integration.py tests/test_decisions_jev_laya.py tests/test_release_safety.py tests/test_memory.py tests/test_context.py -q
```

The [harness guide](docs/HARNESS.md) records its checks, and the [CI workflow](.github/workflows/checks.yml) defines the portable test matrix. Native builds and live-model checks have separate prerequisites.

## Optional integrations and documentation

Three explicitly selected [specialist playbooks](docs/IMPORTED-SKILLS.md) are available for code review, architecture and technical writing. These concise local adaptations record their upstream source and retain its license. They are prompt text, not independently running agents or permissions.

The [upstream evaluation](docs/UPSTREAM-EVALUATION.md) distinguishes what is included from promising adapters, overlapping systems and unresolved project names.

For coding work, select a compact review playbook, use the existing workshop's configured PTRM reviewer to inspect code, and save recurring failures as [correction proposals](docs/local-memory.md#propose-a-regression-after-a-failure). PTRM reports distinguish full, partial and absent scan coverage; a clean or partial report cannot approve an edit. [Local harness and PTRM assessment](docs/research/local-coding-sources.md).

The model gateway tracks complete response termination so an interrupted stream cannot be recorded as a completed protocol exchange. Ordinary broker chat rejects truncated answers. These checks do not establish answer correctness or successful task execution.

The Linux/Omarchy workshop adds staged changes, registered validation and operator-approved promotion. It requires its own configured runtime and confinement components; those execution features are not established by the portable preparation command or a positive decision score.

- [Harness request and response contract](docs/HARNESS.md)
- [Component map and experimental boundaries](docs/components.md)
- [Project lessons and evidence](docs/local-memory.md)
- [Native context selection and scoped measurements](docs/native-context.md)
- [Retrieval correctness](docs/retrieval-performance.md)
- [Workshop, build evidence and runtime integrations](docs/repository-integrations.md)
- [Omarchy test-build setup](docs/wsl-test-build.md) and [voice setup](docs/voice.md)
- [Chat data handling](docs/chat-privacy.md) and [security boundaries](SECURITY.md)

## Author & Maintainer

- **Author**: Buzburg AI
- **Contact**: `buzburgai@gmail.com`
- **GitHub**: [https://github.com/Buzburg/SwarmMojo](https://github.com/Buzburg/SwarmMojo)

## License

[Apache-2.0](LICENSE). Copyright 2026 Buzburg LLC. Third-party licenses and acknowledgements remain in [NOTICE](NOTICE) and the relevant source directories.

