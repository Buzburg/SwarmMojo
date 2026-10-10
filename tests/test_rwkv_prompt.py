"""Preserve message data while expressing RWKV's role and reasoning boundaries."""
import asyncio
import os
from pathlib import Path

import httpx
import pytest
jinja2 = pytest.importorskip("jinja2")
from jinja2 import Environment, StrictUndefined
from scripts.verify_all import wait_for_services

ROOT = Path(__file__).resolve().parents[1]


def template():
    return Environment(undefined=StrictUndefined).from_string((ROOT / 'config/rwkv-user-assistant.jinja').read_text())


def test_chat_prefix_preserves_system_and_selected_text():
    messages = [{'role': 'system', 'content': 'Local rules'},
                {'role': 'user', 'content': 'code:\n\nx = 1\n\n'},
                {'role': 'assistant', 'content': 'Previous answer'},
                {'role': 'user', 'content': 'Next request'}]
    rendered = template().render(messages=messages, add_generation_prompt=True, enable_thinking=False)
    assert rendered == ('Local rules\n\nUser: code:\n\nx = 1\n\n\n\n'
                        'Assistant: Previous answer\n\nUser: Next request\n\nAssistant:')
    assert not rendered.endswith((' ', '\n'))


def test_reasoning_history_has_an_explicit_boundary():
    messages = [{'role': 'assistant', 'content': 'Answer', 'reasoning_content': 'Fixture reasoning'}]
    assert template().render(messages=messages, add_generation_prompt=False) == 'Assistant: <think>Fixture reasoning</think>Answer\n\n'
    assert template().render(messages=[], add_generation_prompt=True, enable_thinking=True) == 'Assistant:'


@pytest.mark.skipif(not os.getenv('ROMS_LIVE_DRAFT'), reason='Explicit installed-model verification required')
def test_installed_native_template_and_direct_answer():
    wait_for_services(['/usr/local/bin/goose', '--status'], ROOT, dict(os.environ))
    settings = dict(line.split('=', 1) for line in Path('/home/rryan/.config/goose/runtime.env').read_text().splitlines() if '=' in line)
    async def verify():
        async with httpx.AsyncClient(timeout=90, trust_env=False) as client:
            headers = {'Authorization': 'Bearer ' + settings['ROMS_UPSTREAM_API_KEY']}
            messages = [{'role': 'system', 'content': 'Be concise.'}, {'role': 'user', 'content': 'What is 7 times 8? Reply with only the number.'}]
            rendered = await client.post('http://127.0.0.1:18080/apply-template', json={'messages': messages}, headers=headers)
            rendered.raise_for_status()
            assert rendered.json()['prompt'] == template().render(messages=messages, add_generation_prompt=True, enable_thinking=False)
            response = await client.post('http://127.0.0.1:8844/v1/chat/completions',
                json={'messages': [messages[-1]], 'max_tokens': 256, 'temperature': 0, 'stream': False},
                headers={'Authorization': 'Bearer ' + settings['ROMS_GATEWAY_API_KEY']})
            response.raise_for_status()
            choice = response.json()['choices'][0]
            assert choice['finish_reason'] == 'stop', choice
            assert choice['message']['content'].strip() == '56', choice
    asyncio.run(verify())
