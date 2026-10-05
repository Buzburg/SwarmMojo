"""Mojo RAG Engine: High-performance Hybrid Search (sqlite-vec + FTS5 RRF).

Optimized for local LLM prompt contexts:
- 2-tier query embedding cache (memory & SQLite)
- Reciprocal Rank Fusion of vector distance & BM25 keyword matching
- Bounds total retrieved characters to protect context windows
- High information-density markdown output format
"""

from std.python import Python, PythonObject
from app_mojo.config import get_embedding_model, ROMSConfig
from app_mojo.db import get_connection

def _get_result_cache() raises -> PythonObject:
    var builtins = Python.import_module("builtins")
    var has_cache = Python.evaluate("lambda b: hasattr(b, '_roms_result_cache')")(builtins)
    if not has_cache:
        var cache = Python.evaluate("{}")
        builtins._roms_result_cache = cache
        return cache
    return builtins._roms_result_cache

def search_knowledge_base(query: String, limit: Int = 3, custom_db_path: PythonObject = Python.none()) raises -> String:
    """Performs hybrid vector & BM25 search using Reciprocal Rank Fusion (RRF) and returns compact markdown."""
    var cfg = ROMSConfig()
    var hashlib = Python.import_module("hashlib")
    var re = Python.import_module("re")
    var builtins = Python.import_module("builtins")

    var py_q = Python.evaluate("lambda s: str(s).strip().lower()")(query)
    var cache_key = String(py_q) + "::" + String(limit)

    var cache = _get_result_cache()
    var is_none = Python.evaluate("lambda x: x is None")(custom_db_path)
    if is_none:
        var has_cached = Python.evaluate("lambda c, k: k in c")(cache, cache_key)
        if has_cached:
            return String(cache[cache_key])

    var q_hash = String(hashlib.sha256(py_q.encode("utf-8")).hexdigest())

    var conn = get_connection(custom_db_path)
    var cur = conn.cursor()

    # Tier 1: Check SQLite embedding cache
    var check_params = Python.evaluate("[]")
    check_params.append(q_hash)
    cur.execute("SELECT embedding_blob FROM embedding_cache WHERE query_hash = ?", check_params)
    var cached = cur.fetchone()

    var query_bytes: PythonObject
    if cached is not None:
        query_bytes = cached[0]
    else:
        var model = get_embedding_model()
        query_bytes = model.encode(
            py_q, output_value="sentence_embedding"
        ).astype("float32").tobytes()

        var store_params = Python.evaluate("[]")
        store_params.append(q_hash)
        store_params.append(query_bytes)
        cur.execute(
            "INSERT OR REPLACE INTO embedding_cache (query_hash, embedding_blob) VALUES (?, ?)",
            store_params,
        )
        conn.commit()

    # 1. Vector Search Top Candidates
    var vec_params = Python.evaluate("[]")
    vec_params.append(query_bytes)
    vec_params.append(limit * 2)

    cur.execute(
        """
    SELECT doc_id, content, distance
    FROM vec_chunks
    WHERE embedding MATCH ?
    ORDER BY distance
    LIMIT ?
    """,
        vec_params,
    )
    var vec_rows = cur.fetchall()

    # 2. Lexical BM25 Search Top Candidates via FTS5
    var tokens = re.findall(r"\b[A-Za-z0-9_]+\b", py_q)
    var safe_fts_query = String(Python.evaluate("lambda t: ' OR '.join(t)")(tokens))

    var lex_rows = Python.evaluate("[]")
    if safe_fts_query.byte_length() > 0:
        var fts_params = Python.evaluate("[]")
        fts_params.append(safe_fts_query)
        fts_params.append(limit * 2)
        try:
            cur.execute(
                """
            SELECT doc_id, content, bm25(fts_chunks) AS score
            FROM fts_chunks
            WHERE fts_chunks MATCH ?
            ORDER BY score
            LIMIT ?
            """,
                fts_params,
            )
            lex_rows = cur.fetchall()
        except:
            pass

    conn.close()

    # 3. Reciprocal Rank Fusion (RRF) execution via scope
    var scope = Python.evaluate("{}")
    builtins.exec("""
def fuse(vec_rows, lex_rows, k=60, top_k=3):
    scores = {}
    for rank, r in enumerate(vec_rows, 1):
        key = (str(r[0]), str(r[1]))
        scores[key] = scores.get(key, 0.0) + (1.0 / (k + rank))
    for rank, r in enumerate(lex_rows, 1):
        key = (str(r[0]), str(r[1]))
        scores[key] = scores.get(key, 0.0) + (1.0 / (k + rank))
    sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [(k[0], k[1], score) for k, score in sorted_items[:top_k]]
""", scope)
    var rrf_helper = scope["fuse"]

    var fused_results = rrf_helper(vec_rows, lex_rows, 60, limit)

    if len(fused_results) == 0:
        return "No relevant documentation found."

    var formatted_results = Python.evaluate("[]")
    var format_fn = Python.evaluate("lambda d: f'{float(d):.3f}'")
    var accumulated_chars: Int = 0

    for r in fused_results:
        var doc_id = String(r[0])
        var raw_content = String(r[1])
        var score_rounded = String(format_fn(r[2]))

        if accumulated_chars + raw_content.byte_length() > cfg.max_rag_chars:
            var remaining_budget = cfg.max_rag_chars - accumulated_chars
            if remaining_budget > 100:
                var snippet = raw_content[byte=0:remaining_budget]
                var bounded_content = snippet + "... [TRUNCATED FOR TOKEN BUDGET]"
                var block = "[Source: " + doc_id + " | Score: " + score_rounded + "]\n" + bounded_content
                formatted_results.append(block)
            break

        var block = "[Source: " + doc_id + " | Score: " + score_rounded + "]\n" + raw_content
        formatted_results.append(block)
        accumulated_chars += raw_content.byte_length()

    var joiner = Python.evaluate("lambda items: '\\n\\n---\\n\\n'.join(items)")
    var final_str = String(joiner(formatted_results))
    if is_none:
        cache[cache_key] = final_str
    return final_str
