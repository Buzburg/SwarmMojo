"""Execution deduplication cache compatibility module for SwarmMojo by Buzburg AI.

All deduplication logic is maintained in `app.meta.dedup_cache`.
This module provides backward-compatible exports.
"""
from __future__ import annotations

from app.meta.dedup_cache import (
    DedupEntry,
    DeduplicatedExecutionCache,
    OnceEntry,
    OnceExecutionCache,
)

__all__ = [
    "DedupEntry",
    "DeduplicatedExecutionCache",
    "OnceEntry",
    "OnceExecutionCache",
]
