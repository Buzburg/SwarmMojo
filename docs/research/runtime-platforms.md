# Sovereign Local Model Runtimes & Inference Acceleration

**Swarmojo by Buzburg AI**  
*Maintainer:* Buzburg AI (`buzburgai@gmail.com`)

This specification details the heterogeneous local model runtime layer for Swarmojo.

---

## 1. Supported Inference Backends

Swarmojo connects natively to local model servers without cloud telemetry:

1. **Ollama**: Default local REST API endpoint (`http://localhost:11434`).
2. **LM Studio**: Local OpenAI-compatible REST server (`http://localhost:1234/v1`).
3. **vLLM / SGLang**: High-throughput batched serving engines with PagedAttention and prefix caching.
4. **RWKV-7**: Linear attention RNN inference with zero-memory attention scaling.
5. **Deterministic Mock**: In-memory offline testing runtime for instant, zero-cost regression test suites.

---

## 2. Response Termination & Stream Safety

The gateway enforces complete response envelope checks:
- Truncated or interrupted generation streams are detected immediately and rejected before tool execution occurs.
- Token counts, elapsed times, and model aliases are logged to local audit stores.
