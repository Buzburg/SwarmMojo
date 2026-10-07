"""Memory lifecycle regressions. No model, remote service or user database."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest
from fastmcp import Client, FastMCP
from app import memory
from app.memory_tools import register_memory_tools


@pytest.fixture
def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / 'memory.db'
    monkeypatch.setattr(memory, 'DB_PATH', path)
    return path


def candidate(project: str = 'repo-a', **kwargs):
    return memory.retain_memory(project, 'Fix timezone parsing with explicit UTC', 'commit:abc#parser.py', **kwargs)


def verified(project: str = 'repo-a', code: int = 0, **kwargs):
    record = candidate(project, **kwargs)
    return memory.record_memory_verification(project, record['id'], 'pytest tests/test_time.py', code, 'run:17#results')


def test_candidates_require_explicit_evidence(database: Path) -> None:
    record = candidate()
    assert memory.recall_memory('repo-a', 'timezone')['memories'] == []
    assert memory.recall_memory('repo-a', 'timezone', include_candidates=True)['memories'][0]['status'] == 'candidate'
    with pytest.raises(ValueError):
        memory.record_memory_verification('repo-a', record['id'], '', 0, 'run:17')
    with pytest.raises(ValueError):
        memory.record_memory_verification('repo-a', record['id'], 'pytest', 0, '')
    memory.record_memory_verification('repo-a', record['id'], 'pytest', 0, 'run:17')
    recalled = memory.recall_memory('repo-a', 'timezone')['memories'][0]
    assert recalled['recommendation_eligible'] is True
    assert recalled['verification']['evidence_ref'] == 'run:17'
    with pytest.raises(ValueError):
        memory.record_memory_verification('repo-a', record['id'], 'pytest', 0, 'run:17')


def test_failure_is_retained_but_not_a_recommended_fix(database: Path) -> None:
    verified(code=1)
    record = memory.recall_memory('repo-a', 'timezone')['memories'][0]
    assert record['outcome'] == 'failure'
    assert record['recommendation_eligible'] is False


def test_scope_applies_to_reads_and_every_mutation(database: Path) -> None:
    record = candidate()
    mid = record['id']
    assert memory.recall_memory('repo-b', '', include_candidates=True)['memories'] == []
    attempts = [
        lambda: memory.get_memory('repo-b', mid),
        lambda: memory.record_memory_verification('repo-b', mid, 'pytest', 0, 'run:1'),
        lambda: memory.correct_memory('repo-b', mid, 'different', 'source', 'reason'),
        lambda: memory.retract_memory('repo-b', mid, 'reason'),
        lambda: memory.forget_memory('repo-b', mid),
    ]
    for attempt in attempts:
        with pytest.raises(LookupError):
            attempt()
    assert memory.get_memory('repo-a', mid)['status'] == 'candidate'


def test_correction_invalidates_old_results_and_resets_evidence(database: Path) -> None:
    old = verified()
    corrected = memory.correct_memory('repo-a', old['id'], 'Use aware datetime objects', 'commit:def', 'API changed')
    assert memory.get_memory('repo-a', old['id'])['superseded_by'] == corrected['id']
    assert memory.recall_memory('repo-a', '')['memories'] == []
    assert memory.get_memory('repo-a', corrected['id'])['outcome'] == 'unknown'
    assert len(memory.get_memory('repo-a', corrected['id'])['events']) == 1
    memory.record_memory_verification('repo-a', corrected['id'], 'pytest', 0, 'run:18')
    assert [item['id'] for item in memory.recall_memory('repo-a', '')['memories']] == [corrected['id']]


def test_concurrent_corrections_do_not_fork_active_history(database: Path) -> None:
    old = verified()
    def replace(index: int):
        try:
            return memory.correct_memory('repo-a', old['id'], f'Correction {index}', 'commit:new', 'new evidence')
        except ValueError:
            return None
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(replace, [1, 2]))
    assert sum(result is not None for result in results) == 1


def test_expiry_and_revision_filter(database: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(memory, '_now', lambda: '2026-01-01T00:00:00.000000+00:00')
    verified(revision='abc', expires_at='2026-01-02T00:00:00Z')
    assert memory.recall_memory('repo-a', '', revision='def')['memories'] == []
    assert len(memory.recall_memory('repo-a', '', revision='abc')['memories']) == 1
    monkeypatch.setattr(memory, '_now', lambda: '2026-01-03T00:00:00.000000+00:00')
    assert memory.recall_memory('repo-a', '', include_candidates=True)['memories'] == []
    expired = candidate(expires_at='2026-01-02T00:00:00Z')
    with pytest.raises(ValueError):
        memory.record_memory_verification('repo-a', expired['id'], 'pytest', 0, 'run:1')


def test_retraction_and_forgetting_remove_searchable_content(database: Path) -> None:
    old = verified()
    memory.retract_memory('repo-a', old['id'], 'No longer supported')
    assert memory.recall_memory('repo-a', '', include_candidates=True)['memories'] == []
    assert memory.get_memory('repo-a', old['id'])['events'][0]['action'] == 'retracted'
    memory.forget_memory('repo-a', old['id'])
    with pytest.raises(LookupError):
        memory.get_memory('repo-a', old['id'])
    with sqlite3.connect(database) as connection:
        assert connection.execute('SELECT count(*) FROM lesson_search').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM lesson_events').fetchone()[0] == 0


def test_persists_across_process_restart(database: Path) -> None:
    record = verified()
    result = subprocess.run([sys.executable, '-c',
        'import json,sys; from app.memory import get_memory; print(json.dumps(get_memory("repo-a",sys.argv[2],db_path=sys.argv[1])))',
        str(database), record['id']], cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)['recommendation_eligible'] is True


@pytest.mark.parametrize('query', ['" OR *', "'; DROP TABLE lesson_memories; --", '(){}^', '日本語'])
def test_query_is_data_not_fts_or_sql_syntax(database: Path, query: str) -> None:
    record = verified()
    memory.recall_memory('repo-a', query)
    assert memory.get_memory('repo-a', record['id'])['status'] == 'verified'


def test_recall_fetches_verification_evidence_in_one_query(database: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    records = [verified() for _ in range(4)]
    statements: list[str] = []
    real_connect = sqlite3.connect

    def traced_connect(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(memory.sqlite3, 'connect', traced_connect)
    result = memory.recall_memory('repo-a', '', limit=8)

    verification_queries = [
        statement for statement in statements
        if 'select' in statement.lower() and 'lesson_events' in statement.lower()
    ]
    assert len(verification_queries) == 1
    recalled = {record['id']: record for record in result['memories']}
    assert set(recalled) == {record['id'] for record in records}
    assert all(recalled[record['id']]['verification']['evidence_ref'] == 'run:17#results' for record in records)


def test_recall_budget_and_deterministic_bounds(database: Path) -> None:
    for _ in range(3):
        verified()
    result = memory.recall_memory('repo-a', '', limit=1)
    assert len(result['memories']) == 1 and result['truncated'] is True
    result = memory.recall_memory('repo-a', '', max_chars=500)
    assert len(json.dumps(result, ensure_ascii=False)) <= 500
    assert result['truncated'] is True
    one_result = memory.recall_memory('repo-a', '', limit=1)
    one_result_budget = len(json.dumps(one_result, ensure_ascii=False))
    bounded = memory.recall_memory('repo-a', '', max_chars=one_result_budget)
    assert len(bounded['memories']) == 1 and bounded['truncated'] is True
    assert len(json.dumps(bounded, ensure_ascii=False)) == one_result_budget
    with pytest.raises(ValueError):
        memory.recall_memory('repo-a', '', limit=0)
    with pytest.raises(ValueError):
        memory.recall_memory('repo-a', '', max_chars=1000000)


@pytest.mark.parametrize('overrides', [{'project_id': ''}, {'summary': 'x'*4001}, {'source_ref': ''}, {'expires_at': '2026-01-01'}])
def test_invalid_retention_does_not_create_a_record(database: Path, overrides: dict) -> None:
    arguments = {'project_id':'repo-a', 'summary':'Fix', 'source_ref':'commit:1'} | overrides
    with pytest.raises(ValueError):
        memory.retain_memory(**arguments)
    assert memory.recall_memory('repo-a', '', include_candidates=True)['memories'] == []


def test_memory_mcp_lifecycle_and_playbook(database: Path) -> None:
    server = FastMCP('Memory-test')
    register_memory_tools(server)
    async def run():
        async with Client(server) as client:
            tools = await client.list_tools()
            assert len([tool for tool in tools if tool.name.startswith('memory_')]) == 9
            saved = await client.call_tool('memory_retain', {'project_id':'repo-a', 'summary':'Use UTC', 'source_ref':'commit:1'})
            record = json.loads(saved.content[0].text)
            await client.call_tool('memory_record_verification', {'project_id':'repo-a', 'memory_id':record['id'], 'command':'pytest', 'exit_code':0, 'evidence_ref':'run:2'})
            found = await client.call_tool('memory_recall', {'project_id':'repo-a', 'query':'UTC'})
            assert json.loads(found.content[0].text)['memories'][0]['recommendation_eligible'] is True
            resource = await client.read_resource('skills://verified_memory')
            assert 'caller-supplied' in str(resource)
            prompt = await client.get_prompt('verified_memory_sop')
            assert 'Do not invent evidence' in str(prompt)
    asyncio.run(run())


def test_skill_distillation_defaults_to_inactive_drafts(database: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import trajectory_recorder as recorder, tools
    skill_dir = tmp_path / 'skills'
    monkeypatch.setattr(recorder, 'SKILLS_DIR', skill_dir)
    monkeypatch.setattr(tools, 'SKILLS_DIR', skill_dir)
    monkeypatch.setattr(recorder, 'get_trajectory', lambda *a, **kw: {
        'goal':'Fix timezone parsing', 'steps':[], 'success':True, 'final_result':'done',
    })
    result = recorder.distill_trajectory_to_skill('example', 'timezone_fix')
    assert 'Candidate skill' in result and 'not active' in result
    draft = skill_dir / '_candidates' / 'timezone_fix.md'
    assert draft.is_file()
    assert 'review_status: "candidate"' in draft.read_text(encoding='utf-8')
    assert tools.list_skills() == []


def test_evolver_does_not_activate_success_flag_alone(database: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import auto_evolver, trajectory_recorder as recorder
    from app.db import init_database
    init_database(database)
    skill_dir = tmp_path / 'skills'
    monkeypatch.setattr(auto_evolver, 'SKILLS_DIR', skill_dir)
    monkeypatch.setattr(recorder, 'SKILLS_DIR', skill_dir)
    recorder.start_session('draft-only-test', 'Timezone repair process', db_path=database)
    recorder.record_step('draft-only-test', 'edit', {}, 'changed', db_path=database)
    recorder.record_step('draft-only-test', 'chat', {}, 'looks good', db_path=database)
    recorder.finish_session('draft-only-test', True, 'Model response completed', db_path=database)
    result = auto_evolver.scan_and_evolve_skills(db_path=database)
    assert len(result) == 1
    assert not list(skill_dir.glob('*.md'))
    assert list((skill_dir / '_candidates').glob('*.md'))
