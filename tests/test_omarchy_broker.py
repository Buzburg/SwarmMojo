"""Offline native broker contract tests; run on Linux with an explicitly built binary."""
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor


class NativeBrokerTests(unittest.TestCase):
    def setUp(self):
        prefix = Path(os.getenv('ROMS_PYTHON_PREFIX', str(Path(__file__).resolve().parents[1] / '.pixi/envs/default')))
        self.binary = os.environ.get('OMARCHY_BROKER_BINARY', str(prefix / 'bin/omarchy-broker'))
        self.assertTrue(Path(self.binary).is_file(), 'Build the native broker first')
        self.directory = tempfile.TemporaryDirectory(prefix='omarchy-')
        self.addCleanup(self.directory.cleanup)
        self.path = str(Path(self.directory.name) / 'broker.sock')
        self.env = dict(os.environ, OMARCHY_BROKER_SOCKET=self.path, ROMS_GATEWAY_PORT='9',
                        OMARCHY_TASK_WORKER_SOCKET=str(Path(self.directory.name) / 'missing-worker.sock'))
        self.process = subprocess.Popen([self.binary], env=self.env,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self.stop)
        deadline = time.monotonic() + 5
        while not Path(self.path).exists():
            if self.process.poll() is not None:
                self.fail(self.process.communicate()[1].decode(errors='replace'))
            if time.monotonic() > deadline:
                self.fail('Broker did not bind within five seconds')
            time.sleep(0.01)

    def stop(self):
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.communicate(timeout=5)

    def connect(self):
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(8)
        client.connect(self.path)
        return client

    def request(self, payload):
        with self.connect() as client:
            client.sendall(payload)
            return self.response(client)

    def v1(self, action, args=None):
        response = self.request((json.dumps({'v': 1, 'id': 'fixture', 'action': action, 'args': args or {}}) + '\n').encode())
        self.assertEqual(response['v'], 1)
        self.assertEqual(response['id'], 'fixture')
        self.assertEqual(set(response), {'v', 'id', 'ok', 'result' if response['ok'] else 'error'})
        return response

    def response(self, client):
        data = bytearray()
        while not data.endswith(b'\n'):
            chunk = client.recv(4096)
            if not chunk:
                break
            data.extend(chunk)
        self.assertTrue(data.endswith(b'\n'), data)
        return json.loads(data)

    def test_ping_and_permissions(self):
        self.assertEqual(self.request(b'PING\n'), {'ok': True, 'result': 'pong'})
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o700)

    def test_status_does_not_claim_inference_or_tools(self):
        result = self.request(b'STATUS\n')
        self.assertTrue(result['ok'])
        self.assertEqual(result['transport'], 'native-mojo-unix')
        self.assertEqual(result['rwkv7'], 'not_connected')
        self.assertFalse(result['tool_execution'])

    def test_mock_is_explicit(self):
        self.assertEqual(self.v1('mock')['result'],
                         {'mock': True, 'result': 'Mock response; no model invoked'})

    def test_anchor_response(self):
        result = self.v1('anchor')['result']
        self.assertIn('[SYSTEM_ANCHOR]', result['anchor'])
        self.assertIn('2026', result['anchor'])

    def test_protocol_v1_structured_requests(self):
        self.assertEqual(self.v1('ping'),
                         {'ok': True, 'v': 1, 'id': 'fixture', 'result': 'pong'})

        status = self.v1('status')['result']
        self.assertEqual(status['transport'], 'native-mojo-unix')
        self.assertEqual(status['rwkv7'], 'not_connected')
        self.assertEqual(status['sandbox'], 'disabled')

        mock = self.v1('mock')['result']
        self.assertEqual(mock, {'mock': True, 'result': 'Mock response; no model invoked'})

        anchor = self.v1('anchor')['result']
        self.assertIn('2026', anchor['anchor'])

        sandbox = self.v1('sandbox_status')['result']
        self.assertEqual(sandbox['sandbox'], 'disabled')
        from app.broker_actions import landlock_abi
        self.assertEqual(sandbox['landlock_abi'], landlock_abi())
        self.assertTrue(sandbox['dry_run_only'])

        landlock = self.v1('landlock_probe')['result']
        self.assertEqual(landlock['landlock_supported'], landlock_abi() >= 1)
        self.assertEqual(landlock['abi_version'], landlock_abi())

        rwkv = self.v1('rwkv_status')['result']
        self.assertEqual(rwkv['rwkv7'], 'not_connected')
        self.assertFalse(rwkv['tool_execution'])

        telemetry = self.v1('telemetry')['result']
        self.assertEqual(telemetry['type'], 'telemetry')
        self.assertEqual(telemetry['status'], 'unavailable')

        os_ctrl = self.v1('os_controller')['result']
        self.assertEqual(os_ctrl['controller'], 'unavailable')
        self.assertFalse(os_ctrl['hyprland_ipc'])
        self.assertFalse(os_ctrl['quickshell_ipc'])
        self.assertFalse(os_ctrl['fastpath_enabled'])

        unknown_v1 = self.v1('nonexistent')
        self.assertFalse(unknown_v1['ok'])
        self.assertEqual(unknown_v1['error']['code'], 'NOT_IMPLEMENTED')

    def test_json_whitespace_and_key_order(self):
        for payload in ({'v': 1, 'id': 'fixture', 'action': 'ping', 'args': {}},
                        {'args': {}, 'action': 'ping', 'id': 'fixture', 'v': 1}):
            self.assertEqual(self.request((json.dumps(payload) + '\n').encode())['result'], 'pong')

    def test_strict_contract_over_real_socket(self):
        for payload in (b'{"v":1,"v":1,"id":"x","action":"ping","args":{}}',
                        b'{"v":true,"id":"x","action":"ping","args":{}}',
                        b'{"v":1,"id":"x","action":"ping","args":{},"extra":0}',
                        b'{"v":1,"id":"x","action":"chat","args":{"prompt":"\xff"}}'):
            with self.subTest(payload=payload):
                response = self.request(payload + b'\n')
                self.assertFalse(response['ok'])
                self.assertEqual(set(response['error']), {'code', 'message'})
        nested = '[' * 16 + '0' + ']' * 16
        raw = ('{"v":1,"id":"x","action":"state.save","args":{"nested":' + nested + '}}\n').encode()
        self.assertEqual(self.request(raw)['error']['code'], 'INVALID_REQUEST')
        self.assertEqual(self.v1('state.save')['error']['code'], 'NOT_IMPLEMENTED')
        self.assertEqual(self.v1('ping')['result'], 'pong')

    def test_concurrent_callers_keep_their_response_ids(self):
        def call(number):
            payload = {'v': 1, 'id': str(number), 'action': 'ping', 'args': {}}
            response = self.request((json.dumps(payload) + '\n').encode())
            return response['id'], response['result']
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(list(pool.map(call, range(16))), [(str(i), 'pong') for i in range(16)])

    def test_unknown_and_non_ascii_commands_are_rejected(self):
        for payload in (b'RUN rm -rf /\n', b'\xff\n', b'\n', b'PING\x00\n'):
            with self.subTest(payload=payload):
                response = self.request(payload)
                self.assertFalse(response['ok'])
                self.assertEqual(response['error']['code'], 'INVALID_REQUEST')
                self.assertIsNone(response['id'])

    def test_fragmented_command(self):
        with self.connect() as client:
            client.sendall(b'PI')
            time.sleep(0.03)
            client.sendall(b'NG\n')
            self.assertEqual(self.response(client)['result'], 'pong')

    def test_oversized_and_pipelined_frames(self):
        self.assertEqual(self.request(b'A' * 65537)['error']['code'], 'REQUEST_TOO_LARGE')
        self.assertEqual(self.request(b'PING\nSTATUS\n')['error']['code'], 'MULTIPLE_FRAMES')

    def test_incomplete_and_idle_clients_do_not_block_forever(self):
        with self.connect() as client:
            client.sendall(b'PI')
            client.shutdown(socket.SHUT_WR)
            self.assertEqual(self.response(client)['error']['code'], 'INCOMPLETE_REQUEST')
        with self.connect() as client:
            started = time.monotonic()
            self.assertEqual(self.response(client)['error']['code'], 'REQUEST_TIMEOUT')
            self.assertGreaterEqual(time.monotonic() - started, 4.8)
        self.assertEqual(self.request(b'PING\n')['result'], 'pong')

    def test_disconnect_does_not_kill_broker(self):
        with self.connect() as client:
            client.sendall(b'PING\n')
        self.assertEqual(self.request(b'PING\n')['result'], 'pong')
        self.assertIsNone(self.process.poll())

    def test_second_broker_does_not_replace_socket(self):
        before = os.stat(self.path).st_ino
        result = subprocess.run([self.binary], env=self.env, capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(os.stat(self.path).st_ino, before)
        self.assertEqual(self.request(b'PING\n')['result'], 'pong')

    def test_existing_regular_file_is_preserved(self):
        obstacle = Path(self.directory.name) / 'existing'
        obstacle.write_text('keep me')
        result = subprocess.run([self.binary],
                                env=dict(self.env, OMARCHY_BROKER_SOCKET=str(obstacle)),
                                capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(obstacle.read_text(), 'keep me')

    def test_maximum_frame_boundary(self):
        payload = json.dumps({'v': 1, 'id': 'boundary', 'action': 'ping', 'args': {}}).encode()
        payload += b' ' * (65536 - len(payload))
        self.assertEqual(self.request(payload + b'\n')['result'], 'pong')
        self.assertEqual(self.request(payload + b' \n')['error']['code'], 'REQUEST_TOO_LARGE')

    def test_missing_or_relative_socket_path_is_rejected(self):
        for value in ('', 'relative.sock'):
            with self.subTest(value=value):
                result = subprocess.run([self.binary],
                                        env=dict(self.env, OMARCHY_BROKER_SOCKET=value),
                                        capture_output=True, timeout=5)
                self.assertNotEqual(result.returncode, 0)

    def test_existing_symlink_is_preserved(self):
        target = Path(self.directory.name) / 'target'
        target.write_text('keep target')
        link = Path(self.directory.name) / 'link.sock'
        link.symlink_to(target)
        result = subprocess.run([self.binary],
                                env=dict(self.env, OMARCHY_BROKER_SOCKET=str(link)),
                                capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(link.is_symlink())
        self.assertEqual(target.read_text(), 'keep target')

    def test_symlinked_runtime_directory_is_rejected(self):
        link = Path(self.directory.name) / 'alias'
        link.symlink_to(self.directory.name, target_is_directory=True)
        result = subprocess.run([self.binary],
                                env=dict(self.env, OMARCHY_BROKER_SOCKET=str(link / 'alias.sock')),
                                capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((Path(self.directory.name) / 'alias.sock').exists())

    def test_symlinked_ancestor_is_rejected(self):
        real = Path(self.directory.name) / 'real'
        real.mkdir(mode=0o700)
        nested = real / 'nested'
        nested.mkdir(mode=0o700)
        alias = Path(self.directory.name) / 'ancestor'
        alias.symlink_to(real, target_is_directory=True)
        result = subprocess.run([self.binary],
                                env=dict(self.env, OMARCHY_BROKER_SOCKET=str(alias / 'nested' / 'other.sock')),
                                capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((nested / 'other.sock').exists())

    def test_runtime_directory_rename_does_not_redirect_broker(self):
        directory = Path(self.directory.name)
        moved = Path(str(directory) + '-moved')
        directory.rename(moved)
        try:
            directory.mkdir(mode=0o700)
            self.path = str(moved / 'broker.sock')
            self.assertEqual(self.request(b'PING\n')['result'], 'pong')
            self.assertFalse((directory / 'broker.sock').exists())
        finally:
            directory.rmdir()
            moved.rename(directory)

    def test_invalid_socket_leaf_names_are_rejected(self):
        for leaf in ('', '.', '..'):
            with self.subTest(leaf=leaf):
                result = subprocess.run([self.binary],
                                        env=dict(self.env, OMARCHY_BROKER_SOCKET=self.directory.name + '/' + leaf),
                                        capture_output=True, timeout=5)
                self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.request(b'PING\n')['result'], 'pong')

    def test_repeated_clients_do_not_leak_descriptors(self):
        descriptors = Path('/proc') / str(self.process.pid) / 'fd'
        self.request(b'PING\n')
        before = len(list(descriptors.iterdir()))
        for _ in range(40):
            self.assertEqual(self.request(b'PING\n')['result'], 'pong')
        deadline = time.monotonic() + 1
        while len(list(descriptors.iterdir())) > before and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertLessEqual(len(list(descriptors.iterdir())), before)

    def test_shared_directory_is_rejected(self):
        shared = Path(self.directory.name) / 'shared'
        shared.mkdir(mode=0o755)
        result = subprocess.run([self.binary],
                                env=dict(self.env, OMARCHY_BROKER_SOCKET=str(shared / 'broker.sock')),
                                capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((shared / 'broker.sock').exists())


if __name__ == '__main__':
    unittest.main()
