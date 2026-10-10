"""StateFresh Engine for SwarmMojo.

Optimistic Concurrency Control, version leases, collision prevention, and stale-write guards
for multi-agent workspace operations.
Adapted from Buzburg/statefresh (Apache-2.0).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import time
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


@dataclass(frozen=True)
class Decision:
    outcome: str  # "pass", "block", "refresh"
    reasons: List[str]
    record_version: Optional[int]

    def to_dict(self) -> Dict[str, Any]:
        return dict(asdict(self))


def evaluate_state_update(
    action: Dict[str, Any],
    policy: Dict[str, Any],
    record: Optional[Dict[str, Any]],
    now: Optional[float] = None,
) -> Decision:
    """Preflight check for optimistic concurrency state updates."""
    now = time.time() if now is None else float(now)
    entity = str(action.get("entity_id", ""))
    expected_version = int(action.get("expected_version", 0))
    updates = action.get("updates", {})

    required_fields = policy.get("required_fields", [])
    allowed_updates = policy.get("allowed_updates", list(updates.keys()))
    max_age_seconds = float(policy.get("max_age_seconds", 300.0))

    if not updates:
        return Decision("block", ["Updates payload cannot be empty."], None)

    if record is None:
        return Decision("block", ["Record does not exist in store."], None)

    record_id = str(record.get("id", ""))
    current_version = int(record.get("version", 0))
    observed_at = float(record.get("observed_at", now))
    fields = record.get("fields", {})

    blocked: List[str] = []
    refresh: List[str] = []

    if entity != record_id:
        blocked.append("Action entity_id does not match record id.")

    for req in required_fields:
        if req not in fields or fields[req] in (None, ""):
            blocked.append(f"Required field missing: {req}")
        if req in updates and updates[req] in (None, ""):
            blocked.append(f"Update would clear required field: {req}")

    for k in updates:
        if allowed_updates and k not in allowed_updates:
            blocked.append(f"Update is not allowed for field: {k}")

    if expected_version != current_version:
        refresh.append(f"Stale version detected: expected {expected_version}, current {current_version}.")

    age = now - observed_at
    if age > max_age_seconds:
        refresh.append(f"Observation snapshot is stale ({age:.1f}s > {max_age_seconds:.1f}s max age).")

    outcome = "block" if blocked else "refresh" if refresh else "pass"
    return Decision(outcome, blocked + refresh or ["Checks passed."], current_version)


class StateFreshStore:
    """SQLite-backed atomic optimistic concurrency store."""

    def __init__(self, db_path: Union[str, Path] = ".statefresh.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.db_path)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS records ("
                "id TEXT PRIMARY KEY, version INTEGER, observed_at REAL, fields TEXT)"
            )

    def put(self, entity_id: str, fields: Dict[str, Any]) -> int:
        with closing(sqlite3.connect(self.db_path)) as db, db:
            now = time.time()
            db.execute(
                "INSERT INTO records (id, version, observed_at, fields) VALUES (?, 1, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET version=version+1, observed_at=?, fields=?",
                (entity_id, now, json.dumps(fields), now, json.dumps(fields)),
            )
            row = db.execute("SELECT version FROM records WHERE id=?", (entity_id,)).fetchone()
            return int(row[0]) if row else 1

    def get(self, entity_id: str) -> Optional[Dict[str, Any]]:
        with closing(sqlite3.connect(self.db_path)) as db, db:
            row = db.execute("SELECT version, observed_at, fields FROM records WHERE id=?", (entity_id,)).fetchone()
            if not row:
                return None
            return {
                "id": entity_id,
                "version": int(row[0]),
                "observed_at": float(row[1]),
                "fields": json.loads(row[2]),
            }

    def apply_update(
        self,
        entity_id: str,
        expected_version: int,
        updates: Dict[str, Any],
        policy: Optional[Dict[str, Any]] = None,
    ) -> Decision:
        """Atomic Compare-And-Swap (CAS) update."""
        policy = policy or {}
        with closing(sqlite3.connect(self.db_path, timeout=10)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            rec = self.get(entity_id)
            action = {
                "entity_id": entity_id,
                "expected_version": expected_version,
                "updates": updates,
            }
            decision = evaluate_state_update(action, policy, rec)
            if decision.outcome == "pass" and rec is not None:
                updated_fields = dict(rec.get("fields", {}))
                updated_fields.update(updates)
                now = time.time()
                db.execute(
                    "UPDATE records SET fields=?, version=version+1, observed_at=? WHERE id=? AND version=?",
                    (json.dumps(updated_fields), now, entity_id, expected_version),
                )
            return decision


class FileVersionGuard:
    """Guards workspace files against stale concurrent agent overwrites via SHA-256 digests."""

    def __init__(self, root: str = "."):
        self.root = Path(root).resolve()
        self.store = StateFreshStore(self.root / ".mojo_statefresh.db")

    def fingerprint_file(self, rel_path: str) -> str:
        target = (self.root / rel_path).resolve()
        if not target.exists():
            return ""
        return hashlib.sha256(target.read_bytes()).hexdigest()

    def check_and_stage_write(
        self,
        rel_path: str,
        expected_digest: str,
        new_content: str,
    ) -> Dict[str, Any]:
        """Verifies that the target file has not been modified since expected_digest."""
        current_digest = self.fingerprint_file(rel_path)
        if expected_digest and current_digest != expected_digest:
            return {
                "allowed": False,
                "reason": f"File '{rel_path}' was modified concurrently (expected digest {expected_digest[:8]}, found {current_digest[:8]}).",
                "current_digest": current_digest,
            }

        rec = self.store.get(rel_path)
        expected_ver = rec["version"] if rec else 0
        if rec and rec.get("fields", {}).get("digest") != expected_digest:
            return {
                "allowed": False,
                "reason": "Stale version record detected in StateFresh lease store.",
                "current_version": rec["version"],
            }

        new_digest = hashlib.sha256(new_content.encode("utf-8")).hexdigest()
        new_ver = self.store.put(rel_path, {"digest": new_digest, "size": len(new_content)})

        return {
            "allowed": True,
            "version": new_ver,
            "digest": new_digest,
        }


class StateFreshCoordinator:
    """Multi-agent resource coordinator providing leases and optimistic locking."""

    def __init__(self, db_path: Union[str, Path] = ".mojo_leases.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.db_path)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS leases ("
                "resource TEXT PRIMARY KEY, holder TEXT, expires_at REAL)"
            )

    def acquire_lease(self, resource: Union[str, Path], holder: str, ttl_seconds: float = 30.0) -> Optional[Dict[str, Any]]:
        res_key = str(resource)
        now = time.time()
        expires = now + float(ttl_seconds)
        with closing(sqlite3.connect(self.db_path, timeout=10)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT holder, expires_at FROM leases WHERE resource=?", (res_key,)).fetchone()
            if row:
                current_holder, current_expires = row[0], float(row[1])
                if current_expires > now and current_holder != holder:
                    return None  # Held by another agent and not expired
            db.execute(
                "INSERT INTO leases (resource, holder, expires_at) VALUES (?, ?, ?) "
                "ON CONFLICT(resource) DO UPDATE SET holder=?, expires_at=?",
                (res_key, holder, expires, holder, expires),
            )
            return {"resource": res_key, "holder": holder, "expires_at": expires}

    def release_lease(self, resource: Union[str, Path], holder: str) -> bool:
        res_key = str(resource)
        with closing(sqlite3.connect(self.db_path, timeout=10)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT holder FROM leases WHERE resource=?", (res_key,)).fetchone()
            if row and row[0] == holder:
                db.execute("DELETE FROM leases WHERE resource=?", (res_key,))
                return True
            return False

