"""Compatibility stub for Swarmojo decisions module pending upgraded Decision Maker AI engine."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict

DEFAULT_STATE_DIR = str(Path.home() / ".swarmmojo")


def evaluate_decision(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    """Fallback stub for decision evaluation."""
    return {
        "status": "abstained",
        "choice": None,
        "engine": "Swarmojo Decision Maker",
        "abstention_reasons": ["evidence_missing"],
        "probabilities": {},
    }
