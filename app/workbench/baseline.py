"""Start an isolated pinned llama-server for measured qualification; stop it afterward."""
from __future__ import annotations

import json
import os
import re
import secrets
import signal
import socket
import subprocess
import threading
import time
import uuid
from pathlib import Path

import httpx
import psutil

from .qualification import probe_endpoint
from .receipts import Collector, private_directory
from .state import ROOT, digest


def measure(server: Path, model: Path, model_key: str, collector: Collector, *, gpu_layers: int = 0) -> dict:
    inputs = json.loads((ROOT / 'config/build-inputs.json').read_text())
    expected = inputs['models'][model_key]
    if model.stat().st_size != expected['bytes'] or digest(model) != expected['sha256']:
        raise ValueError('Benchmark model does not match the pinned input')
    runtime = json.loads(server.with_name('omarchy-runtime.json').read_text())
    if runtime['revision'] != inputs['runtime']['revision'] or digest(server) != runtime['artifacts'][server.name]:
        raise ValueError('Benchmark runtime does not match its artifact manifest')
    for name, sha in runtime['artifacts'].items():
        if '.so' in name and digest(server.with_name(name)) != sha:
            raise ValueError('Benchmark runtime library changed')
    directory = private_directory(collector.root / 'benchmarks' / uuid.uuid4().hex)
    with socket.socket() as selected:
        selected.bind(('127.0.0.1', 0))
        port = selected.getsockname()[1]
    key = secrets.token_hex(32)
    url = f'http://127.0.0.1:{port}'
    command = [str(server.resolve()), '-m', str(model.resolve()), '--host', '127.0.0.1', '--port', str(port),
        '-c', '2048', '-np', '1', '-b', '64', '-ub', '64', '-t', '3', '-ngl', str(gpu_layers),
        '--no-warmup', '--jinja', '--reasoning', 'auto', '--reasoning-format', 'deepseek',
        '--chat-template-file', str(ROOT / 'config/rwkv-user-assistant.jinja'),
        '--alias', 'goose-' + ('2.9b' if model_key == '2.9b' else '7.2b'), '--slots', '--api-key', key]
    log = directory / 'runtime.log'
    started = time.monotonic()
    memory = {'peak_rss_bytes': 0, 'limited': False}
    stop = threading.Event()
    with log.open('xb') as stream:
        process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            start_new_session=True, env={'HOME': str(Path.home()), 'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8',
                                        'LD_LIBRARY_PATH': str(server.parent.resolve())})
        def monitor() -> None:
            while not stop.wait(.1):
                try:
                    memory['peak_rss_bytes'] = max(memory['peak_rss_bytes'], psutil.Process(process.pid).memory_info().rss)
                    if time.monotonic() - started > 300 or log.stat().st_size > 16 * 1024 * 1024:
                        memory['limited'] = True
                        os.killpg(process.pid, signal.SIGKILL)
                        return
                except (ProcessLookupError, psutil.NoSuchProcess):
                    return
        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
        try:
            with httpx.Client(headers={'Authorization': 'Bearer ' + key}, timeout=2, trust_env=False) as client:
                while True:
                    if process.poll() is not None or time.monotonic() - started > 90:
                        raise RuntimeError('Isolated model did not become ready; inspect ' + str(log))
                    try:
                        if client.get(url + '/health').status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(.2)
            startup = time.monotonic() - started
            result = probe_endpoint(url, 'goose-' + ('2.9b' if model_key == '2.9b' else '7.2b'),
                key=key, checkpoint_sha256=expected['sha256'])
        finally:
            stop.set()
            thread.join(timeout=2)
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
    text = log.read_text(errors='replace')
    offload = re.findall(r'offloaded (\d+)/(\d+) layers', text)
    result.update(process_startup_seconds=startup, startup_scope='new process; OS/model file cache may be warm',
        **memory, runtime_revision=runtime['revision'], server_sha256=digest(server),
        raw_log=str(log), raw_log_sha256=digest(log), server_stopped=process.poll() is not None,
        gpu_layers_requested=gpu_layers,
        observed_gpu_layers=int(offload[-1][0]) if offload else None)
    if offload and int(offload[-1][0]) > 0:
        result['environment']['gpu_model_placement'] = 'runtime reported layer offload; see captured log'
    result['receipt'] = collector.record('isolated-runtime-baseline', [result])
    return result
