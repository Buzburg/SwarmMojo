"""Small boundary and report helpers; no external dependencies."""

from __future__ import annotations

import html
import json
import math
from pathlib import Path
from typing import cast


def mapping(value: object, label: str = "value") -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, object], value)


def text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    return value


def strings(value: object, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")  # noqa: TRY004 - uniform invalid-JSON contract
    return [text(v, label) for v in value]


def number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def load(path: Path) -> dict[str, object]:
    return mapping(json.loads(path.read_text(encoding="utf-8-sig")), str(path))


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def _label(key: str) -> str:
    return key.replace("_", " ").strip().capitalize()


def _render(value: object) -> str:
    if isinstance(value, dict):
        rows: list[str] = []
        for key, item in value.items():
            label = html.escape(_label(str(key)))
            if isinstance(item, (dict, list)):
                rows.append(f"<details><summary>{label}</summary>{_render(item)}</details>")
            else:
                rows.append(f'<div class="row"><dt>{label}</dt><dd>{_render(item)}</dd></div>')
        return "<dl>" + "".join(rows) + "</dl>"
    if isinstance(value, list):
        if not value:
            return '<span class="muted">None</span>'
        return "<ul>" + "".join(f"<li>{_render(item)}</li>" for item in value) + "</ul>"
    if isinstance(value, bool):
        return '<strong class="badge">' + ("Yes" if value else "No") + "</strong>"
    if value is None:
        return '<span class="muted">Not recorded</span>'
    escaped = html.escape(str(value))
    if value in (
        "pass",
        "passed",
        "completed",
        "reused",
        "block",
        "refresh",
        "uncertain",
        "failed",
        "skipped",
    ):
        return f'<strong class="badge">{escaped}</strong>'
    return escaped


def report(path: Path, title: str, value: object) -> None:
    heading = html.escape(title)
    if isinstance(value, dict):
        cards = "".join(
            f'<section class="card"><h2>{html.escape(_label(str(key)))}</h2>{_render(item)}</section>'
            for key, item in value.items()
        )
    else:
        cards = '<section class="card">' + _render(value) + "</section>"
    raw = html.escape(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{heading}</title>
<style>
:root{{color-scheme:light}}*{{box-sizing:border-box}}body{{margin:0;background:#f6f4ee;color:#24302a;font:17px/1.65 system-ui}}
main{{max-width:1100px;margin:auto;padding:36px 24px 64px}}header{{padding:20px 0 30px;border-bottom:2px solid #24302a;margin-bottom:30px}}
h1{{font-size:clamp(2rem,5vw,3.5rem);line-height:1.13;letter-spacing:-.035em;max-width:900px}}h2{{font-size:1.25rem;margin:0 0 18px}}
.tag{{font-size:12px;text-transform:uppercase;letter-spacing:.18em;font-weight:750;color:#475c4c}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,390px),1fr));gap:20px;align-items:start}}
.card{{background:white;border:1px solid #d1d9cd;padding:25px;border-radius:12px;min-width:0;overflow-wrap:anywhere}}
dl{{margin:0}}.row{{display:grid;grid-template-columns:minmax(110px,1fr) minmax(0,2fr);gap:16px;padding:9px 0;border-bottom:1px solid #ecefe9}}
dt{{font-size:14px;color:#536258}}dd{{margin:0;white-space:pre-wrap;font-size:15px}}.badge{{display:inline-block;background:#e5eddc;color:#243d27;padding:2px 10px;border-radius:6px;font-size:14px}}
details{{margin:12px 0}}summary{{cursor:pointer;font-weight:650;padding:8px 0;color:#334d3a}}summary:focus-visible,button:focus-visible{{outline:3px solid #b6562d;outline-offset:4px}}
details details{{margin-left:10px}}ul{{padding-left:22px}}li{{margin:9px 0}}.muted,footer{{color:#536258}}
button{{background:#263d2e;color:white;border:0;padding:12px 20px;border-radius:7px;font:inherit;cursor:pointer}}
pre{{overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;background:white;padding:20px;font:13px/1.6 ui-monospace,monospace}}
footer{{font-size:13px;margin-top:32px}}@media(max-width:520px){{main{{padding:20px 14px}}.card{{padding:18px}}.row{{grid-template-columns:1fr;gap:2px}}}}
@media print{{body{{background:white}}button{{display:none}}.grid{{display:block}}.card{{break-inside:avoid;margin-bottom:16px}}}}
</style></head><body><main><header><p class="tag">Buzburg LLC / Agent Workbench</p><h1>{heading}</h1>
<p>Inspect the outcomes. Expand a section when you need the supporting evidence.</p>
<button type="button" onclick="window.print()">Print / save PDF</button></header><div class="grid">{cards}</div>
<details><summary>Full machine-readable evidence</summary><pre>{raw}</pre></details>
<footer>Generated locally · Copyright 2026 Buzburg LLC · Apache-2.0</footer></main></body></html>""",
        encoding="utf-8",
    )
