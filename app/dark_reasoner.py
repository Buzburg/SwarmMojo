"""DARK — Deductive / Abductive Reasoning Knowledge bridge.

Lightweight, template-based pre/post-reasoning hook ported from MoI3.0 / NSagent.
Pure stdlib (`re`, `typing`). No torch, no neural networks, zero runtime overhead.
Enforces deterministic reasoning gates outside the LLM:
- Deductive templates: Identity, Capability, Conditional ("if... then"), Classification ("Is X a Y?")
- Abductive templates: Causal ("Why did X occur?"), Observation ("I noticed that X")
- Formats explicit [DARK:mode | conf] reasoning blocks.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, List, Optional, Tuple

# Built-in deductive templates
_DEDUCTIVE_TEMPLATES: List[Tuple[re.Pattern, str, str]] = [
    (
        re.compile(r"(?i)^(who|what)\s+(are|is)\s+(?P<subject>.+?)\s*\??$"),
        "identity",
        "Based on known premises, {subject} is defined as: {premise}.",
    ),
    (
        re.compile(
            r"(?i)^(can|could|are\s+you\s+able\s+to|do\s+you)\s+(?:you\s+)?(?P<capability>.+?)\s*\??$"
        ),
        "capability",
        "Deductive conclusion: the capability '{capability}' is {verdict} based on known premises.",
    ),
    (
        re.compile(r"(?i)^if\s+(?P<antecedent>.+?),?\s+then\s+(?P<consequent>.+)$"),
        "conditional",
        "Given that '{antecedent}' holds, it follows that '{consequent}'.",
    ),
    (
        re.compile(r"(?i)^is\s+(?P<subject>.+?)\s+(?:a|an)\s+(?P<category>.+?)\s*\??$"),
        "classification",
        "Deductive check: {subject} {verdict} a member of category '{category}' per known premises.",
    ),
]

# Built-in abductive templates
_ABDUCTIVE_TEMPLATES: List[Tuple[re.Pattern, str, str]] = [
    (
        re.compile(r"(?i)^why\s+did\s+(?P<event>.+?)\s*(happen|occur)?\s*\??$"),
        "causal",
        "Best abductive hypothesis for '{event}': {hypothesis}.",
    ),
    (
        re.compile(r"(?i)^what\s+(caused|led\s+to|explains?)\s+(?P<event>.+?)\s*\??$"),
        "causal",
        "Likely cause of '{event}': {hypothesis}.",
    ),
    (
        re.compile(r"(?i)^how\s+come\s+(?P<event>.+?)\s*\??$"),
        "causal",
        "Abductive explanation for '{event}': {hypothesis}.",
    ),
    (
        re.compile(r"(?i)(?:I\s+)?(?:observed?|noticed?|saw|found)\s+(?:that\s+)?(?P<event>.+)"),
        "observation",
        "Given the observation of '{event}', the most consistent hypothesis is: {hypothesis}.",
    ),
]

_DEDUCTIVE_SIGNALS = re.compile(
    r"(?i)\b(who|what|is|are|can|could|do you|if .* then|define|classify)\b"
)
_ABDUCTIVE_SIGNALS = re.compile(
    r"(?i)\b(why|cause|explain|how come|observed|noticed|because|reason)\b"
)

_STOP = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been",
    "do", "does", "did", "can", "could", "will", "would", "should",
    "i", "you", "he", "she", "it", "we", "they", "my", "your",
    "to", "of", "in", "on", "at", "for", "with", "from", "by",
    "and", "or", "but", "not", "if", "then", "that", "this",
    "what", "who", "why", "how", "when", "where", "which",
})


def _extract_keywords(text: str) -> List[str]:
    tokens = re.split(r"[^a-zA-Z0-9']+", text.lower())
    return [t for t in tokens if t and t not in _STOP and len(t) > 1]


def _best_match(items: List[str], keywords: List[str]) -> Optional[str]:
    if not items:
        return None
    kws = [k for k in (kw.lower() for kw in keywords) if len(k) > 2]
    if not kws:
        return items[0]
    scored: List[Tuple[int, str]] = []
    for item in items:
        item_l = item.lower()
        score = sum(1 for kw in kws if kw in item_l)
        scored.append((score, item))
    scored.sort(key=lambda t: (t[0], -len(t[1])), reverse=True)
    return scored[0][1] if scored[0][0] > 0 else items[0]


def _confidence_for(matched: bool, premise_overlap: bool) -> float:
    if matched and premise_overlap:
        return 0.85
    if matched:
        return 0.65
    if premise_overlap:
        return 0.50
    return 0.30


class DARKReasoningBridge:
    """DARK — Deductive / Abductive Reasoning Knowledge bridge."""

    def __init__(
        self,
        extra_premises: Optional[List[str]] = None,
        extra_rules: Optional[List[str]] = None,
    ) -> None:
        self._premises: List[str] = list(extra_premises or [])
        self._rules: List[str] = list(extra_rules or [])

    def add_premise(self, premise: str) -> None:
        if premise:
            self._premises.append(premise)

    def add_rule(self, rule: str) -> None:
        if rule:
            self._rules.append(rule)

    def add_recall(self, hits: Iterable[Any]) -> int:
        added = 0
        for hit in reversed(list(hits)):
            text = getattr(hit, "text", None)
            if text is None and isinstance(hit, str):
                text = hit
            if text:
                self._premises.insert(0, text)
                added += 1
        return added

    @property
    def premise_count(self) -> int:
        return len(self._premises)

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    def deductive_step(self, premises: List[str], query: str) -> str:
        query = query.strip()
        keywords = _extract_keywords(query)
        best_premise = _best_match(premises, keywords)

        for pattern, tpl_key, tpl_text in _DEDUCTIVE_TEMPLATES:
            m = pattern.match(query)
            if m is None:
                continue
            fill: dict[str, str] = {**m.groupdict()}
            fill["premise"] = best_premise or "(no matching premise)"

            if tpl_key == "capability":
                cap = fill.get("capability", "").lower()
                supported = any(cap in p.lower() for p in premises)
                fill["verdict"] = "SUPPORTED" if supported else "NOT confirmed"

            if tpl_key == "classification":
                subj = fill.get("subject", "").lower()
                cat = fill.get("category", "").lower()
                member = any(subj in p.lower() and cat in p.lower() for p in premises)
                fill["verdict"] = "IS" if member else "is NOT confirmed as"

            return tpl_text.format(**fill)

        if best_premise:
            return f"From the given premises, the most relevant conclusion is: {best_premise}"
        return "No deductive conclusion could be drawn from the provided premises."

    def abductive_step(self, observation: str, known_rules: List[str]) -> str:
        observation = observation.strip()
        keywords = _extract_keywords(observation)
        best_rule = _best_match(known_rules, keywords)

        for pattern, _tpl_key, tpl_text in _ABDUCTIVE_TEMPLATES:
            m = pattern.match(observation) or pattern.search(observation)
            if m is None:
                continue
            fill: dict[str, str] = {**m.groupdict()}
            fill["hypothesis"] = best_rule or "insufficient rules to hypothesise"
            return tpl_text.format(**fill)

        if best_rule:
            return f"Given the observation '{observation}', the best available hypothesis is: {best_rule}"
        return f"No abductive hypothesis could be formed for: '{observation}'."

    def reason(self, text: str, mode: str = "auto") -> dict[str, Any]:
        text = text.strip()
        chain: List[str] = []

        if mode == "auto":
            d_score = len(_DEDUCTIVE_SIGNALS.findall(text))
            a_score = len(_ABDUCTIVE_SIGNALS.findall(text))
            chain.append(f"Auto-detect scores -- deductive: {d_score}, abductive: {a_score}")
            mode = "abductive" if a_score > d_score else "deductive"
            chain.append(f"Selected mode: {mode}")
        else:
            mode_norm = mode.lower()
            mode = mode_norm if mode_norm in ("deductive", "abductive") else "deductive"
            chain.append(f"Mode forced: {mode}")

        keywords = _extract_keywords(text)
        premises = self._premises
        rules = self._rules

        if mode == "deductive":
            conclusion = self.deductive_step(premises, text)
            chain.append(f"Premises consulted: {len(premises)}")
            chain.append(f"Conclusion: {conclusion}")
            matched = any(p.match(text) is not None for p, _, _ in _DEDUCTIVE_TEMPLATES)
            premise_hit = _best_match(premises, keywords) is not None and len(premises) > 0
        else:
            conclusion = self.abductive_step(text, rules)
            chain.append(f"Rules consulted: {len(rules)}")
            chain.append(f"Hypothesis: {conclusion}")
            matched = any((p.match(text) or p.search(text)) is not None for p, _, _ in _ABDUCTIVE_TEMPLATES)
            premise_hit = _best_match(rules, keywords) is not None and len(rules) > 0

        confidence = _confidence_for(matched, premise_hit)
        chain.append(f"Confidence: {confidence:.2f}")

        return {
            "mode": mode,
            "conclusion": conclusion,
            "confidence": confidence,
            "chain": chain,
        }


def format_dark_block(result: dict[str, Any]) -> str:
    """Render a reasoning result dict as a prompt-splice block."""
    mode = result.get("mode", "unknown")
    conclusion = result.get("conclusion", "")
    confidence = result.get("confidence", 0.0)
    chain = result.get("chain", [])

    chain_str = " -> ".join(chain) if chain else "(empty)"
    lines = [
        f"[DARK:{mode} | conf={confidence:.2f}]",
        f"Conclusion: {conclusion}",
        f"Chain: {chain_str}",
        "[/DARK]",
    ]
    return "\n".join(lines)


# Singleton instance
dark_bridge = DARKReasoningBridge()
