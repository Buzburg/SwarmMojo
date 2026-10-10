# Sovereign Neural Memory & Test-Time Learning Architecture

**SwarmMojo by Buzburg AI**  
*Maintainer:* Buzburg AI (`buzburgai@gmail.com`)

This specification defines the neural memory, test-time learning, and knowledge recall architecture in SwarmMojo.

---

## 1. Titans Test-Time Memorization (`mojo-titans`)

SwarmMojo implements the Titans architecture (arXiv:2501.00663) as an in-memory test-time learning engine accelerated in Mojo SIMD (`app_mojo/titans_core.mojo`):
- **Surprise Error Formulation**: Evaluates associative prediction error $e_t = M_{t-1} k_t - v_t$.
- **Surprise Momentum Gate**: Maintains momentum buffer $S_t = \eta S_{t-1} - \theta \nabla \mathcal{L}_t$.
- **Adaptive Forgetting**: Decays older memory states $M_t = (1 - \alpha) M_{t-1} + S_t$ to prevent memory saturation.

---

## 2. Compact-KV & Context Compaction (`mojo-compact-kv`, `mojo-sieve`)

- Working memory scratchpads are capped at 800 tokens using rotary positional embedding retention and sliding-window budgeting.
- Streaming logs are compacted in under 2ms using `mojo-sieve`, eliminating repetitive passing assertions and preserving error root causes.
- Long-term lessons and verification proofs are stored with SHA-256 fingerprints in local state directories.
