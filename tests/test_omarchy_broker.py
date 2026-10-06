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
        client.settimeout(5)
        client.connect(self.path)
        return client

    def request(self, payload):
        with self.connect() as client:
            client.sendall(payload)
            return self.response(client)

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
        self.assertEqual(self.request(b'MOCK\n'),
                         {'ok': True, 'mock': True, 'result': 'Mock response; no model invoked'})

    def test_anchor_response(self):
        result = self.request(b'ANCHOR\n')
        self.assertTrue(result['ok'])
        self.assertIn('[SYSTEM_ANCHOR]', result['anchor'])
        self.assertIn('2026', result['anchor'])

    def test_protocol_v1_structured_requests(self):
        self.assertEqual(self.request(b'{"v":1,"action":"ping"}\n'),
                         {'ok': True, 'v': 1, 'result': 'pong'})

        status = self.request(b'{"v":1,"action":"status"}\n')
        self.assertTrue(status['ok'])
        self.assertEqual(status['v'], 1)
        self.assertEqual(status['transport'], 'native-mojo-unix')
        self.assertEqual(status['rwkv7'], 'not_connected')
        self.assertEqual(status['sandbox'], 'disabled')

        mock = self.request(b'{"v":1,"action":"mock"}\n')
        self.assertEqual(mock, {'ok': True, 'v': 1, 'mock': True, 'result': 'Mock response; no model invoked'})

        anchor = self.request(b'{"v":1,"action":"anchor"}\n')
        self.assertTrue(anchor['ok'])
        self.assertEqual(anchor['v'], 1)
        self.assertIn('2026', anchor['anchor'])

        sandbox = self.request(b'{"v":1,"action":"sandbox_status"}\n')
        self.assertTrue(sandbox['ok'])
        self.assertEqual(sandbox['v'], 1)
        self.assertEqual(sandbox['sandbox'], 'disabled')
        from app.broker_actions import landlock_abi
        self.assertEqual(sandbox['landlock_abi'], landlock_abi())
        self.assertTrue(sandbox['dry_run_only'])

        landlock = self.request(b'{"v":1,"action":"landlock_probe"}\n')
        self.assertTrue(landlock['ok'])
        self.assertEqual(landlock['v'], 1)
        self.assertEqual(landlock['landlock_supported'], landlock_abi() >= 1)
        self.assertEqual(landlock['abi_version'], landlock_abi())

        rwkv = self.request(b'{"v":1,"action":"rwkv_status"}\n')
        self.assertTrue(rwkv['ok'])
        self.assertEqual(rwkv['v'], 1)
        self.assertEqual(rwkv['rwkv7'], 'not_connected')
        self.assertFalse(rwkv['tool_execution'])

        telemetry = self.request(b'{"v":1,"action":"telemetry"}\n')
        self.assertTrue(telemetry['ok'])
        self.assertEqual(telemetry['v'], 1)
        self.assertEqual(telemetry['type'], 'telemetry')
        self.assertEqual(telemetry['status'], 'unavailable')

        os_ctrl = self.request(b'{"v":1,"action":"os_controller"}\n')
        self.assertTrue(os_ctrl['ok'])
        self.assertEqual(os_ctrl['v'], 1)
        self.assertEqual(os_ctrl['controller'], 'unavailable')
        self.assertFalse(os_ctrl['hyprland_ipc'])
        self.assertFalse(os_ctrl['quickshell_ipc'])
        self.assertFalse(os_ctrl['fastpath_enabled'])

        unknown_v1 = self.request(b'{"v":1,"action":"nonexistent"}\n')
        self.assertEqual(unknown_v1, {'ok': False, 'v': 1, 'error': 'unsupported_v1_action'})

    def test_json_whitespace_and_key_order(self):
        for payload in ({'v': 1, 'action': 'ping'}, {'action': 'ping', 'v': 1}):
            self.assertEqual(self.request((json.dumps(payload) + '\n').encode())['result'], 'pong')

    def test_unknown_and_non_ascii_commands_are_rejected(self):
        for payload in (b'RUN rm -rf /\n', b'\xff\n', b'\n', b'PING\x00\n'):
            with self.subTest(payload=payload):
                self.assertEqual(self.request(payload),
                                 {'ok': False, 'error': 'unsupported_command'})

    def test_fragmented_command(self):
        with self.connect() as client:
            client.sendall(b'PI')
            time.sleep(0.03)
            client.sendall(b'NG\n')
            self.assertEqual(self.response(client)['result'], 'pong')

    def test_oversized_and_pipelined_frames(self):
        self.assertEqual(self.request(b'A' * 1025),
                         {'ok': False, 'error': 'request_too_large'})
        self.assertEqual(self.request(b'PING\nSTATUS\n'),
                         {'ok': False, 'error': 'multiple_frames'})

    def test_incomplete_and_idle_clients_do_not_block_forever(self):
        with self.connect() as client:
            client.sendall(b'PI')
            client.shutdown(socket.SHUT_WR)
            self.assertEqual(self.response(client)['error'], 'incomplete_request')
        with self.connect() as client:
            self.assertEqual(self.response(client)['error'], 'request_timeout')
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
        self.assertEqual(self.request(b'A' * 1024 + b'\n'),
                         {'ok': False, 'error': 'unsupported_command'})
        self.assertEqual(self.request(b'A' * 1025 + b'\n'),
                         {'ok': False, 'error': 'request_too_large'})

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
