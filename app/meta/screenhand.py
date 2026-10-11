"""Desktop Automation Bridge compatibility module for SwarmMojo by Buzburg AI.

All desktop automation logic is maintained in `app.meta.desktop_bridge`.
This module provides backward-compatible exports.
"""
from __future__ import annotations

from app.meta.desktop_bridge import (
    DesktopAction,
    DesktopAutomationBridge,
    ScreenhandDesktopBridge,
)

__all__ = [
    "DesktopAction",
    "DesktopAutomationBridge",
    "ScreenhandDesktopBridge",
]
