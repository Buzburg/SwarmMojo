"""Completion checks cannot authorize actions or turn a failed check into success."""

from .tools import bounded_process, validate_action
from .recovery import redact


def validate_commands(commands):
    if not isinstance(commands, list) or len(commands) > 3:
        raise ValueError('At most three explicit verification commands are allowed')
    for argv in commands:
        validate_action({'tool': 'run_command', 'args': {'argv': argv}})
    return commands


def check(workspace, commands):
    results = []
    for argv in validate_commands(commands):
        try:
            result = bounded_process(argv, workspace, timeout=30, limit=8000)
        except OSError as exc:
            result = {'ok': False, 'error': str(exc)}
        results.append({'argv': argv, 'result': redact(result)})
    return {'ok': all(row['result']['ok'] for row in results), 'checks': results}


def assess(judge, goal, answer, events):
    # Use already-bounded evidence summaries. Never infer success from the answer alone.
    evidence = [{'action': e.get('action'), 'result': e.get('result')} for e in events[-4:]]
    return judge.ask({'goal': goal, 'proposed_answer': answer[:4000], 'evidence': evidence}, [{
        'id': 'completion', 'type': 'choice',
        'question': 'Does observed evidence establish that the entire requested work is complete?',
        'options': {'supported': 'Observed results support completion',
                    'incomplete': 'Evidence shows unfinished or failed work',
                    'unknown': 'Available evidence cannot establish completion'}}])['completion']
