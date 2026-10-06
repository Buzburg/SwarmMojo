"""Opt-in real 2.9B answer based on an isolated MCP memory fixture."""
import asyncio
import json
import os
from pathlib import Path
import secrets

import pytest

from app import gateway, memory
from test_broker_chat import native_chat
from test_broker_memory import database, contents
from test_gateway_disconnect import serving


@pytest.mark.skipif(not os.getenv('ROMS_LIVE_DRAFT'), reason='Explicit installed-model verification required')
@pytest.mark.parametrize('trial', [1, 2])
def test_actual_model_answers_from_mcp_project_memory(native_chat, database, monkeypatch, trial):
    settings = dict(line.split('=', 1) for line in
                    Path('/home/rryan/.config/goose/runtime.env').read_text().splitlines() if '=' in line)
    for name in ('ROMS_GATEWAY_API_KEY', 'ROMS_UPSTREAM_API_KEY'):
        monkeypatch.setenv(name, settings[name])
    monkeypatch.setattr(gateway, 'ROMS_UPSTREAM_LLM_URL', 'http://127.0.0.1:18080/v1')
    monkeypatch.setattr(gateway, 'hybrid_search', lambda **_: pytest.fail('Unscoped retrieval crossed the project boundary'))
    monkeypatch.setattr(gateway, 'start_session', lambda **_: None)
    monkeypatch.setattr(gateway, 'finish_session', lambda **_: None)
    completions = []
    original_decode = gateway.decode_completed_response
    def decode(value):
        completions.append(value)
        return original_decode(value)
    monkeypatch.setattr(gateway, 'decode_completed_response', decode)
    code = 'ORCHID-' + secrets.token_hex(3)
    row = memory.retain_memory('memory-fixture', 'Timezone fixture deployment code is ' + code,
                               'fixture:deployment', db_path=database[0])
    memory.record_memory_verification('memory-fixture', row['id'], 'fixture: simulated check', 0,
                                     'fixture:receipt', db_path=database[0])
    before = contents(database[0])
    async def check():
        async with serving(gateway.app) as port:
            return await asyncio.to_thread(native_chat, port, settings['ROMS_GATEWAY_API_KEY'],
                'For this timezone fixture, what is the deployment code? Return its literal value from project memory.')
    result = asyncio.run(check())
    (database[0].parent / 'live-chat-completion.json').write_text(json.dumps(
        {'broker': result, 'completions': completions}, ensure_ascii=False, indent=2))
    assert result['ok'], {'broker': result, 'completion': completions}
    assert result['result']['generated'] is True
    assert completions[0]['choices'][0]['finish_reason'] == 'stop', completions
    assert row['id'] in {item['id'] for item in result['result']['memory']['records']}
    assert code.lower() in result['result']['answer'].lower(), completions
    assert contents(database[0]) == before
