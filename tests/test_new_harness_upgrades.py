"""Tests for Swarmojo Supercharged Coding, Design, Studio, and Meta Harness Engines."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
import pytest

from app.engines.code_review import CodeReviewEngine, ReviewFinding, CodeReviewReport
from app.engines.reverse_engineering import ReverseEngineeringEngine, BinaryHeaderInfo
from app.engines.code_ledger import CodeLedgerEngine, FileCodemap, LedgerTransaction
from app.engines.design import PhotocraftCanvasEngine, CanvasLayer, LiquidGlassMaterial
from app.engines.studio import (
    DirectorBoardEngine,
    DirectorShot,
    VideoTimelineEngine,
    TimelineClip,
    ReasonixVerdictEngine,
)
from app.meta.antibody import AntibodyRegistry, AntibodySignature
from app.meta.once_cache import OnceExecutionCache
from app.meta.printing_press import CliPrintingPress
from app.meta.screenhand import ScreenhandDesktopBridge
from app.meta.everywhere import EverywhereDispatcher
from fastmcp import FastMCP
from app.meta.meta_tools import register_meta_tools


def test_code_review_engine_detects_security_and_perf():
    engine = CodeReviewEngine()
    bad_code = """
import os

def run_user_code(user_input):
    eval(user_input)
    api_key = "sk_live_12345678abcdefgh"
    items = []
    for x in range(10):
        items.append([y for y in range(5)])
"""
    report = engine.review_source(bad_code, filename="test_vuln.py")
    assert not report.passed
    assert report.critical_count >= 1
    rule_ids = [f.rule_id for f in report.findings]
    assert "SEC-001" in rule_ids  # eval detection


def test_code_review_engine_passes_clean_code():
    engine = CodeReviewEngine()
    clean_code = """
def add(a: int, b: int) -> int:
    return a + b
