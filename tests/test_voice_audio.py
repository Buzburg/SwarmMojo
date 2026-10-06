import socket
import subprocess
import sys
import threading

import numpy as np
import pytest

from app import voice_audio

pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='Linux audio process contract')


def test_remote_audio_server_rejected(monkeypatch):
    monkeypatch.setenv('PULSE_SERVER', 'tcp:example.com:4713')
    with pytest.raises(voice_audio.VoiceAudioError, match='local audio'):
        voice_audio.audio_environment()


def test_audio_children_receive_no_api_keys(tmp_path, monkeypatch):
    server = socket.socket(socket.AF_UNIX)
    path = tmp_path / 'pulse'
    server.bind(str(path))
    monkeypatch.setenv('PULSE_SERVER', 'unix:' + str(path))
    monkeypatch.setenv('ROMS_GATEWAY_API_KEY', 'private')
    monkeypatch.setenv('LD_PRELOAD', '/tmp/untrusted.so')
    try:
        env = voice_audio.audio_environment()
        assert env['PULSE_SERVER'] == 'unix:' + str(path)
        assert 'ROMS_GATEWAY_API_KEY' not in env
        assert 'LD_PRELOAD' not in env
    finally:
        server.close()


def audio_processes(monkeypatch, program):
    original = subprocess.Popen
    processes = []
    def launch(*args, **kwargs):
        kwargs['env'] = {'PATH': '/usr/bin:/bin'}
        process = original([sys.executable, '-c', program], **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr(voice_audio, 'audio_environment', lambda: {})
    monkeypatch.setattr(voice_audio.subprocess, 'Popen', launch)
    return processes


def test_cancelled_recording_never_opens_microphone(monkeypatch):
    processes = audio_processes(monkeypatch, 'import time; time.sleep(30)')
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(voice_audio.VoiceAudioCancelled):
        voice_audio.record(lambda: False, cancel)
    assert processes == []


def test_recording_duration_cannot_be_unbounded():
    with pytest.raises(ValueError):
        voice_audio.record(lambda: False, threading.Event(), duration=31)


def test_microphone_disconnect_is_reported(monkeypatch):
    processes = audio_processes(monkeypatch, 'pass')
    with pytest.raises(voice_audio.VoiceAudioError, match='Microphone disconnected'):
        voice_audio.record(lambda: False, threading.Event())
    assert processes[0].poll() is not None


def test_recording_limit_starts_when_audio_arrives(monkeypatch):
    processes = audio_processes(monkeypatch,
        'import sys,time; time.sleep(.15); sys.stdout.buffer.write(bytes(3200)); sys.stdout.buffer.flush(); time.sleep(30)')
    ready = []
    pcm = voice_audio.record(lambda: False, threading.Event(), duration=0.1,
                             on_ready=lambda: ready.append(True))
    assert len(pcm) == 3200 and ready == [True]
    assert processes[0].poll() is not None


@pytest.mark.parametrize('chunk', [np.array([float('nan')]), np.zeros((2, 3)), np.zeros(24000 * 91)])
def test_invalid_or_excessive_speech_closes_child(monkeypatch, chunk):
    processes = audio_processes(monkeypatch, 'import sys; sys.stdin.buffer.read()')
    with pytest.raises(voice_audio.VoiceAudioError):
        voice_audio.play([chunk], 24000, threading.Event())
    assert processes[0].poll() is not None


def test_cancellation_stops_playback(monkeypatch):
    processes = audio_processes(monkeypatch, 'import time; time.sleep(30)')
    cancel = threading.Event()
    def chunks():
        cancel.set()
        yield np.zeros(240)
    with pytest.raises(voice_audio.VoiceAudioCancelled):
        voice_audio.play(chunks(), 24000, cancel)
    assert processes[0].poll() is not None


def test_pre_cancelled_playback_never_opens_speakers(monkeypatch):
    monkeypatch.setattr(voice_audio.subprocess, 'Popen', lambda *a, **kw: pytest.fail('device opened'))
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(voice_audio.VoiceAudioCancelled):
        voice_audio.play([np.zeros(240)], 24000, cancel)


def test_audio_is_fully_drained_before_success(monkeypatch):
    processes = audio_processes(monkeypatch, 'import sys; data=sys.stdin.buffer.read(); sys.exit(0 if len(data)==480 else 2)')
    assert voice_audio.play([np.zeros(240)], 24000, threading.Event()) == 0.01
    assert processes[0].returncode == 0
