"""Durable events, verified recipes, and bounded recurrent byte traces."""

import hashlib
import json
import math
from pathlib import Path
import sqlite3
import time
import uuid


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(packed(value).encode()).hexdigest()


class Memory:
    def __init__(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(directory / "memory.sqlite3")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, goal TEXT, workspace TEXT, status TEXT,
                pending TEXT, llm_calls INTEGER DEFAULT 0, steps INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY, session TEXT, kind TEXT, data TEXT, created REAL);
            CREATE TABLE IF NOT EXISTS recipes (
                key TEXT PRIMARY KEY, actions TEXT, expires REAL);
            CREATE TABLE IF NOT EXISTS traces (
                label TEXT PRIMARY KEY, vector TEXT, samples INTEGER);
        """)
        columns = {r[1] for r in self.db.execute('PRAGMA table_info(sessions)')}
        with self.db:
            if 'decision_calls' not in columns:
                self.db.execute('ALTER TABLE sessions ADD COLUMN decision_calls INTEGER DEFAULT 0')

    def close(self):
        self.db.close()

    def new_session(self, goal, workspace):
        sid = uuid.uuid4().hex[:16]
        with self.db:
            self.db.execute("INSERT INTO sessions(id,goal,workspace,status) VALUES(?,?,?,?)",
                            (sid, goal, str(Path(workspace).resolve()), "active"))
        return sid

    def session(self, sid):
        row = self.db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        if row is None:
            raise ValueError("Unknown session")
        result = dict(row)
        result["pending"] = json.loads(result["pending"]) if result["pending"] else None
        return result

    def update(self, sid, **fields):
        if not set(fields) <= {"status", "pending", "llm_calls", "steps", "decision_calls"}:
            raise ValueError("Invalid session field")
        if "pending" in fields and fields["pending"] is not None:
            fields["pending"] = packed(fields["pending"])
        with self.db:
            self.db.execute("UPDATE sessions SET " + ",".join(f"{k}=?" for k in fields) + " WHERE id=?",
                            (*fields.values(), sid))

    def event(self, sid, kind, data):
        with self.db:
            cursor = self.db.execute("INSERT INTO events(session,kind,data,created) VALUES(?,?,?,?)",
                                     (sid, kind, packed(data), time.time()))
        return cursor.lastrowid

    def events(self, sid):
        return [{**json.loads(row["data"]), "kind": row["kind"], "event_id": row['id']} for row in self.db.execute(
            "SELECT id,kind,data FROM events WHERE session=? ORDER BY id", (sid,))]

    def recipe(self, goal, workspace):
        row = self.db.execute("SELECT actions FROM recipes WHERE key=? AND expires>?",
                              (digest([goal, str(Path(workspace).resolve())]), time.time())).fetchone()
        return json.loads(row[0]) if row else None

    def learn_recipe(self, goal, workspace, actions, ttl):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO recipes VALUES(?,?,?)",
                            (digest([goal, str(Path(workspace).resolve())]), packed(actions), time.time()+ttl))

    def observe(self, goal, label):
        vector = byte_trace(goal)
        row = self.db.execute("SELECT vector,samples FROM traces WHERE label=?", (label,)).fetchone()
        count = row[1] if row else 0
        old = json.loads(row[0]) if row else [0.0] * len(vector)
        merged = [(x*min(count, 31)+y)/(min(count, 31)+1) for x, y in zip(old, vector)]
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO traces VALUES(?,?,?)", (label, packed(merged), count+1))

    def hints(self, goal):
        query = byte_trace(goal)
        norm = math.sqrt(sum(x*x for x in query)) or 1
        scores = []
        for row in self.db.execute("SELECT * FROM traces"):
            vector = json.loads(row["vector"])
            denom = norm * (math.sqrt(sum(x*x for x in vector)) or 1)
            scores.append({"label": row["label"], "similarity": sum(a*b for a,b in zip(query,vector))/denom,
                           "samples": row["samples"]})
        return sorted(scores, key=lambda x: x["similarity"], reverse=True)[:3]


def byte_trace(text, dim=64):
    """TMT-inspired decaying state over UTF-8 bytes; not a trained JEPA model.

    Used only as an advisory retrieval hint, never as authorization or a plan.
    """
    state = [0.0] * dim
    previous = 0
    for byte in text.encode("utf-8")[:4096]:
        state = [x * 0.97 for x in state]
        state[byte % dim] += 1
        state[(previous * 257 + byte) % dim] += 0.5
        previous = byte
    return state


def compact(events, budget):
    """Drop old successful read pairs intact; preserve failures and recent events.

    Full events remain in SQLite. Never silently truncate instructions or writes.
    """
    kept = list(events)
    from .tools import READ_TOOLS
    read_tools = READ_TOOLS
    recent = {id(x) for x in kept[-4:]}
    for event in list(kept):
        if len(packed(kept).encode()) <= budget:
            break
        if (id(event) not in recent and event.get("kind") == "tool"
                and event.get("result", {}).get("ok") is True
                and event.get("action", {}).get("tool") in read_tools):
            kept.remove(event)
    if len(packed(kept).encode()) > budget:
        raise ValueError("Pinned context exceeds budget; start a new task or increase max_context_bytes")
    return kept
