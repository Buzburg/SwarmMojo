"""Mojo Phase-Vector Associative Memory for SwarmMojo.

Zero-dependency Python implementation of Buzburg/mojo-memory phase-vector algebra.
Preserves lessons and evidence with median sub-10 ms recall.
Adapted from Buzburg/mojo-memory (Apache-2.0).
"""
from __future__ import annotations

import json
import math
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import functools

DIM = 512
TAU = 6.283185307179586


@functools.lru_cache(maxsize=32768)
def atom_phase(token: str) -> List[float]:
    """Generates 512 phase angles in [0, 2π) using 64-bit splitmix mixing."""
    seed = 14695981039346656037
    for byte in token.encode("utf-8"):
        seed = ((seed ^ byte) * 1099511628211) & 0xFFFFFFFFFFFFFFFF

    phases: List[float] = []
    for _ in range(DIM):
        seed = (seed + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        mixed = seed
        mixed = ((mixed ^ (mixed >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        mixed = ((mixed ^ (mixed >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        mixed = (mixed ^ (mixed >> 31)) & 0xFFFFFFFFFFFFFFFF
        angle = float(mixed >> 11) * (TAU / 9007199254740992.0)
        phases.append(angle)
    return phases


def encode_text_phases(tokens: List[str]) -> List[float]:
    """Superposes token phases into a bundled phase vector."""
    if not tokens:
        tokens = ["default"]
    real = [0.0] * DIM
    imag = [0.0] * DIM
    for tok in tokens:
        phases = atom_phase(tok)
        for i in range(DIM):
            real[i] += math.cos(phases[i])
            imag[i] += math.sin(phases[i])
    return [math.atan2(imag[i], real[i]) for i in range(DIM)]


def phase_similarity(left: List[float], right: List[float]) -> float:
    """Computes mean cosine similarity between two phase vectors."""
    total = sum(math.cos(l - r) for l, r in zip(left, right))
    return max(0.0, total / DIM)


class MojoMemoryEngine:
    """Persistent local filing cabinet for lessons, evidence, and verified notes."""

    def __init__(self, root: str = ".", scope: str = "default"):
        self.root = Path(root).resolve()
        self.scope = scope
        self.mem_dir = self.root / ".mojo_memory"
        self.store_file = self.mem_dir / f"{scope}_memory.json"
        self.mem_dir.mkdir(parents=True, exist_ok=True)
        if not self.store_file.exists():
            self._save([])

    def _load(self) -> List[Dict[str, Any]]:
        if not self.store_file.exists():
            return []
        try:
            return json.loads(self.store_file.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save(self, records: List[Dict[str, Any]]) -> None:
        self.store_file.write_text(json.dumps(records, indent=2), encoding="utf-8")

    def put_lesson(self, text: str, evidence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Stores a lesson and its evidence."""
        tokens = [t.lower() for t in text.split() if len(t) > 1]
        phases = encode_text_phases(tokens)
        records = self._load()
        item = {
            "id": f"rec-{len(records)+1}-{int(time.time())}",
            "text": text,
            "evidence": evidence or {},
            "phases": phases,
            "timestamp": time.time(),
        }
        records.append(item)
        self._save(records)
        return {"id": item["id"], "text": text, "status": "stored"}

    def search_lessons(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Recalls relevant lessons matching the query."""
        tokens = [t.lower() for t in query.split() if len(t) > 1]
        q_phases = encode_text_phases(tokens)
        records = self._load()

        scored = []
        for r in records:
            sim = phase_similarity(q_phases, r["phases"])
            scored.append({
                "id": r["id"],
                "text": r["text"],
                "evidence": r["evidence"],
                "similarity": round(sim, 4),
            })

        scored.sort(key=lambda x: x["similarity"], reverse=True)
        return scored[:limit]

    def stats(self) -> Dict[str, Any]:
        records = self._load()
        return {
            "scope": self.scope,
            "total_records": len(records),
            "store_path": str(self.store_file),
        }


class MojoMemory(MojoMemoryEngine):
    """Convenience alias for MojoMemoryEngine with key-value store/query semantics."""

    def __init__(self, root: str = ".", scope: str = "default", dimension: int = DIM):
        super().__init__(root=root, scope=scope)
        self.dimension = dimension

    def store(self, key: str, text: str, phase: float = 0.0) -> Dict[str, Any]:
        return self.put_lesson(text=text, evidence={"key": key, "phase": phase})

    def query(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        results = self.search_lessons(query=query, limit=top_k)
        for r in results:
            r["key"] = r.get("evidence", {}).get("key", r["id"])
        return results

