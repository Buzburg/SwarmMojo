"""Deterministic parity checks and same-algorithm timings including native conversion."""
from collections.abc import Callable
import json
import platform
from pathlib import Path
import random
import statistics
import tempfile
import time

from app import memory
from app.context_select import select_context
from app.memory_context import prepare_context

Selector = Callable[[list[int], list[int], int, int], list[int]]


def median_ms(fn: Callable[[], object]) -> float:
    samples = []
    for _ in range(9):
        start = time.perf_counter_ns()
        fn()
        samples.append((time.perf_counter_ns() - start) / 1e6)
    return statistics.median(samples)


def run(native: Selector) -> None:
    rng = random.Random(20260927)
    for _ in range(400):
        count = rng.randrange(0, 21)
        costs = [rng.randrange(1, 900) for _ in range(count)]
        values = [rng.randrange(1, 10000) for _ in range(count)]
        budget = rng.randrange(0, 3000)
        required = rng.randrange(-1, count) if count else -1
        if required >= 0 and costs[required] > budget:
            required = -1
        assert native(costs, values, budget, required) == select_context(costs, values, budget, required)
    for costs, values, budget, required in [([0], [1], 20, -1), ([1], [], 20, -1),
            ([1]*65, [1]*65, 20, -1), ([1], [1], 20001, -1), ([10], [1], 5, 0)]:
        try:
            native(costs, values, budget, required)
        except Exception:
            pass
        else:
            raise AssertionError('Native invalid input accepted')
    cases = []
    for label, costs, budget in [('all-fit-5', [400]*5, 6000),
            ('tight-20', [400 + i*41 for i in range(20)], 2000),
            ('standard-20', [500 + i*73 for i in range(20)], 6000),
            ('large-20', [1400 + i*79 for i in range(20)], 18000)]:
        values = [10000 // (i + 1) for i in range(len(costs))]
        required = len(costs) - 1
        expected = select_context(costs, values, budget, required)
        assert native(costs, values, budget, required) == expected
        py_ms = median_ms(lambda: select_context(costs, values, budget, required))
        native_ms = median_ms(lambda: native(costs, values, budget, required))
        cases.append({'case': label, 'records': len(costs), 'budget_chars': budget,
                      'python_ms': round(py_ms, 6), 'mojo_ms': round(native_ms, 6),
                      'ratio_python_over_mojo': round(py_ms/native_ms, 2), 'selected': len(expected)})
    with tempfile.TemporaryDirectory(prefix='roms-context-bench-') as temporary:
        database = Path(temporary) / 'fixture.db'
        for i in range(20):
            lesson = memory.retain_memory('bench', f'Timezone case {i}: ' + 'preserve UTC ' * 12,
                                          'fixture:source', db_path=database)
            memory.record_memory_verification('bench', str(lesson['id']), 'fixture: simulated check',
                                              1 if i == 0 else 0, 'fixture:result', db_path=database)
        def python_context() -> str:
            return prepare_context('bench', 'timezone', db_path=database)
        def native_context() -> str:
            return prepare_context('bench', 'timezone', selector=native, backend='mojo', db_path=database)
        reference = json.loads(python_context())
        actual = json.loads(native_context())
        assert reference['records'] == actual['records']
        assert actual['warning_included'] and actual['omitted'] > 0
        python_total = median_ms(python_context)
        native_total = median_ms(native_context)
    print(json.dumps({'python': platform.python_version(), 'machine': platform.machine(),
                      'parity_cases': 400, 'invalid_inputs_rejected': 5, 'samples': 9,
                      'scope': 'Selection only; native timings include Python conversion. No database or model time.',
                      'cases': cases,
                      'context_with_sqlite_and_json': {'fixture_records': 20, 'budget_chars': 6000,
                          'python_ms': round(python_total, 6), 'mojo_ms': round(native_total, 6),
                          'ratio_python_over_mojo': round(python_total/native_total, 2),
                          'scope': 'Warm local fixture; includes SQLite recall, packing and JSON. Excludes MCP/model.'}},
                     indent=2), flush=True)
