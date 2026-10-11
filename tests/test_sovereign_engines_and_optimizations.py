"""Unit tests for SwarmMojo sovereign engines and developer performance optimizations."""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path
import pytest

from app.engines import (
    VisualCanvasEngine,
    OpticalGlassMaterial,
    SceneDirectorEngine,
    VisualVerdictEngine,
    DiffusionGraphBridge,
    BinaryAnalysisEngine,
    FastSearchEngine,
    GitCheckpointGuard,
    SymNexus,
    TitanDelta,
    ToolMender,
    TaskHorizon,
    PhaseGate,
    SnapScratchpad,
    DeltaRewind,
    PathSentry,
    StateEpoch,
    ProofGraph,
    CognitiveShield,
    ParetoTriad,
)
from app.meta import (
    HerdImmunityRegistry,
    ImmunitySignature,
    DesktopAutomationBridge,
    DesktopAction,
    DeduplicatedExecutionCache,
    DedupEntry,
    OmnipresentDispatcher,
    QuickAction,
    TerminalPressEngine,
    ParallelToolDispatcher,
    TaskExecutionResult,
)


def test_sovereign_visual_canvas_and_glass():
    canvas = VisualCanvasEngine()
    info = canvas.create_canvas(preset="social_banner")
    assert info["width"] == 1200
    assert info["height"] == 630

    layer = canvas.add_layer(name="Title", kind="text", x=100, y=100, width=800, height=120)
    assert len(canvas.layers) == 2
    spec = canvas.export_spec(title="Banner Spec")
    assert spec["title"] == "Banner Spec"

    glass = OpticalGlassMaterial(blur_px=30, transparency=0.8, refraction_index=1.5)
    css = glass.to_css()
    assert "backdrop-filter: blur(30px)" in css
    assert "optical-glass" in css


def test_sovereign_scene_director_and_verdict():
    director = SceneDirectorEngine(project_name="Deep Space Exploration")
    shot = director.plan_shot(
        camera_move="orbital 360",
        focal_length="50mm prime",
        duration_s=5.0,
        subject_action="Station docking maneuver against binary star system",
    )
    assert shot.shot_number == 1
    bible = director.compile_production_bible()
    assert bible["total_shots"] == 1
    assert bible["estimated_duration_s"] == 5.0

    verdict_engine = VisualVerdictEngine()
    verdict = verdict_engine.evaluate_render_quality(
        shot_description="Cinematic wide shot with neon rim lighting and volumetric haze",
        resolution=(1920, 1080),
    )
    assert verdict["acceptable"] is True
    assert verdict["cost_index"] > 0


def test_sovereign_binary_analysis():
    engine = BinaryAnalysisEngine()
    with tempfile.NamedTemporaryFile(suffix=".wasm", delete=False) as f:
        f.write(b"\x00asm\x01\x00\x00\x00")
        f.flush()
        t_name = f.name

    try:
        header = engine.identify_format(t_name)
        assert "WebAssembly" in header.format_name
        assert header.architecture == "wasm-stack"
    finally:
        if os.path.exists(t_name):
            os.remove(t_name)


def test_sovereign_herd_immunity():
    registry = HerdImmunityRegistry()
    assert len(registry.immunities) >= 3

    # Check query
    matches = registry.check_immunity("ImportError: No module named 'fcntl' on Windows")
    assert len(matches) >= 1
    assert matches[0].error_type == "ModuleNotFoundError"

    # Register custom immunity
    sig = registry.register_immunity(
        error_type="ConnectionRefusedError",
        error_pattern="connection refused on port 8000",
        root_cause="Local inference daemon not started yet",
        remedy="Invoke health check before model dispatch",
        prevention_rule="Poll readiness probe with 5s timeout",
        discovered_by="fleet_agent",
    )
    assert sig.immunity_id.startswith("ab_")
    matched_custom = registry.check_immunity("Error: connection refused on port 8000")
    assert any(m.immunity_id == sig.immunity_id for m in matched_custom)


