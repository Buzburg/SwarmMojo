import json
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from aeon.mcp import Server


class Sink:
    def __init__(self):
        self.messages = queue.Queue()

    def write(self, value):
        self.messages.put(json.loads(value))

    def flush(self):
        pass

    def get(self):
        return self.messages.get(timeout=10)


class SwarmInterfaces(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'sample.py').write_text('class Service:\n    def send(self, item):\n        return item\n')

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *args):
        result = subprocess.run([sys.executable, '-m', 'swarm_mojo', '--config', str(self.root / 'missing.toml'),
                                 '--state-dir', str(self.root / '.state'), *args, '--workspace', str(self.root)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / '.state').exists())
        return json.loads(result.stdout)

    def test_offline_cli_reads_source_without_model_configuration(self):
        mapping = self.cli('repo-map')
        self.assertIn('Service.send', json.dumps(mapping))
        result = self.cli('swarm-review', 'Review this service', '--mode', 'MEDIUM')
        self.assertEqual(result['status'], 'prepared')
        self.assertEqual(result['model_calls'], 0)
        self.assertEqual(len(result['reviews']), 3)
        self.assertFalse(result['executionAllowed'])

    def test_mcp_packets_never_enable_model_or_execution(self):
        sink = Sink()
        server = Server(self.root, None, sink)
        def send(rid, method, params):
            server.dispatch({'jsonrpc': '2.0', 'id': rid, 'method': method, 'params': params})
            return sink.get()
        try:
            response = send(1, 'initialize', {'protocolVersion': '2025-11-25', 'capabilities': {},
                                            'clientInfo': {'name': 'test', 'version': '1'}})
            self.assertEqual(response['result']['serverInfo']['name'], 'swarm-mojo')
            server.dispatch({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
            with patch('aeon.inference.make_backend') as backend:
                for tool, args in [('repo_map', {}), ('swarm_review', {'goal': 'Review service', 'mode': 'high'})]:
                    result = send(2, 'tools/call', {'name': tool, 'arguments': args})['result']
                    self.assertFalse(result['isError'])
                    self.assertFalse(result['structuredContent']['value']['executionAllowed'])
                for extra in ({'model': 'msgl'}, {'execute': True}, {'mode': []}, {'path': '../outside'}):
                    result = send(3, 'tools/call', {'name': 'swarm_review',
                                                 'arguments': {'goal': 'Review service', **extra}})['result']
                    self.assertTrue(result['isError'])
                backend.assert_not_called()
        finally:
            server.close()


if __name__ == '__main__':
    unittest.main()
