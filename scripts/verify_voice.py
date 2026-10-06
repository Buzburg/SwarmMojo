"""Measure installed CPU voice models; never save audio, transcripts, or credentials.

Run with the isolated voice Python. The default check uses no microphone or speaker.
Audio-device and local-Goose checks require their explicit command-line flags.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import random
import re
import statistics
import threading
import time
from typing import Any

from app.voice_stt import TinyRecognizer
from app.voice_tts import PocketSpeaker

FIXTURE_TEXT = 'Goose voice is ready. The number is forty two.'
MAX_AUDIO_SECONDS = 30
COMMON_FIXTURES = (
    ('ready', 'The voice assistant is ready. The number is forty two.', {'voice', 'assistant', 'ready'}),
    ('arithmetic', 'What is six times seven?', {'what', 'six', 'times', 'seven'}),
    ('workshop', 'Open the system workshop.', {'open', 'system', 'workshop'}),
    ('status', 'Tell me the status of the computer.', {'tell', 'status', 'computer'}),
)


def _has_forty_two(text: str) -> bool:
    return bool(re.search(r'\b(?:42|forty[\s-]+two)\b', text, re.IGNORECASE))


def _roundtrip_matches(text: str) -> bool:
    words = set(re.findall(r'[a-z]+', text.lower()))
    return {'goose', 'voice', 'ready'} <= words and _has_forty_two(text)


def _seed(value: int) -> None:
    import numpy as np
    import torch

    random.seed(value)
    np.random.seed(value)
    torch.manual_seed(value)


def _common_roundtrips(speaker: PocketSpeaker, recognizer: TinyRecognizer) -> list[dict[str, Any]]:
    results = []
    for seed in (0, 1):
        for name, text, required in COMMON_FIXTURES:
            _seed(seed)
            measurement, pcm = _synthesize(speaker, text)
            started = time.perf_counter()
            transcript = recognizer.transcribe(pcm, speaker.sample_rate)
            words = set(re.findall(r'[a-z]+|\d+', transcript.lower()))
            words = {{'6': 'six', '7': 'seven'}.get(word, word) for word in words}
            matched = required <= words and (name != 'ready' or _has_forty_two(transcript))
            results.append({'fixture': name, 'seed': seed, 'semantic_match': matched,
                            'transcript_characters': len(transcript),
                            'recognition_seconds': time.perf_counter() - started,
                            'audio_seconds': measurement['audio_seconds']})
    return results


def _memory() -> dict[str, int]:
    import resource

    current = 0
    with Path('/proc/self/status').open(encoding='ascii') as source:
        for line in source:
            if line.startswith('VmRSS:'):
                current = int(line.split()[1]) * 1024
                break
    if current <= 0:
        raise RuntimeError('Linux process memory measurement unavailable')
    return {'rss_bytes': current,
            'peak_rss_bytes': int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024}


def _synthesize(speaker: PocketSpeaker, text: str = FIXTURE_TEXT) -> tuple[dict[str, Any], bytes]:
    import numpy as np

    started = time.perf_counter()
    first = None
    samples, chunks = 0, 0
    pcm = bytearray()
    with closing(speaker.iter_audio(text, threading.Event())) as audio:
        for chunk in audio:
            if not chunk.size:
                continue
            if first is None:
                first = time.perf_counter() - started
            samples += chunk.size
            chunks += 1
            if samples > speaker.sample_rate * MAX_AUDIO_SECONDS:
                raise RuntimeError('Voice fixture exceeded 30 seconds')
            pcm.extend((np.clip(chunk, -1, 1) * 32767).astype('<i2').tobytes())
    elapsed = time.perf_counter() - started
    if first is None or samples == 0:
        raise RuntimeError('Voice model produced no audio')
    seconds = samples / speaker.sample_rate
    return {'ttfa_seconds': first, 'generation_seconds': elapsed,
            'audio_seconds': seconds, 'real_time_factor': elapsed / seconds,
            'chunks': chunks}, bytes(pcm)


def _cancellation(speaker: PocketSpeaker) -> dict[str, Any]:
    cancel = threading.Event()
    cancel.set()
    started = time.perf_counter()
    with closing(speaker.iter_audio(FIXTURE_TEXT, cancel)) as audio:
        if next(audio, None) is not None:
            raise RuntimeError('Pre-cancelled speech emitted audio')
    before = time.perf_counter() - started
    cancel = threading.Event()
    with closing(speaker.iter_audio(FIXTURE_TEXT, cancel)) as audio:
        first = next(audio, None)
        if first is None or first.size == 0:
            raise RuntimeError('Cancellation fixture produced no first chunk')
        started = time.perf_counter()
        cancel.set()
        if next(audio, None) is not None:
            raise RuntimeError('Cancelled speech continued emitting audio')
    after = time.perf_counter() - started
    recovery, _ = _synthesize(speaker, 'Ready.')
    return {'before_first_chunk_seconds': before, 'after_first_chunk_seconds': after,
            'post_cancel_chunks': 0, 'subsequent_request_succeeded': True,
            'recovery_ttfa_seconds': recovery['ttfa_seconds']}


def _chat(speaker: PocketSpeaker) -> dict[str, Any]:
    from app.voice_audio import play
    from app.voice_chat import sentence_chunks, stream_answer

    key = os.environ.get('ROMS_GATEWAY_API_KEY', '')
    if not key:
        raise RuntimeError('An authenticated local chat environment is required')
    cancel = threading.Event()
    started = time.perf_counter()
    first_text = first_audio = None
    answer = []
    parts = stream_answer([{'role': 'user', 'content':
                           'What is six times seven? Answer in one short sentence.'}], key, cancel)

    def spoken_chunks():
        nonlocal first_text, first_audio
        for sentence in sentence_chunks(parts):
            if first_text is None:
                first_text = time.perf_counter() - started
            answer.append(sentence)
            with closing(speaker.iter_audio(sentence, cancel)) as audio:
                for chunk in audio:
                    if first_audio is None:
                        first_audio = time.perf_counter() - started
                    yield chunk

    try:
        with closing(spoken_chunks()) as audio:
            seconds = play(audio, speaker.sample_rate, cancel)
    finally:
        cancel.set()
        parts.close()
    visible = ' '.join(answer)
    if not _has_forty_two(visible) or seconds <= 0:
        raise RuntimeError('Local Goose arithmetic or speech check failed')
    return {'expected_number_present': True, 'answer_characters': len(visible),
            'first_speakable_text_seconds': first_text, 'first_generated_audio_seconds': first_audio,
            'complete_playback_seconds': time.perf_counter() - started, 'audio_seconds': seconds}


def run_verification(data_dir: Path, *, playback: bool = False, chat: bool = False,
                     microphone: bool = False) -> dict[str, Any]:
    """Run real installed models, returning an evidence report even on failure."""
    report: dict[str, Any] = {
        'schema_version': 1, 'success': False, 'functional_success': False,
        'started_utc': datetime.now(timezone.utc).isoformat(),
        'measurement_source': 'this_process_actual_models',
        'fixture': 'goose-ready-forty-two-v1',
        'fixture_seed': 0,
        'functional_scope': 'Common-word recognition, synthesis and cancellation, plus explicitly '
                            'requested device/chat checks; excludes brand-recognition quality.',
        'quality_failures': [],
        'timing_definition': 'TTS TTFA starts at iter_audio and ends at first generated chunk; '
                             'RTF is generation seconds/audio seconds. Neither includes chat or playback.',
        'cold_load_definition': 'First load in this process, including asset verification/imports; '
                                'the operating-system file cache is not cleared. TTS loads before STT.',
        'memory_definition': 'Linux process RSS and process-lifetime peak RSS, including both models.',
        'options': {'playback': playback, 'chat': chat, 'microphone': microphone},
    }
    stage = 'platform'
    recognizer = None
    started = time.perf_counter()
    try:
        if platform.system() != 'Linux':
            raise RuntimeError('This runtime verification requires Linux')
        report['platform'] = {'system': 'Linux', 'machine': platform.machine(),
                              'python': platform.python_version(), 'logical_cpus': os.cpu_count()}
        report['memory_before_load'] = _memory()
        stage = 'tts_load'
        speaker = PocketSpeaker(data_dir)
        load_started = time.perf_counter()
        speaker.load()
        report['tts_load_seconds'] = time.perf_counter() - load_started
        stage = 'stt_load'
        recognizer = TinyRecognizer(data_dir)
        load_started = time.perf_counter()
        recognizer.load()
        report['stt_load_seconds'] = time.perf_counter() - load_started
        report['versions'] = {name: metadata.version(name) for name in ('pocket-tts', 'moonshine-voice')}
        with (data_dir / 'voice-runtime.json').open('rb') as source:
            report['manifest_sha256'] = hashlib.file_digest(source, 'sha256').hexdigest()
        report['memory_after_load'] = _memory()
        stage = 'roundtrip'
        _seed(0)
        report['first_synthesis'], pcm = _synthesize(speaker)
        recognition_started = time.perf_counter()
        transcript = recognizer.transcribe(pcm, speaker.sample_rate)
        report['roundtrip'] = {'semantic_match': _roundtrip_matches(transcript),
                               'recognition_seconds': time.perf_counter() - recognition_started,
                               'transcript_characters': len(transcript)}
        del pcm, transcript
        if not report['roundtrip']['semantic_match']:
            report['quality_failures'].append('brand_roundtrip')
        stage = 'warm_synthesis'
        report['warm_synthesis'] = [_synthesize(speaker)[0] for _ in range(3)]
        report['warm_medians'] = {key: statistics.median(row[key] for row in report['warm_synthesis'])
                                  for key in ('ttfa_seconds', 'real_time_factor')}
        stage = 'cancellation'
        report['cancellation'] = _cancellation(speaker)
        stage = 'common_word_roundtrips'
        report['common_word_roundtrips'] = _common_roundtrips(speaker, recognizer)
        common_passed = sum(row['semantic_match'] for row in report['common_word_roundtrips'])
        report['common_word_summary'] = {'passed': common_passed, 'total': 8}
        if common_passed != 8:
            report['quality_failures'].append('common_word_roundtrips')
        if playback:
            from app.voice_audio import play
            stage = 'playback'
            playback_started = time.perf_counter()
            with closing(speaker.iter_audio(FIXTURE_TEXT, threading.Event())) as audio:
                seconds = play(audio, speaker.sample_rate, threading.Event())
            report['playback'] = {'completed': True, 'audio_seconds': seconds,
                                  'elapsed_seconds': time.perf_counter() - playback_started,
                                  'audibility_verified': False}
        if chat:
            stage = 'chat'
            report['chat'] = _chat(speaker)
        if microphone:
            from app.voice_audio import record
            stage = 'microphone'
            pcm = record(lambda: False, threading.Event(), duration=1.0)
            if not 0 < len(pcm) <= 32000:
                raise RuntimeError('One-second microphone check returned invalid audio length')
            report['microphone'] = {'capture_completed': True, 'sample_rate': 16000,
                                    'sample_count': len(pcm) // 2, 'pcm_bytes': len(pcm),
                                    'audio_saved': False, 'transcribed': False}
            del pcm
        report['memory_after_checks'] = _memory()
        report['functional_success'] = common_passed == 8
        report['success'] = report['functional_success'] and report['roundtrip']['semantic_match']
        if not report['success']:
            report['failure_stage'] = ('roundtrip' if not report['roundtrip']['semantic_match']
                                       else 'common_word_roundtrips')
            report['failure_type'] = 'ContentMismatch'
    except Exception as error:
        # Never serialize exception messages: upstream failures can contain paths or text.
        report['failure_stage'] = stage
        report['failure_type'] = type(error).__name__
    finally:
        if recognizer is not None:
            try:
                recognizer.close()
            except Exception as error:
                report['success'] = False
                report['functional_success'] = False
                report['cleanup_failure_type'] = type(error).__name__
        report['elapsed_seconds'] = time.perf_counter() - started
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path('/opt/goose-voice-data'))
    parser.add_argument('--output', type=Path, required=True, help='New metadata-only JSON evidence file')
    parser.add_argument('--playback', action='store_true', help='Play the known generated fixture')
    parser.add_argument('--chat', action='store_true', help='Ask local Goose fixed arithmetic and speak its answer')
    parser.add_argument('--microphone', action='store_true', help='Capture one second; retain only sample counts')
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Choose a new evidence filename; existing reports are preserved')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = run_verification(args.data_dir, playback=args.playback, chat=args.chat,
                              microphone=args.microphone)
    with args.output.open('x', encoding='utf-8') as target:
        json.dump(report, target, indent=2, allow_nan=False)
        target.write('\n')
    print(json.dumps({'success': report['success'], 'functional_success': report['functional_success'],
                      'failure_stage': report.get('failure_stage'),
                      'output': str(args.output)}))
    return 0 if report['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
