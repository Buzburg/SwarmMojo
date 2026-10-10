import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from aeon.config import load
from aeon.decisions import DecisionClient, distribution, route, validate_question
from aeon.engine import Harness
from aeon.evaluation import evaluate
from aeon.evidence import search, review, verify_claim, documents
from aeon.inference import SGLang, InferenceError
from aeon.memory import Memory
from aeon.recovery import diagnose, redact
from aeon.tools import Tools


QUESTION = {'id': 'test', 'type': 'choice', 'question': 'Which?',
            'options': {'yes': 'Supported', 'unknown': 'Not established'}}


class Backend:
    def __init__(self):
        self.profile = {'model_path': 'test/model', 'context_length': 8192}
        self.url, self.key = 'http://127.0.0.1:1', ''
        self.requests = []
        self.version = 1
        self.bad = False

    def info(self):
        return {'model_path': 'test/model', 'version': self.version}

    def call(self, path, body):
        self.requests.append((path, body))
        if path == '/v1/tokenize':
            return {'tokens': [ord(body['prompt'])] if 'prompt' in body else [1, 2, 3]}
        if path == '/v1/detokenize':
            return {'text': chr(body['tokens'][0])}
        return {'meta_info': {'completion_tokens': 1,
                'output_token_ids_logprobs': [[[float('nan') if self.bad else (-.01 if i == 0 else -10), t, None]
                    for i, t in enumerate(body['token_ids_logprob'])]]}}


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.backend = Backend()
        self.judge = DecisionClient(self.backend)

    def test_protocol_and_state_cache(self):
        result = self.judge.ask({'goal': 'a'}, [QUESTION])['test']
        self.assertEqual(result['choice'], 'yes')
        self.assertFalse(result['calibrated'])
        self.assertAlmostEqual(sum(result['probabilities'].values()), 1)
        self.assertTrue(self.judge.ask({'goal': 'a'}, [QUESTION])['test']['cached'])
        self.judge.ask({'goal': 'b'}, [QUESTION])
        self.backend.version = 2
        self.judge.ask({'goal': 'b'}, [QUESTION])
        self.assertEqual(self.judge.calls, 3)
        body = self.backend.requests[-1][1]
        self.assertEqual(body['sampling_params']['max_new_tokens'], 1)
        self.assertEqual(body['token_ids_logprob'], [65, 66])
        self.assertEqual(body['logprob_start_len'], -1)

    def test_ttl_and_options_invalidate(self):
        self.judge.cache_seconds = 0
        self.judge.ask({}, [QUESTION])
        self.judge.ask({}, [QUESTION])
        changed = copy.deepcopy(QUESTION)
        changed['options']['yes'] = 'Changed'
        self.judge.ask({}, [changed])
        self.assertEqual(self.judge.calls, 3)

    def test_equivalent_question_slots_share_scoring_not_mutable_results(self):
        second = {**copy.deepcopy(QUESTION), 'id': 'second'}
        result = self.judge.ask({'goal': 'a'}, [QUESTION, second])
        self.assertEqual(self.judge.calls, 1)
        self.assertFalse(result['test']['cached'])
        self.assertTrue(result['second']['cached'])
        result['second']['probabilities']['yes'] = 0
        self.assertGreater(result['test']['probabilities']['yes'], .9)
        self.assertGreater(self.judge.ask({'goal': 'a'}, [second])['second']['probabilities']['yes'], .9)
        self.judge.ask({'goal': 'a'}, [second], reverse=True)
        self.assertEqual(self.judge.calls, 2)

    def test_budget_and_no_error_cache(self):
        self.backend.bad = True
        self.judge.max_calls = 1
        with self.assertRaises(InferenceError):
            self.judge.ask({}, [QUESTION])
        self.assertFalse(self.judge.cache)
        with self.assertRaisesRegex(InferenceError, 'budget'):
            self.judge.ask({}, [QUESTION])

    def test_order_bias_abstains(self):
        self.assertFalse(route(self.judge, 'show files')['accepted'])

    def test_label_and_context_validation(self):
        original = self.backend.call
        def multi(path, body):
            if path == '/v1/tokenize':
                return {'tokens': [1, 2]}
            return original(path, body)
        self.backend.call = multi
        with self.assertRaisesRegex(InferenceError, 'single token'):
            self.judge.ask({}, [QUESTION])
        self.backend.call = original
        self.backend.profile['context_length'] = 3
        with self.assertRaisesRegex(InferenceError, 'context'):
            self.judge.ask({}, [QUESTION])

    def test_model_mismatch(self):
        self.backend.profile['model_path'] = 'wrong'
        with self.assertRaises(InferenceError):
            self.judge.ask({}, [QUESTION])
        self.assertEqual(self.judge.calls, 0)

    def test_distribution_rejects_invalid(self):
        for value in [math.nan, math.inf, .1, '0']:
            with self.assertRaises(InferenceError):
                distribution({'completion_tokens': 1, 'output_token_ids_logprobs': [[[value, 1], [-1, 2]]]}, [1, 2])
        good = distribution({'completion_tokens': 1, 'output_token_ids_logprobs': [[[-math.inf, 1], [-1, 2]]]}, [1, 2])
        self.assertEqual(good, [0, 1])
        with self.assertRaises(InferenceError):
            distribution({'completion_tokens': 2}, [1, 2])

    def test_typed_questions(self):
        result = self.judge.ask({}, [dict(id='n', type='noul', question='True?'),
                                    dict(id='s', type='score', question='Impact?', options=['low', 'high'])])
        self.assertIn('noul', result['n'])
        self.assertIn('score', result['s'])
        self.assertEqual(result['s']['legend'], {'0': 'low', '1': 'high'})
        with self.assertRaises(ValueError):
            validate_question(dict(QUESTION, options={'only': 'one'}))
        with self.assertRaises(ValueError):
            self.judge.ask({}, [QUESTION, QUESTION])

    def test_cancel_during_generation_discards_result(self):
        cancelled = threading.Event()
        self.judge.cancel_event = cancelled
        original = self.backend.call
        def cancel_generate(path, body):
            response = original(path, body)
            if path == '/generate':
                self.assertEqual(self.judge.active_rid, body['rid'])
                cancelled.set()
            return response
        self.backend.call = cancel_generate
        with self.assertRaisesRegex(InferenceError, 'cancelled'):
            self.judge.ask({}, [QUESTION])
        self.assertFalse(self.judge.cache)
        self.assertIsNone(self.judge.active_rid)
        self.assertEqual(self.judge.calls, 1)

    def test_evaluation_reports_order_instability(self):
        report = evaluate(self.judge, [('Do not list files', 'abstain')])
        self.assertEqual(report['false_acceptances'], 0)
        self.assertEqual(report['order_disagreements'], 1)
        self.assertIsNone(report['selective_accuracy'])

    def test_live_http_shape(self):
        backend = self.backend
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def reply(self, body):
                data = json.dumps(body).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            def do_GET(self):
                self.reply(backend.info())
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                self.reply(backend.call(self.path, body))
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            client = SGLang({**backend.profile, 'endpoint': f'http://127.0.0.1:{server.server_port}'})
            self.assertEqual(DecisionClient(client).ask({}, [QUESTION])['test']['choice'], 'yes')
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.tools = Tools(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_ranked_search_citations_and_private_exclusion(self):
        (self.root/'a.py').write_text('first\nlogin token validation\nlast\n')
        (self.root/'.env').write_text('login token validation secret')
        result = search(self.tools, 'login validation')
        self.assertEqual(len(result['matches']), 1)
        match = result['matches'][0]
        self.assertEqual(match['path'], 'a.py')
        self.assertEqual(match['line'], 1)
        self.assertEqual(match['sha256'], self.tools.read('a.py')['sha256'])
        with self.assertRaises(ValueError):
            search(self.tools, 'login', '../')

    def test_partial_coverage_and_missing_path(self):
        (self.root/'long.txt').write_text('x'*33000)
        self.assertTrue(search(self.tools, 'hello')['coverage']['partial'])
        with self.assertRaises(ValueError):
            search(self.tools, 'hello', 'missing')

    def test_semantic_failure_keeps_lexical_results(self):
        (self.root/'a.txt').write_text('evidence')
        judge = DecisionClient(Backend(), max_calls=0)
        result = search(self.tools, 'evidence', judge=judge)
        self.assertEqual(result['ranking'], 'lexical')
        self.assertTrue(result['matches'])
        self.assertIn('judgment_error', result)

    def test_claim_quote_gate(self):
        (self.root/'a.txt').write_text('Header\nThe limit is 10.')
        judge = DecisionClient(Backend())
        bad = verify_claim(self.tools, 'a.txt', 'limit is 20', 'limit is 20', judge)
        self.assertFalse(bad['quote_found'])
        self.assertEqual(judge.calls, 0)
        good = verify_claim(self.tools, 'a.txt', 'limit is 10', 'The limit is 10.')
        self.assertEqual(good['line'], 2)
        self.assertEqual(good['status'], 'quote_verified_claim_unchecked')

    def test_review_syntax_and_grounded_semantic_regions(self):
        (self.root/'bad.py').write_text('def broken(:\n  pass\n')
        result = review(self.tools)
        self.assertEqual(result['findings'][0]['line'], 1)
        self.assertTrue(result['findings'][0]['verified'])
        semantic = review(self.tools, judge=DecisionClient(Backend()))
        self.assertEqual(len(semantic['findings']), 2)
        self.assertFalse(semantic['findings'][1]['verified'])
        self.assertIn('def broken', semantic['findings'][1]['text'])

    def test_tool_dispatch(self):
        (self.root/'a.txt').write_text('evidence')
        result = self.tools.execute({'tool': 'evidence_search', 'args': {'path': '.', 'query': 'evidence'}})
        self.assertTrue(result['matches'])


class SupervisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.memory = Memory(self.root/'.aeon')
        self.config = load()
        self.config['decisions']['enabled'] = False

    def tearDown(self):
        self.memory.close()
        self.temp.cleanup()

    def test_failed_check_blocks_completion(self):
        engine = Harness(self.config, self.memory, self.root)
        result = engine.run('list files', offline=True,
                            verify_commands=[[sys.executable, '-c', 'raise SystemExit(1)']])
        self.assertEqual(result['status'], 'needs_verification')
        self.assertEqual(result['verification'], 'failed')
        self.assertFalse(result['verification_checks'][0]['ok'])
        with self.assertRaisesRegex(ValueError, 'original'):
            engine.run(sid=result['session'], offline=True, verify_commands=[])

    def test_successful_check_is_recorded(self):
        result = Harness(self.config, self.memory, self.root).run('list files', offline=True,
                            verify_commands=[[sys.executable, '-c', 'print("PASS")']])
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['verification'], 'explicit_checks_passed')
        self.assertEqual(result['decision_calls'], 0)

    def test_read_retry_once(self):
        engine = Harness(self.config, self.memory, self.root)
        with patch.object(engine.tools, 'execute', return_value={'ok': False, 'error': 'connection reset'}) as execute:
            result = engine.run('list files', offline=True)
        self.assertEqual(execute.call_count, 2)
        self.assertEqual(result['tool_steps'], 2)
        self.assertEqual(result['status'], 'blocked')

    def test_command_never_retried(self):
        action = {'tool': 'run_command', 'args': {'argv': ['example']}}
        self.memory.learn_recipe('custom task', self.root, [action], 60)
        engine = Harness(self.config, self.memory, self.root)
        with patch.object(engine.tools, 'execute', return_value={'ok': False, 'error': 'connection reset'}) as execute:
            result = engine.run('custom task', offline=True, confirm=lambda *_: True)
        self.assertEqual(execute.call_count, 1)
        self.assertEqual(result['status'], 'blocked')

    def test_diagnostics_and_redaction(self):
        self.assertEqual(diagnose({'ok': False, 'error': 'Permission denied'})['class'], 'permission')
        self.assertEqual(diagnose({'ok': False, 'output': 'SyntaxError'})['class'], 'code_bug')
        with patch.dict(os.environ, {'EXAMPLE_API_KEY': '12345678secret'}):
            value = redact({'text': '12345678secret password=abc Bearer abcdefghijk'})
        self.assertNotIn('12345678secret', value['text'])
        self.assertNotIn('password=abc', value['text'])
        self.assertNotIn('abcdefghijk', value['text'])

    def test_old_database_migration(self):
        directory = self.root/'old'
        directory.mkdir()
        db = sqlite3.connect(directory/'memory.sqlite3')
        db.execute('CREATE TABLE sessions(id TEXT PRIMARY KEY, goal TEXT, workspace TEXT, status TEXT, pending TEXT, llm_calls INTEGER DEFAULT 0, steps INTEGER DEFAULT 0)')
        db.close()
        memory = Memory(directory)
        try:
            sid = memory.new_session('old', self.root)
            self.assertEqual(memory.session(sid)['decision_calls'], 0)
        finally:
            memory.close()

    def test_persisted_judgment_budget_and_shadow_route(self):
        backend = Backend()
        client = SGLang({**backend.profile, 'endpoint': backend.url})
        self.config['decisions'].update(enabled=True, max_calls=2, routing='shadow')
        with patch.object(client, 'info', backend.info), patch.object(client, 'call', backend.call), \
             patch.object(client, 'decide', return_value=({'actions': [], 'answer': 'Done', 'done': True}, {})) as decide:
            result = Harness(self.config, self.memory, self.root, backend=client).run('Explain the directory')
        self.assertEqual(decide.call_count, 1)
        self.assertEqual(result['decision_calls'], 2)
        self.assertEqual(self.memory.session(result['session'])['decision_calls'], 2)
        self.assertEqual(result['verification'], 'model_reported')
        self.assertIn('budget', result['verification_checks'][0]['error'])

    def test_interrupted_verification_cannot_replay(self):
        engine = Harness(self.config, self.memory, self.root)
        with patch('aeon.supervisor.check', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                engine.run('list files', offline=True, verify_commands=[[sys.executable, '-c', 'print(1)']])
        sid = self.memory.db.execute('SELECT id FROM sessions').fetchone()[0]
        with patch('aeon.supervisor.check') as check:
            result = engine.run(sid=sid, offline=True)
        self.assertEqual(result['status'], 'blocked')
        check.assert_not_called()


if __name__ == '__main__':
    unittest.main()
