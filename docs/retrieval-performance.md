# Retrieval correctness and performance

## Scope
2026-10-02: focused changes to the Python `app/rag_engine.py` implementation.
No new dependencies, models, live database edits, or schema changes. The separate
Mojo retrieval implementation has not been optimized or benchmarked here.

## Changes
- Unicode-aware, case-folded, deduplicated, quoted FTS5 terms: literal `OR` no
  longer produces a syntax error; international words retain their characters.
  Any-term (OR) semantics remain unchanged. This does not add exact-phrase search.
- Tuple fusion keys replace concatenated `doc_id::content` strings. Indexed
  results now merge by `chunk_id` (not identical text), retain that ID in output,
  and don't conflate separate passages or document revisions. Legacy/mock search
  results without chunk IDs fall back to `(doc_id, content)`.
- Result-cache keys include `k_constant`. Caller-owned connections bypass the
  global result cache to avoid mixing databases or transaction snapshots.
- Cache dictionaries are copied on insertion and retrieval so callers cannot
  mutate another caller's cached evidence. Default-path hot-result caching remains.

## Measurements
Same Windows Python environment and fixed synthetic corpus, before/after.
Seven batches, each 20 warmups plus 200 measured cold-result-cache queries;
40 candidates per retrieval path, approximately 18,000 characters per passage.
Only fusion and result assembly are timed: vector/keyword retrieval is supplied
by fixed fixtures. No inference, disk retrieval, or network costs are measured.

| Metric | Before | After |
|---|---:|---:|
| Median of batch-median fusion latency | 0.36935 ms | 0.02890 ms |
| Batch-median range | 0.36340–0.37455 ms | 0.02840–0.02990 ms |
| Lexical top-1 correct on four fixture cases | 2/4 | 4/4 |

The observed fusion-stage speedup is approximately 12.8x (92.2% lower latency).
That is NOT a whole-system speedup. Four targeted lexical cases are regression
fixtures, not a representative accuracy benchmark and not a model-answer score.
Cases: literal OR, Überprüfung, ERR_CONNECTION_REFUSED, and refund.

## Reproduce (from ROMS, Windows Git Bash)
```sh
.venv/Scripts/python.exe -m pytest tests/test_retrieval_quality.py tests/test_release_safety.py tests/test_memory.py tests/test_context.py -q
PYTHONPATH=. .venv/Scripts/python.exe tests/test_retrieval_quality.py
```
The benchmark and tests use isolated in-memory SQLite and fixed passage fixtures.
Do not substitute the older `scripts/benchmark_performance.py` for this baseline:
that script touches project directories and may invoke an embedding model.

## Remaining accuracy and performance work
- Build a reviewed, representative document/query/relevance dataset before
  changing fusion weights, candidate counts, rerankers, chunking, or embeddings.
  Measure recall@k, nDCG, source grounding, and cold/warm end-to-end latency.
- Embedding checkpoint-revision tracking still needs an independent fix;
  provider/model names alone cannot detect changed weights served under the same
  name. Python result freshness now checks SQLite changes (see follow-up below).
- Result-cache normalization still lowercases queries, following existing
  behavior. Explicit connection queries deliberately sacrifice result caching
  for isolation; see the embedding-cache correctness follow-up below.
- No real embedding-model integration test, Mojo retrieval parity test, model
  answer-quality evaluation, or production-load benchmark was performed.
- Cold benchmark values after each increment are recorded below; the latest
  0.0359 ms fusion latency includes chunk-level provenance and is the current
  measured value on fixed fixtures, not an end-to-end target.

## Embedding-cache correctness follow-up
Query vectors and result-cache keys now include provider, model name, dimension,
and the active remote endpoint. Persistent query hashes also have a version tag.
The in-memory embedding cache is database-path scoped; caller-owned connections
bypass it and read their own persistent entries. Verified hot memory hits avoid
SQL and repeat inference, and persistent hits avoid repeat inference.

Persistent blobs must have exactly 384 finite float32 values; malformed entries
are recomputed. Provider vectors must have a one-dimensional 384-value finite
shape before any cache write. Invalid provider output raises `ValueError`.

