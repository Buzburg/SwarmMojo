"""Contract, process-boundary and actual pinned-runner checks for advisory rehearsal."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from aeon import rehearsal as r


EXAMPLES = Path(__file__).resolve().parents[1] / 'examples' / 'triggertangle'
NODE = shutil.which('node')


@unittest.skipUnless(NODE, 'Node.js is required for the pinned runner contract')
class RehearsalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.valid = r.rehearse(EXAMPLES/'contact-loop.json', EXAMPLES/'guarded-sync.json',
                               EXAMPLES/'contact-suite.json', node=NODE)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='aeon-rehearsal-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = [self.root/'baseline.json', self.root/'candidate.json', self.root/'suite.json']
        for target, source in zip(self.paths, ['contact-loop.json', 'guarded-sync.json', 'contact-suite.json']):
            target.write_bytes((EXAMPLES/source).read_bytes())

    def run_review(self, **kwargs):
        return r.rehearse(*self.paths, node=NODE, **kwargs)

    def test_actual_repair_keeps_required_work_and_never_authorizes(self):
        before = [p.read_bytes() for p in self.paths]
        result = self.run_review()
        self.assertEqual(result['status'], 'review-required')
        self.assertEqual([p.read_bytes() for p in self.paths], before)
        self.assertEqual(len(result['report']['cases']), 2)
        self.assertTrue(all(c['baseline']['status'] == 'blocked' for c in result['report']['cases']))
        self.assertTrue(all(c['candidate']['status'] == 'review-required' for c in result['report']['cases']))
        self.assertTrue(result['advisory_only'])
        self.assertIs(result['authorizes_apply'], False)
        self.assertIs(result['executionAllowed'], False)
        self.assertEqual(result['evidence']['runner_sha256'], r.RUNNER_SHA256)
        self.assertEqual(result['evidence']['input_sha256']['candidate'], hashlib.sha256(before[1]).hexdigest())

    def test_actual_unchanged_loop_is_blocked(self):
        self.paths[1].write_bytes(self.paths[0].read_bytes())
        self.assertEqual(self.run_review()['status'], 'blocked')

    def test_actual_budget_exhaustion_is_inconclusive(self):
        result = self.run_review(max_states=1)
        self.assertEqual(result['status'], 'inconclusive')
        self.assertIs(result['executionAllowed'], False)

    def test_disabling_workflows_is_not_a_valid_fix(self):
        candidate = json.loads(self.paths[1].read_text())
        candidate['workflows'] = []
        self.paths[1].write_text(json.dumps(candidate), encoding='utf-8')
        result = self.run_review()
        self.assertEqual(result['status'], 'blocked')
        self.assertTrue(all(not c['candidate']['required'][0]['observed'] for c in result['report']['cases']))

    def test_forbidden_output_blocks_otherwise_settling_plan(self):
        suite = json.loads(self.paths[2].read_text())
        suite['cases'][0]['forbidden'] = deepcopy(suite['cases'][0]['required'])
        self.paths[2].write_text(json.dumps(suite), encoding='utf-8')
        self.assertEqual(self.run_review()['status'], 'blocked')

    def test_bom_and_numeric_equivalence_preserve_text_binding(self):
        raw = b'\xef\xbb\xbf' + self.paths[0].read_bytes().replace(b'"version": 1,', b'"version": 1.0,')
        self.paths[0].write_bytes(raw)
        result = self.run_review()
        self.assertEqual(result['status'], 'review-required')
        self.assertEqual(result['evidence']['input_sha256']['baseline'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result['report']['evidence']['baselineTextSha256'], hashlib.sha256(raw[3:]).hexdigest())

    def test_bad_inputs_fail_before_process_launch(self):
        for content in [b'x'*(r.INPUT_LIMIT+1), b'\xff', b'{"x": NaN}', b'{"x": 1e999}', b'{', b'['*2000]:
            with self.subTest(content=content[:30]), patch.object(r, '_run') as launch:
                self.paths[0].write_bytes(content)
                with self.assertRaises(ValueError):
                    self.run_review()
                launch.assert_not_called()

    def test_invalid_domain_schema_is_rejected_by_runner(self):
        self.paths[0].write_text('{}', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.run_review()

    def test_tampered_runner_is_rejected_before_execution(self):
        runner = self.root/'runner.mjs'
        runner.write_bytes(r.RUNNER.read_bytes()+b'\n// modified')
        with patch.object(r, 'RUNNER', runner), patch.object(r, '_run') as launch:
            with self.assertRaisesRegex(ValueError, 'integrity'):
                self.run_review()
            launch.assert_not_called()

    def test_runner_and_inputs_use_private_cleaned_snapshots(self):
        original_run = r._run
        seen = []

        def inspect(command, cancelled):
            seen.append(Path(command[1]).parent)
            self.assertNotEqual(Path(command[1]), r.RUNNER)
            self.assertEqual(hashlib.sha256(Path(command[1]).read_bytes()).hexdigest(), r.RUNNER_SHA256)
            for name, source in zip(['baseline', 'candidate', 'suite'], self.paths):
                copied = Path(command[command.index('--'+name)+1])
                self.assertNotEqual(copied, source)
                self.assertEqual(copied.read_bytes(), source.read_bytes())
            return original_run(command, cancelled)

        with patch.object(r, '_run', side_effect=inspect):
            self.assertEqual(self.run_review()['status'], 'review-required')
        self.assertFalse(seen[0].exists())

    def test_original_snapshot_and_runner_changes_are_rejected(self):
        original_run = r._run
        for target in ['original', 'snapshot', 'runner-copy', 'runner-source']:
            with self.subTest(target=target):
                runner = self.root/'runner.mjs'
                runner.write_bytes(r.RUNNER.read_bytes())
                self.paths[0].write_bytes((EXAMPLES/'contact-loop.json').read_bytes())

                def changed(command, cancelled):
                    response = original_run(command, cancelled)
                    path = {'original': self.paths[0], 'snapshot': Path(command[command.index('--baseline')+1]),
                            'runner-copy': Path(command[1]), 'runner-source': runner}[target]
                    path.write_bytes(path.read_bytes()+b' ')
                    return response

                with patch.object(r, 'RUNNER', runner), patch.object(r, '_run', side_effect=changed):
                    with self.assertRaisesRegex(ValueError, 'changed during'):
                        self.run_review()

    def test_budget_boolean_out_of_range_and_missing_node_rejected(self):
        for options in [{'max_states': True}, {'max_states': 0}, {'max_states': 513},
                        {'max_transitions': False}, {'max_transitions': 8193}]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.run_review(**options)
        with patch.object(r.shutil, 'which', return_value=None), self.assertRaisesRegex(ValueError, 'Node.js'):
            r.rehearse(*self.paths)
        with self.assertRaisesRegex(ValueError, 'absolute'):
            r.rehearse(*self.paths, node='node')

    def test_cancelled_request_does_not_launch(self):
        cancelled = threading.Event(); cancelled.set()
        with patch.object(r, '_run') as launch, self.assertRaisesRegex(RuntimeError, 'cancelled'):
            self.run_review(cancelled=cancelled)
        launch.assert_not_called()

    def test_tampered_report_cannot_change_contract_or_approval(self):
        mutations = {
            'approval': lambda d: d.update(executionAllowed=True),
            'suite-name': lambda d: d.update(name='Changed suite name'),
            'status': lambda d: d.update(status='blocked'),
            'missing-case': lambda d: d['cases'].pop(),
            'hash': lambda d: d['evidence'].update(candidateTextSha256='0'*64),
            'input': lambda d: d['inputs']['baseline']['seed']['data'].update(origin='modified'),
            'bool-number': lambda d: d['inputs']['baseline'].update(version=True),
            'case-bool': lambda d: d['cases'][0]['candidate'].update(complete=1),
            'case-status': lambda d: d['cases'][0]['candidate'].update(status='blocked'),
            'missing-required': lambda d: d['cases'][0]['candidate']['required'][0].update(observed=False),
            'forbidden': lambda d: d['cases'][0]['candidate']['forbidden'][0].update(observed=True),
            'incomplete': lambda d: d['cases'][0]['candidate'].update(complete=False),
            'loop': lambda d: d['cases'][0]['candidate'].update(analysisStatus='loop-found'),
            'count': lambda d: d['cases'][0]['candidate']['stats'].update(states=0),
            'false-count': lambda d: d['cases'][0]['candidate']['stats'].update(states=True),
            'delivery': lambda d: d['cases'][0]['candidate']['stats'].update(workflowStarts=None),
            'regression': lambda d: d['regressions'].append('invented'),
        }
        for name, mutate in mutations.items():
            report = deepcopy(self.valid['report']); mutate(report)
            with self.subTest(name=name), patch.object(r, '_run', return_value=(0, json.dumps(report).encode())):
                with self.assertRaises(ValueError):
                    self.run_review()

    def test_aggregate_status_cannot_hide_consistent_blocked_case(self):
        report = deepcopy(self.valid['report'])
        report['cases'][0]['candidate']['required'][0]['observed'] = False
        report['cases'][0]['candidate']['status'] = 'blocked'
        with patch.object(r, '_run', return_value=(0, json.dumps(report).encode())):
            with self.assertRaisesRegex(ValueError, 'summary contradicts'):
                self.run_review()

    def test_wrong_exit_code_and_non_json_output_fail(self):
        for response in [(1, json.dumps(self.valid['report']).encode()), (0, b'not json'),
                         (0, b'\xff'), (3, b'{"error":"invalid inputs"}')]:
            with self.subTest(response=response[0]), patch.object(r, '_run', return_value=response):
                with self.assertRaises(ValueError):
                    self.run_review()


class FileBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='aeon-rehearsal-files-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root/'input.json'; self.file.write_bytes(b'{}')

    def test_regular_file_and_limits(self):
        self.assertEqual(r.read_input(self.file), b'{}')
        with self.assertRaises(ValueError):
            r.read_input(self.root)
        with self.assertRaises(ValueError):
            r.read_input(self.root/'missing.json')
        with self.assertRaises(ValueError):
            r.read_input(self.root/'child'/'..'/'input.json')
        self.file.write_bytes(b' '*(r.INPUT_LIMIT+1))
        with self.assertRaises(ValueError):
            r.read_input(self.file)

    def test_symlink_components_are_rejected(self):
        link = self.root/'link.json'
        try:
            link.symlink_to(self.file)
        except OSError:
            self.skipTest('Host does not permit creating symlinks')
        with self.assertRaises(ValueError):
            r.read_input(link)
        folder = self.root/'linked-folder'
        folder.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            r.read_input(folder/'input.json')

    @unittest.skipUnless(os.name == 'nt', 'Windows reparse attributes')
    def test_windows_junction_attribute_is_rejected(self):
        real_lstat = Path.lstat

        def junction(path):
            info = real_lstat(path)
            if path == self.file:
                class Reparse:
                    st_mode = info.st_mode
                    st_file_attributes = 0x400
                return Reparse()
            return info

        with patch.object(Path, 'lstat', junction), self.assertRaisesRegex(ValueError, 'junction'):
            r.read_input(self.file)

    def test_json_scalar_types_are_distinct(self):
        self.assertTrue(r._same_json({'a': [1.0]}, {'a': [1]}))
        self.assertFalse(r._same_json({'a': [True]}, {'a': [1]}))
        self.assertFalse(r._same_json({'a': None}, {}))
        self.assertFalse(r._same_json({'a': '1'}, {'a': 1}))


class ProcessBoundaryTests(unittest.TestCase):
    def launch(self, script, cancelled=None):
        return r._run([sys.executable, '-B', '-c', script], cancelled)

    def test_timeout_kills_and_waits_for_process(self):
        captured = []
        popen = subprocess.Popen

        def record(*args, **kwargs):
            process = popen(*args, **kwargs); captured.append(process); return process

        with patch.object(r.subprocess, 'Popen', side_effect=record), patch.object(r, 'TIMEOUT', .1):
            with self.assertRaisesRegex(RuntimeError, 'timed out'):
                self.launch('import time; time.sleep(30)')
        self.assertIsNotNone(captured[0].poll())

    def test_cancellation_kills_running_process(self):
        cancelled = threading.Event()
        timer = threading.Timer(.15, cancelled.set); timer.start()
        self.addCleanup(timer.cancel)
        started = time.monotonic()
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            self.launch('import time; time.sleep(30)', cancelled)
        self.assertLess(time.monotonic()-started, 5)

    def test_output_limit_rejects_truncation(self):
        with patch.object(r, 'OUTPUT_LIMIT', 1000), self.assertRaisesRegex(RuntimeError, 'byte limit'):
            self.launch("import sys; sys.stdout.write('x'*100000)")

    def test_node_environment_injection_is_removed(self):
        with patch.dict(os.environ, {'NODE_OPTIONS': '--require malicious.js', 'NODE_PATH': '/untrusted'}):
            code, output = self.launch("import os,json; print(json.dumps([os.getenv('NODE_OPTIONS'),os.getenv('NODE_PATH')]))")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output), [None, None])


if __name__ == '__main__':
    unittest.main()
