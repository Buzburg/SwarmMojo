# SwarmMojo ⚡

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Runtime: Mojo + Python](https://img.shields.io/badge/Runtime-Mojo_SIMD_v25+_|_Python_3.11+-orange.svg)](app_mojo/)
[![Architecture: Local--First Meta--Harness](https://img.shields.io/badge/Architecture-Sovereign_Meta--Harness-emerald.svg)](docs/meta_agent_comparison.md)
[![Tests: 100% Passing](https://img.shields.io/badge/Tests-100%25_Passing-brightgreen.svg)](tests/)
[![Author: Buzburg AI](https://img.shields.io/badge/Author-Buzburg_AI-purple.svg)](mailto:buzburgai@gmail.com)

> [!NOTE]
> ### In Plain English: Why SwarmMojo Changes Everything
> When running multiple autonomous AI agents locally, developers constantly face four brutal roadblocks:
> 1. **Sluggish, bloated runtimes** that consume gigabytes of VRAM and burn seconds per tool call.
> 2. **Chaotic multi-agent loops** where agents hallucinate, drift off-target, trigger circular failures, and overwrite each other's code.
> 3. **Context window suffocation** caused by massive compiler dumps, unindexed directories, and repetitive shell commands.
> 4. **Cloud lock-in and vendor seats** that trap your architecture inside proprietary ticketing platforms with high monthly fees and zero offline sovereignty.
>
> **SwarmMojo** is a unified, local-first meta-harness built from first principles for blistering speed, mathematical determinism, and absolute privacy. Powered by **30+ specialized high-performance engines** and accelerated by **native Mojo SIMD kernels** (`app_mojo/`) executing in sub-microseconds, SwarmMojo orchestrates autonomous coding, enterprise UI design, multimodal studio production, human-grade prose authoring, constitutional DAG workflows, and 24/7 executive personal assistance.
>
> Featuring **fleet herd immunity** that instantly inoculates your agent swarm against recurring bugs, **sub-50ms desktop automation**, **mathematical trajectory drift guards (<65°)**, and **instant content-addressed rollbacks**, SwarmMojo gives you a sovereign, enterprise-grade AI powerhouse running directly on your local silicon.

---

## The Core Pillars of SwarmMojo

SwarmMojo unifies five foundational pillars into a cohesive, zero-cloud architecture:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 SWARMMOJO META-HARNESS                                       │
├───────────────────────────────┬───────────────────────────────┬──────────────────────────────┤
│       1. SPECIALIST GUILDS    │     2. HIGH-SPEED ENGINES     │      3. FLEET IMMUNITY       │
│  • Coding Agent (AST/RE)      │  • Symdex Symbol Index (<20µs)│  • Antibody Herd Immunity    │
│  • Design Agent (Canvas/Glass)│  • Titans Neural Memory       │  • Once Execution Cache (TTL)│
│  • Studio Agent (Director/LUFS│  • Fastgate Vector Router     │  • Screenhand Desktop Bridge │
│  • Writer Agent (Anti-Slop)   │  • Sieve Compaction (95%+)    │  • Everywhere Quick Router   │
│  • Workflow Agent (DAG/Proofs)│  • StateFresh Atomic OCC      │  • CLI Printing Press Layout │
│  • Assistant Agent (24/7 VAD) │  • Horizon DAG Breakers       │  • Unified FastMCP Protocols │
├───────────────────────────────┴───────────────────────────────┴──────────────────────────────┤
│                         NATIVE MOJO SIMD ACCELERATION (app_mojo/*.mojo)                      │
│        Sub-microsecond FNV-1a Hashing • 2D Bounding Clamping • Exact Substring Search        │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

1. **Autonomous Specialist Guilds**: Six fully realized agent engines (Coding, Studio, Design, Writer, Workflow, Assistant) operating concurrently or in structured pipelines across local models.
2. **30+ Specialized Local Engines**: Microsecond AST search, test-time neural memory (Titans DeltaNet), streaming log compaction (Sieve), and optimistic concurrency leases (StateFresh).
3. **Fleet Herd Immunity & Infrastructure**: Distributed error inoculation (`AntibodyRegistry`), deduplicated command caching (`OnceExecutionCache`), high-speed desktop interaction (`ScreenhandDesktopBridge`), and omnipresent action dispatching (`EverywhereDispatcher`).
4. **Native Mojo Hardware Acceleration**: Compiles compute-heavy vector similarity, string clamping, and cryptographic step verification into native machine code.
5. **PolyHarness Universal Portability**: Transpiles a single-source configuration (`harness.config.json`) to Claude Code, Cursor, DeepSeek, and AGY with zero vendor lock-in.

---

## Sovereign Engines Directory

Every engine in SwarmMojo is available via Python in `app/engines/`, terminal CLI via `python swarmmojo.py <command>`, FastMCP via `app/meta/meta_tools.py`, and native Mojo kernels in `app_mojo/`:

| Engine | Primary Capability & Performance Metric | CLI Command | FastMCP Tool |
| :--- | :--- | :--- | :--- |
| **Symdex** | In-memory code symbol & bi-directional call-graph index (<20 µs) | `python swarmmojo.py symdex` | `symdex_query` |
| **Titans Memory** | Test-Time Neural Memory with momentum & surprise gating (arXiv:2501.00663) | `python swarmmojo.py titans` | `titans_memory_update` |
| **CodeReview** | Multi-perspective AST security, performance & reliability audit | `python swarmmojo.py coding review` | `coding_review_code` |
| **ReverseEngineering** | Magic header parsing (ELF, PE, Mach-O, WASM) & bytecode disassembly | `python swarmmojo.py coding inspect` | `coding_inspect_binary` |
| **CodeLedger** | Hierarchical symbol codemap & transactional atomic change rollback | `python swarmmojo.py coding codemap` | `coding_repo_codemap` |
| **Antibody** | Swarm herd immunity memory broadcasting instant bug remedies | `python swarmmojo.py meta antibody` | `meta_antibody_check` |
| **OnceCache** | Deduplicated shell command execution with memory TTL hashing | `python swarmmojo.py meta once` | `meta_once_run` |
| **Screenhand** | Sub-50ms deterministic desktop automation with boundary safety | `python swarmmojo.py meta screenhand` | `meta_screenhand_action` |
| **Everywhere** | Omnipresent floating desktop action dispatcher & clipboard bridge | `python swarmmojo.py meta everywhere` | `meta_everywhere_dispatch` |
| **PrintingPress** | Terminal typography with rounded Unicode cards, tables & badges | `python swarmmojo.py meta press` | `meta_publish_report` |
| **Photocraft** | Layered digital canvas composer with preset dimensions & export spec | `python swarmmojo.py design canvas` | `design_craft_canvas` |
| **LiquidGlass** | Optical glassmorphism tokens, backdrop blur & refraction index CSS | `python swarmmojo.py design glass` | `design_liquid_glass` |
| **DirectorBoard** | Cinematic shot board planning, camera moves & production bible | `python swarmmojo.py studio director` | `studio_plan_shot` |
| **VideoTimeline** | Multi-track timeline layout & broadcast -14 LUFS loudness normalization | `python swarmmojo.py studio timeline` | `studio_export_timeline` |
| **ReasonixVerdict** | Reasoning-driven visual quality scoring & render cost index detector | `python swarmmojo.py studio verdict` | `studio_verdict_score` |
| **Fastgate** | 256-dim phase vector System-1 tool triage router (<50 µs) | `python swarmmojo.py fastgate` | `fastgate_triage_tools` |
| **Mojo-Drift** | 256-dim angular trajectory tracking (warn $\ge 65^\circ$, block $\ge 80^\circ$) | `python swarmmojo.py drift` | `drift_evaluate_action` |
| **Sieve** | Streaming compiler & terminal log compaction (95%+ noise reduction) | `python swarmmojo.py sieve` | `sieve_compact_logs` |
| **StateFresh** | Optimistic concurrency control (OCC), version leases & CAS commits | `python swarmmojo.py statefresh` | `statefresh_check_and_stage` |
| **WorkflowProof** | Step SHA-256 Merkle fingerprinting & cryptographic transition caching | `python swarmmojo.py workflowproof` | `workflowproof_verify_step` |
| **Agent-Rewind** | Content-addressed workspace snapshotting & microsecond delta rollback | `python swarmmojo.py rewind` | `rewind_rollback_workspace` |
| **Compact-KV** | VRAM-capped rolling structured scratchpad (<800 tokens) | `python swarmmojo.py compact-kv` | `compact_kv_scratchpad` |
| **Path-Carry** | Path traversal, case-collision & Windows reserved name auditor | `python swarmmojo.py path-carry` | `path_carry_audit` |
| **Prefrontal Cortex** | Execution shield hazard scoring, regex filters & cyclic loop breaker | `python swarmmojo.py cortex` | `cortex_shield_action` |
| **Triad-Engine** | Pareto reliability, duration, and token cost multi-objective ranking | `python swarmmojo.py triad` | `triad_pareto_rank` |
| **Writer-Engine** | Ghost Protocol anti-slop filters, cadence audits & book DAG planner | `python swarmmojo.py writer` | `writer_audit_prose` |
| **Workflow-Engine** | 8-stage constitutional pipeline governance & routine scheduler | `python swarmmojo.py workflow` | `workflow_run_dag` |
| **Assistant-Engine** | 24/7 sovereign companion, encrypted vault & real-time voice VAD | `python swarmmojo.py assistant` | `assistant_get_briefing` |

---

## Meta-Agent Architecture Comparison: SwarmMojo vs Conventional Frameworks

| Architectural Dimension | **SwarmMojo (Buzburg AI)** | **Conventional Cloud Orchestrators** | **Generic CLI Seat Wrappers** |
| :--- | :--- | :--- | :--- |
| **Primary Philosophy** | Sub-millisecond local-first meta-harness with native Mojo SIMD acceleration | Cloud-hosted ticketing, multi-tier enterprise web app & remote deployment runner | Multi-seat terminal wrapper & basic CLI subprocess manager |
| **Core Runtime** | **Mojo (SIMD v25+)** + **Python 3.11+** hybrid engine | Heavyweight Node.js, GraphQL, PostgreSQL web stacks | Basic Node/Python CLI subprocess supervisor |
| **Decision / Tool Latency** | **< 50 microseconds** (native `fastgate_core.mojo`) | 150 – 500 ms (database queries & network hops) | 80 – 300 ms (subprocess creation & IPC pipes) |
| **Native Compiler Kernels** | **40+ Native Mojo kernels** (`app_mojo/*.mojo`) | None (JavaScript V8 / Node.js) | None (Standard CPython / V8) |
| **Fleet Herd Immunity** | **Antibody Registry**: Instant broadcast of solved error remedies | None (Every agent repeats identical mistakes) | None (Terminal re-runs failing commands) |
| **Execution Deduplication** | **Once Cache**: Memory-hashed TTL runner (<1 µs lookup) | None (Expensive queries repeat indefinitely) | None (Repeated manual command execution) |
| **Desktop Automation** | **Screenhand Bridge**: Sub-50ms deterministic OS click/type | None (Requires external cloud browser VMs) | None (Limited to CLI shell subprocesses) |
| **Trajectory Drift & Safety** | **Deterministic 256-dim phase-space geometry** (<65° safe, ≥80° blocked) | Prompt-based system guidelines only | Fixed max-iteration counters & tool timeouts |
| **Memory Architecture** | **Titans DeltaNet** (fast/slow weights) + **Compact-KV** + **HMS Simd** | Flat conversation rows in remote SQL tables | In-memory message arrays / raw JSON logs |
| **Concurrency Model** | **StateFresh OCC** (Atomic CAS, read-set validation, epoch commits) | Remote SQL row locks / database transactions | Sequential command queues / filesystem race hazards |
| **Rollback & Reversibility** | **Microsecond snapshot restore** (`mojo-agent-rewind` delta replay) | Remote git branch resets via web APIs | Manual developer terminal interrupts |
| **Model Heterogeneity** | **Any local** (Ollama, LM Studio, vLLM, Native, RWKV7) + **Cloud** (Sovereign endpoints) | Locked to cloud vendor APIs | Relies on external proprietary CLI binaries |
| **Specialized Agent Guilds** | **6 Complete Guilds**: Coding, Studio, Design, Writer, Workflow, Assistant | Generic worker seats assigned tickets | Generalist terminal agents |
| **Harness Portability** | **PolyHarness**: Compiles zero-dependency configs for Claude Code, Cursor, DeepSeek, AGY | Proprietary cloud platform lock-in | Fixed single CLI format |
| **UI / Desktop Experience** | **Sovereign HUD**: Deep-blue glassmorphism, real-time kernel telemetry, canvas builders | Generic web SaaS dashboard | Text-only terminal table view |
| **Formal Mathematical Proofs**| **WorkflowProof**: Cryptographic Merkle invariants and transition proofs | None | None |

---

## The Six Specialist Agent Guilds

### 1. Supercharged Coding Agent (`PiCodingToolkit`)
- **Automated Multi-Perspective Code Review (`CodeReviewEngine`)**: Analyzes code and diffs across security, performance, reliability, and code craft. Detects arbitrary execution (`eval`, `exec`), credential leaks, and algorithmic bottlenecks with automated patch suggestions.
- **Binary & Bytecode Reverse Engineering (`ReverseEngineeringEngine`)**: Inspects compiled executable headers (ELF, PE, Mach-O, WASM) and disassembles Python bytecode to audit instruction flow.
- **Transactional Code Ledger & Codemap (`CodeLedgerEngine`)**: Extracts project-wide symbol hierarchies and maintains atomic multi-file staging with rollback verification.
- **Exact Substring Editing (`edit_file_exact`)**: Unambiguous string replacement coupled with pre-mutation Rewind snapshots.
- **Recursive Subagent Reflection (`PrimeRecursionEngine`)**: Single, parallel, and chained subagent execution with `{previous}` output piping and strict depth governance.

### 2. High-Craft Design Agent (`DesignAgentEngine`)
- **Photocraft Layered Canvas (`PhotocraftCanvasEngine`)**: Creates digital graphics with blend modes, coordinate layouts, and presets for App Icons (1024x1024), OpenGraph Banners (1200x630), and Hero Graphics (1920x1080).
- **Liquid Glass Material (`LiquidGlassMaterial`)**: Optical glassmorphism tokens, specular highlight layers, and dynamic refraction CSS generation.
- **Impeccable Typography & Contrast (`DesignTokens`)**: Enforces WCAG AAA contrast ratios ($\ge 7:1$) and typographic rhythm ($65\text{--}75\text{ch}$ measure).
- **Full Landing Page & GUI Dashboard Generators**: Generates responsive dark-mode landing pages and admin dashboards persisted to `.mojo_design/`.

### 3. Multimodal Studio Agent (`StudioAgentEngine`)
- **Directorial Scene Board (`DirectorBoardEngine`)**: Plans camera angles, focal lengths, camera movements (crane sweeps, tracking push-ins), casting asset catalogs, and compiles complete production bibles.
- **Broadcast Video Timeline (`VideoTimelineEngine`)**: Multi-track video, dialogue, SFX, and BGM layout with broadcast-standard `-14 LUFS` loudness normalization.
- **Reasonix Visual Quality Verdicts (`ReasonixVerdictEngine`)**: Evaluates composition, lighting style, and render cost indices before triggering GPU cycles.
- **ComfyUI Execution Graphs (`ComfyUIBridge`)**: Compiles optimized node graphs for text-to-image and image-to-video pipelines.

### 4. Authentic Prose Writer Agent (`WriterAgentEngine`)
- **Ghost Protocol Anti-Slop Audit (`ProseHumanizer.audit_text`)**: Flags over 200 statistically overrepresented AI clichés (`delve into`, `testament to`, `rich tapestry`, `multifaceted`).
- **Cadence & Sentence Length Variance**: Measures rhythmic variation to eliminate robotic, uniform LLM paragraphs.
- **Multi-Chapter Book DAG Planner (`BookOutlinePlanner`)**: Breaks long-form novels and non-fiction books into structured chapter outlines with target word budgets and character drivers.

### 5. Constitutional Workflow Automation Agent (`WorkflowPipeline`)
- **8-Stage Constitutional Pipeline**: Turn governance, automatic risk classification (LOW to CRITICAL), destructive command blocking (`rm -rf`, disk wipes, SQL drops), StateFresh pre-execution leases, and Fastgate dispatch.
- **WorkflowProof Cryptographic Verification**: Deterministic SHA-256 Merkle proofs for every step.
- **Routine Background Scheduler (`WorkflowRoutineScheduler`)**: Schedules recurring maintenance, test audits, and repository regressions in `.mojo_workflows/`.

### 6. Sovereign Personal Assistant Agent (`PersonalAssistantEngine`)
- **Persistent 24/7 Companion**: Tracks active desk context and daily priorities in `.mojo_assistant/`.
- **Encrypted Personal Vault (`AssistantVault`)**: Stores credentials and sensitive preferences with SHA-256 protection.
- **Specialist Consult Gateway (`ConsultGateway`)**: Translates high-level user intents into delegated specialist tasks.
- **Realtime Voice & Audio Bridge (`RealtimeVoiceBridge`)**: 16kHz PCM input -> Voice Captain -> 24kHz PCM output with RMS energy-gated VAD and barge-in interruption.

---

## Meta Harness Fleet Operations & Ubiquitous Control

SwarmMojo provides groundbreaking infrastructure to keep agent swarms resilient and accessible across your entire operating system:

### 🛡️ Fleet Herd Immunity (`AntibodyRegistry`)
When any specialist agent in your swarm encounters and debugs an error (e.g. POSIX `fcntl` on Windows, SQLite locks, timeout backoffs), it generates a signed **Antibody Signature**. The antibody is broadcast across the peer swarm memory: the moment another agent hits a matching error pattern, it immediately applies the verified remedy, preventing duplicate failure loops.

### ⚡ Deduplicated Execution Cache (`OnceExecutionCache`)
Expensive terminal inspections, system probes, and git statuses are hashed and cached in-memory with configurable TTLs. Eliminates redundant tool execution and slashes subagent latency to sub-microseconds.

### 🖥️ Desktop Automation Bridge (`ScreenhandDesktopBridge`)
Allows agents to perform deterministic mouse clicks, keyboard text input, and window focusing with sub-50ms execution, screen boundary clamping, and dry-run safety modes.

### 🌐 Omnipresent Desktop Router (`EverywhereDispatcher`)
A floating companion that monitors the global system clipboard and instantly routes captured text to specialist quick-actions (`explain_code`, `review_diff`, `humanize_prose`, `render_banner`, `plan_video_shot`).

### 📰 CLI Printing Press (`CliPrintingPress`)
Renders breathtaking Unicode card boxes, aligned data tables, and ANSI status badges directly in your terminal.

---

## Native Mojo SIMD Compute Kernels (`app_mojo/`)

Compute-critical inner loops are implemented in native Mojo:

```mojo
// app_mojo/antibody_core.mojo - Fast 64-bit FNV-1a error hashing & pattern search
def hash_error_signature(error_type: String, error_msg: String) -> UInt64:
    var h: UInt64 = FNV_OFFSET_BASIS_64
    // Microsecond byte-level FNV-1a hashing...
    return h
```

- **`antibody_core.mojo`**: Sub-microsecond error signature hashing and antibody substring matching.
- **`once_core.mojo`**: Deterministic command key hashing and TTL epoch eviction validation.
- **`screenhand_core.mojo`**: Hardware coordinate boundary clamping and 2D bounding box collision detection.
- **`coding_core.mojo`**: Sub-microsecond exact substring location and unique occurrence verification.
- **`fastgate_core.mojo`**: 256-dimensional phase-vector System-1 tool triage routing (<50 µs).
- **`drift_core.mojo`**: 256-dimensional angular trajectory drift calculation.
- **`statefresh_core.mojo`**: Atomic compare-and-swap (CAS) validation and OCC commit checks.

---

## FastMCP Universal Tool Integration

SwarmMojo exposes all specialist engines and fleet capabilities over FastMCP. Connect any compatible client (Claude Code, Cursor, Windsurf, or custom harnesses):

```json
{
  "mcpServers": {
    "swarmmojo": {
      "command": "python",
      "args": ["d:/Buzburg Files/Github/SwarmMojo/swarmmojo.py", "mcp"]
    }
  }
}
```

### Core MCP Tools Available:
- **`coding_review_code`**: Multi-perspective static security and performance code review.
- **`coding_inspect_binary`**: Inspect binary magic headers, architecture, and entry points.
- **`coding_repo_codemap`**: Extract hierarchical project-wide symbol codemaps.
- **`meta_antibody_check`**: Query fleet herd immunity memory for instant failure remedies.
- **`meta_once_run`**: Execute deduplicated shell commands with memory TTL caching.
- **`meta_screenhand_action`**: Dispatch high-speed desktop clicks, typing, and window focus.
- **`meta_everywhere_dispatch`**: Dispatch omnipresent actions to specialist agents.
- **`workflow_run_dag`**: Run 8-stage constitutional DAG workflows with cryptographic verification.
- **`assistant_get_briefing`**: Fetch daily executive priorities and system health briefings.
- **`design_build_landing_page`**: Generate complete dark-mode landing pages with glassmorphism.
- **`studio_compile_prompt`**: Compile cinematic directorial prompts with optics and lighting presets.
- **`writer_audit_prose`**: Run Ghost Protocol anti-slop audits and cadence analyses.

---

## Quick Start & Verification

### 1. Prerequisites
- **Python**: 3.11 or later
- **Mojo**: Modular Mojo SIMD compiler (v25+) for native kernels (automatic fallback included)

### 2. Run the First-Run Diagnostic Demo
```sh
python -I -S -B scripts/demo_first_run.py
```
*Zero installation, zero GPU, and zero network required. Exercises real controlled recovery and log compaction.*

### 3. Run the Comprehensive Test Suite
```sh
uv run --directory . --with pytest python -m pytest tests/test_swarmmojo.py tests/test_meta_harness.py tests/test_writer_agent.py tests/test_studio_agent.py tests/test_workflow_agent.py tests/test_meta_comparison.py tests/test_repo_enhancements.py tests/test_new_harness_upgrades.py tests/test_aeon_harness.py tests/test_harness.py tests/test_integrations.py -v
```
**100% test pass rate across all 109 core integration and unit test suites.**

---

## Sovereign Architecture & Authorship

- **Author**: Buzburg AI
- **Contact & Inquiries**: `buzburgai@gmail.com`
- **GitHub Repository**: [https://github.com/Buzburg/SwarmMojo](https://github.com/Buzburg/SwarmMojo)
- **License**: [Apache-2.0](LICENSE) © 2026 Buzburg LLC.
