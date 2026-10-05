import json
from datetime import datetime
from unittest.mock import patch

from app.broker_actions import handle


def request(text):
    return json.loads(handle(bytearray(text.encode())))


def test_json_equivalence_and_rejected_ambiguity():
    for text in ('{"v":1,"action":"ping"}', '{"action": "ping", "v": 1}'):
        assert request(text) == {"ok": True, "v": 1, "result": "pong"}
    for text in ('{"v":1,"v":1,"action":"ping"}', '{"v":true,"action":"ping"}',
                 '{"v":1,"action":"ping","execute":"anything"}'):
        assert request(text)["ok"] is False


def test_status_cannot_claim_disconnected_model_is_ready():
    with patch('app.broker_actions.gateway', side_effect=OSError):
        assert request('STATUS')['rwkv7'] == 'not_connected'
        assert request('{"v":1,"action":"rwkv_status"}')['rwkv7'] == 'not_connected'


def test_current_anchor_and_no_execution():
    assert str(datetime.now().year) in request('ANCHOR')['anchor']
    assert request('{"v":1,"action":"os_controller"}')['controller'] == 'unavailable'


def test_gateway_auth(monkeypatch):
    from starlette.testclient import TestClient
    from app.gateway import app
    monkeypatch.setenv('ROMS_GATEWAY_API_KEY', 'test-secret')
    with TestClient(app) as client:
        assert client.post('/v1/chat/completions', json={}).status_code == 401
        assert client.post('/v1/chat/completions', json=[],
                           headers={'Authorization': 'Bearer test-secret'}).status_code == 400
