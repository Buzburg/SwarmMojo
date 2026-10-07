"""NESTstack Soul Synthesizer — Pure Standard Library Implementation.

Ported from MoI3.0 / NSagent nest_soul.py.
Computes 4-axis personality vectors mapped to MBTI quadrants and affective states:
  axis_weights[0]: E/I (energy: extraversion / introversion)
  axis_weights[1]: S/N (perception: sensing / intuition)
  axis_weights[2]: T/F (evaluation: thinking / feeling)
  axis_weights[3]: J/P (execution: judging / perceiving)

Zero external dependencies (pure math, no PyTorch).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

AXIS_LABELS: Tuple[str, ...] = ("energy", "perception", "evaluation", "execution")
AXIS_LETTER_PAIRS: Tuple[Tuple[str, str], ...] = (
    ("E", "I"),
    ("S", "N"),
    ("T", "F"),
    ("J", "P"),
)
_AXIS_THRESHOLD: float = 0.0

TRAIT_MAPPINGS: Dict[str, str] = {
    "E": "Assertive, proactive, and expressive. Prefers driving the conversation.",
    "I": "Reflective, analytical, and concise. Prefers listening and parsing details.",
    "S": "Grounded in technical constraints, rules, and raw execution details.",
    "N": "Abstract, pattern-focused, and looking for multi-turn structural synergies.",
    "T": "Prioritizes rigorous logic, algorithmic optimization, and strategic efficiency.",
    "F": "Adaptive, contextual, aligning output cadence to user engagement signals.",
    "J": "Highly structured, deterministic, adhering strictly to plan schemas.",
    "P": "Exploratory, emergent, comfortable adjusting mid-sequence to new states.",
}

EMOTION_DIMENSIONS: Dict[str, Dict[str, Tuple[float, float, Tuple[str, ...]]]] = {
    "confidence": {
        "high": (0.7, 1.0, ("confident", "assertive", "direct")),
        "medium": (0.4, 0.7, ("neutral", "analytical", "measured")),
        "low": (0.0, 0.4, ("uncertain", "exploratory", "cautious")),
    },
    "complexity": {
        "high": (0.7, 1.0, ("challenged", "focused", "intense")),
        "medium": (0.4, 0.7, ("engaged", "methodical", "steady")),
        "low": (0.0, 0.4, ("relaxed", "routine", "simple")),
    },
    "progress": {
        "high": (0.7, 1.0, ("momentum", "advancing", "productive")),
        "medium": (0.4, 0.7, ("steady", "progressing", "building")),
        "low": (0.0, 0.4, ("stalled", "searching", "lost")),
    },
    "engagement": {
        "high": (0.7, 1.0, ("passionate", "invested", "energized")),
        "medium": (0.4, 0.7, ("attentive", "responsive", "present")),
        "low": (0.0, 0.4, ("detached", "passive", "indifferent")),
    },
}
EMOTION_AXIS_ORDER: Tuple[str, ...] = ("confidence", "complexity", "progress", "engagement")


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def tag_emotions(axis_weights: Sequence[float]) -> List[str]:
    weights_list: List[float] = [w for w in axis_weights[:4]]
    while len(weights_list) < 4:
        weights_list.append(0.0)
    normalised: List[float] = [_sigmoid(w) for w in weights_list]

    tags: List[str] = []
    for idx, dim_name in enumerate(EMOTION_AXIS_ORDER):
        score = normalised[idx]
        dims = EMOTION_DIMENSIONS.get(dim_name, {})
        for level, (low, high, level_tags) in dims.items():
            if low <= score <= high:
                tags.append(level_tags[0])
                break
    return tags


def compute_gut_feeling(axis_weights: Sequence[float], turn_count: int = 0) -> float:
    weights = list(axis_weights[:4]) or [0.0]
    magnitude_sq = sum(w * w for w in weights)
    magnitude = math.sqrt(magnitude_sq)
    base = min(1.0, magnitude / 2.0)

    progress_boost = min(0.15, max(0, turn_count) * 0.01)

    mean = sum(weights) / len(weights)
    variance = sum((w - mean) ** 2 for w in weights) / len(weights)
    stability_boost = max(0.0, 0.1 - variance * 0.05)

    gut = base + progress_boost + stability_boost
    return max(0.0, min(1.0, gut))


def _mbti_letter(axis_index: int, weight: float) -> str:
    pos_letter, neg_letter = AXIS_LETTER_PAIRS[axis_index]
    return pos_letter if weight > _AXIS_THRESHOLD else neg_letter


@dataclass
class PersonalityProfile:
    axis_weights: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    turn_count: int = 0
    label: str = ""

    def derive_mbti(self) -> str:
        return "".join(_mbti_letter(i, w) for i, w in enumerate(self.axis_weights))

    def trait_lines(self) -> List[str]:
        mbti = self.derive_mbti()
        return [TRAIT_MAPPINGS[letter] for letter in mbti]

    def emotion_tags(self) -> List[str]:
        return tag_emotions(self.axis_weights)

    def gut_feeling(self) -> float:
        return compute_gut_feeling(self.axis_weights, self.turn_count)

    def format_prompt_block(self) -> str:
        mbti = self.derive_mbti()
        emotions = ", ".join(self.emotion_tags())
        gut = self.gut_feeling()
        traits = " ".join(self.trait_lines())
        return (
            f"[SOUL:archetype={mbti} | gut={gut:.2f} | emotions={emotions}]\n"
            f"Persona traits: {traits}\n"
            f"[/SOUL]"
        )

    def snapshot_dict(self) -> Dict[str, Any]:
        return {
            "axis_weights": [float(w) for w in self.axis_weights],
            "turn_count": int(self.turn_count),
            "label": self.label,
            "mbti": self.derive_mbti(),
            "gut_feeling": self.gut_feeling(),
        }

    @classmethod
    def from_snapshot(cls, data: Any) -> "PersonalityProfile":
        if not isinstance(data, dict):
            return cls()
        raw_weights = data.get("axis_weights", [0.0, 0.0, 0.0, 0.0])
        weights = [float(w) for w in raw_weights[:4]]
        while len(weights) < 4:
            weights.append(0.0)
        return cls(
            axis_weights=(weights[0], weights[1], weights[2], weights[3]),
            turn_count=int(data.get("turn_count", 0)),
            label=str(data.get("label", "")),
        )


# Default Omarchy OS Sovereign Persona (INTP / Analytical Architect)
default_omarchy_soul = PersonalityProfile(
    axis_weights=(-0.5, -0.6, 0.8, -0.2),  # I, N, T, P
    turn_count=1,
    label="Omarchy_Sovereign_Architect",
)
