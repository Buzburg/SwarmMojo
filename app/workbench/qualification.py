"""Measured qualification gates. Missing evidence cannot become a passing claim."""
from __future__ import annotations

import hashlib
import json
import math
import platform
import statistics
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.goose_response import decode_completed_response


def environment_record() -> dict:
    cpu, memory = platform.processor() or 'unknown', None
    if Path('/proc/cpuinfo').exists():
        for line in Path('/proc/cpuinfo').read_text().splitlines():
            if line.startswith('model name'):
                cpu = line.split(':', 1)[1].strip()
                break
    if Path('/proc/meminfo').exists():
        memory = int(Path('/proc/meminfo').read_text().splitlines()[0].split()[1]) * 1024
    return {'cpu': cpu, 'memory_bytes': memory, 'kernel': platform.release(),
        'os': platform.platform(), 'target_qualified': False, 'gpu_model_placement': 'unverified',
        'planned_target': 'Ryzen AI Max+ 395 / 128 GB / native Omarchy',
        'missing_evidence': ['actual GPU placement', 'representative repair tasks', 'native desktop recovery']}


def adoption_decision(baseline: dict, candidate: dict) -> dict:
    reasons = []
    for key in ['machine_sha256', 'workload_sha256']:
        if not baseline.get(key) or candidate.get(key) != baseline[key]:
            reasons.append(key + ' differs or is missing; results are not comparable')
    for key in ['streaming', 'cancellation', 'recovery', 'recurrent_checkpoint']:
        if candidate.get(key) is not True:
            reasons.append(key + ' has not passed')
    if not baseline.get('checkpoint_sha256') or candidate.get('checkpoint_sha256') != baseline['checkpoint_sha256']:
        reasons.append('Model checkpoint identities differ or are missing')
    for label, report in [('baseline', baseline), ('candidate', candidate)]:
        samples = report.get('representative_tasks')
        if type(samples) is not int or samples < 10:
            reasons.append('At least ten representative task results are required for ' + label)
    try:
        values = [baseline[k] for k in ['task_success', 'median_seconds']] + [
            candidate[k] for k in ['task_success', 'median_seconds']]
        if any(type(value) not in (float, int) or not math.isfinite(value) for value in values):
            raise ValueError
        if not 0 <= values[0] <= 1 or not 0 <= values[2] <= 1 or min(values[1], values[3]) <= 0:
            raise ValueError
        if values[2] < values[0]:
            reasons.append('Task success regressed')
        if values[3] >= values[1]:
            reasons.append('No measured latency improvement')
    except (KeyError, TypeError, ValueError):
        reasons.append('Missing or invalid comparable measurements')
    return {'eligible': not reasons, 'reasons': reasons, 'automatically_adopted': False}


def probe_endpoint(url: str, model: str, *, key: str = '', checkpoint_sha256: str = '') -> dict:
    parsed = urlsplit(url)
    if parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost', '::1'} or parsed.username or parsed.query:
        raise ValueError('Qualification only connects to an explicit loopback HTTP endpoint')
    headers = {'Authorization': 'Bearer ' + key} if key else {}
    result: dict[str, Any] = {'checkpoint_sha256': checkpoint_sha256, 'model': model, 'samples': [],
        'streaming': False, 'cancellation': False, 'recovery': False,
        'recurrent_checkpoint': False, 'representative_tasks': 0, 'environment': environment_record()}
    cases = [('Reply with exactly the number 4. What is 2 + 2?', '4'),
             ('Reply with exactly READY and nothing else.', 'READY')]
    result['machine_sha256'] = hashlib.sha256(json.dumps({key: result['environment'][key]
        for key in ['cpu', 'memory_bytes', 'kernel', 'os']}, sort_keys=True).encode()).hexdigest()
    result['workload_sha256'] = hashlib.sha256(json.dumps({'cases': cases, 'repeats': 3,
        'max_tokens': 64, 'temperature': 0, 'kind': 'transport-fixtures'}, sort_keys=True).encode()).hexdigest()
    with httpx.Client(base_url=url.rstrip('/'), headers=headers, timeout=90, trust_env=False) as client:
        for prompt, expected in cases * 3:
            start = time.monotonic()
            try:
                response = client.post('/v1/chat/completions', json={'model': model,
                    'messages': [{'role': 'user', 'content': prompt}], 'temperature': 0,
                    'max_tokens': 64, 'stream': False})
                response.raise_for_status()
                body = decode_completed_response(response.json())
                choice = body['choices'][0]
                text = choice['message']['content']
                passed = choice.get('finish_reason') == 'stop' and text.strip() == expected
                sample = {'passed': passed, 'response': text[:2048]}
            except (httpx.HTTPError, KeyError, ValueError, IndexError, TypeError) as error:
                sample = {'passed': False, 'error': type(error).__name__}
            result['samples'].append({**sample, 'seconds': time.monotonic() - start, 'expected': expected})
        try:
            with client.stream('POST', '/v1/chat/completions', json={'model': model,
                'messages': [{'role': 'user', 'content': 'Count upward indefinitely, one number at a time.'}],
                'max_tokens': 512, 'stream': True, 'temperature': 0}) as stream:
                stream.raise_for_status()
                deadline = time.monotonic() + 30
                for line in stream.iter_lines():
                    if time.monotonic() > deadline:
                        break
                    if line.startswith('data: ') and line != 'data: [DONE]':
                        chunk = json.loads(line[6:])
                        delta = chunk.get('choices', [{}])[0].get('delta', {})
                        if any(isinstance(delta.get(key), str) and delta[key] for key in ('content', 'reasoning_content')):
                            result['streaming'] = True
                            break
            if result['streaming']:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    slots = client.get('/slots', timeout=2)
                    slots.raise_for_status()
                    values = slots.json()
                    if type(values) is list and values and all(slot.get('is_processing') is False for slot in values):
                        result['cancellation'] = True
                        break
                    time.sleep(.1)
                response = client.post('/v1/chat/completions', json={'model': model,
                    'messages': [{'role': 'user', 'content': 'Reply with exactly READY.'}],
                    'temperature': 0, 'max_tokens': 32}, timeout=30)
                result['recovery'] = response.status_code == 200 and bool(response.json().get('choices'))
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as error:
            result['capability_error'] = type(error).__name__
    result['task_success'] = sum(sample['passed'] for sample in result['samples']) / len(result['samples'])
    result['median_seconds'] = statistics.median(sample['seconds'] for sample in result['samples'])
    result['scope'] = 'Transport, exact-answer fixtures, streaming disconnect, and next-request recovery; not representative coding quality'
    return result
