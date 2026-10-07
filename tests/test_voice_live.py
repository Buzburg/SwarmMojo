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


@pytest.mark.parametrize('playback_fails', [False, True], ids=['complete', 'playback-error'])
def test_chat_times_first_visible_delta_before_sentence_buffer_and_closes_streams(monkeypatch, playback_fails):
    from app import voice_audio, voice_chat

    clock = [0.0]
    state = {'chat_closed': False, 'audio_closed': False}
    monkeypatch.setenv('ROMS_GATEWAY_API_KEY', 'fixture-key')
    monkeypatch.setattr(verify_voice.time, 'perf_counter', lambda: clock[0])

    def answer(messages, api_key, cancel):
        assert api_key == 'fixture-key'
        state['cancel'] = cancel
        try:
            clock[0] = 1.0
            yield ' '  # Whitespace is not a visible answer.
            clock[0] = 2.0
            yield '4'
            clock[0] = 4.0
            yield '2. ' if playback_fails else '2'
            clock[0] = 6.0  # An unpunctuated answer is held until EOF.
        finally:
            state['chat_closed'] = True

    def audio(text, cancel):
        assert text == ('42.' if playback_fails else '42') and cancel is state['cancel']
        try:
            clock[0] = 6.25
            yield object()
        finally:
            state['audio_closed'] = True

    def play(chunks, sample_rate, cancel):
        assert sample_rate == 24000
        for chunk in chunks:
            if playback_fails:
                assert not state['chat_closed']
                raise RuntimeError('fixture playback failure')
        clock[0] = 7.25
        return 1.0

    monkeypatch.setattr(voice_chat, 'stream_answer', answer)
    monkeypatch.setattr(voice_audio, 'play', play)
    speaker = SimpleNamespace(iter_audio=audio, sample_rate=24000)
    if playback_fails:
        with pytest.raises(RuntimeError, match='fixture playback failure'):
            verify_voice._chat(speaker)
    else:
        report = verify_voice._chat(speaker)
        assert report['first_visible_text_seconds'] == 2.0
        assert report['first_speakable_text_seconds'] == 6.0
        assert report['first_generated_audio_seconds'] == 6.25
        assert report['complete_playback_seconds'] == 7.25
        assert report['answer_characters'] == 2
        assert '42' not in report.values()
    assert state['chat_closed'] and state['audio_closed']
    assert state['cancel'].is_set()
