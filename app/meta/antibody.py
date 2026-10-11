"""Fleet Herd Immunity Engine compatibility module for SwarmMojo by Buzburg AI.

All herd immunity logic is maintained in `app.meta.herd_immunity`.
This module provides backward-compatible exports.
"""
from __future__ import annotations

from app.meta.herd_immunity import (
    HerdImmunityRegistry,
    ImmunitySignature,
    AntibodyRegistry,
    AntibodySignature,
)

__all__ = [
    "HerdImmunityRegistry",
    "ImmunitySignature",
    "AntibodyRegistry",
    "AntibodySignature",
]
