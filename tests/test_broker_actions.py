import json
import pytest
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


@pytest.mark.parametrize('health', [[], {}, {'upstream_ready': 'true', 'status': 'ready'},
                                   {'upstream_ready': True, 'status': 'degraded'}])
def test_incomplete_health_cannot_claim_chat_ready(health):
    with patch('app.broker_actions.gateway', return_value=health), patch('app.broker_actions.worker_request', side_effect=OSError):
        status = request('STATUS')
    assert status['ok'] is True
    assert status['features']['chat']['state'] == 'unavailable'
    assert status['features']['project_workshop']['state'] == 'unavailable'


def test_status_separates_worker_reachability_from_enforcement(monkeypatch):
    monkeypatch.setenv('ROMS_GATEWAY_API_KEY', 'fixture-key')
    with patch('app.broker_actions.gateway', return_value={'upstream_ready': True, 'status': 'ready', 'model': 'fixture'}), \
            patch('app.broker_actions.worker_request', return_value={'ok': True, 'result': 'pong'}) as worker:
        statuses = [request('STATUS'), request('{"v":1,"action":"status"}'), request('{"v":1,"action":"rwkv_status"}')]
    assert all(status['features'] == statuses[0]['features'] for status in statuses)
    for call in worker.call_args_list:
        assert call.args == ('ping',) and call.kwargs == {'timeout': 1}
    features = statuses[0]['features']
    assert features['chat']['state'] == 'ready'
    assert features['project_workshop']['state'] == 'available'
    assert features['validation_worker']['state'] == 'reachable'
    assert features['knowledge_library']['state'] == 'not_probed'
    assert all(item['reason'] for item in features.values())
    assert all(features[name]['state'] == 'unavailable' for name in ('desktop_control', 'recurrent_state', 'web_evidence', 'guest_delegation', 'training'))
    assert statuses[0]['tool_execution'] is False


@pytest.mark.parametrize('abi', [-1, 1, 2, 3, 6])
def test_kernel_probe_does_not_certify_enforcement(abi):
    with patch('app.broker_actions.landlock_abi', return_value=abi):
        status = request('{"v":1,"action":"sandbox_status"}')
    assert status['required_abi_available'] is (abi >= 3)
    assert status['enforcement_verified'] is False
    assert status['scope'] == 'kernel_abi_probe'


def test_failed_worker_probe_does_not_claim_workshop_available(monkeypatch):
    monkeypatch.setenv('ROMS_GATEWAY_API_KEY', 'fixture-key')
    with patch('app.broker_actions.gateway', return_value={'upstream_ready': True, 'status': 'ready'}), \
            patch('app.broker_actions.worker_request', return_value={'ok': False, 'error': 'worker_busy'}):
        assert request('STATUS')['features']['project_workshop']['state'] == 'unavailable'


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
