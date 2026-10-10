import copy
import hashlib
import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from aeon.cli import main
from aeon.workflows import Workflows
import test_assistant
from test_assistant import check, plan


class WorkflowComparisonTests(unittest.TestCase):
    setUp = test_assistant.AssistantTests.setUp
    tearDown = test_assistant.AssistantTests.tearDown

    def fixtures(self):
        return [
            {'files': {}, 'expect': 'complete',
             'checks': check('file_sha256', path='note.txt', sha256=hashlib.sha256(b'hello').hexdigest())},
            {'files': {'note.txt': 'existing'}, 'expect': 'blocked',
             'checks': check('file_sha256', path='note.txt', sha256=hashlib.sha256(b'existing').hexdigest())},
        ]

    def test_external_check_rejects_self_declared_success(self):
        store = Workflows(self.memory, self.workspace)
        weak = plan()
        weak['steps'][0]['action']['args']['content'] = 'wrong'
        weak['steps'][0]['after'] = check('file_exists', path='note.txt')
        weak['completion'] = check('file_exists', path='note.txt')
        record = store.propose(weak)
        result = store.regress(record['id'], self.fixtures(), self.config)
        self.assertEqual(result['results'][0]['actual'], 'complete')
        self.assertFalse(result['ok'])
        self.assertFalse(result['results'][0]['independent_checks']['ok'])
        with self.assertRaises(ValueError):
            store.review(record['id'])
        self.assertFalse((self.workspace/'note.txt').exists())

    def test_comparison_reports_improvement_regression_and_keeps_approval(self):
        store = Workflows(self.memory, self.workspace)
        good = store.propose(plan())
        store.regress(good['id'], self.fixtures(), self.config)
        store.review(good['id'])
        saved = store.get(good['id'])
        weak = plan(); weak['steps'][0]['action']['args']['content'] = 'wrong'
        weak['steps'][0]['after'] = weak['completion'] = check('file_exists', path='note.txt')
        bad = store.propose(weak)
        forward = store.compare(good['id'], bad['id'], self.fixtures(), self.config)
        self.assertTrue(forward['measured_improvement'])
        self.assertEqual(forward['gained_fixtures'], [0])
        self.assertEqual(forward['regressed_fixtures'], [])
        reverse = store.compare(bad['id'], good['id'], self.fixtures(), self.config)
        self.assertFalse(reverse['ok'])
        self.assertEqual(reverse['regressed_fixtures'], [0])
        same = store.compare(good['id'], good['id'], self.fixtures(), self.config)
        self.assertFalse(same['measured_improvement'])
        self.assertEqual(saved, store.get(good['id']))
        self.assertFalse(store.get(bad['id'])['reviewed'])
        self.assertEqual(forward['candidate_report']['fixtures_hash'], forward['baseline_report']['fixtures_hash'])
        self.assertTrue(all(r['llm_calls'] == 0 for r in forward['candidate_report']['results']))

    def test_comparison_measures_fewer_tools_only_when_checks_pass(self):
        store = Workflows(self.memory, self.workspace)
        efficient = store.propose(plan())
        slower = plan(); slower['name'] = 'create-and-read'
        slower['steps'].append({'action': {'tool': 'read_file', 'args': {'path': 'note.txt'}},
                                'before': copy.deepcopy(slower['completion']),
                                'after': copy.deepcopy(slower['completion'])})
        baseline = store.propose(slower)
        result = store.compare(efficient['id'], baseline['id'], self.fixtures(), self.config)
        self.assertTrue(result['measured_improvement'])
        self.assertEqual(result['tool_step_delta'], -1)
        self.assertEqual(result['gained_fixtures'], [])

    def test_comparison_requires_checks_and_workspace_scope(self):
        store = Workflows(self.memory, self.workspace)
        record = store.propose(plan())
        with self.assertRaises(ValueError):
            store.compare(record['id'], record['id'], [{'files': {}, 'expect': 'complete'}], self.config)
        with self.assertRaises(ValueError):
            Workflows(self.memory, self.root/'other').compare(record['id'], record['id'], self.fixtures(), self.config)
        unsafe = self.fixtures(); unsafe[0]['checks'] = check('command_passed', index=0)
        with self.assertRaises(ValueError):
            store.compare(record['id'], record['id'], unsafe, self.config)
        unknown = self.fixtures(); unknown[0]['checks'] = check('file_exists', path='../outside')
        self.assertFalse(store.regress(record['id'], unknown, self.config)['ok'])

    def test_cli_comparison(self):
        record = Workflows(self.memory, self.workspace).propose(plan())
        fixture_file = self.root/'fixtures.json'
        fixture_file.write_text(json.dumps(self.fixtures()), encoding='utf-8')
        with patch('sys.argv', ['aeon', '--state-dir', str(self.root/'state'), 'workflow', 'compare',
                              '--id', record['id'], '--baseline', record['id'],
                              '--file', str(fixture_file), '--workspace', str(self.workspace)]), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(), 0)
        self.assertTrue(json.loads(output.getvalue())['ok'])
