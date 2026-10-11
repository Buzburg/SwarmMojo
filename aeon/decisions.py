"""Compatibility stub for aeon decisions module pending upgraded Decision Maker AI engine."""
from __future__ import annotations
from typing import Any, Dict, Optional


class DecisionClient:
    """Client stub for decision requests pending upgraded Decision Maker AI engine."""

    def __init__(self, backend: Any = None, cancel_event: Any = None):
        self.backend = backend
        self.cancel_event = cancel_event
        self.calls = 0

    def ask(self, *args: Any, **kwargs: Any) -> Any:
        if self.cancel_event and self.cancel_event.is_set():
            from aeon.inference import InferenceError
            raise InferenceError('cancelled by caller')
        return {"choice": None, "decision_calls": 0}

    def evaluate(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        return {
            "status": "abstained",
            "choice": None,
            "engine": "Swarmojo Decision Maker",
            "decision_calls": 0,
        }
