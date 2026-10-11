"""Omnipresent Dispatcher compatibility module for Swarmojo by Buzburg AI.

All omnipresent dispatch logic is maintained in `app.meta.omnipresent_dispatcher`.
This module provides backward-compatible exports.
"""
from __future__ import annotations

from app.meta.omnipresent_dispatcher import (
    EverywhereDispatcher,
    EverywhereQuickAction,
    OmnipresentDispatcher,
    QuickAction,
)

__all__ = [
    "EverywhereDispatcher",
    "EverywhereQuickAction",
    "OmnipresentDispatcher",
    "QuickAction",
]
