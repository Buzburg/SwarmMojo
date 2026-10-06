"""Local schema-constrained OS proposals are authenticated and never execute."""
import asyncio
import json

import httpx
import pytest
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.routing import Route
from starlette.testclient import TestClient

from app import os_model
from app.gateway import local_auth

PAYLOAD = {'instruction': 'Open the hardware viewer',
           'apps': [{'id': 'lstopo.desktop', 'name': 'Hardware Locality'}]}


@pytest.fixture
def native(monkeypatch):
    result = {'content': json.dumps({'action': 'launch_app', 'app_id': 'lstopo.desktop'}),
              'stop_type': 'eos', 'truncated': False}
    state = {'calls': [], 'tokens': [1] * 100, 'result': result}
    def handle(request):
        assert request.url.host == '127.0.0.1'
        assert request.headers['authorization'] == 'Bearer fixture-upstream-key'
        body = json.loads(request.content)
        state['calls'].append((request.url.path, body))
        if request.url.path == '/apply-template':
            return httpx.Response(200, json={'prompt': 'User: fixture\n\nAssistant:'})
        if request.url.path == '/tokenize':
            return httpx.Response(200, json={'tokens': state['tokens']})
        assert request.url.path == '/completion'
        return httpx.Response(200, json=state['result'])
    original_client = httpx.AsyncClient
    def client(**kwargs):
        assert kwargs['trust_env'] is False
        return original_client(transport=httpx.MockTransport(handle), **kwargs)
    monkeypatch.setattr(os_model.httpx, 'AsyncClient', client)
    monkeypatch.setenv('ROMS_GATEWAY_API_KEY', 'fixture-gateway-key')
    monkeypatch.setenv('ROMS_UPSTREAM_API_KEY', 'fixture-upstream-key')
    monkeypatch.setattr(os_model, 'ROMS_UPSTREAM_LLM_URL', 'http://127.0.0.1:18080/v1')
    return state


@pytest.fixture
def client(native):
    app = Starlette(routes=[Route('/plan', os_model.plan_completion, methods=['POST'])])
    app.add_middleware(BaseHTTPMiddleware, dispatch=local_auth)
    with TestClient(app, headers={'Authorization': 'Bearer fixture-gateway-key'}) as client:
        yield client


def test_authentication_is_required(client, native, monkeypatch):
    assert client.post('/plan', json=PAYLOAD, headers={'Authorization': 'wrong'}).status_code == 401
    monkeypatch.delenv('ROMS_GATEWAY_API_KEY')
    assert client.post('/plan', json=PAYLOAD).status_code == 503
    assert native['calls'] == []


@pytest.mark.parametrize('payload', [[], {}, dict(PAYLOAD, execute=True),
    dict(PAYLOAD, instruction=' '), dict(PAYLOAD, instruction='é' * 513),
    dict(PAYLOAD, instruction='x\x00'), dict(PAYLOAD, apps={}),
    dict(PAYLOAD, apps=PAYLOAD['apps'] * 2),
    dict(PAYLOAD, apps=[{'id': f'app{i}.desktop', 'name': 'App'} for i in range(33)]),
    dict(PAYLOAD, apps=[{'id': '../lstopo.desktop', 'name': 'App'}]),
    dict(PAYLOAD, apps=[{'id': 'é.desktop', 'name': 'App'}]),
    dict(PAYLOAD, apps=[{'id': 'a' * 129 + '.desktop', 'name': 'App'}]),
    dict(PAYLOAD, apps=[{'id': 'lstopo.desktop', 'name': 'x' * 161}]),
    dict(PAYLOAD, apps=[{'id': 'lstopo.desktop', 'name': 'App\nRun command'}]),
    dict(PAYLOAD, apps=[{'id': 'lstopo.desktop', 'name': 'App\u202e'}]),
    dict(PAYLOAD, apps=[dict(PAYLOAD['apps'][0], command='/bin/sh')])])
def test_invalid_catalog_or_instruction_never_reaches_model(client, native, payload):
    assert client.post('/plan', json=payload).status_code == 400
    assert native['calls'] == []


def test_duplicate_json_and_oversized_body_are_rejected(client, native):
    assert client.post('/plan', content=b'{"instruction":"x","instruction":"y","apps":[]}').status_code == 400
    assert client.post('/plan', content=b'x' * 16385).status_code == 413
    assert native['calls'] == []


