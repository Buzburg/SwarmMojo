# Sovereign Multi-Agent Guild Topology & Orchestration Architecture

**Swarmojo by Buzburg AI**  
*Maintainer:* Buzburg AI (`buzburgai@gmail.com`)

This specification defines the multi-agent coordination topologies, thread scheduling, and communication contracts in the Swarmojo meta-harness.

---

## 1. Topologies Supported

Swarmojo provides three native coordination patterns across specialist agents:

1. **Coordinator-Worker (DAG Dispatch)**:
   - Lead coordinator (`Atlas`) decomposes objectives into an acyclic task graph (DAG).
   - Workers execute isolated subtasks with independent context scratchpads.
   - Outputs are distilled and aggregated into the parent context.
2. **Sequential Pipeline (`Chain`)**:
   - Sequential execution stages where each stage automatically pipes its verified output to the next stage via `{previous}` tokens.
   - Guarded by intermediate WorkflowProof Merkle checks.
3. **Structured Deliberation**:
   - Multiple specialist agents (e.g., Architect, Reviewer, Security Auditor) conduct source-grounded review rounds.
   - Operator approval tickets are required before any state mutation is staged.

---

## 2. Safety Bounds

- **Angular Drift Interceptor**: Every subtask action is evaluated geometrically in 256-dimensional phase space. Trajectories with $\ge 80^\circ$ angular deviation from the parent goal are blocked automatically.
- **Circuit Breaker**: Detects repeating semantic loops and terminates recursive loops before token window exhaustion.
