# ROMS

**RAG, OKF documents, MCP tools, and skills for local agents.** By Buzburg LLC.

**ROMS** stands for the four core pillars of this project's local agent architecture:

- **R — RAG (Retrieval-Augmented Generation):** SQLite FTS5 keyword search + vector search.
- **O — OKF (Open Knowledge Format):** Markdown-structured documents with metadata, following this project's OKF convention.
- **M — MCP (Model Context Protocol):** Exposing tools and resources to LLMs.
- **S — Skills:** Reusable agent SOPs (standard operating procedures) and playbooks.

ROMS brings document retrieval and reusable agent playbooks into one local server. The Python implementation combines SQLite keyword search with embedding search and exposes tools through MCP. An optional gateway adds retrieved context to text chat requests sent to an OpenAI-compatible backend.

**Status: experimental developer preview.** Start with a private repository and trusted local clients. The Mojo implementation is a separate experimental path, not a verified replacement for every Python feature. This project is not an inference engine.

## What is included

- SQLite FTS5 keyword search and sqlite-vec embedding search, combined with reciprocal rank fusion.
- Markdown with YAML metadata (the project's OKF convention), plus CSV, TSV, JSON and selected text/code formats.
- Skills exposed as MCP resources and prompts; local Python plugins under `custom_tools/`.
- Project-scoped lesson memory with evidence records, corrections, expiry and bounded keyword recall.
- Budgeted memory context that preserves a relevant failed-attempt warning. Native Mojo selection on the Mojo server, with a Python fallback; [implementation and measured results](docs/native-context.md).
- Sample support-ticket tools, trajectory recording, and experimental research/dataset helpers. Generated skills start as inactive drafts.
- A polling file watcher. Indexing latency depends on document size, embedding work and polling interval.

Research and dataset helpers are heuristics over local records. They do not establish factual correctness, prevent hallucinations, or perform model training. No universal latency or token-saving claim is made.

## Start the Python MCP server

Use Python 3.11 or 3.12. From this folder on Windows:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m app.server
```

On Linux, use `python3` to create the environment and `.venv/bin/python` for subsequent commands. Configure your MCP client to launch that Python executable with `-m app.server` and this repository as its working directory. Startup messages go to stderr; stdout is reserved for MCP. Running it in a terminal waits for a client and does not open a web page.

The default embedding model is `sentence-transformers/all-MiniLM-L6-v2`. Its first use may download model files. Local embeddings run on CPU. Selecting Ollama or an OpenAI-compatible embedding endpoint sends text to that configured endpoint, whose hardware and privacy behavior are outside ROMS. The database expects 384-dimensional embeddings; changing models/providers requires a compatible model and a fresh index.

## Optional chat gateway

Start your own OpenAI-compatible model server, then run:

```powershell
$env:ROMS_UPSTREAM_LLM_URL = "http://127.0.0.1:11434/v1"
.venv\Scripts\python -m app.gateway
```

ROMS initializes its database and indexes knowledge on startup. The default gateway is `http://127.0.0.1:8844/v1`. It accepts text role/content messages; multimodal input is not supported. It is an experimental partial API proxy, not a claim of full OpenAI compatibility. It has no authentication and must remain local. Completion caching is disabled so model/settings/context changes cannot reuse an unrelated response. Streaming error handling still needs integration coverage.

## Retrieval quality and performance

The Python retrieval engine quotes and deduplicates Unicode FTS5 terms, isolates
caller-owned connections from the shared result cache, and uses collision-free
fusion keys. A fixed offline fixture measured approximately 12.8x faster **rank
fusion**, not end-to-end search; targeted lexical cases improved from 2/4 to 4/4.
See [measurement scope, reproduction, and remaining limits](docs/retrieval-performance.md).
Query embedding caches are now scoped by provider, model, dimension, and remote
endpoint, with finite-vector validation and corrupt-entry recovery. Legacy Python
query-cache entries are retained but recomputed under the new namespace. Changing
models still requires a fresh document index and a process restart.
Python result-cache lookups check SQLite local/external changes; transactional
reads bypass that cache, preventing reuse of rolled-back or outdated evidence.
Search results also retain indexed chunk IDs, so identical text from separate
chunks keeps its source provenance. FTS operational errors surface rather than
being silently reported as an empty search. Details and benchmarks:
[retrieval performance and correctness](docs/retrieval-performance.md).
These results do not establish general model-answer accuracy or Mojo parity.

## Local project memory

Eight `memory_*` tools retain lessons between sessions on both MCP servers. New lessons are candidates; recall normally includes only current records with test evidence supplied by the caller. Corrections need fresh verification, and failed attempts remain labeled warnings. Evidence is recorded, not independently certified. Read the [memory guide](docs/local-memory.md) for the workflow and limits. No extra runtime package or service is needed.

## Data and configuration

`knowledge/` and `skills/` contain starter examples. Treat the bundled refund policy as fictional demonstration content, not an actual Buzburg customer policy. Replace it with reviewed documents for your use case.

`data/` holds the database, support records, lesson memory and agent trajectories; it is ignored by Git. Review newly added knowledge, skills and plugins before committing: these directories are source content and are not ignored. Document text, prompts and tool outputs can become persistent records.

See `app/config.py` for `ROMS_DATA_DIR`, `ROMS_DB_PATH`, `ROMS_KNOWLEDGE_DIR`, `ROMS_SKILLS_DIR`, upstream URL and resource limits. Keep credentials in private environment configuration. See [SECURITY.md](SECURITY.md) for the local trust model.

## Tests

```powershell
.venv\Scripts\python -m pytest tests/test_release_safety.py tests/test_memory.py tests/test_context.py -q
.venv\Scripts\python -m pytest tests/test_roms.py -q
```

The release-safety and memory tests use isolated files and mocked upstream responses without a model download. The original integration suite uses the real embedding model and also touches configured runtime directories: run it in a disposable copy or configure temporary data, knowledge and skills folders. See [docs/github-readiness.md](docs/github-readiness.md) for actual verification results and unresolved checks. CI runs the offline release-safety, memory and context-selection suites on Windows and Linux; it is not a full model or Mojo validation.

## Mojo path

`pixi.toml` declares a Linux x86-64 environment. Windows needs WSL for this path. From the repository directory inside Linux/WSL, install the environment with `pixi install`, then use `pixi run test` or `pixi run server`. The Mojo 1.1.0 server now compiles, and its MCP interface passed an end-to-end protocol test in WSL. The launchers call these same Pixi tasks from the project directory. See [the bridge verification record](docs/mojo-bridge-fix.md) for test scope and reproduction steps. Mojo modules use Python interoperability and do not have demonstrated feature parity with the Python server.

## Omarchy Mojo RWKV7 foundation

The custom Arch/Omarchy WSL test build runs Goose 2.9B with ROMS, a native authenticated socket broker and an operator-guided project workshop. The actual Mojo sandbox requires Landlock ABI 3+ and combines with rootless containers for registered Python checks. Reviewed patches support controlled apply and rollback. Real model-state persistence/fork, desktop control, web evidence and guest delegation remain unfinished.

`config/build-inputs.json` pins supplied GGUF identities, the native runtime revision and the reviewed environment lockfile. `scripts/download_rwkv7.py` verifies local files by default; explicit HTTPS acquisition requires matching the recorded bytes. It performs no checkpoint conversion or unpinned native-library build. See [model input verification](docs/model-input-verification.md).

Use the [current readiness guide](docs/omarchy-rwkv7-harness-ready.md) and [operating guide](docs/wsl-test-build.md) for supported launchers, installed service architecture, verification profiles and remaining limits. A passing selected profile does not certify the full PDF roadmap.

## License and attribution

Original project code is licensed under Apache-2.0; see [LICENSE](LICENSE) and [NOTICE](NOTICE). Dependencies and downloaded models retain their own licenses. Reference PDFs, local environments, databases and generated datasets are excluded from the proposed upload. Verify the provenance of any copied code or playbooks before a public release.
