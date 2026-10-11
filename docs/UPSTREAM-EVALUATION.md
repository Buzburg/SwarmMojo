# Sovereign Architecture & Engine Evaluation

**SwarmMojo by Buzburg AI**  
*Maintainer:* Buzburg AI (`buzburgai@gmail.com`)

SwarmMojo maintains complete architectural sovereignty. It avoids dependencies on external agent frameworks, cloud orchestrators, or third-party wrappers, relying instead on 19 native Buzburg AI mathematical engines and over 40 compiled Mojo SIMD kernels.

---

## 1. Sovereign Architecture Invariants

SwarmMojo enforces five foundational architectural invariants:

1. **Sub-Millisecond System-1 Triage (`mojo-fastgate`)**:
   Deterministic 256-dimensional phase embeddings evaluated in SIMD Mojo kernels triage tool capabilities in under 50 microseconds, completely bypassing expensive LLM reasoning turns for basic routing.
2. **Dual-Weight Test-Time Neural Memory (`mojo-titans`)**:
   Implements Titans DeltaNet with fused gradient descent, surprise momentum buffers, and adaptive forgetting, coupled with Compact-KV sliding-window attention eviction.
3. **Deterministic Geometric Drift Bounds (`mojo-drift`)**:
   Trajectory safety is enforced mathematically in 256-dimensional phase space ($\theta < 65^\circ$ safe, $\theta \ge 80^\circ$ blocked), providing a deterministic guardrail rather than probabilistic prompt instructions.
4. **Optimistic Concurrency Control (`statefresh`)**:
   Multi-agent swarms operate concurrently using atomic Compare-And-Swap (CAS) version leases and read-set validation, eliminating filesystem clobbering and locks.
5. **Microsecond Transactional Rollback (`mojo-agent-rewind`)**:
   Working tree changes are snapshot in microseconds using content-addressed SHA-256 trees, enabling instant rollback on tool errors or test failures.

---

## 2. Native Engine Integration Matrix

| Engine | Namespace | Primary Role | Acceleration |
| :--- | :--- | :--- | :--- |
| **Symdex** | `app.engines.symdex` | In-memory bi-directional call-graph & symbol indexing (<20 µs) | `app_mojo/symdex_core.mojo` |
| **Titans** | `app.engines.titans` | Test-time neural memory with momentum & surprise gating | `app_mojo/titans_core.mojo` |
| **Micro-ToolCall** | `app.engines.toolcall` | Deterministic schema coercion and repair for 7B-32B local models | `app_mojo/toolcall_core.mojo` |
| **Sieve** | `app.engines.sieve` | Streaming terminal log compaction (95%+ noise reduction) | `app_mojo/sieve_core.mojo` |
| **Local-Horizon** | `app.engines.horizon` | State-machine task graph DAG & anti-loop circuit breaker | `app_mojo/horizon_core.mojo` |
| **Fastgate** | `app.engines.fastgate` | 256-dim phase vector System-1 tool triage | `app_mojo/fastgate_core.mojo` |
| **Compact-KV** | `app.engines.compact_kv` | Rolling structured working memory scratchpad (<800 tokens) | `app_mojo/compact_kv_core.mojo` |
| **Agent-Rewind** | `app.engines.rewind` | Content-addressed workspace snapshots & instant rollback | `app_mojo/rewind_core.mojo` |
| **Path-Carry** | `app.engines.path_carry` | Filename safety, cross-platform reserved-name audit | `path_carry_audit` |
| **Mojo-Drift** | `app.engines.drift` | 256-dim phase-space angular drift guardrails (<65° safe, ≥80° block) | `app_mojo/drift_core.mojo` |
| **StateFresh** | `app.engines.statefresh` | Optimistic Concurrency Control (OCC) & atomic CAS leases | OCC validation |
| **WorkflowProof** | `app.engines.workflowproof` | Cryptographic Merkle invariant proofs & SHA-256 execution caching | Merkle tree validation |
| **Triad-Engine** | `app.engines.triad` | Multi-objective Pareto ranking (reliability, duration, token cost) | Pareto ranking |
| **Studio-Engine** | `app.engines.studio` | Multimodal cinematic video, directorial optics & visual graphs | `app_mojo/studio_core.mojo` |
| **Design-Engine** | `app.engines.design` | Impeccable UI craft floor, WCAG AAA contrast & enterprise dashboards | `app_mojo/design_core.mojo` |
| **Writer-Engine** | `app.engines.writer` | Ghost Protocol anti-slop filters & chapter outline DAGs | `app_mojo/writer_core.mojo`, `prose_metric.mojo` |
| **Workflow-Engine**| `app.engines.workflow_automation` | 8-stage constitutional pipeline governance & routine triggers | `app_mojo/workflow_core.mojo` |
| **Assistant-Engine**| `app.engines.personal_assistant` | 24/7 personal companion, encrypted vault & realtime voice bridge | `app_mojo/assistant_core.mojo` |
| **PolyHarness** | `app.polyharness` | Universal zero-dependency transpiler for IDE & runtime configs | PolyHarness AST |

---

## 3. Sovereign Deployment Guarantee

SwarmMojo is 100% locally sovereign:
- Operates fully air-gapped without external cloud telemetries or databases.
- Supports heterogeneous local model inference (Ollama, LM Studio, vLLM, Native, RWKV7).
- Preserves all licenses, proofs, and developer artifacts on the operator's machine.
