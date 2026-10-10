"""OKF (Open Knowledge Format) & Universal Multi-Format Document Ingestion Engine.

Inspired by Open Knowledge Format (OKF) specifications:
- Heterogeneous document support: .md, .csv, .json/.jsonl, .txt, source code (.py, .mojo, .sql, .ts, etc.)
- Schema-preserving tabular chunking: Column headers retained across every CSV chunk
- Synchronously populates both sqlite-vec (semantic vector index) and SQLite FTS5 (BM25 lexical index)
- SHA-256 deduplication and Tier-0 RRF cache auto-invalidation
"""

import csv
import hashlib
import io
import itertools
import json
import os
from pathlib import Path
from typing import List, Optional, Tuple
import frontmatter
import numpy as np

from app.config import get_embedding_model, KNOWLEDGE_DIR
from app.db import get_connection

SUPPORTED_EXTENSIONS = {
    ".md",
    ".markdown",
    ".csv",
    ".tsv",
    ".json",
    ".jsonl",
    ".txt",
    ".py",
    ".mojo",
    ".sql",
    ".sh",
    ".ps1",
    ".ts",
    ".js",
    ".tsx", ".jsx", ".rs", ".go", ".c", ".h", ".cpp", ".hpp",
    ".toml", ".yaml", ".yml", ".ini", ".css", ".html", ".xml",
}


