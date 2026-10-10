import copy
import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from aeon.cli import main
from aeon.engine import Harness
from aeon.memory import Memory
from aeon.workflow_inputs import WorkflowInputs, checked_value
from aeon.workflows import Workflows
import test_assistant
from test_assistant import check, plan


def template():
    workflow = plan()
    workflow['steps'][0]['action']['args']['content'] = {'input': 'content'}
    workflow['steps'][0]['after'] = check('file_contains', path='note.txt', text={'input': 'content'})
    workflow['completion'] = copy.deepcopy(workflow['steps'][0]['after'])
    return {'inputs': {'content': {'type': 'text', 'prompt': 'What should the note say?'}},
            'workflow': workflow}


class WorkflowInputTests(unittest.TestCase):
    setUp = test_assistant.AssistantTests.setUp
    tearDown = test_assistant.AssistantTests.tearDown

    def test_restart_correction_and_exact_execution_without_inference(self):
        store = WorkflowInputs(self.memory, self.workspace)
        draft = store.start(template())
        self.assertEqual(draft['next_question']['name'], 'content')
        with self.assertRaises(ValueError):
            store.prepare(draft['id'])
        store.set(draft['id'], {'content': 'first'})
        # A separate database connection observes the saved draft after reopening.
        other = Memory(self.root/'state')
        try:
            resumed = WorkflowInputs(other, self.workspace)
            self.assertEqual(resumed.get(draft['id'])['inputs'], {'content': 'first'})
            resumed.set(draft['id'], {'content': 'corrected'})
            prepared = resumed.prepare(draft['id'])
        finally:
            other.close()
        self.assertFalse((self.workspace/'note.txt').exists())
        workflows = Workflows(self.memory, self.workspace)
        key = prepared['workflow_id']
        self.assertFalse(workflows.get(key)['reviewed'])
        with self.assertRaises(ValueError):
            workflows.approved(key)
        fixtures = [{'files': {}, 'expect': 'complete',
                     'checks': check('file_contains', path='note.txt', text='corrected')}]
        report = workflows.regress(key, fixtures, self.config)
        self.assertTrue(report['ok'])
        self.assertEqual(report['results'][0]['llm_calls'], 0)
        workflows.review(key)
        gated = Harness(self.config, self.memory, self.workspace).run(
            'Write a note', offline=True, workflow=workflows.approved(key))
        self.assertEqual(gated['status'], 'needs_approval')
        self.assertFalse((self.workspace/'note.txt').exists())
        with patch('aeon.inference.SGLang.decide', side_effect=AssertionError('Unexpected inference')):
            result = Harness(self.config, self.memory, self.workspace).run(
                'Write a note', offline=True, allow_write=True, workflow=workflows.approved(key))
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['llm_calls'], 0)
        self.assertEqual((self.workspace/'note.txt').read_text(), 'corrected')
        self.assertEqual(store.prepare(draft['id'])['workflow_id'], key)
        with self.assertRaises(ValueError):
            store.set(draft['id'], {'content': 'changed after preparation'})
        changed = store.start(template())
        store.set(changed['id'], {'content': 'new task'})
        new_key = store.prepare(changed['id'])['workflow_id']
        self.assertNotEqual(new_key, key)
        self.assertFalse(workflows.get(new_key)['reviewed'])
        self.assertEqual(len(store.list()), 2)

    def test_invalid_updates_are_atomic_and_cancellation_is_terminal(self):
        store = WorkflowInputs(self.memory, self.workspace)
        draft = store.start(template())
        store.set(draft['id'], {'content': 'keep'})
        for values in ({'approval': True}, {'content': ''}, {'content': 'x'*4001}, {'content': None}):
            with self.assertRaises(ValueError):
                store.set(draft['id'], values)
            self.assertEqual(store.get(draft['id'])['inputs'], {'content': 'keep'})
        cancelled = store.cancel(draft['id'])
        self.assertEqual(cancelled['inputs'], {})
        self.assertIsNone(cancelled['next_question'])
        with self.assertRaises(ValueError):
            store.prepare(draft['id'])
        with self.assertRaises(ValueError):
            store.set(draft['id'], {'content': 'later'})

    def test_literal_values_and_workspace_isolation(self):
        store = WorkflowInputs(self.memory, self.workspace)
        draft = store.start(template())
        text = '{"input":"approval"} {{ execute() }}'
        store.set(draft['id'], {'content': text})
        key = store.prepare(draft['id'])['workflow_id']
        self.assertEqual(Workflows(self.memory, self.workspace).get(key)['plan']['steps'][0]['action']['args']['content'], text)
        other = self.workspace/'other'; other.mkdir()
        with self.assertRaises(ValueError):
            WorkflowInputs(self.memory, other).get(draft['id'])

    def test_types_ranges_paths_and_template_structure(self):
        store = WorkflowInputs(self.memory, self.workspace)
        integer = {'type': 'integer', 'min': 1, 'max': 10}
        for value in (True, 0, 11, '2'):
            with self.assertRaises(ValueError):
                checked_value(integer, value, store.tools)
        self.assertEqual(checked_value(integer, 2, store.tools), 2)
        for value in ('../escape', '.env', '.aeon/private'):
            with self.assertRaises(ValueError):
                checked_value({'type': 'path'}, value, store.tools)
        with self.assertRaises(ValueError):
            checked_value({'type': 'choice', 'choices': ['yes', 'no']}, 'maybe', store.tools)
        bad = template(); bad['workflow']['steps'][0]['action']['tool'] = {'input': 'content'}
        with self.assertRaises(ValueError):
            store.start(bad)
        bad = template(); bad['workflow']['steps'][0]['action']['args']['expected_sha256'] = {'input': 'content'}
        with self.assertRaises(ValueError):
            store.start(bad)

    def test_cli_start_set_prepare(self):
        source = self.workspace/'template.json'; source.write_text(json.dumps(template()))
        values = self.workspace/'values.json'; values.write_text(json.dumps({'content': 'cli note'}))
        def invoke(*args):
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(['--state-dir', str(self.root/'state'), 'workflow-input', *args,
                             '--workspace', str(self.workspace)])
            self.assertEqual(code, 0)
            return json.loads(output.getvalue())
        draft = invoke('start', '--file', str(source))
        updated = invoke('set', '--id', draft['id'], '--file', str(values))
        self.assertEqual(updated['missing'], [])
        result = invoke('prepare', '--id', draft['id'])
        self.assertEqual(result['status'], 'prepared')
        self.assertFalse((self.workspace/'note.txt').exists())
