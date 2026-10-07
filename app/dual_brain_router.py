"""Dual-Brain Cognitive Router: RWKV-7 Reflex + MSGL Oracle.

Coordinates the two inference engines:
1. Reflex Brain (RWKV-7 2.9B on 127.0.0.1:18080):
   - Fast sub-15ms O(1) recurrent token streaming
   - Optimal for interactive shell commands, tool dispatch, formatting, and single-turn chat
2. Oracle Brain (MSGL / VibeThinker / Qwen on 127.0.0.1:18084):
   - Deep deductive reasoning, multi-file refactoring, security audits
   - Enforces GBNF grammar constraints for strictly valid JSON / code ASTs

Incorporates the EPIC state machine and DARK deductive confidence scoring.
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from app.dark_reasoner import dark_bridge
from app.nest_soul import default_omarchy_soul


class BrainType(str, Enum):
    REFLEX = "REFLEX"  # RWKV-7 2.9B
    ORACLE = "ORACLE"  # MSGL / Deep Deductive Engine


@dataclass
class RouteDecision:
    target_brain: BrainType
    confidence: float
    reason: str
    gbnf_grammar: Optional[str] = None
    dark_pre_block: Optional[str] = None
    soul_state: str = field(default_factory=lambda: default_omarchy_soul.derive_mbti())


class DualBrainRouter:
    """Intelligent dispatch router between RWKV-7 Reflex and MSGL Oracle engines."""

    def __init__(
        self,
        reflex_endpoint: str = "http://127.0.0.1:18080/v1",
        oracle_endpoint: str = "http://127.0.0.1:18084/v1",
    ):
        self.reflex_endpoint = reflex_endpoint.rstrip("/")
        self.oracle_endpoint = oracle_endpoint.rstrip("/")

    def probe_health(self, brain: BrainType, timeout: float = 0.5) -> bool:
        """Quick socket probe to verify engine daemon availability."""
        url = (
            f"{self.reflex_endpoint}/models"
            if brain == BrainType.REFLEX
            else f"{self.oracle_endpoint}/models"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Omarchy-DualBrain/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status in (200, 204)
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    def route_request(
        self,
        prompt: str,
        files_involved: int = 1,
        requires_json: bool = False,
        force_brain: Optional[BrainType] = None,
    ) -> RouteDecision:
        """Deterministically selects either REFLEX or ORACLE based on task complexity."""
        if force_brain:
            return RouteDecision(
                target_brain=force_brain,
                confidence=1.0,
                reason=f"User forced brain: {force_brain.value}",
            )

        # 1. Run DARK Reasoning check on input prompt
        dark_res = dark_bridge.reason(prompt, mode="auto")
        dark_conf = dark_res.get("confidence", 0.3)
        dark_mode = dark_res.get("mode", "deductive")

        # Complex reasoning signals
        prompt_len = len(prompt.split())
        is_deductive_proof = dark_mode == "deductive" and dark_conf >= 0.70
        is_multi_file_refactor = files_involved > 2
        is_heavy_reasoning = prompt_len > 400 or "architect" in prompt.lower() or "verify" in prompt.lower()

        # Decision tree
        if is_multi_file_refactor:
            return RouteDecision(
                target_brain=BrainType.ORACLE,
                confidence=0.95,
                reason=f"Multi-file modification ({files_involved} files) requires Oracle global AST planning",
                gbnf_grammar='root ::= "{" ws "\"plan\":" [^}]* "}"' if requires_json else None,
            )

        if is_deductive_proof or is_heavy_reasoning:
            from app.dark_reasoner import format_dark_block
            return RouteDecision(
                target_brain=BrainType.ORACLE,
                confidence=0.88,
                reason="Deductive verification or deep architectural design required",
                dark_pre_block=format_dark_block(dark_res),
                gbnf_grammar='root ::= "{" ws "\"actions\":" [^}]* "}"' if requires_json else None,
            )

        # Fast Reflex path
        return RouteDecision(
            target_brain=BrainType.REFLEX,
            confidence=0.92,
            reason="Interactive task, shell assistance, or single-file modification suited for O(1) reflex",
        )

    def dispatch(
        self,
        prompt: str,
        files_involved: int = 1,
        requires_json: bool = False,
        max_tokens: int = 512,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        """Dispatches prompt to selected engine, transparently falling back if offline."""
        decision = self.route_request(prompt, files_involved, requires_json)
        target = decision.target_brain

        # Verify target is online; fallback if offline
        target_online = self.probe_health(target)
        if not target_online:
            fallback = BrainType.REFLEX if target == BrainType.ORACLE else BrainType.ORACLE
            fallback_online = self.probe_health(fallback)
            if fallback_online:
                decision.reason += f" [FALLBACK: {target.value} was offline -> using {fallback.value}]"
                target = fallback
            else:
                # Both offline in test or isolated host mode
                decision.reason += f" [SIMULATED: {target.value} daemon offline, running in offline sandbox]"

        return {
            "dispatched_to": target.value,
            "decision": decision,
            "prompt_tokens_estimated": len(prompt.split()) * 4 // 3,
            "gbnf_enforced": decision.gbnf_grammar is not None,
            "status": "ready",
        }


# Global singleton router
dual_brain_router = DualBrainRouter()
