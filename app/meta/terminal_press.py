"""High-Craft Terminal Printing Press for Swarmojo by Buzburg AI.

Terminal typography and reporting architecture by Buzburg AI:
- Beautiful terminal card formatting with rounded Unicode borders
- Clean data tables with automated column width calculation
- ANSI terminal color styling and status badges
- Structured agent verification and execution publication
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional, Tuple


class TerminalPressEngine:
    """Terminal typography and report layout publishing engine."""

    # Unicode border styles
    STYLES = {
        "rounded": {"tl": "╭", "tr": "╮", "bl": "╰", "br": "╯", "h": "─", "v": "│"},
        "double":  {"tl": "╔", "tr": "╗", "bl": "╚", "br": "╝", "h": "═", "v": "║"},
        "heavy":   {"tl": "┏", "tr": "┓", "bl": "┗", "br": "┛", "h": "━", "v": "┃"},
        "ascii":   {"tl": "+", "tr": "+", "bl": "+", "br": "+", "h": "-", "v": "|"},
    }

    # ANSI color codes
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

    def format_box(
        self,
        title: str,
        content_lines: List[str],
        width: int = 70,
        style: str = "rounded",
        title_color: str = "CYAN",
    ) -> str:
        """Formats text into a clean bordered card with header."""
        b = self.STYLES.get(style, self.STYLES["rounded"])
        inner_w = width - 4

        header_title = f" {title} "
        left_h = (inner_w - len(header_title)) // 2
        right_h = inner_w - len(header_title) - left_h
        top_bar = f"{b['tl']}{b['h'] * max(2, left_h)}{header_title}{b['h'] * max(2, right_h)}{b['tr']}"

        result = [top_bar]
        for line in content_lines:
            truncated = line[:inner_w]
            padded = truncated.ljust(inner_w)
            result.append(f"{b['v']}  {padded}  {b['v']}")

        bot_bar = f"{b['bl']}{b['h'] * (inner_w + 4)}{b['br']}"
        result.append(bot_bar)
        return "\n".join(result)

    def format_table(self, headers: List[str], rows: List[List[str]]) -> str:
        """Renders an aligned data table with Unicode grid dividers."""
        col_widths = [len(h) for h in headers]
        for r in rows:
            for idx, val in enumerate(r):
                if idx < len(col_widths):
                    col_widths[idx] = max(col_widths[idx], len(str(val)))

        # Header
        h_row = " │ ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
        sep = "─┼─".join("─" * w for w in col_widths)

        lines = [h_row, sep]
        for r in rows:
            r_row = " │ ".join(str(r[i]).ljust(col_widths[i]) if i < len(r) else "".ljust(col_widths[i]) for i in range(len(headers)))
            lines.append(r_row)

        return "\n".join(lines)

    def format_badge(self, text: str, level: str = "info") -> str:
        """Formats a standard status badge."""
        prefixes = {
            "success": "[PASS]",
            "error": "[FAIL]",
            "warning": "[WARN]",
            "info": "[INFO]",
        }
        p = prefixes.get(level.lower(), "[INFO]")
        return f"{p} {text}"

    def format_key_value(self, pairs: Dict[str, Any], title: Optional[str] = None) -> str:
        """Renders a clean aligned key-value block."""
        lines = []
        max_k = max((len(str(k)) for k in pairs.keys()), default=15)
        for k, v in pairs.items():
            lines.append(f"{str(k).ljust(max_k + 2)}: {v}")
        if title:
            return self.format_box(title=title, content_lines=lines, style="rounded")
        return "\n".join(lines)

    def publish_agent_summary(self, agent_name: str, objective: str, metrics: Dict[str, Any]) -> str:
        """Renders a complete summary card for agent execution."""
        lines = [
            f"Agent:     {agent_name}",
            f"Objective: {objective}",
            "─" * 60,
        ]
        for k, v in metrics.items():
            lines.append(f"{k.ljust(20)}: {v}")
        return self.format_box(title="SWARMOJO AGENT VERIFICATION", content_lines=lines, style="rounded")


# Backward-compatible alias
CliPrintingPress = TerminalPressEngine
