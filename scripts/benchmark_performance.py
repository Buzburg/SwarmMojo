"""High-Precision Latency & Throughput Benchmark Suite for ROMS.

Measures all critical hot paths:
1. Thread-Local DB Connection Pooling Latency
2. Tier-0 In-Memory RRF Hybrid Search Cache Latency
3. Query Embedding Cache Latency
4. Smart Tool RAG Discovery Latency
5. Context Budgeting & XML Grounding Latency
6. Trajectory Recording & Distillation Latency
"""

import time
import statistics
from pathlib import Path
from app.db import get_connection, init_database
from app.rag_engine import search_knowledge_base, _get_query_embedding, hybrid_search, clear_result_cache
from app.tool_rag import search_tools, format_tool_search_results, init_default_tool_registry, record_tool_call
from app.trajectory_recorder import start_session, record_step, finish_session, distill_trajectory_to_skill
from app.prompt_builder import format_context_for_local_llm

def benchmark_function(fn, iterations=100, warmup=10):
    for _ in range(warmup):
        fn()
    latencies = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        fn()
        t1 = time.perf_counter()
        latencies.append((t1 - t0) * 1000.0) # in ms
    return {
        "p50_ms": statistics.median(latencies),
        "p95_ms": sorted(latencies)[int(iterations * 0.95)],
        "min_ms": min(latencies),
        "avg_ms": statistics.mean(latencies),
    }

def run_benchmarks():
    print("=" * 65)
    print("  ROMS HIGH-PRECISION PERFORMANCE & OPTIMIZATION BENCHMARK")
    print("=" * 65)

    test_db = Path("data/benchmark_roms.db")
    if test_db.exists():
        test_db.unlink()
    init_database(test_db)
    init_default_tool_registry(db_path=test_db)

    # Ingest baseline document
    from app.okf_loader import ingest_document_file
    sample_doc = Path("knowledge/refund_policy.md")
    if sample_doc.exists():
        ingest_document_file(sample_doc, db_path=test_db)

    # 1. Connection Pooling
    def bench_conn():
        conn = get_connection(test_db, reuse=True)
        conn.execute("SELECT 1")
    conn_res = benchmark_function(bench_conn, iterations=500)
    print(f"\n[1] Thread-Local Pooled SQLite Connection:")
    print(f"    Avg: {conn_res['avg_ms']:.4f} ms | Min: {conn_res['min_ms']:.4f} ms | P95: {conn_res['p95_ms']:.4f} ms")

    # 2. Embedding Cache
    def bench_emb_cache():
        _get_query_embedding("transit damage replacement", db_path=test_db)
    # Warm it once
    bench_emb_cache()
    emb_res = benchmark_function(bench_emb_cache, iterations=200)
    print(f"\n[2] Persistent Query Embedding Cache (SQLite BLOB):")
    print(f"    Avg: {emb_res['avg_ms']:.4f} ms | Min: {emb_res['min_ms']:.4f} ms | P95: {emb_res['p95_ms']:.4f} ms")

    # 3. Tier-0 In-Memory RRF Result Cache
    def bench_rrf_cache():
        search_knowledge_base("transit damage replacement", limit=2, db_path=test_db)
    # Warm it once
    bench_rrf_cache()
    rrf_res = benchmark_function(bench_rrf_cache, iterations=500)
    print(f"\n[3] Tier-0 In-Memory RRF Result Cache:")
    print(f"    Avg: {rrf_res['avg_ms']:.4f} ms | Min: {rrf_res['min_ms']:.4f} ms | P95: {rrf_res['p95_ms']:.4f} ms")

    # 4. Smart Tool RAG Discovery
    def bench_tool_rag():
        search_tools("create support ticket customer issue", limit=2, db_path=test_db)
    tool_res = benchmark_function(bench_tool_rag, iterations=200)
    print(f"\n[4] Smart Tool RAG Schema Discovery:")
    print(f"    Avg: {tool_res['avg_ms']:.4f} ms | Min: {tool_res['min_ms']:.4f} ms | P95: {tool_res['p95_ms']:.4f} ms")

    # 5. Context Compression & Grounding for Local LLMs
    dummy_chunks = [
        {"doc_id": "policy.md", "content": "Full refund within 30 days of arrival for transit damages.", "score": 0.045},
        {"doc_id": "policy.md", "content": "Full refund within 30 days of arrival for transit damages.", "score": 0.044}, # duplicate
        {"doc_id": "inventory.csv", "content": "Table: Inventory\nRow 1: GPU RTX 4090 In Stock", "score": 0.038},
    ]
    def bench_prompt_grounding():
        format_context_for_local_llm(dummy_chunks, format_style="xml", max_tokens=256)
    prompt_res = benchmark_function(bench_prompt_grounding, iterations=500)
    print(f"\n[5] Context Compression & XML Grounding:")
    print(f"    Avg: {prompt_res['avg_ms']:.4f} ms | Min: {prompt_res['min_ms']:.4f} ms | P95: {prompt_res['p95_ms']:.4f} ms")

    # 6. UpSkill Trajectory Step Logging
    session_id = "bench_session_01"
    start_session(session_id, "Benchmark task workflow", db_path=test_db)
    def bench_traj_logging():
        record_step(session_id, "search_tools", {"query": "ticket"}, "Found create_ticket", db_path=test_db)
    traj_res = benchmark_function(bench_traj_logging, iterations=100)
    print(f"\n[6] UpSkill Trajectory Step Recording:")
    print(f"    Avg: {traj_res['avg_ms']:.4f} ms | Min: {traj_res['min_ms']:.4f} ms | P95: {traj_res['p95_ms']:.4f} ms")

    # Cleanup
    from app.db import _THREAD_LOCAL
    key = f"conn_{test_db}"
    if hasattr(_THREAD_LOCAL, key):
        try:
            getattr(_THREAD_LOCAL, key).close()
            delattr(_THREAD_LOCAL, key)
        except Exception:
            pass

    if test_db.exists():
        try:
            test_db.unlink()
            wal = Path("data/benchmark_roms.db-wal")
            shm = Path("data/benchmark_roms.db-shm")
            if wal.exists(): wal.unlink()
            if shm.exists(): shm.unlink()
        except Exception:
            pass

    print("\n" + "=" * 65)
    print("  BENCHMARK SUITE COMPLETE")
    print("=" * 65)

if __name__ == "__main__":
    run_benchmarks()
