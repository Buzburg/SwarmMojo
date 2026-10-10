import io
import json
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from aeon.mcp import Server


EXAMPLES = Path(__file__).resolve().parents[1] / 'examples' / 'triggertangle'
NODE = shutil.which('node')


def request(rid, method, params=None):
    value = {'jsonrpc': '2.0', 'method': method, 'params': params or {}}
    if rid is not None:
        value['id'] = rid
    return value


class Sink:
    def __init__(self):
        self.messages = queue.Queue()

    def write(self, text):
        self.messages.put(json.loads(text))

    def flush(self):
        pass

    def get(self):
        return self.messages.get(timeout=10)


@unittest.skipUnless(NODE, 'Node is required for the bundled rehearsal checker')
class RehearsalInterfaces(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / 'workspace'
        self.workspace.mkdir()
        self.baseline = self.root / 'baseline.json'
        self.suite = self.root / 'suite.json'
        self.candidate = self.workspace / 'candidate.json'
        for source, destination in (('contact-loop.json', self.baseline),
                                    ('contact-suite.json', self.suite),
                                    ('guarded-sync.json', self.candidate)):
            shutil.copyfile(EXAMPLES / source, destination)

    def server(self, **kwargs):
        sink = Sink()
        server = Server(self.workspace, None, sink, **kwargs)
        self.addCleanup(server.close)
        server.dispatch(request(1, 'initialize', {'protocolVersion': '2025-11-25',
                          'capabilities': {}, 'clientInfo': {'name': 'test', 'version': '1'}}))
        self.assertIn('fixed local checker', sink.get()['result']['instructions'])
        server.dispatch(request(None, 'notifications/initialized'))
        return server, sink

    def enabled(self):
        return self.server(rehearsal_baseline=self.baseline, rehearsal_suite=self.suite)

    def call(self, server, sink, args):
        server.dispatch(request(3, 'tools/call', {'name': 'rehearse', 'arguments': args}))
        return sink.get()['result']

    def test_opt_in_discovery_does_not_change_default_server(self):
        for enabled in (True, False):
            server, sink = self.enabled() if enabled else self.server()
            server.dispatch(request(2, 'tools/list'))
            tools = {tool['name']: tool for tool in sink.get()['result']['tools']}
            self.assertEqual(len(tools), 7 if enabled else 6)
            if enabled:
                tool = tools['rehearse']
                self.assertEqual(set(tool['inputSchema']['properties']), {'candidate'})
                self.assertFalse(tool['inputSchema']['additionalProperties'])
                self.assertTrue(tool['annotations']['readOnlyHint'])
                self.assertFalse(tool['annotations']['openWorldHint'])
            else:
                server.dispatch(request(3, 'tools/call', {'name': 'rehearse', 'arguments': {'candidate': 'candidate.json'}}))
                self.assertEqual(sink.get()['error']['code'], -32602)

    def test_both_operator_flags_are_required(self):
        for options in ({'rehearsal_baseline': self.baseline}, {'rehearsal_suite': self.suite},
                        {'rehearsal_node': NODE}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                Server(self.workspace, None, io.StringIO(), **options)

    def test_operator_policy_must_be_outside_workspace(self):
        for baseline, suite in ((self.candidate, self.suite), (self.baseline, self.candidate)):
            with self.subTest(baseline=baseline, suite=suite), self.assertRaisesRegex(ValueError, 'outside'):
                Server(self.workspace, None, io.StringIO(), rehearsal_baseline=baseline, rehearsal_suite=suite)

    def test_policy_symlinks_are_rejected(self):
        link = self.root / 'linked-policy.json'
        try:
            link.symlink_to(self.baseline)
        except OSError as exc:
            self.skipTest(f'Symlink creation unavailable: {exc}')
        with self.assertRaises((ValueError, OSError)):
            Server(self.workspace, None, io.StringIO(), rehearsal_baseline=link, rehearsal_suite=self.suite)

    def test_non_object_or_invalid_policy_rejected_at_startup(self):
        for data in (b'[]', b'{broken', b'{"x":NaN}', b'\xff'):
            self.suite.write_bytes(data)
            with self.subTest(data=data), self.assertRaises(ValueError):
                Server(self.workspace, None, io.StringIO(), rehearsal_baseline=self.baseline, rehearsal_suite=self.suite)

    def test_model_cannot_choose_checker_executable(self):
        executable = self.workspace / 'node'
        executable.write_text('untrusted')
        with patch('aeon.mcp.shutil.which', return_value=str(executable)), self.assertRaisesRegex(ValueError, 'outside'):
            Server(self.workspace, None, io.StringIO(), rehearsal_baseline=self.baseline, rehearsal_suite=self.suite)

    def test_policy_is_frozen_and_cleaned_up(self):
        server, sink = self.enabled()
        frozen = server.rehearsal.baseline.parent
        self.baseline.unlink()
        self.suite.write_text('{}')
        result = self.call(server, sink, {'candidate': 'candidate.json'})
        self.assertFalse(result['isError'], result)
        value = result['structuredContent']['value']
        self.assertEqual(value['status'], 'review-required')
        self.assertTrue(value['advisory_only'])
        self.assertFalse(value['authorizes_apply'])
        self.assertFalse(value['executionAllowed'])
        self.assertEqual(len(value['report']['cases']), 2)
        self.assertFalse((self.workspace / '.aeon').exists())
        server.close()
        self.assertFalse(frozen.exists())

    def test_tool_rejects_authority_arguments(self):
        server, sink = self.enabled()
        for key, value in (('baseline', str(self.baseline)), ('suite', str(self.suite)),
                           ('node', NODE), ('execute', True), ('max_states', 1)):
            with self.subTest(key=key), patch('aeon.rehearsal.rehearse') as run:
                result = self.call(server, sink, {'candidate': 'candidate.json', key: value})
                self.assertTrue(result['isError'])
                run.assert_not_called()

    def test_candidate_must_stay_in_workspace(self):
        server, sink = self.enabled()
        for candidate in ('../baseline.json', str(self.baseline), '.git/config', '', 42):
            with self.subTest(candidate=candidate), patch('aeon.rehearsal.rehearse') as run:
                result = self.call(server, sink, {'candidate': candidate})
                self.assertTrue(result['isError'])
                run.assert_not_called()

    def test_cancel_event_reaches_checker_and_suppresses_result(self):
        server, sink = self.enabled()
        entered, finished = threading.Event(), threading.Event()
        received = []

        def checker(*args, **kwargs):
            received.append(kwargs)
            entered.set()
            if not kwargs['cancelled'].wait(5):
                raise RuntimeError('Cancellation did not arrive')
            finished.set()
            return {}

        with patch('aeon.rehearsal.rehearse', side_effect=checker):
            server.dispatch(request(3, 'tools/call', {'name': 'rehearse', 'arguments': {'candidate': 'candidate.json'}}))
            self.assertTrue(entered.wait(5))
            server.dispatch(request(None, 'notifications/cancelled', {'requestId': 3}))
            self.assertTrue(finished.wait(5))
            server.close()
        self.assertTrue(sink.messages.empty())
        self.assertEqual(received[0]['max_states'], 256)
        self.assertEqual(received[0]['max_transitions'], 2048)
        self.assertTrue(Path(received[0]['node']).is_absolute())

    def test_cli_actual_statuses_without_state_or_model_config(self):
        unused_state = self.root / 'unused-state'
        for candidate, extra, expected in ((self.candidate, [], 'review-required'),
                                           (self.baseline, [], 'blocked'),
                                           (self.candidate, ['--max-states', '1'], 'inconclusive')):
            command = [sys.executable, '-m', 'aeon', '--config', str(self.root / 'absent.toml'),
                       '--state-dir', str(unused_state), 'rehearse', '--baseline', str(self.baseline),
                       '--candidate', str(candidate), '--suite', str(self.suite), '--node', NODE, *extra]
            with self.subTest(expected=expected):
                result = subprocess.run(command, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0 if expected == 'review-required' else 2, result.stderr)
                value = json.loads(result.stdout)
                self.assertEqual(value['status'], expected)
                self.assertFalse(value['executionAllowed'])
                self.assertEqual(result.stderr, '')
        self.assertFalse(unused_state.exists())

    def test_cli_invalid_input_is_error(self):
        self.candidate.write_text('{}')
        result = subprocess.run([sys.executable, '-m', 'aeon', 'rehearse', '--baseline', str(self.baseline),
                                 '--candidate', str(self.candidate), '--suite', str(self.suite)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertIn('swarm-mojo:', result.stderr)

    def test_mcp_cli_enables_only_configured_rehearsal(self):
        messages = [request(1, 'initialize', {'protocolVersion': '2025-11-25', 'capabilities': {},
                                             'clientInfo': {'name': 'test', 'version': '1'}}),
                    request(None, 'notifications/initialized'), request(2, 'tools/list')]
        result = subprocess.run([sys.executable, '-m', 'aeon', 'mcp', '--offline', '--workspace', str(self.workspace),
                                 '--rehearsal-baseline', str(self.baseline), '--rehearsal-suite', str(self.suite),
                                 '--rehearsal-node', NODE], input=''.join(json.dumps(row)+'\n' for row in messages),
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        tools = json.loads(result.stdout.splitlines()[1])['result']['tools']
        self.assertIn('rehearse', {tool['name'] for tool in tools})


if __name__ == '__main__':
    unittest.main()
