"""Dream Cycle Continual Learning Flywheel for Omarchy OS.

Asynchronously consolidates daytime task outcomes, verified patches, and reflections,
blending them with curated reasoning examples (such as Oxford Feynman SFT) to synthesize
nightly state-tuning datasets for RWKV-7 without human intervention.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.reflection import ContinuousMemoryReflector, TaskOutcome, _connection
from app.nest_soul import default_omarchy_soul


@dataclass
class DreamBatchSummary:
    timestamp: float
    verified_lessons_count: int
    anti_patterns_count: int
    feynman_samples_count: int
    total_training_pairs: int
    output_path: str


class DreamCycleConsolidator:
    """Consolidates verified engineering outcomes into state-tuning SFT batches."""

    def __init__(
        self,
        workspace_dir: Optional[Path | str] = None,
        db_path: Optional[Path | str] = None,
        feynman_dataset_path: Optional[Path | str] = None,
    ):
        base = Path(__file__).resolve().parent.parent
        self.workspace_dir = Path(workspace_dir) if workspace_dir else base
        self.db_path = db_path
        self.output_dir = self.workspace_dir / "data" / "dream"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if feynman_dataset_path is None:
            feynman_dataset_path = Path("D:/Buzburg Files/Random Extra/oxford_feynman_learning_sft.jsonl")
        self.feynman_dataset_path = Path(feynman_dataset_path)

    def _sample_feynman_data(self, max_samples: int = 50) -> List[Dict[str, Any]]:
        """Samples diverse high-quality scientific reasoning examples if available on disk."""
        samples: List[Dict[str, Any]] = []
        if not self.feynman_dataset_path.exists():
            return samples

        try:
            with self.feynman_dataset_path.open("r", encoding="utf-8") as f:
                for idx, line in enumerate(f):
                    if idx >= max_samples:
                        break
                    line_s = line.strip()
                    if not line_s:
                        continue
                    try:
                        record = json.loads(line_s)
                        samples.append(record)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass
        return samples

    def consolidate(self, max_feynman_samples: int = 50) -> DreamBatchSummary:
        """Builds a new state-tuning SFT batch dataset."""
        now = time.time()

        verified_pairs: List[Dict[str, Any]] = []
        anti_patterns: List[Dict[str, Any]] = []

        # 1. Query verified lessons and anti-patterns from SQLite memory store
        try:
            with _connection(self.db_path) as conn:
                rows = conn.execute(
                    "SELECT id, project_id, summary, source_ref, outcome, created_at "
                    "FROM lesson_memories WHERE status = 'verified' "
                    "ORDER BY created_at DESC LIMIT 200"
                ).fetchall()

            for row in rows:
                mem_id, proj_id, summary, source_ref, outcome, created_at = row
                if outcome == "success":
                    verified_pairs.append({
                        "instruction": f"Apply verified Omarchy workflow for {source_ref}.",
                        "input": f"Project: {proj_id}\nSource: {source_ref}",
                        "output": f"VERIFIED RESOLUTION:\n{summary}",
                        "metadata": {
                            "source": "omarchy_reflection_success",
                            "memory_id": mem_id,
                            "created_at": created_at,
                        },
                    })
                else:
                    anti_patterns.append({
                        "instruction": f"Identify and avoid failure anti-pattern for {source_ref}.",
                        "input": f"Project: {proj_id}\nSource: {source_ref}",
                        "output": f"AVOID ANTI-PATTERN:\n{summary}",
                        "metadata": {
                            "source": "omarchy_reflection_failure",
                            "memory_id": mem_id,
                            "created_at": created_at,
                        },
                    })
        except Exception:
            pass

        # 2. Sample from Oxford Feynman dataset if present
        feynman_records = self._sample_feynman_data(max_samples=max_feynman_samples)
        feynman_pairs: List[Dict[str, Any]] = []
        for rec in feynman_records:
            feynman_pairs.append({
                "instruction": rec.get("instruction") or rec.get("prompt") or "Scientific Reasoning Step",
                "input": rec.get("input", ""),
                "output": rec.get("output") or rec.get("response", ""),
                "metadata": {"source": "oxford_feynman_curriculum"},
            })

        # 3. Assemble and export dataset
        all_pairs = verified_pairs + anti_patterns + feynman_pairs

        if not all_pairs:
            all_pairs.append({
                "instruction": "Execute sovereign Omarchy OS architecture check.",
                "input": "Omarchy Kernel Check",
                "output": f"Omarchy OS active with soul archetype {default_omarchy_soul.derive_mbti()}.",
                "metadata": {"source": "baseline_synthetic"},
            })

        batch_filename = f"dream_batch_{int(now)}.jsonl"
        output_file = self.output_dir / batch_filename

        with output_file.open("w", encoding="utf-8") as f:
            for item in all_pairs:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        latest_file = self.output_dir / "dream_batch_latest.jsonl"
        with latest_file.open("w", encoding="utf-8") as f:
            for item in all_pairs:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        return DreamBatchSummary(
            timestamp=now,
            verified_lessons_count=len(verified_pairs),
            anti_patterns_count=len(anti_patterns),
            feynman_samples_count=len(feynman_pairs),
            total_training_pairs=len(all_pairs),
            output_path=str(output_file),
        )


# Global dream cycle singleton
dream_cycle = DreamCycleConsolidator()
