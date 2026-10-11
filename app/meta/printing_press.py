"""Terminal Printing Press compatibility module for Swarmojo by Buzburg AI.

All terminal formatting and layout logic is maintained in `app.meta.terminal_press`.
This module provides backward-compatible exports.
"""
from __future__ import annotations

from app.meta.terminal_press import (
    CliPrintingPress,
    TerminalPressEngine,
)

__all__ = [
    "CliPrintingPress",
    "TerminalPressEngine",
]
