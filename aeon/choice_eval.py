"""Variable-menu evaluation with calibration and context-permutation controls."""

import json
import math
from pathlib import Path
import time

from .memory import digest


def read_rows(path):
    path = Path(path)
    if path.stat().st_size > 512000:
        raise ValueError('Evaluation input exceeds 512 KB')
    rows = []
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            raise ValueError(f'Invalid JSON on line {number}') from None
    validate_rows(rows)
    return rows


def validate_rows(rows):
    if not isinstance(rows, list) or not 2 <= len(rows) <= 100:
        raise ValueError('Choice evaluation needs 2..100 held-out examples')
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not {'context', 'options', 'label'} <= set(row) or set(row)-{'context', 'options', 'label', 'group'}:
            raise ValueError(f'Row {index}: expected context, options, label, optional group')
        options = row['options']
        if not isinstance(row['context'], str) or not row['context'] or len(row['context'].encode()) > 16000:
            raise ValueError(f'Row {index}: invalid context')
        if (not isinstance(options, list) or not 2 <= len(options) <= 26
                or any(not isinstance(s, str) or not s or len(s)>2000 for s in options)
                or len(set(options)) != len(options)):
            raise ValueError(f'Row {index}: options must be 2..26 distinct bounded strings')
        if type(row['label']) is not int or not 0 <= row['label'] < len(options):
            raise ValueError(f'Row {index}: invalid zero-based label')
        if 'group' in row and (not isinstance(row['group'], str) or not row['group'] or len(row['group']) > 128):
            raise ValueError(f'Row {index}: invalid group')


def metrics(rows):
    if not rows:
        return None
    bins = [[] for _ in range(10)]
    top1 = top3 = top5 = reciprocal_rank = brier = nll = 0
    sizes = {}
    for row in rows:
        probabilities, label = row['probabilities'], row['label']
        if (not isinstance(probabilities, list) or not probabilities
                or any(type(p) not in (float, int) or not math.isfinite(p) or not 0 <= p <= 1 for p in probabilities)
                or not math.isclose(sum(probabilities), 1, abs_tol=1e-6)
                or type(label) is not int or not 0 <= label < len(probabilities)):
            raise ValueError('Invalid evaluation probabilities or label')
        ranked = sorted(range(len(probabilities)), key=lambda i: (-probabilities[i], i))
        confidence = probabilities[ranked[0]]
        correct = ranked[0] == label
        top1 += correct
        top3 += label in ranked[:3]
        top5 += label in ranked[:5]
        reciprocal_rank += 1/(ranked.index(label)+1)
        group = sizes.setdefault(str(len(probabilities)), {'examples': 0, 'correct': 0})
        group['examples'] += 1
        group['correct'] += int(correct)
        bins[min(9, int(confidence*10))].append((confidence, correct))
        brier += sum((p-int(i == label))**2 for i,p in enumerate(probabilities))
        nll -= math.log(max(probabilities[label], 1e-15))
    count = len(rows)
    calibration = [{'lower': i/10, 'upper': (i+1)/10, 'count': len(bucket),
                    'confidence': sum(c for c,_ in bucket)/len(bucket) if bucket else None,
                    'accuracy': sum(y for _,y in bucket)/len(bucket) if bucket else None}
                   for i,bucket in enumerate(bins)]
    return {'examples': count, 'top1': top1/count, 'top3': top3/count,
            'top5': top5/count, 'mean_reciprocal_rank': reciprocal_rank/count,
            'by_menu_size': {size: {**group, 'accuracy': group['correct']/group['examples']}
                             for size, group in sizes.items()},
            'ece': sum(b['count']/count*abs(b['confidence']-b['accuracy']) for b in calibration if b['count']),
            'brier': brier/count, 'negative_log_likelihood': nll/count,
            'random_top1': sum(1/len(r['probabilities']) for r in rows)/count,
            'calibration_bins': calibration}


