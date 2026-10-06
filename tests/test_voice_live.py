"""Explicitly enabled integration check; no downloads, microphone, or speaker use."""
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import verify_voice


@pytest.mark.skipif(os.environ.get('ROMS_LIVE_VOICE') != '1',
                   reason='Set ROMS_LIVE_VOICE=1 in the installed voice runtime')
def test_real_cpu_voice_roundtrip_and_cancellation():
    data_dir = Path(os.environ.get('ROMS_VOICE_DATA_DIR', '/opt/goose-voice-data'))
    report = verify_voice.run_verification(data_dir)
    assert report['success'], report
    assert report['functional_success']
    assert report['measurement_source'] == 'this_process_actual_models'
    assert report['roundtrip']['semantic_match']
    assert len(report['warm_synthesis']) == 3
    for measurement in report['warm_synthesis']:
        assert 0 < measurement['ttfa_seconds'] <= measurement['generation_seconds']
        assert measurement['audio_seconds'] > 0 and measurement['real_time_factor'] > 0
    assert report['cancellation']['post_cancel_chunks'] == 0
    assert report['cancellation']['subsequent_request_succeeded']
    assert report['memory_after_checks']['peak_rss_bytes'] > 0
    assert report['memory_after_checks']['rss_bytes'] > 0
    assert report['common_word_summary'] == {'passed': 8, 'total': 8}
    assert not any(report['options'].values())


@pytest.mark.parametrize('brand_ok,common_ok,strict,functional', [
    (False, True, False, True), (True, True, True, True),
    (True, False, False, False), (False, False, False, False)])
def test_quality_failure_never_becomes_strict_success(tmp_path, monkeypatch,
                                                     brand_ok, common_ok, strict, functional):
    calls = []
    (tmp_path / 'voice-runtime.json').write_text('{}', encoding='utf-8')
    monkeypatch.setattr(verify_voice.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(verify_voice, '_memory', lambda: {'rss_bytes': 1, 'peak_rss_bytes': 1})
    monkeypatch.setattr(verify_voice.metadata, 'version', lambda name: 'fixture')
    monkeypatch.setattr(verify_voice, '_seed', lambda value: None)
    monkeypatch.setattr(verify_voice, 'PocketSpeaker', lambda path: SimpleNamespace(
        load=lambda: None, sample_rate=24000))
    monkeypatch.setattr(verify_voice, 'TinyRecognizer', lambda path: SimpleNamespace(
        load=lambda: None, close=lambda: calls.append('closed'),
        transcribe=lambda pcm, rate: 'Goose voice is ready. The number is 42.' if brand_ok
        else 'Whose voice is ready. The number is 42.'))
    def synthesize(speaker):
        calls.append('synthesis')
        return {'ttfa_seconds': .1, 'real_time_factor': .5}, b'\0\0'
    monkeypatch.setattr(verify_voice, '_synthesize', synthesize)
    monkeypatch.setattr(verify_voice, '_cancellation', lambda speaker: calls.append('cancellation'))
    monkeypatch.setattr(verify_voice, '_common_roundtrips', lambda speaker, recognizer:
                        [{'semantic_match': common_ok} for _ in range(8)])
    monkeypatch.setattr(verify_voice, '_chat', lambda speaker: calls.append('chat'))
    report = verify_voice.run_verification(tmp_path, chat=True)
    assert report['success'] is strict
    assert report['functional_success'] is functional
    assert report['roundtrip']['semantic_match'] is brand_ok
    assert calls == ['synthesis'] * 4 + ['cancellation', 'chat', 'closed']
    assert ('brand_roundtrip' in report['quality_failures']) is (not brand_ok)
    assert ('common_word_roundtrips' in report['quality_failures']) is (not common_ok)
