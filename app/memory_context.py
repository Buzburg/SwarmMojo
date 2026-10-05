"""Build bounded, source-bearing context while keeping failed attempts visible."""
from collections.abc import Callable
import json
from pathlib import Path
from typing import cast

from app import memory
from app.context_select import select_context

Selector = Callable[[list[int], list[int], int, int], list[int]]


def prepare_context(project_id: str, query: str, max_chars: int = 6000, revision: str = '', *,
                    selector: Selector = select_context, backend: str = 'python',
                    db_path: Path | str | None = None) -> str:
    """Return a bounded JSON string; rank utility is a heuristic, not a truth score."""
    if type(max_chars) is not int or not 1024 <= max_chars <= 20000:
        raise ValueError('max_chars must be between 1024 and 20000')
    if backend not in {'python', 'mojo'}:
        raise ValueError('Unknown context selector backend')
    pool = memory.recall_memory(project_id, query, limit=20, max_chars=20000, revision=revision, db_path=db_path)
    records = cast(list[dict[str, object]], pool['memories'])
    unique: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    utilities: list[int] = []
    for rank, record in enumerate(records):
        # Deduplicate identical advice, but preserve differing outcomes and revisions.
        key = (str(record['summary']), str(record['outcome']), str(record['revision']))
        if key in seen:
            continue
        seen.add(key)
        compact = {field: record[field] for field in (
            'id', 'summary', 'source_ref', 'revision', 'expires_at', 'outcome', 'verification',
        )}
        compact['role'] = 'warning' if record['outcome'] == 'failure' else 'lesson'
        compact['retrieval_rank'] = rank + 1
        unique.append(compact)
        utilities.append(10000 // (rank + 1))
    result: dict[str, object] = {
        'project_id': project_id.strip(), 'backend': backend, 'selection': 'rank-utility-knapsack-v1',
        'evidence_authority': 'caller-supplied', 'pool_truncated': bool(pool['truncated']),
        'candidates': len(records), 'duplicates_removed': len(records) - len(unique),
        'omitted': len(unique), 'warning_available': any(item['role'] == 'warning' for item in unique),
        'warning_included': False, 'records': [],
    }
    def encode(value: object) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    # Empty-array envelope is an upper bound: omitted shrinks and false -> true is shorter.
    budget = max_chars - len(encode(result))
    costs = [len(encode(item)) + 1 for item in unique]
    # Reserve the highest-ranked warning that fits; never silently treat failures as repairs.
    required = next((i for i, item in enumerate(unique) if item['role'] == 'warning' and costs[i] <= budget), -1)
    chosen = selector(costs, utilities, max(0, budget), required)
    if (len(set(chosen)) != len(chosen) or any(type(i) is not int or not 0 <= i < len(unique) for i in chosen)
            or sum(costs[i] for i in chosen) > budget or (required >= 0 and required not in chosen)):
        raise RuntimeError('Context selector violated its budget or selection contract')
    result['records'] = [unique[i] for i in chosen]
    result['omitted'] = len(unique) - len(chosen)
    result['warning_included'] = any(unique[i]['role'] == 'warning' for i in chosen)
    payload = encode(result)
    if len(payload) > max_chars:
        raise RuntimeError('Context envelope exceeded its character budget')
    return payload