def test_real_native_request_shape_and_schema_only_use_catalog_ids(client, native):
    response = client.post('/plan', json=PAYLOAD)
    assert response.status_code == 200
    assert response.json() == {'plan': {'action': 'launch_app', 'app_id': 'lstopo.desktop'}}
    calls = native['calls']
    assert [path for path, _ in calls] == ['/apply-template', '/tokenize', '/completion']
    assert json.loads(calls[0][1]['messages'][1]['content']) == PAYLOAD
    body = calls[-1][1]
    assert body['n_predict'] == 128 and body['temperature'] == 0.0
    assert body['stream'] is False and body['cache_prompt'] is False
    assert body['json_schema']['properties']['app_id']['enum'] == [None, 'lstopo.desktop']
    assert body['json_schema']['additionalProperties'] is False


@pytest.mark.parametrize('action', ['inspect_services', 'none'])
def test_nonlaunch_plan_requires_no_app_and_works_with_empty_catalog(client, native, action):
    native['result']['content'] = json.dumps({'action': action, 'app_id': None})
    native['result']['stop_type'] = 'word'
    response = client.post('/plan', json={'instruction': 'Check service health', 'apps': []})
    assert response.status_code == 200
    assert response.json()['plan'] == {'action': action, 'app_id': None}
    assert native['calls'][-1][1]['json_schema']['properties']['app_id']['enum'] == [None]


@pytest.mark.parametrize('content', [
    '{"action":"launch_app","app_id":"forged.desktop"}',
    '{"action":"launch_app","app_id":null}',
    '{"action":"inspect_services","app_id":"lstopo.desktop"}',
    '{"action":"none","app_id":"lstopo.desktop"}',
    '{"action":"run_shell","app_id":null}',
    '{"action":"launch_app","app_id":"lstopo.desktop","command":"/bin/sh"}',
    '{"action":"none","action":"launch_app","app_id":"lstopo.desktop"}',
    '{"action":[],"app_id":null}', '[]', 'not json'])
def test_forged_or_ambiguous_plan_is_never_returned(client, native, content):
    native['result']['content'] = content
    response = client.post('/plan', json=PAYLOAD)
    assert response.status_code == 502
    assert response.json() == {'error': 'Local OS planning failed; no action was executed'}


@pytest.mark.parametrize('change', [{'truncated': True}, {'stop_type': 'limit'}, {'stop_type': None}])
def test_incomplete_generation_is_rejected(client, native, change):
    native['result'].update(change)
    assert client.post('/plan', json=PAYLOAD).status_code == 502


@pytest.mark.parametrize('count,status', [(2944, 200), (2945, 400)])
def test_prompt_and_output_share_the_context_budget(client, native, count, status):
    native['tokens'] = [1] * count
    assert client.post('/plan', json=PAYLOAD).status_code == status
    assert len(native['calls']) == (3 if status == 200 else 2)


@pytest.mark.parametrize('url', ['https://external.example/v1', 'http://user:password@127.0.0.1/v1',
    'http://127.0.0.1/v1?query=x', 'http://127.0.0.1/other'])
def test_upstream_configuration_cannot_exfiltrate_or_disclose_details(client, native, monkeypatch, url):
    monkeypatch.setattr(os_model, 'ROMS_UPSTREAM_LLM_URL', url)
    response = client.post('/plan', json=PAYLOAD)
    assert response.status_code == 502
    assert url not in response.text and 'password' not in response.text
    assert native['calls'] == []


def test_disconnect_cancels_owned_planning(monkeypatch):
    monkeypatch.setenv('ROMS_GATEWAY_API_KEY', 'fixture-gateway-key')
    async def exercise():
        started, settled = asyncio.Event(), asyncio.Event()
        body_sent = False
        async def receive():
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {'type': 'http.request', 'body': json.dumps(PAYLOAD).encode(), 'more_body': False}
            await started.wait()
            return {'type': 'http.disconnect'}
        async def generate(_):
            started.set()
            try:
                await asyncio.Future()
            finally:
                settled.set()
        monkeypatch.setattr(os_model, 'generate_plan', generate)
        response = await asyncio.wait_for(os_model.plan_completion(Request({'type': 'http'}, receive)), 2)
        assert response.status_code == 499 and settled.is_set()
    asyncio.run(exercise())
