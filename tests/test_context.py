"""Context packing correctness and real lesson lifecycle tests; no model needed."""
import asyncio
import itertools
import json
from pathlib import Path
import random

from fastmcp import Client, FastMCP
import pytest

from app import memory
from app.context_select import select_context
from app.prefrontal_cortex import select_context as legacy_select_context
from app.memory_context import prepare_context
from app.memory_tools import register_memory_tools


@pytest.mark.parametrize('selector', [select_context, legacy_select_context])
def test_selector_matches_exhaustive_optimum(selector) -> None:
    rng = random.Random(717)
    for _ in range(150):
        count = rng.randrange(1, 9)
        costs = [rng.randrange(1, 30) for _ in range(count)]
        values = [rng.randrange(1, 20) for _ in range(count)]
        budget = rng.randrange(1, 65)
        required = rng.randrange(-1, count)
        if required >= 0 and costs[required] > budget:
            required = -1
        actual = selector(costs, values, budget, required)
        valid = [items for n in range(count + 1) for items in itertools.combinations(range(count), n)
                 if sum(costs[i] for i in items) <= budget and (required < 0 or required in items)]
        optimum = max(sum(values[i] for i in items) for items in valid)
        assert sum(values[i] for i in actual) == optimum
        assert actual == sorted(set(actual))
        assert sum(costs[i] for i in actual) <= budget


@pytest.mark.parametrize('selector', [select_context, legacy_select_context])
def test_packing_beats_prefix_and_preserves_required_warning(selector) -> None:
    assert selector([9, 5, 5], [10, 8, 8], 10) == [1, 2]
    assert selector([9, 5, 5], [10, 8, 8], 10, 0) == [0]
    assert selector([5, 5], [10, 10], 5) == [0]
    assert selector([], [], 0) == []


@pytest.mark.parametrize('costs,values,budget,required', [
    ([1], [], 5, -1), ([0], [1], 5, -1), ([20001], [1], 20000, -1),
    ([1], [0], 5, -1), ([1], [1000001], 5, -1), ([1], [1], -1, -1),
    ([1], [1], 20001, -1), ([1]*65, [1]*65, 10, -1),
    ([1], [1], 5, 1), ([10], [1], 5, 0), ([True], [1], 5, -1),
    ([1], [True], 5, -1), ([1], [1], True, -1), ([1], [1], 5, True),
    ([1.0], [1], 5, -1), ([1], [1.0], 5, -1),
])
@pytest.mark.parametrize('selector', [select_context, legacy_select_context])
def test_selector_rejects_bad_inputs(selector, costs: list[int], values: list[int], budget: int, required: int) -> None:
    with pytest.raises(ValueError):
        selector(costs, values, budget, required)


@pytest.fixture
def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / 'memory.db'
    monkeypatch.setattr(memory, 'DB_PATH', path)
    return path


def store(summary: str, code: int = 0, project: str = 'roms', revision: str = 'v1', expiry: str = '') -> str:
    record = memory.retain_memory(project, summary, 'fixture:source', revision, expires_at=expiry)
    mid = str(record['id'])
    memory.record_memory_verification(project, mid, 'fixture: simulated check', code, 'fixture:result')
    return mid


def test_context_keeps_warning_and_obeys_actual_json_budget(database: Path) -> None:
    warning = store('Timezone conversion failed: preserve the offset', code=1)
    for index in range(8):
        store(f'Timezone fix {index}: ' + 'use UTC ' * 25)
    for budget in (1024, 1500, 3000, 6000, 20000):
        payload = prepare_context('roms', 'timezone', budget)
        result = json.loads(payload)
        assert len(payload) <= budget
        assert result['warning_available'] and result['warning_included']
        assert any(item['id'] == warning and item['role'] == 'warning' for item in result['records'])
        assert all(item['verification']['authority'] == 'caller-supplied' for item in result['records'])
        assert result['backend'] == 'python'


def test_context_scope_revision_corrections_expiry_and_duplicates(database: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(memory, '_now', lambda: '2026-01-01T00:00:00.000000+00:00')
    expired = store('Timezone obsolete', expiry='2026-01-02T00:00:00Z')
    superseded = store('Timezone previous')
    memory.correct_memory('roms', superseded, 'Timezone candidate', 'fixture:new', 'changed')
    retracted = store('Timezone unsupported')
    memory.retract_memory('roms', retracted, 'unsupported')
    store('Timezone private', project='other')
    store('Timezone different version', revision='v2')
    store('Timezone same advice')
    store('Timezone same advice')
    store('Timezone same advice', code=1)
    monkeypatch.setattr(memory, '_now', lambda: '2026-01-03T00:00:00.000000+00:00')
    result = json.loads(prepare_context('roms', 'timezone', revision='v1'))
    assert result['duplicates_removed'] == 1
    assert len(result['records']) == 2
    assert {item['role'] for item in result['records']} == {'lesson', 'warning'}
    assert not {expired, superseded, retracted} & {item['id'] for item in result['records']}


def test_escaping_pool_truncation_and_unfittable_warning(database: Path) -> None:
    store('Timezone warning ' + '\n"\\' * 700, code=1)
    result = json.loads(prepare_context('roms', 'timezone', 1024))
    assert result['warning_available'] and not result['warning_included']
    assert result['omitted'] == 1
    for i in range(22):
        store(f'Timezone fix {i}')
    payload = prepare_context('roms', 'timezone', 20000)
    assert len(payload) <= 20000
    assert json.loads(payload)['pool_truncated'] is True


def test_backend_contract_and_mcp_registration(database: Path) -> None:
    store('Timezone fix')
    with pytest.raises(RuntimeError):
        prepare_context('roms', 'timezone', selector=lambda *args: [99])
    with pytest.raises(ValueError):
        prepare_context('roms', '', max_chars=100000)
    server = FastMCP('context-test')
    register_memory_tools(server)
    async def run() -> None:
        async with Client(server) as client:
            answer = await client.call_tool('memory_prepare_context', {'project_id': 'roms', 'query': 'timezone', 'max_chars': 1024})
            payload = str(answer.content[0].text)
            assert len(payload) <= 1024
            assert json.loads(payload)['records'][0]['summary'] == 'Timezone fix'
    asyncio.run(run())