"""
    report = engine.review_source(clean_code, filename="clean.py")
    assert report.passed
    assert report.total_findings == 0


def test_reverse_engineering_engine():
    engine = ReverseEngineeringEngine()
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        # Write WASM magic bytes
        f.write(b"\x00asm\x01\x00\x00\x00")
        f.flush()
        temp_name = f.name

    try:
        header = engine.identify_format(temp_name)
        assert "WebAssembly" in header.format_name
        assert header.architecture == "wasm-stack"
        assert header.metadata.get("wasm_version") == 1
    finally:
        if os.path.exists(temp_name):
            os.remove(temp_name)

    # Disassemble Python bytecode
    instrs = engine.disassemble_source_code("x = 1 + 2\n")
    assert len(instrs) > 0
    opnames = [i.opname for i in instrs]
    assert any("STORE" in op for op in opnames)


def test_code_ledger_engine():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_py = Path(tmpdir) / "sample.py"
        test_py.write_text(
            "import os\nfrom math import sqrt\n\ndef compute(val: float) -> float:\n    return sqrt(val)\n",
            encoding="utf-8",
        )

        ledger = CodeLedgerEngine(workspace_root=tmpdir)
        codemap = ledger.extract_file_codemap("sample.py")
        assert codemap.file_path == "sample.py"
        assert codemap.line_count >= 4
        assert "os" in codemap.imports
        assert "math.sqrt" in codemap.imports
        assert any(s.name == "compute" and s.kind == "function" for s in codemap.symbols)

        repo_map = ledger.build_repo_codemap(max_files=10)
        assert "sample.py" in repo_map["codemap"]


def test_photocraft_canvas_and_liquid_glass():
    canvas = PhotocraftCanvasEngine()
    info = canvas.create_canvas(preset="social_banner")
    assert info["width"] == 1200
    assert info["height"] == 630

    layer = canvas.add_layer(name="Headline", kind="text", x=50, y=50, width=500, height=80)
    assert len(canvas.layers) == 2  # background + headline

    spec = canvas.export_spec(title="Social Spec")
    assert spec["total_layers"] == 2
    assert spec["title"] == "Social Spec"

    # Liquid Glass
    glass = LiquidGlassMaterial(blur_px=24, transparency=0.75, refraction_index=1.45)
    css = glass.to_css()
    assert "backdrop-filter: blur(24px)" in css
    assert "rgba" in css


def test_director_board_and_video_timeline():
    director = DirectorBoardEngine(project_name="SciFi Promo")
    shot1 = director.plan_shot(
        camera_move="flyover",
        focal_length="24mm",
        duration_s=3.5,
        subject_action="Drone establishing shot of neon futuristic metropolis",
    )
    assert shot1.shot_number == 1

    bible = director.compile_production_bible()
    assert bible["total_shots"] == 1
    assert bible["estimated_duration_s"] == 3.5

    # Video Timeline
    timeline = VideoTimelineEngine(output_fps=24)
    clip = timeline.add_clip(track="video", start_time_s=0.0, duration_s=3.5, source="city.mp4")
    norm = timeline.normalize_loudness(target_lufs=-14.0)
    assert norm["target_lufs"] == -14.0

    exp = timeline.export_timeline()
    assert exp["total_duration_s"] == 3.5
    assert exp["fps"] == 24


def test_reasonix_verdict_engine():
    engine = ReasonixVerdictEngine()
    verdict = engine.evaluate_render_quality(
        shot_description="Cinematic rembrandt portrait of a space explorer in a glass helmet",
        resolution=(1920, 1080),
    )
    assert "overall_verdict" in verdict
    assert "acceptable" in verdict
    assert verdict["cost_index"] > 0


def test_antibody_herd_immunity_registry():
    registry = AntibodyRegistry()
    summary = registry.summary()
    assert summary["total_antibodies"] >= 3

    # Check known Windows NT fcntl error
    matches = registry.check_immunity("ImportError: No module named 'fcntl' in worker thread")
    assert len(matches) >= 1
    assert matches[0].error_type == "ModuleNotFoundError"
    assert "posix" in matches[0].prevention_rule.lower()

    # Register custom antibody
    new_ab = registry.register_antibody(
        error_type="CustomTimeoutError",
        error_pattern="gateway connect timeout 504",
        root_cause="Upstream proxy cold start",
        remedy="Retry with exponential backoff up to 3 attempts",
        prevention_rule="Wrap proxy clients in circuit breaker",
        discovered_by="agent_test",
    )
    assert new_ab.antibody_id.startswith("ab_")
    matched_custom = registry.check_immunity("Received error: gateway connect timeout 504 on endpoint")
    assert any(m.antibody_id == new_ab.antibody_id for m in matched_custom)


def test_once_execution_cache():
    cache = OnceExecutionCache(default_ttl_seconds=5.0)
    # Run simple echo
    cmd = f'{sys.executable} -c "print(12345)"'
    res1 = cache.get_or_run(cmd)
    assert res1["from_cache"] is False
    assert "12345" in res1["stdout"]

    # Run again - should hit cache
    res2 = cache.get_or_run(cmd)
    assert res2["from_cache"] is True
    assert res2["hits"] == 1
    assert "12345" in res2["stdout"]


def test_cli_printing_press():
    press = CliPrintingPress()
    card = press.format_box("Agent Status", ["All 6 specialist agents are operational."])
    assert "Agent Status" in card
    assert "All 6 specialist agents are operational." in card

    table = press.format_table(["Agent", "Status"], [["Coding", "Active"], ["Design", "Active"]])
    assert "Coding" in table
    assert "Active" in table

    badge = press.format_badge("Engine ready", level="success")
    assert "[PASS]" in badge


def test_screenhand_desktop_bridge():
    bridge = ScreenhandDesktopBridge(screen_width=1920, screen_height=1080, dry_run=True)
    res_click = bridge.click(100, 200)
    assert res_click["status"] == "simulated"
    assert res_click["action"]["params"]["x"] == 100

    res_type = bridge.type_text("Hello World")
    assert res_type["status"] == "simulated"

    # Out of bounds
    with pytest.raises(ValueError):
        bridge.click(2500, 500)


def test_everywhere_dispatcher():
    disp = EverywhereDispatcher()
    actions = disp.list_actions()
    assert len(actions) >= 5
    action_ids = [a["action_id"] for a in actions]
    assert "explain_code" in action_ids
    assert "review_diff" in action_ids

    disp.capture_clipboard("def foo(): return 42")
    res = disp.dispatch_action("explain_code")
    assert res["status"] == "routed"
    assert res["target_agent"] == "coding"
    assert "def foo" in res["context_sample"]


def test_mcp_new_tools_registration():
    server = FastMCP(name="SwarmojoTestServer")
    register_meta_tools(server)

    tool_names = [tool.name for tool in asyncio.run(server.list_tools())]
    assert "coding_review_code" in tool_names
    assert "coding_inspect_binary" in tool_names
    assert "coding_repo_codemap" in tool_names
    assert "meta_antibody_check" in tool_names
    assert "meta_once_run" in tool_names
    assert "meta_screenhand_action" in tool_names
    assert "meta_everywhere_dispatch" in tool_names
