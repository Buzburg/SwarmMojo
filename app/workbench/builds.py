"""Trusted operator build workflows; never exposed as a model execution tool."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .receipts import Collector
from .vendor.workflowproof import core


def run_build(manifest: Path, collector: Collector) -> dict:
    manifest = Path(manifest).absolute()
    if manifest.resolve() != manifest or manifest.stat().st_size > 256 * 1024:
        raise ValueError('Expected a bounded operator workflow without symlinks')
    if collector.root.is_relative_to(manifest.parent):
        raise ValueError('Collector secrets must remain outside the build workspace')
    raw = manifest.read_bytes()
    definition = json.loads(raw)
    result = core.run(definition, manifest.parent)
    if manifest.read_bytes() != raw:
        raise ValueError('Build manifest changed while running; no authenticated receipt created')
    receipt = collector.record('operator-build', [{'manifest_sha256': hashlib.sha256(raw).hexdigest(),
        'workspace': str(manifest.parent), 'workflow': result}])
    return {'workflow': result, 'receipt': receipt, 'authorizes_apply': False}
