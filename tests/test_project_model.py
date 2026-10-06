"""Authentication, context budgets and native grammar routing for draft generation."""
import json

import pytest
from starlette.testclient import TestClient

from app.gateway import app
from app import project_model

PAYLOAD = {'instruction': 'Set VALUE to 2', 'files': {'module.py': 'VALUE = 1\n'}}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('ROMS_GATEWAY_API_KEY', 'fixture-gateway-key')
    monkeypatch.setenv('ROMS_UPSTREAM_API_KEY', 'fixture-upstream-key')
    monkeypatch.setattr(project_model, 'ROMS_UPSTREAM_LLM_URL', 'http://127.0.0.1:18080/v1')
    with TestClient(app, headers={'Authorization': 'Bearer fixture-gateway-key'}) as value:
        yield value


def test_drafting_requires_gateway_authentication(client):
    assert client.post('/v1/project/draft', json=PAYLOAD, headers={'Authorization': 'wrong'}).status_code == 401


def test_drafting_is_disabled_without_configured_authentication(client, monkeypatch):
    monkeypatch.delenv('ROMS_GATEWAY_API_KEY')
    async def unexpected(*_):
        pytest.fail('Unauthenticated configuration reached the native model')
    monkeypatch.setattr(project_model, 'native_json', unexpected)
    assert client.post('/v1/project/draft', json=PAYLOAD).status_code == 503


@pytest.mark.parametrize('payload', [[], {}, dict(PAYLOAD, approve=True),
    {'instruction': '', 'files': {'module.py': 'x'}},
    {'instruction': 'x', 'files': {'module.py': 'x' * 4097}},
    {'instruction': 'x', 'files': {'module.py': ['not', 'text']}},
    {'instruction': 'x' * 1025, 'files': {'module.py': 'x'}}])
def test_bad_draft_inputs_do_not_reach_native_runtime(client, monkeypatch, payload):
    async def unexpected(*_):
        pytest.fail('Invalid input reached the native model')
    monkeypatch.setattr(project_model, 'native_json', unexpected)
    assert client.post('/v1/project/draft', json=payload).status_code == 400


@pytest.mark.parametrize('budget,stop,status', [(100, 'eos', 200), (3073, 'eos', 400), (100, 'limit', 200)])
def test_actual_schema_path_and_context_budget(client, monkeypatch, budget, stop, status):
    calls = []
    async def native(_, url, body, headers):
        calls.append((url, body))
        assert headers['Authorization'] == 'Bearer fixture-upstream-key'
        if url.endswith('/apply-template'):
            assert body['messages'][-1]['role'] == 'user'
            return {'prompt': 'User: fixture\n\nAssistant:'}
        if url.endswith('/tokenize'):
            return {'tokens': [1] * budget}
        assert url.endswith('/completion')
        assert body['n_predict'] == 768 and body['stream'] is False
        assert body['json_schema']['properties']['changes']['items']['properties']['path']['enum'] == ['module.py']
        return {'content': json.dumps({'changes': [{'path': 'module.py', 'after': 'VALUE = 2\n'}]}),
                'stop_type': stop, 'truncated': False, 'model': 'goose-2.9b', 'tokens_evaluated': budget, 'tokens_predicted': 30}
    monkeypatch.setattr(project_model, 'native_json', native)
    response = client.post('/v1/project/draft', json=PAYLOAD)
    assert response.status_code == status
    if status == 400:
        assert len(calls) == 2
    else:
        assert len(calls) == 3
        assert response.json()['choices'][0]['finish_reason'] == ('stop' if stop == 'eos' else 'length')


def test_project_context_cannot_be_forwarded_to_an_external_backend(client, monkeypatch):
    monkeypatch.setattr(project_model, 'ROMS_UPSTREAM_LLM_URL', 'https://external.example/v1')
    async def unexpected(*_):
        pytest.fail('Project context escaped the local-only adapter')
    monkeypatch.setattr(project_model, 'native_json', unexpected)
    assert client.post('/v1/project/draft', json=PAYLOAD).status_code == 502
