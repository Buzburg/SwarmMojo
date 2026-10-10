"""
SwarmMojo Specialized Engines Package.
Unifies Buzburg AI specialized engines into SwarmMojo:
- Symdex: High-speed in-memory code symbol & bi-directional call-graph index (<20 µs)
- Titans: Test-time neural memory with momentum & adaptive forgetting (arXiv:2501.00663)
- ToolCall: Microsecond JSON repair, balance extraction & type coercion for 7B-32B models
- Sieve: Streaming log & compiler dump compaction (95%+ noise reduction)
- Horizon: State-machine task graph (DAG) & anti-loop vector circuit breaker
- Fastgate: 256-dim phase vector System-1 tool triage router
- CompactKV: VRAM-capped rolling structured scratchpad (<800 tokens)
- Rewind: Content-addressed workspace snapshotting and microsecond rollback
- PathCarry: Cross-platform filename, path traversal & case-collision safety audit
- LocalDocSearch: Line-level local document chunking & search
"""

from .symdex import SymdexIndex
from .titans import TitansMemory
from .toolcall import extract_outer_json, repair_json_string
from .sieve import compact_text
from .horizon import HorizonManager
from .fastgate import route_tools
from .compact_kv import CompactKVManager
from .rewind import RewindEngine
from .path_carry import audit_directory, audit_filename, PathAuditResult
from .localdoc_search import chunk_document

__all__ = [
    "SymdexIndex",
    "TitansMemory",
    "extract_outer_json",
    "repair_json_string",
    "compact_text",
    "HorizonManager",
    "route_tools",
    "CompactKVManager",
    "RewindEngine",
    "audit_directory",
    "audit_filename",
    "PathAuditResult",
    "chunk_document",
]
