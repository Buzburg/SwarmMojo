"""Tests for Personal Assistant Engine by Buzburg AI."""
import pytest
from app.engines.personal_assistant import (
    AssistantVault,
    ConsultGateway,
    DailyBriefingEngine,
    PersonalAssistantEngine,
    RealtimeVoiceBridge,
)


def test_vault_credentials_and_preferences():
    engine = PersonalAssistantEngine()
    store_res = engine.store_credential("github_pat", "ghp_mock_secret_token_12345")
    assert store_res["status"] == "stored"

    secret = engine.vault.get_secret("github_pat")
    assert secret == "ghp_mock_secret_token_12345"

    prefs = engine.vault.get_preferences()
    assert prefs.user_name == "Operator"


def test_consult_gateway_dispatch():
    engine = PersonalAssistantEngine()
    res = engine.consult_specialist("Analyze code complexity", division="coding")
    assert res["status"] == "COMPLETED"
    assert "coding guild" in res["result"]
    assert res["id"].startswith("c_")


def test_daily_briefing_generation():
    engine = PersonalAssistantEngine()
    briefing = engine.get_briefing()
    assert "Daily Briefing" in briefing["title"]
    assert "Good morning" in briefing["summary_text"]
    assert len(briefing["tasks"]) >= 1
    assert len(briefing["routines"]) >= 1


def test_realtime_voice_bridge_vad():
    bridge = RealtimeVoiceBridge()
    # Test silence
    silence = [0.001] * 100
    res_silence = bridge.evaluate_audio_energy(silence)
    assert not res_silence["speech_active"]
    assert not res_silence["barge_in"]

    # Test speech
    speech = [0.05] * 100
    res_speech = bridge.evaluate_audio_energy(speech)
    assert res_speech["speech_active"]

    # Test barge-in interruption
    loud = [0.12] * 100
    res_loud = bridge.evaluate_audio_energy(loud)
    assert res_loud["barge_in"]
