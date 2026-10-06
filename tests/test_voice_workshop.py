import threading
import wave

import pytest

from scripts import voice_chat


def test_wave_rejects_stereo_and_long_input(tmp_path):
    for channels, seconds in [(2, 1), (1, 31)]:
        path = tmp_path / 'input.wav'
        with wave.open(str(path), 'wb') as output:
            output.setnchannels(channels)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(b'\0' * (16000 * seconds * channels * 2))
        with pytest.raises(ValueError):
            voice_chat.read_wave(path)


def test_wave_accepts_bounded_mono_pcm(tmp_path):
    path = tmp_path / 'input.wav'
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b'\0' * 32000)
    assert voice_chat.read_wave(path) == (b'\0' * 32000, 16000)


class Speaker:
    sample_rate = 24000
    def iter_audio(self, text, cancel):
        yield text


def test_failed_reply_closes_stream_without_committing_history(monkeypatch):
    closed = []
    def answer(*args):
        try:
            yield 'A partial answer.'
            raise RuntimeError('Connection lost')
        finally:
            closed.append(True)
    monkeypatch.setenv('ROMS_GATEWAY_API_KEY', 'test')
    monkeypatch.setattr(voice_chat, 'stream_answer', answer)
    monkeypatch.setattr(voice_chat, 'sentence_chunks', lambda parts: parts)
    monkeypatch.setattr(voice_chat, 'play', lambda chunks, rate, cancel: list(chunks))
    history = []
    cancel = threading.Event()
    with pytest.raises(RuntimeError, match='Connection lost'):
        voice_chat.reply('Hello', history, Speaker(), cancel)
    assert history == []
    assert closed == [True]
    assert cancel.is_set()


def test_completed_reply_keeps_bounded_history(monkeypatch):
    def answer(*args):
        yield 'Hello.'
    monkeypatch.setenv('ROMS_GATEWAY_API_KEY', 'test')
    monkeypatch.setattr(voice_chat, 'stream_answer', answer)
    monkeypatch.setattr(voice_chat, 'sentence_chunks', lambda parts: parts)
    def playback(chunks, rate, cancel):
        assert list(chunks) == ['Hello.']
        return 0.5
    monkeypatch.setattr(voice_chat, 'play', playback)
    history = []
    for _ in range(4):
        voice_chat.reply('Hello', history, Speaker(), threading.Event())
    assert len(history) == 6
    assert history[-1] == {'role': 'assistant', 'content': 'Hello.'}


def test_oversized_request_never_contacts_model(monkeypatch):
    monkeypatch.setattr(voice_chat, 'stream_answer', lambda *args: pytest.fail('must not contact model'))
    with pytest.raises(ValueError):
        voice_chat.reply('x' * 2049, [], Speaker(), threading.Event())


def test_speaker_generator_closes_immediately_on_playback_failure(monkeypatch):
    closed = []
    class TrackedSpeaker(Speaker):
        def iter_audio(self, text, cancel):
            try:
                yield text
                yield text
            finally:
                closed.append(True)
    def broken_playback(chunks, rate, cancel):
        next(chunks)
        raise OSError('Speaker disconnected')
    monkeypatch.setattr(voice_chat, 'play', broken_playback)
    monkeypatch.setattr(voice_chat, 'sentence_chunks', lambda parts: parts)
    with pytest.raises(OSError):
        voice_chat.speak('Hello.', TrackedSpeaker(), threading.Event())
    assert closed == [True]
