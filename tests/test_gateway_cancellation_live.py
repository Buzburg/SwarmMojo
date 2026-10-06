"""Confirm a disconnected installed chat releases the actual native model slot."""
import asyncio
import json
import os
from pathlib import Path
import time

import httpx
import pytest

from scripts.verify_all import wait_for_services

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not os.getenv('ROMS_LIVE_DRAFT'), reason='Explicit installed-model verification required')
def test_disconnect_releases_installed_model_slot():
    wait_for_services(['/usr/local/bin/goose', '--status'], ROOT, dict(os.environ))
    settings = dict(line.split('=', 1) for line in Path('/home/rryan/.config/goose/runtime.env').read_text().splitlines() if '=' in line)

    async def check():
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            async def slots():
                response = await client.get('http://127.0.0.1:18080/slots',
                    headers={'Authorization': 'Bearer ' + settings['ROMS_UPSTREAM_API_KEY']})
                response.raise_for_status()
                return response.json()
            initial = await slots()
            assert len(initial) == 1 and not initial[0]['is_processing'], 'Run the live cancellation check with an idle model'
            reader, writer = await asyncio.open_connection('127.0.0.1', 8844)
            payload = json.dumps({'messages': [{'role': 'user', 'content': 'Count upward from one, one number per line.'}],
                                  'max_tokens': 1024, 'ignore_eos': True, 'stream': False, 'temperature': 0}).encode()
            headers = ('POST /v1/chat/completions HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\n'
                       'Authorization: Bearer ' + settings['ROMS_GATEWAY_API_KEY'] + '\r\nContent-Length: ' + str(len(payload)) + '\r\n\r\n')
            writer.write(headers.encode() + payload)
            await writer.drain()
            try:
                deadline = time.monotonic() + 15
                while not (await slots())[0]['is_processing']:
                    assert time.monotonic() < deadline, 'The test generation never occupied the model slot'
                    await asyncio.sleep(0.1)
                # Prove token generation, rather than only queued work or prefill.
                deadline = time.monotonic() + 45
                while True:
                    slot = (await slots())[0]
                    assert slot['is_processing'], 'The completion ended before the disconnect test'
                    if slot['next_token'][0]['n_decoded'] > 0:
                        break
                    assert time.monotonic() < deadline, 'The test prompt never reached token generation'
                    await asyncio.sleep(0.1)
            finally:
                writer.close()
                await writer.wait_closed()
            deadline = time.monotonic() + 5
            while (await slots())[0]['is_processing']:
                assert time.monotonic() < deadline, 'The disconnected generation retained the native model slot'
                await asyncio.sleep(0.1)
            assert time.monotonic() <= deadline, 'Native slot release exceeded the five-second cancellation bound'
    asyncio.run(check())
