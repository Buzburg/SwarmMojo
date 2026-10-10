"""Explicit source indexing and lexical recall; excerpts never become facts."""

import re
import math
import sqlite3
import time

from .evidence import documents
from .memory import digest
from .recovery import redact


def tokens(text):
    """Keep identifiers intact and expose snake/camel/acronym components."""
    words = re.findall(r'\w+', text)
    expanded = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', text)
    expanded = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', expanded).replace('_', ' ')
    return set(w.casefold() for w in words + re.findall(r'\w+', expanded))


def search_text(path, text):
    return ' '.join(sorted(tokens(path) | tokens(text)))


def chunks(text, size=1200):
    """Contiguous character slices, preserving long lines and exact source offsets."""
    line, column = 1, 1
    for offset in range(0, len(text), size):
        piece = text[offset:offset+size]
        yield {'text': piece, 'offset': offset, 'line': line, 'column': column,
               'end_line': line+piece.count('\n')}
        line += piece.count('\n')
        column = len(piece.rsplit('\n', 1)[-1])+1 if '\n' in piece else column+len(piece)


class Knowledge:
    def __init__(self, db, tools):
        self.db, self.tools = db, tools
        self.workspace = str(tools.root)
        db.executescript('''
            CREATE TABLE IF NOT EXISTS knowledge_sources (
                workspace TEXT, path TEXT, sha256 TEXT, indexed REAL, truncated INTEGER,
                PRIMARY KEY(workspace,path));
            CREATE TABLE IF NOT EXISTS knowledge_chunks (
                key TEXT PRIMARY KEY, workspace TEXT, path TEXT, offset INTEGER,
                line INTEGER, column_no INTEGER, end_line INTEGER, text TEXT, redacted INTEGER);
            CREATE INDEX IF NOT EXISTS knowledge_scope ON knowledge_chunks(workspace,path);
            CREATE TABLE IF NOT EXISTS knowledge_index_version (version INTEGER);
        ''')
        self.fts = True
        try:
            db.execute('CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(key UNINDEXED,workspace UNINDEXED,text)')
            with db:
                version = db.execute('SELECT version FROM knowledge_index_version').fetchone()
                if version is None or version[0] != 2:
                    # Rebuild derived search data only; raw excerpts and hashes stay intact.
                    db.execute('DELETE FROM knowledge_fts')
                    db.execute('DELETE FROM knowledge_index_version')
                    db.execute('INSERT INTO knowledge_index_version VALUES(2)')
                db.execute('DELETE FROM knowledge_fts WHERE key NOT IN (SELECT key FROM knowledge_chunks)')
                missing = db.execute('SELECT key,workspace,path,text FROM knowledge_chunks WHERE key NOT IN (SELECT key FROM knowledge_fts)').fetchall()
                db.executemany('INSERT INTO knowledge_fts VALUES(?,?,?)',
                               ((r[0], r[1], search_text(r[2], r[3])) for r in missing))
        except sqlite3.OperationalError as exc:
            if 'no such module' not in str(exc).lower():
                raise
            self.fts = False

    def index(self, path: str = '.') -> dict[str, object]:
        docs, coverage = documents(self.tools, path)
        total, unchanged = 0, 0
        with self.db:
            for doc in docs:
                name = doc['path']
                safe_text = redact(doc['text'], preserve_positions=True)
                previous = self.db.execute('SELECT sha256,truncated FROM knowledge_sources WHERE workspace=? AND path=?',
                                           (self.workspace, name)).fetchone()
                stored = self.db.execute('SELECT text FROM knowledge_chunks WHERE workspace=? AND path=? ORDER BY offset',
                                         (self.workspace, name)).fetchall() if previous else []
                if (previous and previous['sha256'] == doc['sha256']
                        and bool(previous['truncated']) == bool(doc['truncated'])
                        and ''.join(row['text'] for row in stored) == safe_text):
                    # Recheck redaction as well as source bytes before reusing stored text.
                    unchanged += 1
                    total += len(stored)
                    continue
                # Reindexing replaces that source atomically; unrelated sources remain.
                if self.fts:
                    self.db.execute('DELETE FROM knowledge_fts WHERE key IN (SELECT key FROM knowledge_chunks WHERE workspace=? AND path=?)',
                                    (self.workspace, name))
                self.db.execute('DELETE FROM knowledge_chunks WHERE workspace=? AND path=?', (self.workspace, name))
                self.db.execute('INSERT OR REPLACE INTO knowledge_sources VALUES(?,?,?,?,?)',
                                (self.workspace, name, doc['sha256'], time.time(), int(doc['truncated'])))
                # Redact before splitting so a credential crossing a chunk boundary
                # cannot evade matching. Preserve source line/character positions.
                for chunk in chunks(safe_text):
                    key = digest([self.workspace, name, doc['sha256'], chunk['offset']])
                    text = chunk['text']
                    self.db.execute('INSERT INTO knowledge_chunks VALUES(?,?,?,?,?,?,?,?,?)',
                                    (key, self.workspace, name, chunk['offset'], chunk['line'], chunk['column'],
                                     chunk['end_line'], text, int(text != doc['text'][chunk['offset']:chunk['offset']+len(text)])))
                    if self.fts:
                        self.db.execute('INSERT INTO knowledge_fts VALUES(?,?,?)', (key, self.workspace, search_text(name, text)))
                    total += 1
        return {'ok': True, 'indexed_files': len(docs), 'chunks': total, 'coverage': coverage,
                'updated_files': len(docs)-unchanged, 'unchanged_files': unchanged,
                'backend': 'sqlite_fts5' if self.fts else 'bounded_lexical', 'trust': 'untrusted_source_excerpts'}

    def search(self, query, limit=5):
        if not isinstance(query, str) or not 1 <= len(query) <= 4000 or type(limit) is not int or not 1 <= limit <= 10:
            raise ValueError('Recall needs a 1..4000 character query and limit 1..10')
        terms = sorted(tokens(query))[:32]
        if not terms:
            raise ValueError('Recall query has no searchable words')
        if self.fts:
            expression = ' OR '.join('"'+term+'"' for term in terms)
            rows = self.db.execute('''SELECT c.*,s.sha256,s.indexed,s.truncated FROM knowledge_fts f
                JOIN knowledge_chunks c ON c.key=f.key
                JOIN knowledge_sources s ON s.workspace=c.workspace AND s.path=c.path
                WHERE knowledge_fts MATCH ? AND c.workspace=? ORDER BY bm25(knowledge_fts),c.path,c.offset LIMIT 51''',
                (expression, self.workspace)).fetchall()
        else:
            # Portable fallback has an explicit coverage ceiling, not a hidden full scan.
            rows = self.db.execute('''SELECT c.*,s.sha256,s.indexed,s.truncated FROM knowledge_chunks c
                JOIN knowledge_sources s ON s.workspace=c.workspace AND s.path=c.path
                WHERE c.workspace=? ORDER BY c.path,c.offset LIMIT 1001''', (self.workspace,)).fetchall()
        capped = len(rows) > (50 if self.fts else 1000)
        rows = rows[:50 if self.fts else 1000]
        features = [(row, tokens(row['text']), tokens(row['path'])) for row in rows]
        weights = {term: 1 + math.log((1+len(rows))/(1+sum(term in body or term in path
                   for _, body, path in features))) for term in terms}
        ranked = []
        for row, body, path in features:
            matched = sorted(body & set(terms))
            path_matched = sorted(path & set(terms))
            score = sum(weights[t] for t in matched) + 0.25*sum(weights[t] for t in path_matched)
            if score:
                ranked.append((score, row, body, matched, path_matched))
        ranked.sort(key=lambda pair: (-pair[0], pair[1]['path'], pair[1]['offset']))
        matches, rejected, checked, seen = [], [], {}, set()
        candidates = []
        for score,row,body,matched,path_matched in ranked[:50]:
            path = row['path']
            if path not in checked:
                try:
                    current = self.tools.read(path)
                    checked[path] = current['sha256'] == row['sha256']
                    if not checked[path]:
                        rejected.append({'path': path, 'reason': 'source_changed'})
                except (OSError, ValueError) as exc:
                    checked[path] = False
                    rejected.append({'path': path, 'reason': 'source_unavailable', 'error': str(exc)})
            if not checked[path]:
                continue
            text = redact(row['text'], preserve_positions=True)
            key = digest(text)
            if key in seen:
                continue
            seen.add(key)
            candidates.append((body, {'path': path, 'sha256': row['sha256'], 'line': row['line'], 'column': row['column_no'],
                            'offset': row['offset'], 'end_line': row['end_line'], 'text': text,
                            'indexed_at': row['indexed'], 'source_truncated': bool(row['truncated']),
                            'redacted': bool(row['redacted']) or text != row['text'], 'lexical_score': score,
                            'matched_terms': matched, 'matched_path_terms': path_matched}))
        selected = []
        while candidates and len(matches) < limit:
            def utility(candidate):
                body, result = candidate
                similarity = max((len(body & other)/max(1, len(body | other)) for other in selected), default=0)
                return result['lexical_score'] * (1 - 0.35*similarity), similarity
            best = max(range(len(candidates)), key=lambda i: utility(candidates[i])[0])
            score, similarity = utility(candidates[best])
            body, result = candidates.pop(best)
            result.update(selection_score=score, similarity_to_selected=similarity)
            matches.append(result)
            selected.append(body)
        return {'ok': True, 'matches': matches, 'rejected_sources': rejected,
                'partial': capped or len(ranked)>50 or bool(rejected) or any(m['source_truncated'] for m in matches),
                'scope': 'Explicitly indexed text only; up to 50 candidate chunks revalidated against current file hashes',
                'ranking': 'code-aware candidate-local IDF; path weight 0.25; lexical diversity penalty 0.35',
                'query_terms': terms,
                'trust': 'untrusted_source_excerpts', 'backend': 'sqlite_fts5' if self.fts else 'bounded_lexical'}

    def clear(self):
        with self.db:
            if self.fts:
                self.db.execute('DELETE FROM knowledge_fts WHERE workspace=?', (self.workspace,))
            self.db.execute('DELETE FROM knowledge_chunks WHERE workspace=?', (self.workspace,))
            self.db.execute('DELETE FROM knowledge_sources WHERE workspace=?', (self.workspace,))
        return {'ok': True, 'cleared_workspace': self.workspace}
