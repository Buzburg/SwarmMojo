"""Mojo SQLite and sqlite-vec + FTS5 Database Initialization and Management."""

from std.python import Python, PythonObject
from app_mojo.config import ROMSConfig, get_base_paths

def _get_pool() raises -> PythonObject:
    var builtins = Python.import_module("builtins")
    var has_pool = Python.evaluate("lambda b: hasattr(b, '_roms_pool')")(builtins)
    if not has_pool:
        var pool = Python.evaluate("{}")
        builtins._roms_pool = pool
        return pool
    return builtins._roms_pool

def get_connection(custom_db_path: PythonObject = Python.none()) raises -> PythonObject:
    """Creates or reuses a pooled SQLite connection with WAL mode enabled and sqlite-vec loaded."""
    var is_none = Python.evaluate("lambda x: x is None")(custom_db_path)
    var db_path_str: String
    if not is_none:
        db_path_str = String(custom_db_path)
    else:
        var paths = get_base_paths()
        var data_dir = paths[0]
        data_dir.mkdir(parents=True, exist_ok=True)
        db_path_str = String(paths[1])

    # Check pooled connection
    var pool = _get_pool()
    var has_key = Python.evaluate("lambda p, k: k in p")(pool, db_path_str)
    if has_key:
        var existing = pool[db_path_str]
        try:
            existing.execute("SELECT 1")
            return existing
        except:
            pass

    var sqlite3 = Python.import_module("sqlite3")
    var sqlite_vec = Python.import_module("sqlite_vec")
    var conn = sqlite3.connect(db_path_str, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA cache_size=-64000;")
    conn.execute("PRAGMA mmap_size=268435456;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    pool[db_path_str] = conn
    return conn

def init_database(custom_db_path: PythonObject = Python.none()) raises:
    """Initializes ROMS schema in SQLite: OKF registry, vec0 virtual table, FTS5 lexical table, and support tickets."""
    var cfg = ROMSConfig()
    var conn = get_connection(custom_db_path)
    var cur = conn.cursor()

    # 1. OKF Registry Table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS okf_registry (
        doc_id TEXT PRIMARY KEY,
        title TEXT,
        doc_type TEXT,
        source_path TEXT,
        checksum TEXT,
        last_indexed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 2. vec0 Virtual Table with auxiliary columns (+prefix)
    var vec_table_sql = (
        "CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0("
        + "chunk_id INTEGER PRIMARY KEY, "
        + "+doc_id TEXT, "
        + "embedding float[" + String(cfg.embedding_dim) + "], "
        + "+content TEXT"
        + ")"
    )
    cur.execute(vec_table_sql)

    # 3. FTS5 Lexical Table for Porter-stemmed BM25 search
    cur.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS fts_chunks USING fts5(
        chunk_id UNINDEXED,
        doc_id UNINDEXED,
        content,
        tokenize='porter unicode61'
    )
    """)

    # 4. Query Embedding Cache Table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS embedding_cache (
        query_hash TEXT PRIMARY KEY,
        embedding_blob BLOB,
        last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 5. Operational Table: Support tickets
    cur.execute("""
    CREATE TABLE IF NOT EXISTS support_tickets (
        ticket_id TEXT PRIMARY KEY,
        customer_email TEXT,
        issue_summary TEXT,
        status TEXT DEFAULT 'OPEN',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_tickets_status ON support_tickets(status);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tickets_email ON support_tickets(customer_email);")

    # 6. Tool Registry & Discovery (AnyTool Smart Tool RAG)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tool_registry (
        tool_name TEXT PRIMARY KEY,
        category TEXT,
        description TEXT,
        parameters_json TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 7. Tool Execution Analytics & Self-Healing Reliability Stats
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tool_stats (
        tool_name TEXT PRIMARY KEY,
        call_count INTEGER DEFAULT 0,
        success_count INTEGER DEFAULT 0,
        fail_count INTEGER DEFAULT 0,
        total_latency_ms REAL DEFAULT 0.0,
        last_latency_ms REAL DEFAULT 0.0,
        last_error TEXT DEFAULT '',
        last_called TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 8. UpSkill Trajectory Recording for SOP Distillation
    cur.execute("""
    CREATE TABLE IF NOT EXISTS agent_trajectories (
        session_id TEXT PRIMARY KEY,
        goal TEXT,
        steps_json TEXT,
        success INTEGER DEFAULT 0,
        final_result TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_tool_cat ON tool_registry(category);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_traj_success ON agent_trajectories(success);")

    # 9. Hierarchical Topic Taxonomy & Topic Routing
    cur.execute("""
    CREATE TABLE IF NOT EXISTS topics (
        topic_id TEXT PRIMARY KEY,
        parent_topic TEXT,
        label TEXT,
        description TEXT DEFAULT '',
        chunk_count INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS chunk_topics (
        chunk_id INTEGER,
        topic_id TEXT,
        score REAL DEFAULT 1.0,
        PRIMARY KEY (chunk_id, topic_id)
    )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_chunk_topics_tid ON chunk_topics(topic_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_topics_parent ON topics(parent_topic);")

    # 10. AutoKarpathy Evaluation & Optimization Loop
    cur.execute("""
    CREATE TABLE IF NOT EXISTS karpathy_evals (
        eval_id TEXT PRIMARY KEY,
        task_name TEXT,
        prompt TEXT,
        score REAL,
        feedback TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()

