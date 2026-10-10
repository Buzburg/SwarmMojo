import io
import json
import math
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from aeon.choice_eval import evaluate, metrics, read_rows, validate_rows
from aeon.config import load
from aeon.decisions import DecisionClient
from aeon.inference import InferenceError
from aeon.mcp import Server, serve, MAX_MESSAGE
from aeon.memory import Memory
from aeon.transcripts import TranscriptBridge


class Sink:
    def __init__(self):
        self.messages = queue.Queue()

    def write(self, text):
        self.messages.put(json.loads(text))

    def flush(self):
        pass

    def get(self):
        return self.messages.get(timeout=3)


def request(rid, method, params=None):
    result = {'jsonrpc': '2.0', 'method': method, 'params': params or {}}
    if rid is not None:
        result['id'] = rid
    return result


class MCPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root/'sample.txt').write_text('hello evidence')
        self.sink = Sink()
        self.server = Server(self.root, None, self.sink)

    def tearDown(self):
        self.server.close()
        self.temp.cleanup()

    def initialize(self):
        self.server.dispatch(request(1, 'initialize', {'protocolVersion': '2025-11-25',
                              'capabilities': {}, 'clientInfo': {'name': 'test', 'version': '1'}}))
        result = self.sink.get()['result']
        self.assertEqual(result['protocolVersion'], '2025-11-25')
        self.server.dispatch(request(None, 'notifications/initialized'))

    def test_handshake_and_readonly_discovery(self):
        self.server.dispatch(request(0, 'tools/list'))
        self.assertIn('error', self.sink.get())
        self.initialize()
        self.server.dispatch(request(2, 'tools/list'))
        tools = self.sink.get()['result']['tools']
        self.assertEqual({t['name'] for t in tools}, {'evaluate', 'search', 'review', 'verify_claim', 'repo_map', 'swarm_review'})
        self.assertTrue(all(t['annotations']['readOnlyHint'] for t in tools))
        self.server.dispatch(request(3, 'tools/call', {'name': 'run_command', 'arguments': {'argv': ['bad']}}))
        self.assertEqual(self.sink.get()['error']['code'], -32602)

    def test_local_search_and_structured_result(self):
        self.initialize()
        self.server.dispatch(request(2, 'tools/call', {'name': 'search', 'arguments': {'query': 'evidence'}}))
        result = self.sink.get()['result']
        self.assertFalse(result['isError'])
        self.assertEqual(result['structuredContent']['value']['matches'][0]['path'], 'sample.txt')
        self.assertEqual(json.loads(result['content'][0]['text']), result['structuredContent'])

    def test_tool_errors_are_results(self):
        self.initialize()
        for args in [{'query': 'hello', 'path': '../'}, {'query': 'hello', 'semantic': True},
                     {'query': 'hello', 'semantic': 'yes'}, {'query': 'hello', 'extra': 2}]:
            self.server.dispatch(request(2, 'tools/call', {'name': 'search', 'arguments': args}))
            self.assertTrue(self.sink.get()['result']['isError'])

    def test_bad_requests_do_not_crash(self):
        for item in [[], {'jsonrpc': '2.0', 'id': [], 'method': 'ping'}, request(1, 'unknown')]:
            self.server.dispatch(item)
            self.assertIn('error', self.sink.get())
        self.initialize()
        self.server.dispatch(request(2, 'tools/call', {'name': [], 'arguments': {}}))
        self.assertEqual(self.sink.get()['error']['code'], -32602)

    def test_message_bound_and_parse_recovery(self):
        output = io.StringIO()
        data = b'not json\n{"jsonrpc":"2.0","id":1,"method":"ping"}\n'
        serve(self.root, None, io.BytesIO(data), output)
        lines = [json.loads(s) for s in output.getvalue().splitlines()]
        self.assertEqual(lines[0]['error']['code'], -32700)
        self.assertEqual(lines[1]['result'], {})
        output = io.StringIO()
        serve(self.root, None, io.BytesIO(b'x'*(MAX_MESSAGE+1)), output)
        self.assertIn('exceeds', json.loads(output.getvalue())['error']['message'])

    def test_cancel_and_serial_model_calls(self):
        class BlockingJudge:
            calls = 0
            cancel_event = None
            entered = threading.Event()
            def ask(self, *_):
                self.entered.set()
                if not self.cancel_event.wait(3):
                    raise RuntimeError('test timeout')
                return {}
            def cancel(self):
                self.cancel_event.set()
        judge = BlockingJudge()
        self.server.judge = judge
        self.initialize()
        arguments = {'state': {}, 'questions': [{'id': 'x', 'type': 'noul', 'question': 'Supported?'}]}
        self.server.dispatch(request(2, 'tools/call', {'name': 'evaluate', 'arguments': arguments}))
        self.assertTrue(judge.entered.wait(3))
        self.server.dispatch(request(3, 'tools/call', {'name': 'evaluate', 'arguments': arguments}))
        self.assertEqual(self.sink.get()['error']['code'], -32000)
        self.server.dispatch(request(4, 'ping'))
        self.assertEqual(self.sink.get()['result'], {})
        self.server.dispatch(request(None, 'notifications/cancelled', {'requestId': 2}))
        self.server.close()
        self.assertTrue(self.sink.messages.empty())

    def test_stdio_subprocess(self):
        proc = subprocess.Popen([sys.executable, '-m', 'aeon', 'mcp', '--offline', '--workspace', str(self.root)],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        replies = queue.Queue()
        def read():
            for line in proc.stdout:
                replies.put(json.loads(line))
        worker = threading.Thread(target=read, daemon=True)
        worker.start()
        def send(message):
            proc.stdin.write(json.dumps(message).encode()+b'\n')
            proc.stdin.flush()
        try:
            send(request(1, 'initialize', {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 'test', 'version': '1'}}))
            self.assertEqual(replies.get(timeout=5)['result']['protocolVersion'], '2025-06-18')
            send(request(None, 'notifications/initialized'))
            send(request(2, 'tools/call', {'name': 'search', 'arguments': {'query': 'hello'}}))
            self.assertFalse(replies.get(timeout=5)['result']['isError'])
            proc.stdin.close()
            self.assertEqual(proc.wait(timeout=5), 0)
            self.assertEqual(proc.stderr.read(), b'')
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
            for pipe in (proc.stdin, proc.stdout, proc.stderr):
                pipe.close()
            worker.join(timeout=2)


class TranscriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.memory = Memory(self.root/'.aeon')
        self.config = load()
        self.bridge = TranscriptBridge(self.config, self.memory, self.root, offline=True)

    def tearDown(self):
        self.memory.close()
        self.temp.cleanup()

    def event(self, text='Aeon list files', revision=1, final=True, uid='speech-1'):
        return {'source': 'test', 'id': uid, 'revision': revision, 'text': text, 'final': final}

    def test_swarm_mojo_address_preserves_explicit_approval_boundary(self):
        result = self.bridge.accept(self.event('Swarm Mojo, list files'))
        self.assertEqual(result['result']['status'], 'complete')
        self.assertEqual(self.bridge.accept(self.event('Swarm Mojo confirm', uid='confirm'))['status'],
                         'use_explicit_session_controls')
        self.assertEqual(self.bridge.accept(self.event('We said Swarm Mojo list files', uid='quoted'))['status'],
                         'not_addressed')

    def test_interim_stale_and_final(self):
        with patch.object(self.bridge.engine, 'run', wraps=self.bridge.engine.run) as run:
            self.assertEqual(self.bridge.accept(self.event('Aeon list', 2, False))['status'], 'waiting_for_final')
            self.assertEqual(self.bridge.accept(self.event(revision=1))['status'], 'stale')
            run.assert_not_called()
            result = self.bridge.accept(self.event(revision=3))
        self.assertEqual(result['result']['status'], 'complete')
        self.assertEqual(result['result']['decision_calls'], 0)
        self.assertEqual(run.call_count, 1)

    def test_durable_duplicate_and_changed_final(self):
        result = self.bridge.accept(self.event())
        new_bridge = TranscriptBridge(self.config, self.memory, self.root, offline=True)
        with patch.object(new_bridge.engine, 'run') as run:
            repeated = new_bridge.accept(self.event())
            changed = new_bridge.accept(self.event('Aeon system status', 2))
        run.assert_not_called()
        self.assertEqual(repeated['session'], result['session'])
        self.assertEqual(repeated['status'], 'duplicate')
        self.assertEqual(changed['status'], 'consumed_revision')

    def test_crash_receipt_never_replays(self):
        with patch.object(self.bridge.engine, 'run', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.bridge.accept(self.event())
        new_bridge = TranscriptBridge(self.config, self.memory, self.root, offline=True)
        with patch.object(new_bridge.engine, 'run') as run:
            duplicate = new_bridge.accept(self.event())
        run.assert_not_called()
        self.assertEqual(self.memory.session(duplicate['session'])['status'], 'active')

    def test_addressing_and_confirmation(self):
        for text, expected in [('We said Aeon list files', 'not_addressed'),
                               ('Aeon confirm', 'use_explicit_session_controls'),
                               ('Aeon yes', 'use_explicit_session_controls')]:
            with patch.object(self.bridge.engine, 'run') as run:
                self.assertEqual(self.bridge.accept(self.event(text))['status'], expected)
                run.assert_not_called()

    def test_payload_is_verbatim_and_no_mutation_approval(self):
        text = 'Aeon, read file "thanks now.txt"'
        (self.root/'thanks now.txt').write_text('preserved')
        result = self.bridge.accept(self.event(text))
        self.assertEqual(self.memory.session(result['session'])['goal'], 'read file "thanks now.txt"')
        self.assertEqual(result['result']['results'][0]['result']['text'], 'preserved')
        self.memory.learn_recipe('make change', self.root, [{'tool': 'write_file', 'args': {
            'path': 'new.txt', 'content': 'hello', 'expected_sha256': 'missing'}}], 60)
        result = self.bridge.accept(self.event('Aeon make change', uid='speech-2'))
        self.assertEqual(result['result']['status'], 'needs_approval')
        self.assertFalse((self.root/'new.txt').exists())

    def test_invalid_revision_and_same_revision_change(self):
        self.bridge.accept(self.event('Aeon list', final=False))
        with self.assertRaises(ValueError):
            self.bridge.accept(self.event('Aeon list files'))
        with self.assertRaises(ValueError):
            self.bridge.accept(self.event(revision=True))


class ChoiceTests(unittest.TestCase):
    def test_metrics_include_confidence_one_and_zero_probability(self):
        result = metrics([{'probabilities': [1, 0], 'label': 1}, {'probabilities': [.2, .8], 'label': 1}])
        self.assertEqual(result['top1'], .5)
        self.assertEqual(result['top3'], 1)
        self.assertAlmostEqual(result['ece'], .6)
        self.assertAlmostEqual(result['brier'], 1.04)
        self.assertTrue(math.isfinite(result['negative_log_likelihood']))
        self.assertEqual(result['calibration_bins'][9]['count'], 1)

    def test_invalid_dataset_and_probability_rejected(self):
        for probabilities in [[.2, .2], [math.nan, .5], [-.1, 1.1], [True, False]]:
            with self.assertRaises(ValueError):
                metrics([{'probabilities': probabilities, 'label': 0}])
        with self.assertRaises(ValueError):
            validate_rows([{'context': 'x', 'options': ['a', 'a'], 'label': 0}]*2)

    def test_controls_and_order_comparison(self):
        class Judge:
            calls = 0
            def ask(self, state, questions, reverse=False):
                self.calls += 1
                options = questions[0]['options']
                choice = str(len(options)-1) if reverse else '0'
                return {'selection': {'choice': choice, 'probabilities': {k: int(k == choice) for k in options}}}
        rows = [{'context': 'first', 'options': ['a', 'b'], 'label': 0, 'group': 'g1'},
                {'context': 'second', 'options': ['a', 'b', 'c', 'd'], 'label': 3, 'group': 'g2'}]
        judge = Judge()
        judge.calls = 8  # Previous activity must not inflate this run's count.
        report = evaluate(judge, rows)
        self.assertEqual(report['decision_calls'], 6)
        self.assertEqual(report['request_latency_ms']['forward']['requests'], 2)
        self.assertEqual(report['request_latency_ms']['forward']['cache_hits'], 0)
        self.assertEqual(report['order_disagreements'], 2)
        self.assertEqual(report['control_skipped'], 0)
        self.assertEqual(report['rows'][0]['control_context_index'], 1)
        self.assertAlmostEqual(report['model']['random_top1'], .375)
        rows[1]['group'] = 'g1'
        report = evaluate(Judge(), rows)
        self.assertEqual(report['control_skipped'], 2)
        self.assertIsNone(report['shuffled_context'])

    def test_example_jsonl_valid(self):
        rows = read_rows(Path(__file__).resolve().parents[1]/'examples/choice-evaluation.jsonl')
        self.assertEqual(len(rows), 4)

    def test_ranking_menu_sizes_and_latency(self):
        from aeon.choice_eval import latency_summary
        result = metrics([{'probabilities': [.1, .9], 'label': 0},
                          {'probabilities': [.1, .2, .7], 'label': 2}])
        self.assertEqual(result['mean_reciprocal_rank'], .75)
        self.assertEqual(result['top5'], 1)
        self.assertEqual(result['by_menu_size']['2']['accuracy'], 0)
        self.assertEqual(result['by_menu_size']['3']['accuracy'], 1)
        self.assertEqual(latency_summary([10, 30, 20, 40], 1)['p50'], 20)
        self.assertEqual(latency_summary([10, 30, 20, 40], 1)['p95'], 40)
        self.assertIsNone(latency_summary([], 0)['p50'])
        rows = read_rows(Path(__file__).resolve().parents[1]/'examples/contrastive-decisions.jsonl')
        self.assertEqual(len(rows), 6)
        for index in range(0, len(rows), 2):
            self.assertEqual(rows[index]['group'], rows[index+1]['group'])
            self.assertNotEqual(rows[index]['label'], rows[index+1]['label'])

    def test_cancelled_decision_stops_before_network(self):
        event = threading.Event()
        event.set()
        judge = DecisionClient(None, cancel_event=event)
        with self.assertRaisesRegex(InferenceError, 'cancelled'):
            judge.ask({}, [])
        self.assertEqual(judge.calls, 0)


if __name__ == '__main__':
    unittest.main()
