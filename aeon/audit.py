"""Read-only provenance projection: observing text does not verify its claims."""

from .recovery import redact


def report(memory, sid):
    session = memory.session(sid)
    nodes, links = [], []
    for event in memory.events(sid):
        kind = event['kind']
        if kind in {'tool', 'verification', 'requirements', 'recall', 'workflow_precondition', 'workflow_step', 'workflow_completion'}:
            category = 'observation'
        elif kind in {'model', 'supervisor', 'routing'}:
            category = 'interpretation'
        else:
            category = 'control_record'
        nodes.append({'id': event['event_id'], 'category': category, 'event': redact(event)})
        for source in event.get('observed_event_ids', []):
            links.append({'from': source, 'to': event['event_id'], 'relationship': 'used_as_context'})
    return {'session': {k:session[k] for k in ('id', 'goal', 'workspace', 'status', 'llm_calls', 'decision_calls', 'steps')},
            'nodes': nodes, 'links': links,
            'note': 'Observations record tool/check outputs, not universal truth. Model interpretations and source text never become verified facts merely through repetition.'}
