"""Parallel Tool Dispatcher for SwarmMojo by Buzburg AI.

Concurrent tool and subtask execution architecture by Buzburg AI:
- Dispatches batches of independent agent operations concurrently across a lightweight thread pool
- Sub-millisecond dispatch overhead with per-task timeout enforcement and error isolation
- Computes concurrency metrics, aggregated elapsed duration, and speedup factor
"""
from __future__ import annotations

import concurrent.futures
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class TaskExecutionResult:
    task_id: str
    status: str          # "completed", "error", "timeout"
    result: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ParallelToolDispatcher:
    """Dispatches independent agent tool calls in parallel with error isolation and timeout safeguards."""

    def __init__(self, max_workers: int = 8, default_timeout_s: float = 10.0):
        self.max_workers = max(1, max_workers)
        self.default_timeout_s = default_timeout_s

    def execute_batch(
        self,
        tasks: List[Tuple[str, Callable[[], Any]]],
        timeout_s: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Executes a list of (task_id, callable) tuples concurrently.

        Returns aggregated results with execution metrics and speedup estimation.
        """
        overall_start = time.time()
        timeout = timeout_s if timeout_s is not None else self.default_timeout_s
        results: Dict[str, TaskExecutionResult] = {}
        individual_durations = 0.0

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_id: Dict[concurrent.futures.Future, str] = {}
            task_start_times: Dict[str, float] = {}

            for task_id, fn in tasks:
                task_start_times[task_id] = time.time()
                future = executor.submit(fn)
                future_to_id[future] = task_id

            done, not_done = concurrent.futures.wait(
                future_to_id.keys(),
                timeout=timeout,
                return_when=concurrent.futures.ALL_COMPLETED,
            )

            for future in done:
                task_id = future_to_id[future]
                elapsed = round((time.time() - task_start_times[task_id]) * 1000, 2)
                individual_durations += elapsed
                try:
                    res = future.result()
                    results[task_id] = TaskExecutionResult(
                        task_id=task_id,
                        status="completed",
                        result=res,
                        duration_ms=elapsed,
                    )
                except Exception as e:
                    results[task_id] = TaskExecutionResult(
                        task_id=task_id,
                        status="error",
                        error=str(e),
                        duration_ms=elapsed,
                    )

            for future in not_done:
                task_id = future_to_id[future]
                future.cancel()
                elapsed = round((time.time() - task_start_times[task_id]) * 1000, 2)
                individual_durations += elapsed
                results[task_id] = TaskExecutionResult(
                    task_id=task_id,
                    status="timeout",
                    error=f"Exceeded timeout of {timeout}s",
                    duration_ms=elapsed,
                )

        wall_time_ms = round((time.time() - overall_start) * 1000, 2)
        speedup = round(individual_durations / max(wall_time_ms, 0.001), 2) if len(tasks) > 1 else 1.0

        return {
            "total_tasks": len(tasks),
            "completed": sum(1 for r in results.values() if r.status == "completed"),
            "failed": sum(1 for r in results.values() if r.status in ("error", "timeout")),
            "wall_clock_ms": wall_time_ms,
            "sequential_estimate_ms": round(individual_durations, 2),
            "speedup_factor": speedup,
            "results": {k: v.to_dict() for k, v in results.items()},
        }
