"""Exercise correction persistence through both supported public entry points."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys

from fastmcp import Client, FastMCP

from app import memory
from app.memory_tools import register_memory_tools

ROOT = Path(__file__).resolve().parents[1]


def test_cli_retry_from_another_directory_and_invalid_input(tmp_path):
    database = tmp_path / 'lessons.db'
    arguments = [sys.executable, '-B', str(ROOT / 'swarmmojo.py'), 'correction',
                 '--project', 'demo', '--revision', 'abc123', '--failure', 'Tax rounded twice',
                 '--correction', 'Round once', '--check', 'Assert exact cents',
                 '--evidence', 'fixture:receipt', 'a' * 64, '--db', str(database)]
    environment = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1',
                   'SWARMMOJO_STATE_DIR': str(tmp_path / 'unused-state'),
                   'SWARMMOJO_DATA_DIR': str(tmp_path / 'unused-data')}
    for repeat in (False, True):
        result = subprocess.run(arguments, cwd=tmp_path, env=environment,
                                capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        report = json.loads(result.stdout)
        assert report['deduplicated'] is repeat
        assert report['memory']['status'] == 'candidate'
        assert not report['execution_allowed'] and report['regression_status'] == 'not-run'
    assert memory.recall_memory('demo', '', db_path=database)['memories'] == []
    arguments[-3] = 'invalid-hash'
    result = subprocess.run(arguments, cwd=tmp_path, env=environment,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 2 and not result.stdout
    assert json.loads(result.stderr)['execution_allowed'] is False
    assert not (tmp_path / 'unused-state').exists()
    assert not (tmp_path / 'unused-data').exists()


def test_mcp_proposal_uses_configured_database_and_existing_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, 'DB_PATH', tmp_path / 'lessons.db')
    server = FastMCP('correction-boundary')
    register_memory_tools(server)
    payload = dict(project_id='demo', revision='abc123', failure='Wrong total',
                   correction='Round once', proposed_check='Assert cents',
                   evidence=[{'ref': 'fixture:receipt', 'sha256': 'b' * 64}])

    async def call():
        async with Client(server) as client:
            tool = next(t for t in await client.list_tools() if t.name == 'memory_propose_correction')
            schema = getattr(tool, 'input_schema', None)
            if schema is None:
                schema = tool.inputSchema
            assert 'db_path' not in schema['properties']
            result = await client.call_tool('memory_propose_correction', payload)
            report = json.loads(result.content[0].text)
            mid = report['memory']['id']
            assert not report['evidence_authenticated']
            await client.call_tool('memory_retract', dict(project_id='demo', memory_id=mid, reason='Not applicable'))
            repeated = await client.call_tool('memory_propose_correction', payload)
            assert json.loads(repeated.content[0].text)['memory']['status'] == 'retracted'
            result = await client.call_tool('memory_get', dict(project_id='demo', memory_id=mid))
            assert any(event['action'] == 'correction_proposal'
                       for event in json.loads(result.content[0].text)['events'])
    asyncio.run(call())
