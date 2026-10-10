"""Final-transcript bridge; recording and speech recognition stay external."""

import json
import re
import uuid

from .engine import Harness
from .memory import digest


class TranscriptBridge:
    def __init__(self, config, memory, workspace, model=None, offline=False, backend=None):
        self.engine = Harness(config, memory, workspace, model, backend)
        self.memory, self.offline = memory, offline
        self.interim = {}
        with memory.db:
            memory.db.execute('''CREATE TABLE IF NOT EXISTS transcripts (
                key TEXT PRIMARY KEY, text_hash TEXT NOT NULL, session TEXT NOT NULL)''')

    def accept(self, event):
        if not isinstance(event, dict) or set(event) != {'source', 'id', 'revision', 'text', 'final'}:
            raise ValueError('Transcript requires source, id, revision, text, final')
        for field in ('source', 'id'):
            if not isinstance(event[field], str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', event[field]):
                raise ValueError(f'Invalid transcript {field}')
        if type(event['revision']) is not int or not 0 <= event['revision'] <= 1_000_000_000:
            raise ValueError('revision must be an integer from 0 to 1000000000')
        text = event['text']
        if not isinstance(text, str) or len(text.encode()) > 16000 or '\x00' in text or type(event['final']) is not bool:
            raise ValueError('Invalid transcript text or final flag')
        key = digest([str(self.engine.tools.root), event['source'], event['id']])
        previous = self.memory.db.execute('SELECT text_hash,session FROM transcripts WHERE key=?', (key,)).fetchone()
        if previous:
            return {'status': 'duplicate' if previous['text_hash'] == digest(text) else 'consumed_revision',
                    'session': previous['session'], 'executed': False}
        old = self.interim.get(key)
        if old and event['revision'] < old['revision']:
            return {'status': 'stale', 'executed': False}
        if old and event['revision'] == old['revision'] and text != old['text']:
            raise ValueError('A transcript revision cannot change text; increment revision')
        if not event['final']:
            if key not in self.interim and len(self.interim) >= 1024:
                raise ValueError('Too many unfinished utterances; restart the transcript bridge')
            self.interim[key] = event.copy()
            return {'status': 'waiting_for_final', 'executed': False}
        self.interim.pop(key, None)
        match = re.match(r'^(?:swarm mojo|aeon)(?:[:,]?\s+)([\s\S]+)$', text.strip(), re.I)
        if not match or not match[1].strip():
            return {'status': 'not_addressed', 'executed': False}
        goal = match[1].strip()
        # Spoken confirmation never approves an existing mutation ticket.
        if goal.casefold() in {'confirm', 'yes', 'approve', 'cancel'}:
            return {'status': 'use_explicit_session_controls', 'executed': False}
        sid = uuid.uuid4().hex[:16]
        # Receipt and session are committed atomically BEFORE running any tool.
        # A duplicate after a crash points to the session for manual inspection.
        with self.memory.db:
            cursor = self.memory.db.execute('INSERT OR IGNORE INTO transcripts VALUES(?,?,?)',
                                            (key, digest(text), sid))
            if cursor.rowcount != 1:
                previous = self.memory.db.execute('SELECT session FROM transcripts WHERE key=?', (key,)).fetchone()
                return {'status': 'duplicate', 'session': previous['session'], 'executed': False}
            self.memory.db.execute('INSERT INTO sessions(id,goal,workspace,status) VALUES(?,?,?,?)',
                                   (sid, goal, str(self.engine.tools.root), 'active'))
        self.memory.event(sid, 'goal', {'text': goal})
        self.memory.event(sid, 'transcript', {'source': event['source'], 'id': event['id'], 'revision': event['revision']})
        result = self.engine.run(sid=sid, offline=self.offline)
        return {'status': 'submitted', 'session': sid, 'result': result}


def serve(bridge, source, sink):
    """One bounded JSON event per line; serial work, no background microphone."""
    while True:
        line = source.readline(65537)
        if not line:
            return
        if len(line) > 65536:
            raise ValueError('Transcript event exceeds 64 KiB')
        try:
            result = bridge.accept(json.loads(line))
        except (ValueError, OSError, RuntimeError) as exc:
            result = {'status': 'error', 'error': str(exc)}
        sink.write(json.dumps(result, ensure_ascii=True, allow_nan=False) + '\n')
        sink.flush()