Compatibility: legacy query-only entries are retained but not reused by Python;
the first query under the new namespace will recompute its embedding (which can
contact the configured provider during normal operation). No schema migration or
cache deletion is required. The separate Mojo retrieval path still uses its old
cache convention and does not return chunk IDs in the same contract; parity remains
unfinished.

## Provenance and query-failure follow-up
Before this fix, hybrid fusion used only `(doc_id, content)`, dropping `chunk_id`.
Different indexed chunks with identical text collapsed into one, while the same
chunk with changed content could appear twice if vector and FTS indexes differed.
Fusion now uses a chunk ID when available, merges matching vector/FTS hits by that
ID, and retains its ID on results. Legacy injected result fixtures without IDs keep
the old pair-based fallback. Three regressions failed before the fix.

`lexical_search` also swallowed every SQLite exception and mislabeled corrupt,
missing, or inaccessible FTS indexes as an empty result. It now returns `[]` only
for valid no-match searches and propagates operational errors to the caller. Test:
dropping the FTS table raises `sqlite3.OperationalError`, while a valid no-match
remains empty. After these changes, the combined offline suites report 95 passed,
1 existing skip.

With the provenance fields and merging enabled, the same synthetic cold-fusion
median measured 0.0359 ms (batch medians 0.0357–0.0362 ms); hot cache measured
0.0077 ms (batch medians 0.0077–0.0078 ms). Retrieval fixtures and test timing are
not representative of live data or a whole pipeline. Changing embedding models STILL
requires reindexing document vectors in a fresh compatible index. Namespaced
query caching does not convert existing document vectors, and does not support
hot-swapping the process's loaded local model; restart/reindex when changing it.

Eight new failures were reproduced before the fix. Follow-up tests additionally
cover provider/endpoint changes, legacy entries, nested vectors, and retained hot
caching. Combined offline verification: 86 passed, 1 existing skip.

Before preserving chunk IDs, the latest synthetic fusion median was 0.0286 ms
(batch medians 0.0284–0.0289 ms), versus the original 0.36935 ms. After preserving
chunk IDs, the median is 0.0359 ms (batch medians 0.0357–0.0362 ms). The additional
provenance work has a measurable cost and was kept for correctness. The earlier
12.8x fusion improvement is a historic measurement, not a promise about this
implementation or end-to-end latency.

## Result-cache freshness follow-up
Python hybrid search now obtains its pooled connection before checking the result
cache. Cache keys include the connection itself, SQLite `PRAGMA data_version`
(other connections' commits), and `total_changes` (local writes). Transactional
queries bypass the result cache. Results are only cached if the change token
remains stable through retrieval. The cache remains capped at 512 entries;
obsolete generations are evicted by the existing LRU policy. Cache keys retain
connection references until eviction/clear, but do not create new connections.

Reproduced four stale-result failures before the fix: local writes, a separate
writer's commits, connection replacement, and rollback of private edits. Added
coverage for writes during retrieval. The final combined offline suite after the
additional provenance fixes reports 95 passed, 1 existing skip.

After adding the SQLite freshness check, before the provenance changes, the hot
lookup median was 0.0073 ms (seven batches 0.0072–0.0076 ms); the latest measured
hot result after preserving chunk IDs is 0.0077 ms (seven batches 0.0077–0.0078 ms).
This benchmark uses in-memory SQLite, fixed candidate fixtures, and 20-result
dictionary copies; it is not a disk/network benchmark or a before/after baseline.
Checking freshness adds a SQLite PRAGMA on each eligible hot lookup. Unchanged
queries still avoid keyword/vector retrieval and model inference.

Limits: commits visible before the version check invalidate cached results; a
writer racing after the check may still leave that particular response stale.
This is not a linearizability or atomic two-path retrieval guarantee. Changes to
any SQLite table can conservatively invalidate results, including memory or query
embedding writes. A cold query that persists a new embedding may skip result
caching once because its change token moved. Mojo retrieval still lacks this
freshness check. Explicit embedding-cache entries and in-memory vectors are not
made cross-process coherent by this result-cache change.