def test_sovereign_desktop_bridge_and_batching():
    bridge = DesktopAutomationBridge(screen_width=2560, screen_height=1440, dry_run=True)
    info = bridge.get_display_info()
    assert info["width"] == 2560
    assert info["center_x"] == 1280

    batch = bridge.batch_actions([
        {"type": "click", "x": 500, "y": 300},
        {"type": "type", "text": "echo testing", "enter": True},
        {"type": "hotkey", "keys": ["ctrl", "s"]},
    ])
    assert batch["batch_size"] == 3
    assert batch["dispatched"] == 3
    assert len(bridge.history) == 3


def test_sovereign_dedup_cache():
    cache = DeduplicatedExecutionCache(default_ttl_seconds=10.0)
    cmd = f'{sys.executable} -c "print(998877)"'
    res1 = cache.get_or_run(cmd)
    assert res1["from_cache"] is False
    assert "998877" in res1["stdout"]

    res2 = cache.get_or_run(cmd)
    assert res2["from_cache"] is True
    assert res2["hits"] == 1


def test_sovereign_omnipresent_dispatcher():
    disp = OmnipresentDispatcher()
    actions = disp.list_actions()
    assert len(actions) >= 5

    disp.capture_clipboard("def calculate_total(): pass")
    routed = disp.dispatch_action("review_diff")
    assert routed["status"] == "routed"
    assert routed["target_agent"] == "coding"


def test_sovereign_terminal_press():
    press = TerminalPressEngine()
    card = press.format_box("Sovereign Fleet", ["All nodes synchronized."], width=60)
    assert "Sovereign Fleet" in card
    kv = press.format_key_value({"Engine": "SwarmMojo", "Speed": "Sub-millisecond"})
    assert "Engine" in kv
    assert "SwarmMojo" in kv


def test_parallel_tool_dispatcher():
    dispatcher = ParallelToolDispatcher(max_workers=4)

    def task_1():
        time.sleep(0.05)
        return "result_1"

    def task_2():
        time.sleep(0.05)
        return "result_2"

    def task_3():
        time.sleep(0.05)
        return "result_3"

    report = dispatcher.execute_batch([
        ("t1", task_1),
        ("t2", task_2),
        ("t3", task_3),
    ])

    assert report["total_tasks"] == 3
    assert report["completed"] == 3
    assert report["failed"] == 0
    # Sequential would take ~150ms; parallel should take significantly less
    assert report["speedup_factor"] >= 1.2
    assert report["results"]["t1"]["result"] == "result_1"


def test_fast_search_engine():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "alpha.py").write_text("def sovereign_function():\n    return 42\n", encoding="utf-8")
        (tmp_path / "src" / "beta.py").write_text("# unrelated comment\nx = 100\n", encoding="utf-8")

        searcher = FastSearchEngine(workspace_root=tmpdir)
        files = searcher.find_files("*.py")
        assert len(files) == 2

        grep_res = searcher.grep("sovereign_function")
        assert grep_res["total_matches"] == 1
        assert grep_res["matches"][0]["line_number"] == 1

        slice_res = searcher.read_slice("src/alpha.py", start_line=1, end_line=2)
        assert slice_res["total_lines_read"] == 2
        assert "def sovereign_function():" in slice_res["content"]


def test_git_checkpoint_guard():
    guard = GitCheckpointGuard(workspace_root=".")
    if guard.is_git_repo():
        cp = guard.create_checkpoint(label="unit_test_checkpoint")
        assert cp.checkpoint_id.startswith("chk_")
        assert len(cp.commit_sha) >= 4 or cp.commit_sha == ""


def test_sovereign_buzburg_engine_aliases():
    assert SymNexus is not None
    assert TitanDelta is not None
    assert ToolMender is not None
    assert TaskHorizon is not None
    assert PhaseGate is not None
    assert SnapScratchpad is not None
    assert DeltaRewind is not None
    assert PathSentry is not None
    assert StateEpoch is not None
    assert ProofGraph is not None
    assert CognitiveShield is not None
    assert ParetoTriad is not None
