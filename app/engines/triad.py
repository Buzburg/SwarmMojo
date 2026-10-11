"""Triad Engine for Swarmojo.

Evaluates coding workflows and agent configurations across three Pareto dimensions:
1. Reliability (verification pass rate)
2. Duration (task completion time)
3. Cost (token and resource expenditure)
Adapted from Buzburg/triad-engine (Apache-2.0).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass
class TriadMetrics:
    workflow_id: str
    reliability: float  # [0.0, 1.0]
    duration_s: float   # Seconds
    cost_tokens: int    # Total tokens consumed
    passed: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TriadEngine:
    """Evaluates and compares candidate agent workflows on Pareto frontiers."""

    def __init__(self, min_reliability: float = 0.85, max_duration_s: float = 120.0):
        self.min_reliability = min_reliability
        self.max_duration_s = max_duration_s
        self.records: List[TriadMetrics] = []

    def record_run(
        self,
        workflow_id: str,
        reliability: float,
        duration_s: float,
        cost_tokens: int,
        passed: bool = True,
    ) -> TriadMetrics:
        metric = TriadMetrics(
            workflow_id=workflow_id,
            reliability=reliability,
            duration_s=duration_s,
            cost_tokens=cost_tokens,
            passed=passed,
        )
        self.records.append(metric)
        return metric

    def filter_viable_workflows(self) -> List[TriadMetrics]:
        """Filters workflows meeting minimal reliability and timing bounds."""
        return [
            m for m in self.records
            if m.reliability >= self.min_reliability and m.duration_s <= self.max_duration_s and m.passed
        ]

    def rank_pareto_front(self) -> List[Dict[str, Any]]:
        """Calculates Pareto-optimal frontier across (reliability, -duration, -cost)."""
        viable = self.filter_viable_workflows()
        if not viable:
            return []

        # Sort by composite utility: 0.5 * reliability + 0.3 * (1 - norm_duration) + 0.2 * (1 - norm_cost)
        max_dur = max((m.duration_s for m in viable), default=1.0) or 1.0
        max_cost = max((m.cost_tokens for m in viable), default=1) or 1

        ranked = []
        for m in viable:
            norm_dur = m.duration_s / max_dur
            norm_cost = m.cost_tokens / max_cost
            score = (0.5 * m.reliability) + (0.3 * (1.0 - norm_dur)) + (0.2 * (1.0 - norm_cost))
            ranked.append({
                "workflow_id": m.workflow_id,
                "score": round(score, 4),
                "metrics": m.to_dict(),
            })

        ranked.sort(key=lambda x: x["score"], reverse=True)
        return ranked

    def pareto_frontier(self) -> List[Dict[str, Any]]:
        front = self.rank_pareto_front()
        return [{"id": item["workflow_id"], "score": item["score"], **item["metrics"]} for item in front]

    def summary(self) -> Dict[str, Any]:
        return {
            "total_runs": len(self.records),
            "viable_runs": len(self.filter_viable_workflows()),
            "best": self.rank_pareto_front()[:1],
        }

