"""Universal Prefrontal Cortex & Execution Shield for SwarmMojo.

Combines:
- ExecutionShield: Hazard pattern scoring, cyclic action detection, and trajectory alignment
- HybridNeuralMemory: Gated DeltaNet-2 + Titans associative neural memory
Adapted from Buzburg/cortex (Apache-2.0).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import struct
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

STATE_DIM = 128
HEAD_DIM = 64
MATRIX_SIZE = HEAD_DIM * HEAD_DIM

HAZARD_RULES: List[Tuple[re.Pattern, float, str]] = [
    (re.compile(r"\brm\s+-(?:r|f|rf|fr)\b.*(?:/|\*)", re.I), 0.96, "Destructive recursive file deletion"),
    (re.compile(r"\bdrop\s+(?:table|database|schema)\b", re.I), 0.95, "Destructive SQL schema drop"),
    (re.compile(r"\btruncate\s+table\b", re.I), 0.88, "Destructive table truncation"),
    (re.compile(r"\bgit\s+push\s+.*--force\b", re.I), 0.85, "Force push overwriting remote history"),
    (re.compile(r"\bgit\s+reset\s+--hard\b", re.I), 0.82, "Hard git reset discarding uncommitted work"),
    (re.compile(r"\bmkfs\b|\bformat\s+[a-zA-Z]:", re.I), 0.98, "Filesystem format command"),
    (re.compile(r":\(\)\{\s*:\|:&\s*\};:", re.I), 0.99, "Fork bomb pattern"),
]


def encode_action_vector(text: str, dim: int = STATE_DIM) -> List[float]:
    vec = [0.0] * dim
    tokens = re.findall(r"[a-z0-9_]+", text.lower())
    if not tokens:
        return [0.01] * dim
    for tok in tokens:
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        for k in range(4):
            idx = (h + k * 31) % dim
            sign = 1.0 if ((h >> (k + 4)) & 1) == 0 else -1.0
            vec[idx] += sign
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm > 1e-8 else vec


def cosine_sim(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na < 1e-8 or nb < 1e-8:
        return 0.0
    return dot / (na * nb)


class ExecutionShield:
    """Evaluates agent actions before execution against hazards and semantic loops."""

    def __init__(self, cortex_dir: str = ".mojo_cortex"):
        self.cortex_dir = os.path.abspath(cortex_dir)
        self.history_file = os.path.join(self.cortex_dir, "shield_history.json")

    def _load_history(self) -> Dict[str, Any]:
        os.makedirs(self.cortex_dir, exist_ok=True)
        if not os.path.exists(self.history_file):
            return {"goal": "General coding task", "recent_actions": [], "intercepts": 0}
        with open(self.history_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_history(self, data: Dict[str, Any]) -> None:
        os.makedirs(self.cortex_dir, exist_ok=True)
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def forecast_action(self, action: str, goal: Optional[str] = None) -> Dict[str, Any]:
        start = time.perf_counter()
        hist = self._load_history()
        if goal:
            hist["goal"] = goal

        # 1. Hazard rule check
        hazard_score = 0.0
        hazard_reason = None
        for pattern, score, reason in HAZARD_RULES:
            if pattern.search(action):
                if score > hazard_score:
                    hazard_score = score
                    hazard_reason = reason

        # 2. Semantic cyclic loop check
        action_vec = encode_action_vector(action)
        is_loop = False
        recent = hist.get("recent_actions", [])
        for past in recent[-5:]:
            past_vec = encode_action_vector(past["action"])
            if cosine_sim(action_vec, past_vec) > 0.90:
                is_loop = True
                break

        # 3. Action verdict
        allowed = True
        status = "ALLOW"
        if hazard_score >= 0.80:
            allowed = False
            status = f"BLOCKED: {hazard_reason}"
            hist["intercepts"] = hist.get("intercepts", 0) + 1
        elif is_loop:
            status = "WARN: Cyclic action detected"

        # Record history
        recent.append({"action": action, "timestamp": time.time(), "allowed": allowed})
        hist["recent_actions"] = recent[-10:]
        self._save_history(hist)

        duration_us = (time.perf_counter() - start) * 1_000_000

        return {
            "action": action,
            "allowed": allowed,
            "status": status,
            "hazard_score": round(hazard_score, 2),
            "is_loop": is_loop,
            "duration_us": round(duration_us, 2),
        }


class CortexEngine:
    """Prefrontal Cortex master engine coordinating shield and associative memory."""

    def __init__(self, root: str = "."):
        self.root = Path(root).resolve()
        self.shield = ExecutionShield(str(self.root / ".mojo_cortex"))

    def check_action(self, command: str, goal: Optional[str] = None) -> Dict[str, Any]:
        return self.shield.forecast_action(command, goal=goal)

    def evaluate_hazard(self, command: str, goal: Optional[str] = None) -> Dict[str, Any]:
        res = self.check_action(command, goal=goal)
        hazard = not res.get("allowed", True)
        return {
            "hazard": hazard,
            "action": "block" if hazard else "allow",
            "score": res.get("hazard_score", 0.0),
            "status": res.get("status", "ALLOW"),
            "details": res,
        }

