import copy
from pathlib import Path
import sys
import tempfile
import unittest

from aeon.config import load
from aeon.engine import Harness
from aeon.memory import Memory
from aeon.planner import local_plan, preview
from aeon.workflows import Workflows


def condition(kind, **args):
    return {'id': 'check', 'description': 'File evidence', 'check': {'type': kind, **args}}


def workflow():
    return {'name': 'make-note', 'description': 'Create a note',
            'steps': [{'action': {'tool': 'write_file', 'args': {'path': 'note.txt', 'content': 'hello', 'expected_sha256': 'missing'}},
                       'before': condition('file_absent', path='note.txt'),
                       'after': condition('file_contains', path='note.txt', text='hello')}],
            'completion': condition('file_contains', path='note.txt', text='hello')}


class LocalPlanningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.work = self.root/'work'; self.work.mkdir()
        self.memory = Memory(self.root/'state'); self.config = load()

    def tearDown(self):
        self.memory.close(); self.temp.cleanup()

    def test_compound_offline_and_duplicate_reads(self):
        (self.work/'a.txt').write_text('hello')
        goal = 'list files then read file "a.txt"; list files'
        plan = preview(self.config, self.memory, self.work, goal)
        self.assertEqual(plan['tool_steps'], 2)
        self.assertFalse(plan['requires_approval'])
        result = Harness(self.config, self.memory, self.work).run(goal, offline=True)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['llm_calls'], 0)
        self.assertEqual(result['decision_calls'], 0)
        self.assertEqual(result['tool_steps'], 2)

    def test_quotes_and_all_or_nothing_recognition(self):
        plan = local_plan('find "alpha then beta; gamma" in "a.txt"\nlist files')
        self.assertEqual(plan[1][0]['args']['text'], 'alpha then beta; gamma')
        for text in ('list files then delete everything', 'list files then focus window "X"',
                     'list files;', 'list files then do not read file "x"', 'list files\nread file "bad'):
            self.assertIsNone(local_plan(text))
            result = Harness(self.config, self.memory, self.work).run(text, offline=True)
            self.assertEqual(result['status'], 'needs_model')
            self.assertEqual(result['tool_steps'], 0)

    def test_budget_rejects_whole_plan_before_first_read(self):
        config = copy.deepcopy(self.config); config['harness']['max_steps'] = 1
        result = Harness(config, self.memory, self.work).run('list files then system status', offline=True)
        self.assertEqual(result['status'], 'budget_exhausted')
        self.assertEqual(result['tool_steps'], 0)
        self.assertFalse(preview(config, self.memory, self.work, 'list files then system status')['within_step_budget'])

    def reviewed(self, plan=None):
        store = Workflows(self.memory, self.work)
        draft = store.propose(plan or workflow())
        store.regress(draft['id'], [{'files': {}, 'expect': 'complete'}], self.config)
        store.review(draft['id'])
        return store

    def test_named_workflow_preview_approval_and_resume(self):
        self.reviewed()
        plan = preview(self.config, self.memory, self.work, 'run workflow "make-note"')
        self.assertEqual(plan['source'], 'reviewed_workflow')
        self.assertTrue(plan['requires_approval'])
        self.assertFalse((self.work/'note.txt').exists())
        engine = Harness(self.config, self.memory, self.work)
        result = engine.run('run workflow "make-note"', offline=True)
        self.assertEqual(result['status'], 'needs_approval')
        self.assertEqual(result['llm_calls'], 0)
        result = engine.run(sid=result['session'], approve=result['pending']['ticket'], offline=True)
        self.assertEqual(result['verification'], 'workflow_verified')
        self.assertEqual((self.work/'note.txt').read_text(), 'hello')

    def test_unreviewed_ambiguous_and_foreign_workflow_rejected(self):
        store = Workflows(self.memory, self.work)
        store.propose(workflow())
        with self.assertRaises(ValueError): preview(self.config, self.memory, self.work, 'run workflow "make-note"')
        self.reviewed()
        other = self.root/'other'; other.mkdir()
        with self.assertRaises(ValueError): preview(self.config, self.memory, other, 'run workflow "make-note"')
        changed = workflow(); changed['description'] = 'Another plan with the same name'
        self.reviewed(changed)
        with self.assertRaisesRegex(ValueError, 'Multiple'): preview(self.config, self.memory, self.work, 'run workflow "make-note"')

    def test_completion_evidence_after_verification_mutation(self):
        result = Harness(self.config, self.memory, self.work).run('Create a note', workflow=workflow(), offline=True,
            allow_write=True, verify_commands=[[sys.executable, '-c', "from pathlib import Path; Path('note.txt').write_text('changed')"]])
        self.assertEqual(result['status'], 'needs_verification')
        self.assertEqual(result['verification'], 'workflow_unmet')
        events = self.memory.events(result['session'])
        kinds = [e['kind'] for e in events]
        self.assertLess(kinds.index('verification'), kinds.index('workflow_completion'))
