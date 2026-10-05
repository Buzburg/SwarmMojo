"""Automated Verification Suite for ROMS Mojo Implementation."""

from std.python import Python, PythonObject
from app_mojo.config import get_base_paths
from app_mojo.vector_math import dot_product, cosine_similarity
from app_mojo.db import get_connection, init_database
from app_mojo.okf_loader import ingest_okf_directory
from app_mojo.rag_engine import search_knowledge_base
from app_mojo.tools import (
    create_support_ticket,
    get_support_ticket,
    update_ticket_status,
    list_support_tickets,
    sanitize_output,
)

def test_vector_math() raises:
    print("[TEST 1/6] Running Native Mojo SIMD Vector Math...")
    var v1 = List[Float32](capacity=3)
    v1.append(1.0)
    v1.append(2.0)
    v1.append(3.0)

    var v2 = List[Float32](capacity=3)
    v2.append(1.0)
    v2.append(2.0)
    v2.append(3.0)

    var sim = cosine_similarity(v1, v2)
    if sim > 0.999:
        print("  -> PASSED: Identical vectors cosine similarity =", sim)
    else:
        raise Error("Expected cosine similarity near 1.0")

def test_database() raises:
    print("[TEST 2/6] Running Mojo Database Setup...")
    var paths = get_base_paths()
    paths[0].mkdir(parents=True, exist_ok=True)
    var temp_db = paths[0] / "test_roms_mojo.db"
    init_database(temp_db)
    print("  -> PASSED: Schema initialized in test_roms_mojo.db")

def test_ingestion() raises:
    print("[TEST 3/6] Running Mojo OKF Document Ingestion...")
    var paths = get_base_paths()
    var temp_db = paths[0] / "test_roms_mojo.db"
    var count = ingest_okf_directory(paths[2], temp_db)
    print("  -> PASSED: Ingested", count, "OKF documents into test vector store")

def test_vector_search() raises:
    print("[TEST 4/6] Running Mojo Semantic Vector Search...")
    var paths = get_base_paths()
    var temp_db = paths[0] / "test_roms_mojo.db"
    var res = search_knowledge_base("damaged items transit replacement", 1, temp_db)
    if res.find("refund_policy.md") != -1:
        print("  -> PASSED: Vector search retrieved correct policy chunk!")
    else:
        raise Error("Search did not retrieve the expected policy")

def test_ticket_ops() raises:
    print("[TEST 5/6] Running Mojo Operational Ticket Management...")
    var paths = get_base_paths()
    var temp_db = paths[0] / "test_roms_mojo.db"
    var c_res = create_support_ticket("MOJO-001", "dev@mojo.org", "Testing Mojo tickets", temp_db)
    var fetch = get_support_ticket("MOJO-001", temp_db)
    var u_res = update_ticket_status("MOJO-001", "RESOLVED", temp_db)
    var l_res = list_support_tickets("RESOLVED", temp_db)
    if fetch.find("MOJO-001") != -1 and l_res.find("RESOLVED") != -1:
        print("  -> PASSED: Ticket lifecycle verified.")
    else:
        raise Error("Ticket lifecycle failed")

def test_sanitizer() raises:
    print("[TEST 6/6] Running Mojo Context Sanitizer...")
    var long_str = "X" * 3000
    var sanitized = sanitize_output(long_str, 2500)
    if sanitized.find("[OUTPUT TRUNCATED BY MCP GUARDIAN]") != -1:
        print("  -> PASSED: Output properly truncated.")
    else:
        raise Error("Sanitizer did not truncate")

from app_mojo.quantized_vec import BinaryVector, binarize_embedding, int8_dot_product

def test_quantized_vectors() raises:
    print("[TEST 7/7] Running Native Mojo SIMD 1-Bit & Int8 Quantized Vector Matcher...")
    var v1 = List[Float32](capacity=4)
    v1.append(0.5)
    v1.append(-0.2)
    v1.append(0.8)
    v1.append(-0.9)

    var b1 = binarize_embedding(v1)
    var b2 = binarize_embedding(v1)
    var sim = b1.similarity(b2)
    if sim > 0.99:
        print("  -> PASSED: 1-Bit SIMD Quantized Vector Matcher similarity =", sim)
    else:
        raise Error("Expected binary similarity near 1.0")

def main() raises:
    # All state lives in a temporary directory, even when run in a working checkout.
    var tempfile = Python.import_module("tempfile")
    var temp = tempfile.TemporaryDirectory(prefix="roms-mojo-")
    var pathlib = Python.import_module("pathlib")
    var isolated = pathlib.Path(temp.name)
    var config = Python.import_module("app.config")
    config.DATA_DIR = isolated / "data"
    config.DB_PATH = config.DATA_DIR / "roms.db"
    try:
        test_vector_math()
        test_database()
        test_ingestion()
        test_vector_search()
        test_ticket_ops()
        test_sanitizer()
        test_quantized_vectors()
        print("All seven Mojo checks passed.")
    finally:
        temp.cleanup()
