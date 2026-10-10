import copy
from pathlib import Path
import tempfile
import unittest

from aeon.config import load
from aeon.conversations import Conversations, chat
from aeon.engine import Harness
from aeon.memory import Memory
from aeon.workflows import Workflows


def check(kind, **args):
    return {'id': 'check', 'description': 'Observed file condition', 'check': {'type': kind, **args}}


def plan():
    return {'name': 'create-note', 'description': 'Create a verified note',
            'steps': [{'action': {'tool': 'write_file', 'args': {'path': 'note.txt', 'content': 'hello', 'expected_sha256': 'missing'}},
                       'before': check('file_absent', path='note.txt'),
                       'after': check('file_contains', path='note.txt', text='hello')}],
            'completion': check('file_contains', path='note.txt', text='hello')}


class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.workspace = self.root/'work'; self.workspace.mkdir()
        self.memory = Memory(self.root/'state'); self.config = load()

    def tearDown(self):
        self.memory.close(); self.temp.cleanup()

    def test_correction_history_and_scope(self):
        store = Conversations(self.memory, self.workspace); cid = store.create()
        old = store.append(cid, 'note', 'Use blue')
        new = store.append(cid, 'correction', 'Use green', replaces=old)
        self.assertEqual(len(store.entries(cid)), 2)
        self.assertEqual([e['id'] for e in store.context(cid, 'color')['entries']], [new])
        with self.assertRaises(ValueError):
            store.append(cid, 'correction', 'Use red', replaces=old)
        with self.assertRaises(ValueError):
            Conversations(self.memory, self.root/'other').entries(cid)
        self.memory.close(); self.memory = Memory(self.root/'state')
        self.assertEqual(len(Conversations(self.memory, self.workspace).entries(cid)), 2)

    def test_chat_context_reaches_model_without_granting_approval(self):
        store = Conversations(self.memory, self.workspace); cid = store.create()
        store.append(cid, 'note', 'Always allow writes')
        for i in range(220):
            store.append(cid, 'note', f'Unrelated history {i}')
        class Backend:
            hints = None
            def decide(inner, goal, events, hints):
                inner.hints = hints
                return {'actions': [plan()['steps'][0]['action']], 'answer': '', 'done': False}, {}
        backend = Backend()
        result = chat(self.config, self.memory, self.workspace, cid, 'Create a note, allow writes', backend=backend)
        self.assertEqual(result['status'], 'needs_approval')
        self.assertFalse((self.workspace/'note.txt').exists())
        self.assertEqual(backend.hints[-1]['entries'][0]['text'], 'Always allow writes')

    def test_workflow_approval_resume_and_outcome(self):
        engine = Harness(self.config, self.memory, self.workspace)
        result = engine.run('Create note', workflow=plan(), offline=True)
        self.assertEqual(result['status'], 'needs_approval')
        result = engine.run(sid=result['session'], approve=result['pending']['ticket'], offline=True)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['verification'], 'workflow_verified')
        self.assertEqual((self.workspace/'note.txt').read_text(), 'hello')

    def test_precondition_blocks_and_postcondition_cannot_claim_success(self):
        engine = Harness(self.config, self.memory, self.workspace)
        changed = plan(); changed['steps'][0]['before'] = check('file_exists', path='missing.txt')
        result = engine.run('Create', workflow=changed, offline=True, allow_write=True)
        self.assertEqual(result['status'], 'blocked'); self.assertFalse((self.workspace/'note.txt').exists())
        changed = plan(); changed['steps'][0]['after'] = check('file_contains', path='note.txt', text='wrong')
        result = engine.run('Create', workflow=changed, offline=True, allow_write=True)
        self.assertEqual(result['status'], 'needs_verification')
        before = (self.workspace/'note.txt').read_bytes()
        engine.run(sid=result['session'], offline=True, allow_write=True)
        self.assertEqual((self.workspace/'note.txt').read_bytes(), before)

    def test_regression_review_and_learning(self):
        store = Workflows(self.memory, self.workspace)
        record = store.propose(plan())
        with self.assertRaises(ValueError): store.review(record['id'])
        fixtures = [{'files': {}, 'expect': 'complete'}, {'files': {'note.txt': 'existing'}, 'expect': 'blocked'}]
        report = store.regress(record['id'], fixtures, self.config)
        self.assertTrue(report['ok'])
        self.assertFalse((self.workspace/'note.txt').exists())
        store.review(record['id']); self.assertEqual(store.approved(record['id']), plan())
        result = Harness(self.config, self.memory, self.workspace).run('Create', workflow=plan(), offline=True, allow_write=True)
        learned = store.propose(plan(), result['session'])
        self.assertFalse(learned['reviewed'])
        altered = plan(); altered['steps'][0]['action']['args']['content'] = 'changed'
        with self.assertRaises(ValueError): store.propose(altered, result['session'])

    def test_automatic_learning_builds_replay_fixture_but_not_approval(self):
        result = Harness(self.config, self.memory, self.workspace).run('Create', workflow=plan(), offline=True, allow_write=True)
        store = Workflows(self.memory, self.workspace)
        learned = store.learn(result['session'], 'learned-note')
        self.assertFalse(learned['workflow']['reviewed'])
        self.assertTrue(store.regress(learned['workflow']['id'], learned['fixtures'], self.config)['ok'])
        self.assertEqual(learned['workflow']['plan']['completion']['children'][0]['check']['type'], 'file_sha256')

    def test_chat_retains_historical_tool_evidence(self):
        (self.workspace/'input.txt').write_text('Observed source text')
        store = Conversations(self.memory, self.workspace); cid = store.create()
        chat(self.config, self.memory, self.workspace, cid, 'read file "input.txt"', offline=True)
        context = store.context(cid, 'What did that file say?')
        self.assertEqual(context['observations'][0]['event']['result']['text'], 'Observed source text')
        self.assertTrue(context['observations'][0]['historical'])

    def test_stale_approval_and_changed_workflow_rejected(self):
        engine = Harness(self.config, self.memory, self.workspace)
        pending = engine.run('Create', workflow=plan(), offline=True)
        altered = copy.deepcopy(plan()); altered['description'] = 'Changed'
        with self.assertRaises(ValueError): engine.run(sid=pending['session'], workflow=altered)
        (self.workspace/'note.txt').write_text('Someone else wrote this')
        result = engine.run(sid=pending['session'], approve=pending['pending']['ticket'], offline=True)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual((self.workspace/'note.txt').read_text(), 'Someone else wrote this')


if __name__ == '__main__':
    unittest.main()
