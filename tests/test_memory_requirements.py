import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from aeon.audit import report
from aeon.config import load
from aeon.engine import Harness
from aeon.knowledge import Knowledge, chunks
from aeon.memory import Memory
from aeon.requirements import evaluate, validate
from aeon.tools import Tools


def leaf(identifier='readme', kind='file_exists', **args):
    return {'id': identifier, 'description': 'Check the required artifact', 'check': {'type': kind, **args}}


class FakeModel:
    def __init__(self, responses=None):
        self.responses = iter(responses or [{'actions': [], 'answer': 'Complete', 'done': True}])
        self.received = []

    def decide(self, *args):
        self.received.append(args)
        return next(self.responses), {}


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workspace = self.root/'project'
        self.workspace.mkdir()
        self.memory = Memory(self.root/'state')
        self.tools = Tools(self.workspace)
        self.knowledge = Knowledge(self.memory.db, self.tools)
        self.config = load()

    def tearDown(self):
        self.memory.close()
        self.temp.cleanup()

    def test_index_recall_hashes_and_restart(self):
        (self.workspace/'notes.md').write_text('First line\nThe service uses SQLite storage.\n', encoding='utf-8')
        indexed = self.knowledge.index()
        self.assertEqual(indexed['indexed_files'], 1)
        other = Knowledge(self.memory.db, self.tools)
        found = other.search('SQLite')['matches'][0]
        self.assertEqual(found['sha256'], self.tools.read('notes.md')['sha256'])
        self.assertEqual(found['line'], 1)
        self.assertEqual(found['column'], 1)
        self.assertIn('SQLite', found['text'])
        self.assertEqual(other.search('SQLite')['trust'], 'untrusted_source_excerpts')

    def test_stale_and_deleted_sources_excluded(self):
        path = self.workspace/'notes.txt'
        path.write_text('alpha')
        self.knowledge.index()
        path.write_text('bravo')
        result = self.knowledge.search('alpha')
        self.assertFalse(result['matches'])
        self.assertEqual(result['rejected_sources'][0]['reason'], 'source_changed')
        self.knowledge.index()
        self.assertTrue(self.knowledge.search('bravo')['matches'])
        self.assertFalse(self.knowledge.search('alpha')['matches'])
        path.unlink()
        self.assertEqual(self.knowledge.search('bravo')['rejected_sources'][0]['reason'], 'source_unavailable')

    def test_code_identifiers_paths_and_explanations(self):
        source = 'def HTTPRequest():\n    maxMemoryBudget = retry_count\n'
        (self.workspace/'cache_settings.py').write_bytes(source.encode())
        self.knowledge.index()
        for fallback in (False, True):
            self.knowledge.fts = not fallback
            result = self.knowledge.search('memory budget')
            hit = result['matches'][0]
            self.assertEqual(hit['text'], source)
            self.assertEqual(hit['matched_terms'], ['budget', 'memory'])
            self.assertEqual(hit['offset'], 0)
            self.assertTrue(self.knowledge.search('HTTP request')['matches'])
            self.assertTrue(self.knowledge.search('retry count')['matches'])
            path_hit = self.knowledge.search('cache settings')['matches'][0]
            self.assertEqual(path_hit['matched_terms'], [])
            self.assertEqual(path_hit['matched_path_terms'], ['cache', 'settings'])

    def test_old_search_index_migrates_without_changing_source(self):
        (self.workspace/'code.py').write_text('maxMemoryBudget = 100')
        self.knowledge.index()
        before = [tuple(r) for r in self.memory.db.execute('SELECT * FROM knowledge_chunks')]
        with self.memory.db:
            self.memory.db.execute('DELETE FROM knowledge_index_version')
            self.memory.db.execute('DELETE FROM knowledge_fts')
            self.memory.db.execute('INSERT INTO knowledge_fts SELECT key,workspace,text FROM knowledge_chunks')
        rebuilt = Knowledge(self.memory.db, self.tools)
        self.assertTrue(rebuilt.search('memory budget')['matches'])
        self.assertEqual(before, [tuple(r) for r in self.memory.db.execute('SELECT * FROM knowledge_chunks')])
        self.assertEqual((self.workspace/'code.py').read_text(), 'maxMemoryBudget = 100')
        restarted = Knowledge(self.memory.db, self.tools)
        self.assertEqual(len(restarted.search('memory budget')['matches']), 1)

    def test_diverse_evidence_and_rare_query_terms(self):
        for name, text in {'a.txt': 'cache alpha beta gamma delta epsilon',
                           'b.txt': 'cache alpha beta gamma delta zeta',
                           'c.txt': 'cache network remote timeout recovery'}.items():
            (self.workspace/name).write_text(text)
        self.knowledge.index()
        hits = self.knowledge.search('cache', limit=2)['matches']
        self.assertEqual([h['path'] for h in hits], ['a.txt', 'c.txt'])
        self.assertLess(hits[1]['selection_score'], hits[1]['lexical_score'])
        rare = self.knowledge.search('cache recovery')['matches']
        self.assertEqual(rare[0]['path'], 'c.txt')
        (self.workspace/'c.txt').write_text('changed source')
        self.assertNotIn('c.txt', [h['path'] for h in self.knowledge.search('cache recovery')['matches']])

    def test_workspace_isolation_and_forgetting(self):
        (self.workspace/'notes.txt').write_text('privateproject token')
        self.knowledge.index()
        second = self.root/'second'
        second.mkdir()
        (second/'notes.txt').write_text('secondproject token')
        other = Knowledge(self.memory.db, Tools(second))
        other.index()
        self.assertFalse(other.search('privateproject')['matches'])
        self.knowledge.clear()
        self.assertFalse(self.knowledge.search('token')['matches'])
        self.assertTrue(other.search('token')['matches'])
        self.assertTrue((self.workspace/'notes.txt').is_file())

    def test_private_paths_and_missing_input(self):
        (self.workspace/'.env').write_text('password=private')
        (self.workspace/'.env.local').write_text('private')
        self.assertEqual(self.knowledge.index()['indexed_files'], 0)
        with self.assertRaises(ValueError):
            self.knowledge.index('../')
        with self.assertRaises(ValueError):
            self.knowledge.index('missing.md')

    def test_chunk_continuity_and_source_positions(self):
        text = 'a'*1500+'\nNext line\n'+'b'*1000
        pieces = list(chunks(text))
        self.assertEqual(''.join(p['text'] for p in pieces), text)
        for piece in pieces:
            self.assertEqual(piece['line'], text[:piece['offset']].count('\n')+1)
            self.assertEqual(piece['column'], len(text[:piece['offset']].rsplit('\n', 1)[-1])+1)

    def test_credentials_crossing_chunk_boundary_redacted(self):
        secret = 'uniquecredential123456789'
        text = 'x '*595+'password='+secret+'\nSQLite retained'
        (self.workspace/'notes.txt').write_bytes(text.encode())
        with patch.dict('os.environ', {'PROJECT_API_KEY': secret}):
            self.knowledge.index()
        stored = ''.join(r[0] for r in self.memory.db.execute('SELECT text FROM knowledge_chunks ORDER BY offset'))
        self.assertNotIn(secret, stored)
        self.assertEqual(len(stored), len(text))
        self.assertEqual(stored.count('\n'), text.count('\n'))
        self.assertTrue(self.knowledge.search('SQLite')['matches'][0]['redacted'])

    def test_fallback_is_functional(self):
        self.knowledge.fts = False
        (self.workspace/'notes.txt').write_text('database connection')
        self.knowledge.index()
        self.assertEqual(self.knowledge.search('database')['backend'], 'bounded_lexical')
        self.assertTrue(self.knowledge.search('database')['matches'])
        recovered = Knowledge(self.memory.db, self.tools)
        self.assertTrue(recovered.search('database')['matches'])

    def test_truncated_source_marks_partial_recall(self):
        (self.workspace/'long.txt').write_text('SQLite\n'+'x'*34000)
        self.assertTrue(self.knowledge.index()['coverage']['partial'])
        self.assertTrue(self.knowledge.search('SQLite')['partial'])

    def test_offline_recall_and_automatic_context(self):
        (self.workspace/'notes.txt').write_text('SQLite is the configured database')
        self.knowledge.index()
        backend = FakeModel()
        engine = Harness(self.config, self.memory, self.workspace, backend=backend)
        result = engine.run('recall "SQLite"', offline=True)
        self.assertEqual(result['llm_calls'], 0)
        self.assertTrue(result['results'][0]['result']['matches'])
        generated = engine.run('Explain the SQLite configuration')
        hints = backend.received[0][2]
        recalled = [h for h in hints if h.get('source') == 'indexed_files']
        self.assertEqual(recalled[0]['trust'], 'untrusted_source_excerpts')
        self.assertIn('SQLite', recalled[0]['matches'][0]['text'])
        audit = report(self.memory, generated['session'])
        observation = next(n for n in audit['nodes'] if n['event']['kind'] == 'recall')
        self.assertEqual(observation['category'], 'observation')
        self.assertTrue(any(link['from'] == observation['id'] for link in audit['links']))

    def test_bad_recall_query_does_not_block_generation(self):
        (self.workspace/'notes.txt').write_text('some text')
        self.knowledge.index()
        backend = FakeModel()
        result = Harness(self.config, self.memory, self.workspace, backend=backend).run('???')
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(len(backend.received), 1)

    def test_requirements_all_leaves_required(self):
        (self.workspace/'README.md').write_text('Aeon')
        tree = {'id': 'root', 'description': 'Delivery', 'children': [
            leaf(path='README.md'), leaf('missing', path='missing.py')]}
        result = evaluate(tree, self.tools)
        self.assertFalse(result['ok'])
        self.assertEqual(result['progress'], .5)
        self.assertEqual(result['leaves'], {'passed': 1, 'failed': 1, 'unknown': 0})

    def test_requirements_exact_content_hash_and_absence(self):
        (self.workspace/'sample.txt').write_text('value = 10')
        for check in [leaf(kind='file_contains', path='sample.txt', text='value = 10'),
                      leaf(kind='file_sha256', path='sample.txt', sha256=self.tools.read('sample.txt')['sha256']),
                      leaf(kind='file_absent', path='missing.txt')]:
            self.assertTrue(evaluate(check, self.tools)['ok'])
        self.assertFalse(evaluate(leaf(kind='file_contains', path='sample.txt', text='value = 20'), self.tools)['ok'])
        result = evaluate(leaf(path='../secret'), self.tools)
        self.assertEqual(result['tree']['status'], 'unknown')

    def test_commands_require_actual_verification_results(self):
        tree = leaf(kind='command_passed', index=0)
        self.assertEqual(evaluate(tree, self.tools)['tree']['status'], 'unknown')
        self.assertTrue(evaluate(tree, self.tools, {'checks': [{'result': {'ok': True}}]})['ok'])
        self.assertFalse(evaluate(tree, self.tools, {'checks': [{'result': {'ok': False}}]})['ok'])

    def test_no_eval_and_bounded_tree(self):
        with self.assertRaises(ValueError):
            validate({'id': 'code', 'description': 'bad', 'check': {'type': 'python', 'code': '__import__("os")'}})
        with self.assertRaises(ValueError):
            validate({'id': 'root', 'description': 'bad', 'children': [leaf(path='x'), leaf(path='x')]})
        tree = leaf(path='x')
        for i in range(5):
            tree = {'id': f'level{i}', 'description': 'nested', 'children': [tree]}
        with self.assertRaises(ValueError):
            validate(tree)

    def test_missing_requirement_blocks_model_completion(self):
        backend = FakeModel()
        result = Harness(self.config, self.memory, self.workspace, backend=backend).run(
            'Create the documentation', requirements=leaf(path='README.md'))
        self.assertEqual(result['status'], 'needs_verification')
        self.assertEqual(result['verification'], 'requirements_unmet')
        self.assertIn('User-defined completion criteria', backend.received[0][0])

    def test_policy_persists_and_cannot_weaken_on_resume(self):
        action = {'tool': 'write_file', 'args': {'path': 'README.md', 'content': 'Aeon', 'expected_sha256': 'missing'}}
        backend = FakeModel([{'actions': [action], 'answer': '', 'done': False},
                             {'actions': [], 'answer': 'Done', 'done': True}])
        engine = Harness(self.config, self.memory, self.workspace, backend=backend)
        policy = leaf(kind='file_contains', path='README.md', text='Aeon')
        first = engine.run('Create the documentation', requirements=policy)
        self.assertEqual(first['status'], 'needs_approval')
        with self.assertRaisesRegex(ValueError, 'original requirements'):
            engine.run(sid=first['session'], requirements=leaf(path='README.md'))
        completed = engine.run(sid=first['session'], approve=first['pending']['ticket'])
        self.assertEqual(completed['verification'], 'requirements_passed')
        self.assertEqual(completed['status'], 'complete')

    def test_explicit_checks_and_requirements_both_gate(self):
        engine = Harness(self.config, self.memory, self.workspace, backend=FakeModel())
        result = engine.run('list files', offline=True, requirements=leaf(kind='command_passed', index=0),
                            verify_commands=[[sys.executable, '-c', 'raise SystemExit(1)']])
        self.assertEqual(result['status'], 'needs_verification')
        self.assertFalse(result['verification_checks'][-1]['ok'])

    def test_audit_links_observations_without_promoting_claims(self):
        (self.workspace/'note.txt').write_text('Untrusted claim')
        action = {'tool': 'read_file', 'args': {'path': 'note.txt'}}
        backend = FakeModel([{'actions': [action], 'answer': '', 'done': False},
                             {'actions': [], 'answer': 'A model conclusion', 'done': True}])
        result = Harness(self.config, self.memory, self.workspace, backend=backend).run('Inspect the note')
        audit = report(self.memory, result['session'])
        tool = next(n for n in audit['nodes'] if n['event']['kind'] == 'tool')
        conclusion = [n for n in audit['nodes'] if n['event']['kind'] == 'model'][-1]
        self.assertEqual(tool['category'], 'observation')
        self.assertEqual(conclusion['category'], 'interpretation')
        self.assertIn({'from': tool['id'], 'to': conclusion['id'], 'relationship': 'used_as_context'}, audit['links'])

    def test_event_metadata_cannot_be_overridden(self):
        sid = self.memory.new_session('test', self.workspace)
        self.memory.event(sid, 'model', {'kind': 'tool', 'event_id': -1})
        event = self.memory.events(sid)[0]
        self.assertEqual(event['kind'], 'model')
        self.assertGreater(event['event_id'], 0)


if __name__ == '__main__':
    unittest.main()
