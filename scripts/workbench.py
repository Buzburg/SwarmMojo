"""Operator-only repository integrations; no broker/model command execution API."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from app.workbench import integrations
from app.workbench.builds import run_build
from app.workbench.context import CodeIndex, compact_log
from app.workbench.qualification import (
    adoption_decision,
    environment_record,
    probe_endpoint,
)
from app.workbench.receipts import Collector


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument('--store', type=Path, help='Private Linux evidence directory, outside all worker stages')
    commands = root.add_subparsers(dest='command', required=True)
    commands.add_parser('status')
    baseline = commands.add_parser('baseline', help='Measure a separate pinned model process; never restart the installed service')
    baseline.add_argument('--server', type=Path, default=Path('/opt/goose-runtime/bin/llama-server'))
    baseline.add_argument('--model', type=Path, required=True)
    baseline.add_argument('--model-key', choices=['2.9b', '7.2b-q8'], required=True)
    baseline.add_argument('--gpu-layers', type=int, default=0)
    configure = commands.add_parser('configure')
    configure.add_argument('--ptrm', type=Path, required=True)
    configure.add_argument('--triad', type=Path, required=True)
    build = commands.add_parser('build', help='Run an operator-owned trusted build manifest')
    build.add_argument('manifest', type=Path)
    find = commands.add_parser('find')
    find.add_argument('root', type=Path)
    find.add_argument('symbol')
    log = commands.add_parser('log', help='Print a compact view without modifying the original log')
    log.add_argument('path', type=Path)
    log.add_argument('--max-lines', type=int, default=60)
    log.add_argument('--max-bytes', type=int, default=6000)
    review = commands.add_parser('review')
    review.add_argument('task_id')
    analysis = commands.add_parser('analyze')
    analysis.add_argument('runs', type=Path)
    analysis.add_argument('policy', type=Path)
    analysis.add_argument('output', type=Path)
    verify = commands.add_parser('verify-receipt')
    verify.add_argument('run_id')
    qualify = commands.add_parser('probe')
    qualify.add_argument('--url', required=True)
    qualify.add_argument('--model', required=True)
    qualify.add_argument('--checkpoint-sha256', required=True)
    compare = commands.add_parser('compare')
    compare.add_argument('baseline', type=Path)
    compare.add_argument('candidate', type=Path)
    state = commands.add_parser('state-run', help='Run an isolated real recurrent session and atomically save its turn')
    state.add_argument('--library', type=Path, required=True)
    state.add_argument('--model', type=Path, required=True)
    state.add_argument('--model-key', choices=['2.9b', '7.2b-q8'], required=True)
    state.add_argument('--restore', help='Restore or fork an immutable checkpoint into this new session')
    state.add_argument('--save', required=True, help='New immutable checkpoint name')
    state.add_argument('--persona', default='Answer briefly and accurately.')
    state.add_argument('--tokens', type=int, default=64)
    state.add_argument('--context', type=int, default=2048)
    state.add_argument('prompt')
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    result: dict[str, Any]
    if args.command == 'status':
        result = {'environment': environment_record(), 'integrations': {
            name: 'configured' if integrations.get_dependency(name) else 'unavailable' for name in ['ptrm', 'triad']},
            'broker_permissions_changed': False}
    elif args.command == 'configure':
        for path, marker in [(args.ptrm, 'ptrm_reviewer/__main__.py'), (args.triad, 'scripts/run.sh')]:
            if not (path / marker).is_file():
                raise ValueError('Expected an existing reviewed repository: ' + str(path))
        from app.patch_tasks import durable_json
        result = {'ptrm': str(args.ptrm.resolve()), 'triad': str(args.triad.resolve())}
        durable_json(integrations.SETTINGS, result)
    elif args.command == 'find':
        result = CodeIndex(args.root).query(args.symbol)
    elif args.command == 'log':
        with args.path.open('rb') as stream:
            data = stream.read(10 * 1024 * 1024 + 1)
        result = compact_log(data.decode('utf-8', errors='replace'), max_lines=args.max_lines, max_bytes=args.max_bytes)
        result['raw_sha256'] = hashlib.sha256(data).hexdigest()
        result['original_log'] = str(args.path.resolve())
    elif args.command == 'compare':
        result = adoption_decision(json.loads(args.baseline.read_text()), json.loads(args.candidate.read_text()))
    else:
        collector = Collector(args.store)
        if args.command == 'baseline':
            from app.workbench.baseline import measure
            result = measure(args.server, args.model, args.model_key, collector, gpu_layers=args.gpu_layers)
        elif args.command == 'build':
            result = run_build(args.manifest, collector)
        elif args.command == 'review':
            result = asyncio.run(integrations.review_task(args.task_id, collector))
        elif args.command == 'analyze':
            result = asyncio.run(integrations.analyze_runs(args.runs, args.policy, args.output, collector))
        elif args.command == 'verify-receipt':
            result = collector.verify(args.run_id)
        elif args.command == 'probe':
            result = probe_endpoint(args.url, args.model, key=os.getenv('OMARCHY_BENCHMARK_API_KEY', ''),
                                    checkpoint_sha256=args.checkpoint_sha256)
            result['receipt'] = collector.record('runtime-probe', [result])
        elif args.command == 'state-run':
            from app.patch_tasks import durable_json
            from app.workbench.receipts import private_directory
            from app.workbench.state import CheckpointStore, Runtime
            checkpoints = CheckpointStore(collector.root / 'states', collector.key)
            checkpoints._path(args.save)
            intents = private_directory(collector.root / 'state-turns')
            intent = intents / (args.save + '.json')
            # Exclusive intent prevents uncertain requests from silently executing twice.
            with intent.open('x') as stream:
                json.dump({'state': 'pending', 'restore': args.restore, 'save': args.save}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            descriptor = os.open(intents, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            with Runtime(args.library, args.model, model_key=args.model_key) as runtime, runtime.session(
                    persona=args.persona, context=args.context) as session:
                if args.restore:
                    session.restore(checkpoints, args.restore)
                answer = session.chat(args.prompt, args.tokens)
                metadata = checkpoints.save(args.save, session)
                result = {'state': 'committed', 'checkpoint': args.save, 'turn': metadata['turn'],
                          'answer': answer, 'finish_reason': session.finish_reason}
                durable_json(intent, result)
                result['receipt'] = collector.record('recurrent-turn', [result])
    print(json.dumps(result, indent=2, ensure_ascii=True))
    failed = result.get('status') in {'failed', 'unavailable'} or result.get('valid') is False
    failed = failed or result.get('workflow', {}).get('success') is False
    failed = failed or result.get('eligible') is False
    return 1 if failed else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        raise SystemExit('Workbench: ' + str(error)) from error
