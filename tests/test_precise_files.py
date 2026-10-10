import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aeon.config import load
from aeon.engine import Harness
from aeon.inference import SGLang, decision_schema
from aeon.memory import Memory, packed
from aeon.tools import Tools, validate_action
from aeon.workflows import Workflows
from test_harness import FakeModel, decision
from test_decisions import Backend


class PreciseFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.work = self.root/'work'; self.work.mkdir()
        self.tools = Tools(self.work)
        self.memory = Memory(self.root/'state')
        self.config = load()

    def tearDown(self):
        self.memory.close(); self.tmp.cleanup()

    def edit(self, old='target = 1', new='target = 2'):
        return {'tool': 'edit_file', 'args': {'path': 'code.txt', 'old_text': old, 'new_text': new,
                'expected_sha256': self.tools.read('code.txt')['sha256']}}

    def test_local_range_reaches_beyond_prefix_with_exact_evidence(self):
        text = ''.join(f'line {i:04d} preserved contents\r\n' for i in range(1, 1001))
        (self.work/'code.txt').write_bytes(text.encode())
        result = Harness(self.config, self.memory, self.work).run('read lines 900-902 of "code.txt"', offline=True)
        self.assertEqual(result['llm_calls'], 0)
        excerpt = result['results'][0]['result']
        self.assertEqual(excerpt['text'], ''.join(text.splitlines(keepends=True)[899:902]))
        self.assertEqual(excerpt['start_line'], 900)
        self.assertEqual(excerpt['end_line'], 902)
        self.assertEqual(excerpt['sha256'], hashlib.sha256(text.encode()).hexdigest())
        self.assertTrue(excerpt['truncated'])
        self.assertNotIn('line 0900', self.tools.read('code.txt')['text'])

    def test_range_validation_and_output_bounds(self):
        base = {'tool': 'read_lines', 'args': {'path': 'code.txt', 'start_line': 1, 'end_line': 1}}
        for start, end in [(0, 1), (2, 1), (1, 201), (True, 1), ('1', 1)]:
            action = copy.deepcopy(base); action['args'].update(start_line=start, end_line=end)
            with self.assertRaises(ValueError): validate_action(action)
        (self.work/'code.txt').write_bytes(b'x'*16001)
        self.assertFalse(self.tools.execute(base)['ok'])
        (self.work/'code.txt').write_bytes(b'one\n')
        base['args'].update(start_line=3, end_line=3)
        self.assertFalse(self.tools.execute(base)['ok'])
        base['args'].update(path='../outside', start_line=1, end_line=1)
        self.assertFalse(self.tools.execute(base)['ok'])
        schema = next(t for t in decision_schema()['properties']['actions']['items']['anyOf']
                      if t['properties']['tool']['const'] == 'read_lines')
        self.assertEqual(schema['properties']['args']['properties']['start_line']['type'], 'integer')

    def test_small_edit_preserves_other_bytes_and_is_smaller_than_rewrite(self):
        before = ('untouched αβ\r\n'*2000 + 'target = 1\r\n' + 'tail\r\n').encode()
        target = self.work/'code.txt'; target.write_bytes(before)
        action = self.edit()
        result = self.tools.execute(action, self.tools.prepare(action))
        expected = before.replace(b'target = 1', b'target = 2')
        self.assertTrue(result['ok'])
        self.assertEqual(target.read_bytes(), expected)
        self.assertEqual(result['sha256'], hashlib.sha256(expected).hexdigest())
        whole = {'tool':'write_file','args':{'path':'code.txt','content':expected.decode(),
                 'expected_sha256':hashlib.sha256(before).hexdigest()}}
        self.assertLess(len(packed(action).encode()), len(packed(whole).encode())/50)

    def test_edit_rejects_ambiguous_missing_invalid_and_stale_source(self):
        target = self.work/'code.txt'
        for content, old in [(b'target = 1 target = 1', 'target = 1'), (b'aaa', 'aa'),
                             (b'no match', 'target = 1'), (b'\xfftarget = 1', 'target = 1')]:
            target.write_bytes(content)
            with self.assertRaises(ValueError): self.tools.prepare(self.edit(old=old))
            self.assertEqual(target.read_bytes(), content)
        target.write_bytes(b'target = 1')
        action = self.edit(); binding = self.tools.prepare(action)
        target.write_bytes(b'someone else changed this')
        self.assertFalse(self.tools.execute(action, binding)['ok'])
        self.assertEqual(target.read_bytes(), b'someone else changed this')
        for old, new, sha in [('', 'x', binding['sha256']), ('x', 'x', binding['sha256']), ('x', 'y', 'missing')]:
            bad = self.edit(old, new); bad['args']['expected_sha256'] = sha
            with self.assertRaises(ValueError): validate_action(bad)

    def test_edit_requires_approval_and_resumes_exact_action(self):
        target = self.work/'code.txt'; target.write_bytes(b'target = 1')
        action = self.edit()
        backend = FakeModel(decision([action]), decision(answer='Changed', done=True))
        engine = Harness(self.config, self.memory, self.work, backend=backend)
        pending = engine.run('Change the target')
        self.assertEqual(pending['status'], 'needs_approval')
        self.assertEqual(target.read_bytes(), b'target = 1')
        done = engine.run(sid=pending['session'], approve=pending['pending']['ticket'])
        self.assertEqual(done['status'], 'complete')
        self.assertEqual(target.read_bytes(), b'target = 2')
        self.assertEqual(len(backend.calls), 2)

    def test_edit_can_be_learned_replayed_and_verified(self):
        (self.work/'code.txt').write_bytes(b'target = 1')
        backend = FakeModel(decision([{'tool':'read_file','args':{'path':'code.txt'}}]),
                            decision([self.edit()]), decision(answer='Changed', done=True))
        result = Harness(self.config, self.memory, self.work, backend=backend).run('Update target', allow_write=True)
        self.assertEqual(result['status'], 'complete')
        store = Workflows(self.memory, self.work)
        learned = store.learn(result['session'], 'edit-target')
        report = store.regress(learned['workflow']['id'], learned['fixtures'], self.config)
        self.assertTrue(report['ok'])
        self.assertEqual(report['results'][0]['llm_calls'], 0)

    def test_default_skips_two_shadow_calls_but_keeps_completion_assessment(self):
        counts = {}
        for mode in ('shadow', 'off'):
            backend = Backend()
            client = SGLang({**backend.profile, 'endpoint': backend.url})
            config = copy.deepcopy(self.config); config['decisions']['routing'] = mode
            with patch.object(client, 'info', backend.info), patch.object(client, 'call', backend.call), \
                 patch.object(client, 'decide', return_value=(decision(answer='Answer', done=True), {})):
                result = Harness(config, self.memory, self.work, backend=client).run('Explain the directory')
            counts[mode] = result['decision_calls']
            self.assertEqual(result['llm_calls'], 1)
            self.assertTrue(any(e['kind'] == 'supervisor' for e in self.memory.events(result['session'])))
        self.assertEqual(self.config['decisions']['routing'], 'off')
        self.assertEqual(counts, {'shadow': 3, 'off': 1})