def _parse_markdown(path: Path) -> Tuple[str, str, str, List[str]]:
    """Parses Markdown file, extracting OKF frontmatter and paragraph chunks."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        post = frontmatter.load(f)

    filename = path.name
    title = post.metadata.get("title", filename)
    doc_type = post.metadata.get("type", "general")
    content = post.content.strip()
    if not content:
        return title, doc_type, "", []

    paragraphs = [p.strip() for p in content.split("\n\n") if len(p.strip()) > 5]
    return title, doc_type, content, paragraphs


def _parse_csv(path: Path, rows_per_chunk: int = 5) -> Tuple[str, str, str, List[str]]:
    """Parses tabular CSV/TSV, preserving header context on every chunk for local LLMs."""
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    raw_content = path.read_text(encoding="utf-8", errors="replace")
    reader = csv.reader(io.StringIO(raw_content), delimiter=delimiter)
    headers = next(reader, None)
    if headers is None:
        return path.name, "tabular", "", []

    header_str = ", ".join(headers)
    chunks = []
    row_offset = 0
    while chunk_rows := list(itertools.islice(reader, rows_per_chunk)):
        lines = [f"Table: {path.name}", f"Columns: {header_str}", "Records:"]
        for row_idx, row in enumerate(chunk_rows, start=row_offset + 1):
            record_items = [
                f"{col}: {val}"
                for col, val in zip(headers, row)
                if val.strip()
            ]
            lines.append(f"- Row {row_idx}: " + "; ".join(record_items))
        chunks.append("\n".join(lines))
        row_offset += len(chunk_rows)

    if not chunks:
        chunks.append(f"Table: {path.name}\nColumns: {header_str}\n(No data rows)")

    title = f"Dataset: {path.name}"
    return title, "tabular", raw_content, chunks


def _parse_json(path: Path) -> Tuple[str, str, str, List[str]]:
    """Parses JSON or JSONL into semantically coherent chunk blocks."""
    raw_content = path.read_text(encoding="utf-8", errors="replace").strip()
    if not raw_content:
        return path.name, "json_dataset", "", []

    chunks = []
    is_jsonl = path.suffix.lower() == ".jsonl"

    if is_jsonl:
        lines = [line.strip() for line in raw_content.splitlines() if line.strip()]
        for i in range(0, len(lines), 3):
            group = lines[i : i + 3]
            chunk_text = f"Dataset {path.name} (Lines {i+1}-{i+len(group)}):\n" + "\n".join(group)
            chunks.append(chunk_text)
    else:
        try:
            data = json.loads(raw_content)
            if isinstance(data, list):
                for i in range(0, len(data), 3):
                    group = data[i : i + 3]
                    chunks.append(
                        f"Dataset {path.name} (Items {i+1}-{i+len(group)}):\n"
                        + json.dumps(group, indent=2)
                    )
            elif isinstance(data, dict):
                for k, v in data.items():
                    val_str = json.dumps(v, indent=2) if isinstance(v, (dict, list)) else str(v)
                    chunks.append(f"Document {path.name} [{k}]:\n{val_str}")
            else:
                chunks.append(f"Document {path.name}:\n{raw_content}")
        except Exception:
            chunks = [p.strip() for p in raw_content.split("\n\n") if len(p.strip()) > 5]

    title = f"Structured Data: {path.name}"
    return title, "json_dataset", raw_content, chunks


def _parse_text_or_code(path: Path) -> Tuple[str, str, str, List[str]]:
    """Parses plain text or source code files into logical code/text chunks."""
    raw_content = path.read_text(encoding="utf-8", errors="replace").strip()
    if not raw_content:
        return path.name, "code", "", []

    suffix = path.suffix.lower()
    doc_type = "code" if suffix in {".py", ".mojo", ".sql", ".sh", ".ps1", ".ts", ".js"} else "text"

    raw_blocks = [b.strip() for b in raw_content.split("\n\n") if len(b.strip()) > 5]
    chunks = []
    for b in raw_blocks:
        chunk_text = f"File: {path.name} ({doc_type})\n{b}"
        chunks.append(chunk_text)

    if not chunks:
        chunks = [f"File: {path.name} ({doc_type})\n{raw_content}"]

    title = f"Source: {path.name}"
    return title, doc_type, raw_content, chunks


def ingest_document_file(filepath: Path | str, db_path: Path | str | None = None, *, doc_id: str | None = None) -> bool:
    """Ingests any supported file (.md, .csv, .json, .txt, code) into both vector and FTS5 indexes.

    Returns True if ingested/updated, False if unchanged.
    """
    path = Path(filepath)
    if not path.is_file():
        return False

    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        return False

    if suffix in {".md", ".markdown"}:
        title, doc_type, raw_content, chunks = _parse_markdown(path)
    elif suffix in {".csv", ".tsv"}:
        title, doc_type, raw_content, chunks = _parse_csv(path)
    elif suffix in {".json", ".jsonl"}:
        title, doc_type, raw_content, chunks = _parse_json(path)
    else:
        title, doc_type, raw_content, chunks = _parse_text_or_code(path)

    if not raw_content or not chunks:
        return False

    filename = doc_id if doc_id is not None else path.name
    if not isinstance(filename, str) or not filename or len(filename) > 4096 or '\x00' in filename:
        raise ValueError('Invalid document identity')
    checksum = hashlib.sha256(raw_content.encode("utf-8")).hexdigest()

    from app.config import EMBEDDING_DIM, EMBEDDING_PROVIDER, compute_embedding_vector
    from app.topic import tag_chunks_with_topics

    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT checksum FROM okf_registry WHERE doc_id = ?", (filename,))
    existing = cur.fetchone()
    if existing and existing[0] == checksum:
        return False

    # Finish all model work and validate every vector before touching the old index.
    if EMBEDDING_PROVIDER == "local":
        try:
            import torch
            model = get_embedding_model()
            if hasattr(torch, "inference_mode"):
                with torch.inference_mode():
                    batch_embeddings = np.asarray(
                        model.encode(chunks, output_value="sentence_embedding", batch_size=32),
                        dtype=np.float32,
                    )
            else:
                batch_embeddings = np.asarray(
                    model.encode(chunks, output_value="sentence_embedding", batch_size=32),
                    dtype=np.float32,
                )
        except Exception:
            model = get_embedding_model()
            batch_embeddings = np.asarray(
                model.encode(chunks, output_value="sentence_embedding", batch_size=32),
                dtype=np.float32,
            )
    else:
        batch_embeddings = np.asarray(
            [compute_embedding_vector(chunk_text) for chunk_text in chunks],
            dtype=np.float32,
        )

    expected_shape = (len(chunks), EMBEDDING_DIM)
    if batch_embeddings.shape != expected_shape or not np.isfinite(batch_embeddings).all():
        raise ValueError(f"Expected {len(chunks)} finite embeddings of dimension {EMBEDDING_DIM}")

    # Use a short-lived writer connection so ingestion does not close a pooled
    # connection that active search callers may share.
    conn = get_connection(db_path, reuse=False)
    cur = conn.cursor()
    # Recheck under a savepoint in case another indexer updated this document
    # while embeddings were being calculated. Replacement stays atomic.
    try:
        cur.execute("SAVEPOINT roms_ingest_document")
        cur.execute("SELECT checksum FROM okf_registry WHERE doc_id = ?", (filename,))
        existing = cur.fetchone()
        if existing and existing[0] == checksum:
            cur.execute("RELEASE SAVEPOINT roms_ingest_document")
            conn.commit()
            return False
        old_topic_rows = cur.execute(
            "SELECT DISTINCT ct.topic_id FROM chunk_topics ct "
            "JOIN fts_chunks f USING(chunk_id) WHERE f.doc_id = ?",
            (filename,),
        ).fetchall()
        old_topic_ids = {row[0] for row in old_topic_rows}

        cur.execute(
            """
            INSERT INTO okf_registry (doc_id, title, doc_type, source_path, checksum)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(doc_id) DO UPDATE SET title=excluded.title, doc_type=excluded.doc_type,
                source_path=excluded.source_path, checksum=excluded.checksum,
                last_indexed=CURRENT_TIMESTAMP
            """,
            (filename, title, doc_type, str(path.resolve()), checksum),
        )
        cur.execute(
            "DELETE FROM chunk_topics WHERE chunk_id IN "
            "(SELECT chunk_id FROM fts_chunks WHERE doc_id = ?)", (filename,)
        )
        cur.execute("DELETE FROM vec_chunks WHERE doc_id = ?", (filename,))
        cur.execute("DELETE FROM fts_chunks WHERE doc_id = ?", (filename,))

        vector_rows = [
            (filename, vector.tobytes(), chunk_text)
            for chunk_text, vector in zip(chunks, batch_embeddings)
        ]
        cur.executemany(
            "INSERT INTO vec_chunks (doc_id, embedding, content) VALUES (?, ?, ?)",
            vector_rows,
        )
        first_chunk_id = cur.execute("SELECT last_insert_rowid()").fetchone()[0] - len(chunks) + 1
        chunk_ids = list(range(first_chunk_id, first_chunk_id + len(chunks)))
        cur.executemany(
            "INSERT INTO fts_chunks (chunk_id, doc_id, content) VALUES (?, ?, ?)",
            [(chunk_id, filename, chunk_text)
             for chunk_id, chunk_text in zip(chunk_ids, chunks)],
        )
        tag_chunks_with_topics(
            list(zip(chunk_ids, chunks)), conn, doc_type=doc_type,
            refresh_topic_ids=old_topic_ids,
        )
        cur.execute("RELEASE SAVEPOINT roms_ingest_document")
        conn.commit()
    except BaseException:
        cur.execute("ROLLBACK TO SAVEPOINT roms_ingest_document")
        cur.execute("RELEASE SAVEPOINT roms_ingest_document")
        raise
    finally:
        conn.close()

    # Ingestion commits the writer connection; drop local cached results.
    from app.rag_engine import clear_result_cache
    clear_result_cache()

    return True


# Backwards compatibility alias
ingest_okf_file = ingest_document_file


def ingest_okf_directory(
    directory_path: str | Path | None = None, db_path: Path | str | None = None
) -> int:
    """Scans and ingests all supported knowledge files (.md, .csv, .json, code, .txt) in the directory.

    Returns the number of files ingested or updated.
    """
    target_dir = Path(directory_path) if directory_path is not None else KNOWLEDGE_DIR
    if not target_dir.exists():
        target_dir.mkdir(parents=True, exist_ok=True)
        return 0

    ingested_count = 0
    for file_path in target_dir.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
            if ingest_document_file(file_path, db_path=db_path):
                ingested_count += 1

    return ingested_count