def evaluate(judge, rows):
    validate_rows(rows)
    results, normal, shuffled = [], [], []
    timings = {'forward': [], 'reversed': [], 'control': []}
    cached = {phase: 0 for phase in timings}
    initial_calls = judge.calls
    def ask(phase, state, question, reverse=False):
        begin = time.monotonic()
        result = judge.ask(state, [question], reverse=reverse)['selection']
        timings[phase].append((time.monotonic()-begin)*1000)
        cached[phase] += bool(result.get('cached'))
        return result
    started = time.monotonic()
    for index, row in enumerate(rows):
        question = {'id': 'selection', 'type': 'choice',
                    'question': 'Select the option best supported by the observed context.',
                    'options': {str(i): text for i,text in enumerate(row['options'])}}
        state = {'context': row['context']}
        forward = ask('forward', state, question)
        reverse = ask('reversed', state, question, reverse=True)
        normal.append({'probabilities': [forward['probabilities'][str(i)] for i in range(len(row['options']))],
                       'label': row['label']})
        # Deterministic cyclic search excludes identical contexts and same known group.
        donor = next(((index+step) % len(rows) for step in range(1, len(rows))
                      if rows[(index+step) % len(rows)]['context'] != row['context']
                      and not ('group' in row and rows[(index+step) % len(rows)].get('group') == row['group'])), None)
        control = None
        if donor is not None:
            control = ask('control', {'context': rows[donor]['context']}, question)
            shuffled.append({'probabilities': [control['probabilities'][str(i)] for i in range(len(row['options']))],
                             'label': row['label']})
        results.append({'index': index, 'label': row['label'], 'context_hash': digest(row['context']),
                        'forward': forward, 'reversed': reverse, 'control_context_index': donor, 'control': control})
    matched = [normal[i] for i,r in enumerate(results) if r['control'] is not None]
    return {'model': metrics(normal), 'shuffled_context': metrics(shuffled),
            'selective': selective_metrics(results),
            'matched_control_baseline': metrics(matched), 'control_skipped': len(rows)-len(shuffled),
            'order_disagreements': sum(r['forward']['choice'] != r['reversed']['choice'] for r in results),
            'elapsed_seconds': round(time.monotonic()-started, 3), 'decision_calls': judge.calls-initial_calls,
            'request_latency_ms': {phase: latency_summary(values, cached[phase]) for phase,values in timings.items()},
            'dataset_hash': digest(rows), 'calibrated': False,
            'note': 'Empirical metrics only. Keep related groups out of training and model selection. Shuffled contexts may coincidentally support the same answer.',
            'rows': results}


def latency_summary(values, cache_hits):
    """Nearest-rank percentiles of whole requests, including local preparation."""
    ordered = sorted(values)
    return {'requests': len(values), 'cache_hits': cache_hits,
            'p50': ordered[math.ceil(len(ordered)*.5)-1] if ordered else None,
            'p95': ordered[math.ceil(len(ordered)*.95)-1] if ordered else None,
            'note': 'Whole-request wall time; includes cache hits and cold setup, excludes failed requests. Nearest-rank percentiles.'}


def selective_metrics(results):
    """Fixed diagnostic thresholds, never selected automatically on test labels."""
    summaries = []
    for threshold, margin in ((0.5, 0.0), (0.7, 0.15), (0.9, 0.3)):
        accepted = []
        for row in results:
            forward, reverse = row['forward'], row['reversed']
            # Require both orders to clear the same gates after label remapping.
            if forward['choice'] != reverse['choice']:
                continue
            if all(answer['probabilities'][answer['choice']] >= threshold
                   and answer['margin'] >= margin for answer in (forward, reverse)):
                accepted.append(int(forward['choice']) == row['label'])
        summaries.append({'threshold': threshold, 'margin': margin, 'accepted': len(accepted),
                          'abstained': len(results)-len(accepted),
                          'coverage': len(accepted)/len(results) if results else 0.0,
                          'accuracy_when_accepted': sum(accepted)/len(accepted) if accepted else None,
                          'wrong_accepted': len(accepted)-sum(accepted)})
    return summaries
