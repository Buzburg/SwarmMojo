from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from aeon.config import load
from aeon.web import AssistantServer


class WebTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.work = self.root/'work'; self.work.mkdir()
        self.server = AssistantServer(('127.0.0.1', 0), load(), self.root/'state', self.work, True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.tmp.cleanup()

    def request(self, method, path, body=None, token=True, origin=None, host=None):
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        headers = {'Content-Type': 'application/json'}
        if token: headers['X-Aeon-Token'] = self.server.token
        if origin: headers['Origin'] = origin
        if host: headers['Host'] = host
        connection.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = connection.getresponse(); raw = response.read(); status = response.status
        connection.close()
        return status, raw.decode()

    def job(self, path, body):
        status, raw = self.request('POST', path, body)
        self.assertEqual(status, 202, raw); key = json.loads(raw)['job']
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            status, raw = self.request('GET', '/api/job?id='+key)
            self.assertEqual(status, 200, raw); response = json.loads(raw)
            if response['done']: return response['result']
            time.sleep(.01)
        self.fail('Job did not finish within 10 seconds: ' + raw)

    def test_origin_host_token_and_plain_text_page(self):
        for kwargs in ({'token': False}, {'origin': 'http://evil.test'}, {'host': 'evil.test'}):
            self.assertEqual(self.request('POST', '/api/conversation', {}, **kwargs)[0], 403)
        self.assertEqual(self.request('GET', '/api/state', token=False)[0], 403)
        status, page = self.request('GET', '/', token=False)
        self.assertEqual(status, 200); self.assertIn('textContent', page)
        self.assertNotIn('__TOKEN__', page)

    def test_code_review_observes_source_without_model_state_or_execution(self):
        self.server.offline = False  # This endpoint stays offline even when ordinary chat can use a model.
        source = self.work / 'invoice.py'
        original = 'raise RuntimeError("source must never execute")\nclass Invoice:\n    def total(self):\n        return 42\n'
        source.write_text(original, encoding='utf-8')
        with patch('aeon.inference.make_backend') as backend, patch('aeon.web.Memory') as memory:
            mapping = self.job('/api/swarm', {'operation': 'map', 'path': '.'})
            report = self.job('/api/swarm', {'operation': 'prepare', 'path': '.',
                                          'goal': 'Review Invoice.total', 'mode': 'max'})
            backend.assert_not_called()
            memory.assert_not_called()
        names = [symbol['name'] for file in mapping['files'] for symbol in file['symbols']]
        self.assertEqual(names, ['Invoice', 'Invoice.total'])
        self.assertEqual(report['status'], 'prepared')
        self.assertEqual(report['model_calls'], 0)
        self.assertEqual(len(report['reviews']), 5)
        self.assertTrue(all(role['status'] == 'prepared' for role in report['reviews']))
        for result in (mapping, report):
            self.assertTrue(result['advisory_only'])
            self.assertFalse(result['authorizes_apply'])
            self.assertFalse(result['executionAllowed'])
        self.assertEqual(source.read_text(encoding='utf-8'), original)
        self.assertEqual(list(self.work.iterdir()), [source])
        self.assertFalse((self.root / 'state').exists())

    def test_code_review_rejects_authority_and_wrong_origin(self):
        base = {'operation': 'prepare', 'goal': 'Review the code'}
        for kwargs in ({'token': False}, {'origin': 'http://evil.test'}, {'host': 'evil.test'}):
            self.assertEqual(self.request('POST', '/api/swarm', base, **kwargs)[0], 403)
        invalid = [{}, {'operation': []}, {'operation': 'execute'}, {'operation': 'prepare'},
                   {'operation': 'map', 'goal': 'ignored'}]
        invalid.extend({**base, key: value} for key, value in (
            ('model', 'qwen27'), ('execute', True), ('allow_write', True),
            ('workspace', str(self.root)), ('profile', {}), ('timeout', 600)))
        for body in invalid:
            with self.subTest(body=body):
                self.assertEqual(self.request('POST', '/api/swarm', body)[0], 400)
        self.assertEqual(self.server.jobs, {})

    def test_code_review_invalid_scope_and_goal_return_errors_without_state(self):
        invalid = [{'operation': 'map', 'path': '../'}, {'operation': 'map', 'path': '.state'},
                   {'operation': 'map', 'path': []}, {'operation': 'prepare', 'goal': ''},
                   {'operation': 'prepare', 'goal': 'x' * 8001},
                   {'operation': 'prepare', 'goal': 'review', 'mode': 'unbounded'}]
        for body in invalid:
            with self.subTest(body=body):
                status, raw = self.request('POST', '/api/swarm', body)
                self.assertEqual(status, 202, raw)
                key = json.loads(raw)['job']
                with self.assertRaises(ValueError):
                    self.server.jobs[key].result(timeout=10)
                status, raw = self.request('GET', '/api/job?id=' + key)
                self.assertEqual(status, 400, raw)
                self.assertTrue(json.loads(raw)['error'])
        self.assertFalse((self.root / 'state').exists())

    def test_plan_preview_does_not_execute_or_create_a_task(self):
        from aeon.memory import Memory
        plan = self.job('/api/plan', {'text': 'list files then system status'})
        self.assertEqual(plan['tool_steps'], 2)
        self.assertFalse(plan['requires_approval'])
        self.assertEqual(plan['source'], 'local')
        memory = Memory(self.root/'state')
        try:
            self.assertEqual(memory.db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 0)
        finally:
            memory.close()
        unknown = self.job('/api/plan', {'text': 'list files then invent a story'})
        self.assertEqual(unknown['source'], 'model_required')
        self.assertEqual(unknown['actions'], [])
        self.assertEqual(self.request('POST', '/api/plan', {'text': 'list files'}, token=False)[0], 403)

    def test_conversation_note_correction_and_offline_task(self):
        cid = self.job('/api/conversation', {'title': 'Test'})['conversation']
        entry = self.job('/api/note', {'conversation': cid, 'text': 'blue'})['entry']
        self.job('/api/note', {'conversation': cid, 'text': 'green', 'replaces': entry})
        result = self.job('/api/chat', {'conversation': cid, 'text': 'list files'})
        self.assertEqual(result['status'], 'complete'); self.assertEqual(result['llm_calls'], 0)
        status, raw = self.request('GET', '/api/state?conversation='+cid)
        state = json.loads(raw); self.assertEqual(len(state['entries']), 4)
        self.assertIn(result['session'], state['sessions'])

    def test_workflow_browser_api_keeps_mutation_approval(self):
        from test_assistant import plan
        cid = self.job('/api/conversation', {'title': 'Workflow'})['conversation']
        draft = self.job('/api/workflow', {'operation': 'propose', 'plan': plan()})
        checked = self.job('/api/workflow', {'operation': 'test', 'id': draft['id'],
            'fixtures': [{'files': {}, 'expect': 'complete'}, {'files': {'note.txt': 'keep'}, 'expect': 'blocked'}]})
        self.assertTrue(checked['ok']); self.assertFalse((self.work/'note.txt').exists())
        self.job('/api/workflow', {'operation': 'approve', 'id': draft['id']})
        pending = self.job('/api/workflow', {'operation': 'run', 'id': draft['id'], 'conversation': cid})
        self.assertEqual(pending['status'], 'needs_approval'); self.assertFalse((self.work/'note.txt').exists())
        result = self.job('/api/approve', {'conversation': cid, 'session': pending['session'], 'ticket': pending['pending']['ticket']})
        self.assertEqual(result['status'], 'complete'); self.assertEqual(result['verification'], 'workflow_verified')
        learned = self.job('/api/workflow', {'operation': 'learn', 'session': result['session'], 'name': 'learned'})
        self.assertFalse(learned['workflow']['reviewed'])
        self.assertEqual((self.work/'note.txt').read_text(), 'hello')

    def test_old_memory_inspection_correction_and_scope(self):
        from aeon.memory import Memory
        from aeon.conversations import Conversations
        memory = Memory(self.root/'state')
        try:
            store = Conversations(memory, self.work)
            cid = store.create('Old memory')
            original = store.append(cid, 'note', 'Orchid launch uses violet')
            for i in range(210):
                store.append(cid, 'note', f'Unrelated {i}')
            other = store.create('Other conversation')
            outside = Conversations(memory, self.root/'other').create('Other workspace')
        finally:
            memory.close()
        route = '/api/memory?conversation='+cid+'&query=orchid'
        for kwargs in ({'token': False}, {'origin': 'http://evil.test'}, {'host': 'evil.test'}):
            self.assertEqual(self.request('GET', route, **kwargs)[0], 403)
        status, raw = self.request('GET', route)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)['entries'][0]['id'], original)
        source = '/api/entry?conversation='+cid+'&entry='+str(original)
        self.assertEqual(self.request('GET', source, token=False)[0], 403)
        self.assertIsNone(json.loads(self.request('GET', source)[1])['superseded_by'])
        correction = self.job('/api/note', {'conversation': cid, 'text': 'Orchid launch uses green', 'replaces': original})['entry']
        self.assertEqual(json.loads(self.request('GET', source)[1])['superseded_by'], correction)
        self.assertEqual(json.loads(self.request('GET', route)[1])['entries'][0]['id'], correction)
        current = json.loads(self.request('GET', '/api/entry?conversation='+cid+'&entry='+str(correction))[1])
        self.assertEqual(current['replaces'], original)
        self.assertIsNone(current['superseded_by'])
        self.assertEqual(self.request('GET', source.replace(cid, other))[0], 400)
        self.assertEqual(self.request('GET', route.replace(cid, outside))[0], 400)
        for entry_id in ('invalid', '-1', '999999999999999999999999999'):
            self.assertEqual(self.request('GET', '/api/entry?conversation='+cid+'&entry='+entry_id)[0], 400)
        result = self.job('/api/chat', {'conversation': cid, 'text': 'list files'})
        state = json.loads(self.request('GET', '/api/state?conversation='+cid)[1])
        events = [node['event'] for node in state['sessions'][result['session']]['audit']['nodes']]
        context = next(event['context'] for event in events if event['kind'] == 'conversation_context')
        self.assertIn(correction, [entry['id'] for entry in context['entries']])
        self.assertNotIn(original, [entry['id'] for entry in context['entries']])
        newest = self.job('/api/note', {'conversation': cid, 'text': 'Orchid launch uses gold', 'replaces': correction})['entry']
        state = json.loads(self.request('GET', '/api/state?conversation='+cid)[1])
        events = [node['event'] for node in state['sessions'][result['session']]['audit']['nodes']]
        saved = next(event['context'] for event in events if event['kind'] == 'conversation_context')
        self.assertEqual(saved, context)
        source = json.loads(self.request('GET', '/api/entry?conversation='+cid+'&entry='+str(correction))[1])
        self.assertEqual(source['superseded_by'], newest)


if __name__ == '__main__':
    unittest.main()
