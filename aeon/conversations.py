"""Workspace-scoped conversation history with append-only corrections."""

from pathlib import Path
import re
import sqlite3
import time
import uuid

from .memory import packed
from .recovery import redact


class Conversations:
    def __init__(self, memory, workspace):
        self.memory, self.db = memory, memory.db
        self.workspace = str(Path(workspace).resolve())
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY, workspace TEXT NOT NULL, title TEXT NOT NULL, created REAL);
            CREATE TABLE IF NOT EXISTS conversation_entries (
                id INTEGER PRIMARY KEY, conversation TEXT NOT NULL, role TEXT NOT NULL,
                text TEXT NOT NULL, session TEXT, replaces INTEGER, created REAL);
            CREATE INDEX IF NOT EXISTS conversation_entries_owner ON conversation_entries(conversation,id);
            CREATE INDEX IF NOT EXISTS conversation_entries_revision ON conversation_entries(replaces);
        ''')
        self.fts = True
        try:
            with self.db:
                self.db.execute('BEGIN IMMEDIATE')
                indexed = self.db.execute("SELECT 1 FROM sqlite_master WHERE name='conversation_search'").fetchone()
                tracking = self.db.execute("SELECT 1 FROM sqlite_master WHERE name='conversation_search_insert'").fetchone()
                self.db.execute('CREATE VIRTUAL TABLE IF NOT EXISTS conversation_search USING fts5(text)')
                self.db.execute('''CREATE TRIGGER IF NOT EXISTS conversation_search_insert
                    AFTER INSERT ON conversation_entries BEGIN
                    INSERT INTO conversation_search(rowid,text) VALUES(new.id,new.text); END''')
                if not indexed or not tracking:
                    self.db.execute('''INSERT INTO conversation_search(rowid,text)
                        SELECT id,text FROM conversation_entries WHERE id NOT IN
                        (SELECT rowid FROM conversation_search)''')
        except sqlite3.OperationalError as exc:
            if 'no such module: fts5' not in str(exc).lower():
                raise
            self.fts = False
            with self.db:
                self.db.execute('DROP TRIGGER IF EXISTS conversation_search_insert')

    def create(self, title='New conversation'):
        if not isinstance(title, str) or not 1 <= len(title) <= 200:
            raise ValueError('Conversation title needs 1..200 characters')
        cid = uuid.uuid4().hex[:16]
        with self.db:
            self.db.execute('INSERT INTO conversations VALUES(?,?,?,?)',
                            (cid, self.workspace, redact(title), time.time()))
        return cid

    def get(self, cid):
        row = self.db.execute('SELECT * FROM conversations WHERE id=? AND workspace=?',
                              (cid, self.workspace)).fetchone()
        if row is None:
            raise ValueError('Unknown conversation in this workspace')
        return dict(row)

    def list(self):
        return [dict(r) for r in self.db.execute(
            'SELECT * FROM conversations WHERE workspace=? ORDER BY created DESC LIMIT 100', (self.workspace,))]

    def entries(self, cid):
        self.get(cid)
        return [dict(r) for r in self.db.execute(
            'SELECT * FROM conversation_entries WHERE conversation=? ORDER BY id DESC LIMIT 200', (cid,))][::-1]

    def append(self, cid, role, text, session=None, replaces=None):
        self.get(cid)
        if role not in {'user', 'assistant', 'note', 'correction'}:
            raise ValueError('Invalid conversation role')
        if not isinstance(text, str) or not 1 <= len(text.encode()) <= 32000:
            raise ValueError('Entry needs 1..32000 UTF-8 bytes')
        if (role == 'correction') != (replaces is not None):
            raise ValueError('Only corrections replace earlier entries')
        if session is not None:
            if self.memory.session(session)['workspace'] != self.workspace:
                raise ValueError('Session belongs to another workspace')
        with self.db:
            if replaces is not None:
                row = self.db.execute('SELECT id FROM conversation_entries WHERE id=? AND conversation=?',
                                      (replaces, cid)).fetchone()
                if row is None:
                    raise ValueError('Correction source is not in this conversation')
                if self.db.execute('SELECT 1 FROM conversation_entries WHERE replaces=?', (replaces,)).fetchone():
                    raise ValueError('Entry already corrected; correct its current revision')
            cursor = self.db.execute('INSERT INTO conversation_entries(conversation,role,text,session,replaces,created) VALUES(?,?,?,?,?,?)',
                                     (cid, role, redact(text), session, replaces, time.time()))
        return cursor.lastrowid

    def entry(self, cid, entry_id):
        """Inspect one source revision without changing historical task context."""
        self.get(cid)
        if type(entry_id) is not int or not 1 <= entry_id <= 9223372036854775807:
            raise ValueError('Entry ID must be a positive SQLite integer')
        row = self.db.execute('''SELECT e.*,
            (SELECT n.id FROM conversation_entries n WHERE n.replaces=e.id LIMIT 1) AS superseded_by
            FROM conversation_entries e WHERE e.id=? AND e.conversation=?''', (entry_id, cid)).fetchone()
        if row is None:
            raise ValueError('Entry is not in this conversation')
        return dict(row)

    def search(self, cid, query, limit=10):
        """Current revisions only; retrieval is evidence selection, not validation."""
        self.get(cid)
        if not isinstance(query, str) or len(query.encode()) > 16000:
            raise ValueError('Search query must be text of at most 16000 UTF-8 bytes')
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError('Search limit must be 1..50')
        words = list(dict.fromkeys(re.findall(r'\w+', query.casefold())))[:32]
        mode = 'fts5_full_history' if self.fts else 'lexical_latest_1000'
        if not words:
            return {'entries': [], 'mode': mode}
        if self.fts:
            expression = ' OR '.join('"' + word + '"' for word in words)
            rows = self.db.execute('''SELECT e.* FROM conversation_search
                JOIN conversation_entries e ON e.id=conversation_search.rowid
                WHERE conversation_search MATCH ? AND e.conversation=?
                AND NOT EXISTS(SELECT 1 FROM conversation_entries n WHERE n.replaces=e.id)
                ORDER BY bm25(conversation_search),e.id DESC LIMIT ?''', (expression, cid, limit))
            results = [dict(r) for r in rows]
        else:
            rows = self.db.execute('''SELECT e.* FROM conversation_entries e
                WHERE e.conversation=? AND NOT EXISTS
                (SELECT 1 FROM conversation_entries n WHERE n.replaces=e.id)
                ORDER BY e.id DESC LIMIT 1000''', (cid,))
            ranked = [(len(set(words) & set(re.findall(r'\w+', r['text'].casefold()))), dict(r)) for r in rows]
            results = [r for score, r in sorted(ranked, key=lambda pair: (-pair[0], -pair[1]['id'])) if score][:limit]
        return {'entries': results, 'mode': mode}

    def context(self, cid, query):
        """Recent current revisions plus lexical notes; no inferred facts."""
        self.get(cid)
        rows = [dict(r) for r in self.db.execute('''
            SELECT e.* FROM conversation_entries e WHERE e.conversation=?
            AND NOT EXISTS(SELECT 1 FROM conversation_entries newer WHERE newer.replaces=e.id)
            ORDER BY e.id DESC LIMIT 6''', (cid,))]
        matches = self.search(cid, query)
        recent_ids = {r['id'] for r in rows}
        candidates = rows + [r for r in matches['entries'] if r['id'] not in recent_ids][:4]
        selected, used = [], 0
        for row in candidates:
            entry = {k:row[k] for k in ('id', 'role', 'text', 'session', 'replaces')}
            size = len(packed(entry).encode())
            if used+size > 8000:
                continue
            used += size
            selected.append(entry)
        observations, sessions = [], set()
        for entry in selected:
            sid = entry['session']
            if not sid or sid in sessions:
                continue
            sessions.add(sid)
            for event in self.memory.events(sid)[::-1]:
                if event['kind'] != 'tool':
                    continue
                snapshot = {'session': sid, 'event': event, 'historical': True}
                size = len(packed(snapshot).encode())
                if used+size <= 8000 and len(observations) < 4:
                    used += size
                    observations.append(snapshot)
        return {'source': 'conversation_history', 'conversation': cid,
                'trust': 'untrusted_history_not_authorization',
                'entries': sorted(selected, key=lambda r:r['id']),
                'observations': observations,
                'bounded': True, 'retrieval': matches['mode'],
                'scope': 'Six recent revisions plus up to four lexical matches; up to 8000 bytes selected'}


def chat(config, memory, workspace, cid, text, offline=False, backend=None):
    """One user message is one bounded task; history never grants approval."""
    from .engine import Harness
    if not isinstance(text, str) or not 1 <= len(text.encode()) <= 16000:
        raise ValueError('Message needs 1..16000 UTF-8 bytes')
    store = Conversations(memory, workspace)
    context = store.context(cid, text)
    store.append(cid, 'user', text)
    result = Harness(config, memory, workspace, backend=backend).run(
        text, offline=offline, conversation_context=context)
    store.append(cid, 'assistant', result['answer'] or result['status'], session=result['session'])
    return result
