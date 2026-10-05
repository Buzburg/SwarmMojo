"""Local, project-scoped lessons with explicit evidence and a reversible lifecycle."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from typing import Iterator
from uuid import uuid4

from app.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS lesson_memories (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    revision TEXT NOT NULL,
    session_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('candidate','verified','superseded','retracted')),
    outcome TEXT NOT NULL CHECK(outcome IN ('unknown','success','failure')),
    created_at TEXT NOT NULL,
    expires_at TEXT,
    superseded_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_lesson_scope ON lesson_memories(project_id, status, created_at);
CREATE TABLE IF NOT EXISTS lesson_events (
    event_id INTEGER PRIMARY KEY,
    memory_id TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lesson_events ON lesson_events(memory_id, event_id);
CREATE VIRTUAL TABLE IF NOT EXISTS lesson_search USING fts5(memory_id UNINDEXED, summary);
CREATE TRIGGER IF NOT EXISTS lesson_insert AFTER INSERT ON lesson_memories BEGIN
    INSERT INTO lesson_search(memory_id, summary) VALUES (new.id, new.summary);
END;
CREATE TRIGGER IF NOT EXISTS lesson_delete AFTER DELETE ON lesson_memories BEGIN
    DELETE FROM lesson_search WHERE memory_id = old.id;
    DELETE FROM lesson_events WHERE memory_id = old.id;
END;
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _text(value: str, label: str, maximum: int, *, required: bool = True) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    value = value.strip()
    if (required and not value) or len(value) > maximum or "\x00" in value:
        raise ValueError(f"{label} must contain {'1' if required else '0'}–{maximum} characters")
    return value


def _scope(project_id: str) -> str:
    value = _text(project_id, "project_id", 128)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]*", value):
        raise ValueError("project_id must be a stable project name, with no spaces")
    return value


def _expiry(value: str) -> str | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("expires_at must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")


@contextmanager
def _connection(db_path: Path | str | None) -> Iterator[sqlite3.Connection]:
    path = Path(db_path) if db_path is not None else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript(SCHEMA)
        with connection:
            yield connection
    finally:
        connection.close()


def _find(connection: sqlite3.Connection, project: str, memory_id: str) -> sqlite3.Row:
    row: sqlite3.Row | None = connection.execute(
        "SELECT * FROM lesson_memories WHERE project_id = ? AND id = ?", (project, memory_id)
    ).fetchone()
    if row is None:
        raise LookupError("Memory not found in this project")
    return row


def _event(connection: sqlite3.Connection, memory_id: str, action: str, detail: str) -> None:
    connection.execute(
        "INSERT INTO lesson_events(memory_id, action, detail, created_at) VALUES (?, ?, ?, ?)",
        (memory_id, action, detail, _now()),
    )


def _record(row: sqlite3.Row) -> dict[str, object]:
    record = dict(row)
    expired = row["expires_at"] is not None and row["expires_at"] <= _now()
    record["expired"] = expired
    record["recommendation_eligible"] = (
        row["status"] == "verified" and row["outcome"] == "success" and not expired
    )
    return record


def retain_memory(
    project_id: str, summary: str, source_ref: str, revision: str = "",
    session_id: str = "", expires_at: str = "", *, db_path: Path | str | None = None,
) -> dict[str, object]:
    """Store a candidate; saving text never verifies that it is correct."""
    project = _scope(project_id)
    values = (
        uuid4().hex, project, _text(summary, "summary", 4000),
        _text(source_ref, "source_ref", 1000), _text(revision, "revision", 160, required=False),
        _text(session_id, "session_id", 128, required=False), _now(), _expiry(expires_at),
    )
    with _connection(db_path) as connection:
        connection.execute(
            "INSERT INTO lesson_memories(id, project_id, summary, source_ref, revision, session_id, "
            "status, outcome, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, 'candidate', 'unknown', ?, ?)",
            values,
        )
        _event(connection, values[0], "retained", "Candidate; no verification recorded")
        return _record(_find(connection, project, values[0]))


def record_memory_verification(
    project_id: str, memory_id: str, command: str, exit_code: int, evidence_ref: str,
    *, db_path: Path | str | None = None,
) -> dict[str, object]:
    """Record caller-supplied test evidence. Does not execute commands or authenticate receipts."""
    project = _scope(project_id)
    command = _text(command, "command", 1000)
    reference = _text(evidence_ref, "evidence_ref", 1000)
    if type(exit_code) is not int or not -2147483648 <= exit_code <= 2147483647:
        raise ValueError("exit_code must be an integer process status")
    with _connection(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = _find(connection, project, memory_id)
        if row["status"] != "candidate" or (row["expires_at"] and row["expires_at"] <= _now()):
            raise ValueError("Only a current candidate can receive verification; correct it to create a new candidate")
        outcome = "success" if exit_code == 0 else "failure"
        connection.execute("UPDATE lesson_memories SET status = 'verified', outcome = ? WHERE id = ?", (outcome, memory_id))
        _event(connection, memory_id, "verification", json.dumps({
            "command": command, "exit_code": exit_code, "evidence_ref": reference,
            "authority": "caller-supplied",
        }, ensure_ascii=False))
        return _record(_find(connection, project, memory_id))


def get_memory(project_id: str, memory_id: str, *, db_path: Path | str | None = None) -> dict[str, object]:
    project = _scope(project_id)
    with _connection(db_path) as connection:
        record = _record(_find(connection, project, memory_id))
        record["events"] = [dict(row) for row in connection.execute(
            "SELECT action, detail, created_at FROM lesson_events WHERE memory_id = ? ORDER BY event_id DESC LIMIT 100",
            (memory_id,),
        )]
        return record


def recall_memory(
    project_id: str, query: str, limit: int = 5, max_chars: int = 6000,
    include_candidates: bool = False, revision: str = "", *, db_path: Path | str | None = None,
) -> dict[str, object]:
    """Bounded keyword recall. Default results exclude unverified and inactive records."""
    project = _scope(project_id)
    query = _text(query, "query", 500, required=False)
    revision = _text(revision, "revision", 160, required=False)
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20")
    if type(max_chars) is not int or not 500 <= max_chars <= 20000:
        raise ValueError("max_chars must be between 500 and 20000")
    if type(include_candidates) is not bool:
        raise ValueError("include_candidates must be boolean")
    tokens = re.findall(r"\w+", query, flags=re.UNICODE)[:24]
    if query and not tokens:
        return {"memories": [], "truncated": False}
    terms = " OR ".join('"' + word + '"' for word in tokens)
    statuses = "('verified','candidate')" if include_candidates else "('verified')"
    sql = "SELECT m.* FROM lesson_memories m "
    params: list[str | int] = []
    if terms:
        sql += "JOIN lesson_search ON m.id = lesson_search.memory_id WHERE lesson_search MATCH ? AND "
        params.append(terms)
    else:
        sql += "WHERE "
    sql += f"m.project_id = ? AND m.status IN {statuses} AND (m.expires_at IS NULL OR m.expires_at > ?) "
    params.extend([project, _now()])
    if revision:
        sql += "AND m.revision = ? "
        params.append(revision)
    sql += "ORDER BY " + ("bm25(lesson_search), " if terms else "") + "m.created_at DESC, m.id LIMIT ?"
    params.append(limit + 1)
    with _connection(db_path) as connection:
        rows = connection.execute(sql, params).fetchall()
        recall_rows = rows[:limit]
        verification_by_id: dict[str, object] = {}
        if recall_rows:
            placeholders = ", ".join("?" for _ in recall_rows)
            evidence_rows = connection.execute(
                "SELECT memory_id, detail FROM lesson_events e "
                "WHERE action = 'verification' AND memory_id IN (" + placeholders + ") "
                "AND event_id = (SELECT MAX(latest.event_id) FROM lesson_events latest "
                "WHERE latest.memory_id = e.memory_id AND latest.action = 'verification')",
                [row["id"] for row in recall_rows],
            ).fetchall()
            for evidence in evidence_rows:
                verification_by_id.setdefault(evidence["memory_id"], json.loads(evidence["detail"]))

        truncated = len(rows) > limit
        records: list[dict[str, object]] = []
        records_length = 0
        prefix_length = len('{"memories": [')

        def serialized_length(is_truncated: bool, item_count: int, items_length: int) -> int:
            suffix_length = len('], "truncated": ' + json.dumps(is_truncated) + '}')
            return prefix_length + suffix_length + items_length + 2 * max(0, item_count - 1)

        for row in recall_rows:
            record = _record(row)
            record["verification"] = verification_by_id.get(row["id"])
            record_length = len(json.dumps(record, ensure_ascii=False))
            candidate_length = records_length + record_length + (2 if records else 0)
            if serialized_length(truncated, len(records) + 1, candidate_length) > max_chars:
                truncated = True
            else:
                records.append(record)
                records_length = candidate_length

        return {"memories": records, "truncated": truncated}


def correct_memory(
    project_id: str, memory_id: str, summary: str, source_ref: str, reason: str,
    revision: str = "", expires_at: str = "", *, db_path: Path | str | None = None,
) -> dict[str, object]:
    """Atomically replace a lesson with a new candidate; old evidence never transfers."""
    project = _scope(project_id)
    summary = _text(summary, "summary", 4000)
    source_ref = _text(source_ref, "source_ref", 1000)
    reason = _text(reason, "reason", 1000)
    revision = _text(revision, "revision", 160, required=False)
    expiry = _expiry(expires_at)
    with _connection(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        old = _find(connection, project, memory_id)
        if old["status"] not in {"candidate", "verified"}:
            raise ValueError("Only an active record can be corrected")
        replacement = uuid4().hex
        connection.execute(
            "INSERT INTO lesson_memories(id, project_id, summary, source_ref, revision, session_id, status, outcome, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'candidate', 'unknown', ?, ?)",
            (replacement, project, summary, source_ref, revision, old["session_id"], _now(), expiry),
        )
        connection.execute("UPDATE lesson_memories SET status = 'superseded', superseded_by = ? WHERE id = ?", (replacement, memory_id))
        _event(connection, memory_id, "superseded", reason)
        _event(connection, replacement, "correction", json.dumps({"replaces": memory_id, "reason": reason}))
        return _record(_find(connection, project, replacement))


def retract_memory(project_id: str, memory_id: str, reason: str, *, db_path: Path | str | None = None) -> dict[str, object]:
    project = _scope(project_id)
    reason = _text(reason, "reason", 1000)
    with _connection(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = _find(connection, project, memory_id)
        if row["status"] not in {"candidate", "verified"}:
            raise ValueError("Only an active record can be retracted")
        connection.execute("UPDATE lesson_memories SET status = 'retracted' WHERE id = ?", (memory_id,))
        _event(connection, memory_id, "retracted", reason)
        return _record(_find(connection, project, memory_id))


def forget_memory(project_id: str, memory_id: str, *, db_path: Path | str | None = None) -> dict[str, object]:
    """Delete one record and its FTS/audit content; does not securely erase backups."""
    project = _scope(project_id)
    with _connection(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _find(connection, project, memory_id)
        connection.execute("DELETE FROM lesson_memories WHERE id = ? AND project_id = ?", (memory_id, project))
        return {"forgotten": memory_id, "project_id": project}
