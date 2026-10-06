"""Framing/identity checks for the Mojo worker; all model calls stay in Mojo/C."""
import hashlib
import json
import os
from pathlib import Path
import sys

from app.json_protocol import unique_object
from app.workbench.state import verify_inputs

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def worker_manifest(binary: Path) -> dict:
    manifest = json.loads(binary.with_suffix('.json').read_text())
    if manifest['version'] != 1 or digest(binary) != manifest['sha256']:
        raise ValueError('Native worker identity changed')
    for name, expected in manifest['sources'].items():
        if digest(ROOT / name) != expected:
            raise ValueError('Native worker source changed')
    return manifest


def read_request(binary: str) -> tuple[str, str, int, dict]:
    manifest = worker_manifest(Path(binary))
    raw = sys.stdin.buffer.read(65537)
    request = json.loads(raw, object_pairs_hook=unique_object)
    if (len(raw) > 65536 or type(request) is not dict or set(request) != {'prompt', 'tokens'} or
            not isinstance(request['prompt'], str) or not request['prompt'].strip() or
            len(request['prompt'].encode()) > 16384 or '\x00' in request['prompt'] or
            type(request['tokens']) is not int or not 1 <= request['tokens'] <= 512):
        raise ValueError('Invalid native worker request')
    model = Path(os.environ['OMARCHY_NATIVE_MODEL'])
    identity = verify_inputs(Path(manifest['adapter']), model, '2.9b')
    if identity['adapter_sha256'] != manifest['adapter_sha256']:
        raise ValueError('Native worker adapter changed')
    return str(model), request['prompt'], request['tokens'], identity


def runtime_facts(identity: dict, tokens: int) -> dict:
    return {'model_sha256': identity['model_sha256'],
                  'adapter_sha256': identity['adapter_sha256'], 'runtime_revision': identity['runtime_revision'],
                  'backend': 'cpu', 'context': 4096, 'threads': 4, 'sampler': 'greedy-json-answer-v1',
                  'generated_tokens': tokens, 'session_lifetime': 'one_request'}


def write_ready(identity: dict) -> None:
    sys.stdout.write(json.dumps({'event': 'ready', 'native_runtime': runtime_facts(identity, 0)}) + '\n')
    sys.stdout.flush()


def write_response(output: bytearray, ended: bool, identity: dict, tokens: int) -> None:
    text = output.decode('utf-8', errors='strict')
    result = {'choices': [{'finish_reason': 'stop' if ended else 'length', 'message': {'content': text}}],
              'native_runtime': runtime_facts(identity, tokens)}
    sys.stdout.write(json.dumps(result, ensure_ascii=True) + '\n')
    sys.stdout.flush()
