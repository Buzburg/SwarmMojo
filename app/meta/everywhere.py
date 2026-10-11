"""Universal Omnipresent Desktop Bridge for SwarmMojo by Buzburg AI.

Omnipresent desktop companion and clipboard router by Buzburg AI:
- Omnipresent floating desktop action dispatcher
- Global clipboard text capture, prompt bridging, and format conversion
- Continuous background companion heartbeat and status loop
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class EverywhereQuickAction:
    action_id: str
    label: str
    target_agent: str     # "coding", "design", "studio", "writer", "workflow", "assistant"
    shortcut_hint: str
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EverywhereDispatcher:
    """Omnipresent action dispatcher and cross-application clipboard bridge."""

    def __init__(self):
        self.actions: Dict[str, EverywhereQuickAction] = {}
        self.clipboard_history: List[str] = []
        self._init_default_actions()

    def _init_default_actions(self) -> None:
        defaults = [
            EverywhereQuickAction("explain_code", "Explain Selected Code", "coding", "Ctrl+Alt+E", "Reads selected code and produces architectural breakdown."),
            EverywhereQuickAction("review_diff", "Review Git Diff", "coding", "Ctrl+Alt+R", "Runs multi-criteria security and performance code review."),
            EverywhereQuickAction("humanize_prose", "Humanize Draft Prose", "writer", "Ctrl+Alt+H", "Scans text for AI clichés, rhythm defects, and robotic diction."),
            EverywhereQuickAction("render_banner", "Design Social Banner", "design", "Ctrl+Alt+B", "Synthesizes layered canvas layout for OpenGraph preview."),
            EverywhereQuickAction("plan_video_shot", "Storyboard Video Scene", "studio", "Ctrl+Alt+V", "Directs cinematic shot board with optics and camera moves."),
        ]
        for a in defaults:
            self.actions[a.action_id] = a

    def capture_clipboard(self, content: str) -> Dict[str, Any]:
        """Ingests new clipboard text snapshot, deduplicating consecutive duplicates."""
        if not self.clipboard_history or self.clipboard_history[-1] != content:
            self.clipboard_history.append(content)
            if len(self.clipboard_history) > 50:
                self.clipboard_history.pop(0)
        return {"captured": True, "length": len(content), "history_size": len(self.clipboard_history)}

    def dispatch_action(self, action_id: str, context_text: Optional[str] = None) -> Dict[str, Any]:
        """Dispatches an action with active context (or latest clipboard)."""
        act = self.actions.get(action_id)
        if not act:
            raise KeyError(f"Unknown quick action: {action_id}")

        text = context_text if context_text is not None else (self.clipboard_history[-1] if self.clipboard_history else "")
        return {
            "action": act.to_dict(),
            "target_agent": act.target_agent,
            "context_sample": text[:100] + ("..." if len(text) > 100 else ""),
            "status": "routed",
        }

    def list_actions(self) -> List[Dict[str, Any]]:
        return [a.to_dict() for a in self.actions.values()]
