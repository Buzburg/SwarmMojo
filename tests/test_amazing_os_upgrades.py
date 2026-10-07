r"""Comprehensive verification suite for the 4 Amazing Omarchy OS Upgrades:
1. Holographic Live Indexer (AST symbol extraction, 16k-bit VSA bundling, PageRank)
2. Dual-Brain Cognitive Router (RWKV-7 Reflex vs MSGL Oracle + GBNF)
3. Dream Cycle Continual Learning Flywheel (Outcome synthesis, Feynman SFT, nightly batches)
4. Native Wayland/Hyprland Desktop HUD (Waybar telemetry, Hyprland window rules, systemd units)
"""

import json
from pathlib import Path
import pytest

from app.holographic_indexer import HolographicCodebaseIndexer, split_identifier, bundle_hypervectors
from app.dual_brain_router import DualBrainRouter, BrainType, dual_brain_router
from app.dream_cycle import DreamCycleConsolidator, dream_cycle
from app.omarchy_hud import build_waybar_status, get_system_memory_gb
from app.reflection import ContinuousMemoryReflector, TaskOutcome
from app.vsa_tsl_engine import HypervectorBSC


def test_holographic_live_indexer(tmp_path):
    # Create mock workspace
    ws = tmp_path / "mock_ws"
    ws.mkdir()

    file_a = ws / "api_gateway.py"
    file_a.write_text("""
import database_store

class APIGateway:
    def handle_request(self, req):
        return database_store.query_user(req)
""", encoding="utf-8")

    file_b = ws / "database_store.py"
    file_b.write_text("""
def query_user(user_id):
    return {"id": user_id, "status": "active"}

def optimize_cache():
    pass
""", encoding="utf-8")

    indexer = HolographicCodebaseIndexer(ws)
    count = indexer.index_workspace()
    assert count == 2
    assert "api_gateway.py" in indexer.files
    assert "database_store.py" in indexer.files

    # Check AST symbol extraction
    assert "APIGateway" in indexer.files["api_gateway.py"].symbols
    assert "query_user" in indexer.files["database_store.py"].symbols

    # Check PageRank: database_store is imported by api_gateway, so its pagerank should be higher
    assert indexer.files["database_store.py"].pagerank >= indexer.files["api_gateway.py"].pagerank

    # Search for user query
    results = indexer.instant_search("query user in database", top_k=2)
    assert len(results) > 0
    assert results[0]["path"] == "database_store.py"


def test_hypervector_bundling():
    hv1 = HypervectorBSC.from_seed("symbol_a")
    hv2 = HypervectorBSC.from_seed("symbol_b")
    hv3 = HypervectorBSC.from_seed("symbol_c")

    bundled = bundle_hypervectors([hv1, hv2, hv3])
    # Bundled vector should have positive cosine similarity to all 3 constituent atoms
    assert bundled.cosine_similarity(hv1) > 0.15
    assert bundled.cosine_similarity(hv2) > 0.15
    assert bundled.cosine_similarity(hv3) > 0.15


def test_dual_brain_router():
    router = DualBrainRouter()

    # 1. Simple conversational/shell command prompt -> REFLEX
    dec_reflex = router.route_request("List all running git branches", files_involved=1)
    assert dec_reflex.target_brain == BrainType.REFLEX
    assert "reflex" in dec_reflex.reason.lower()

    # 2. Multi-file refactor -> ORACLE with GBNF grammar
    dec_oracle = router.route_request(
        "Refactor database connector across 5 modules and verify AST",
        files_involved=5,
        requires_json=True,
    )
    assert dec_oracle.target_brain == BrainType.ORACLE
    assert dec_oracle.gbnf_grammar is not None

    # 3. Dispatch execution envelope
    dispatch_res = router.dispatch("Check disk health")
    assert dispatch_res["status"] == "ready"
    assert "dispatched_to" in dispatch_res


def test_dream_cycle_continual_learning(tmp_path):
    test_db = tmp_path / "test_dream.db"
    reflector = ContinuousMemoryReflector(db_path=test_db)

    reflector.reflect(
        TaskOutcome(
            project_id="omarchy-core",
            target_file="ast_validator.py",
            action_taken="Verified AST security gate blocks eval and exec",
            succeeded=True,
            task_id="TEST-DREAM-01",
            patch_summary="import ast; def check(): pass",
        )
    )

    consolidator = DreamCycleConsolidator(workspace_dir=tmp_path, db_path=test_db)
    summary = consolidator.consolidate(max_feynman_samples=5)

    assert summary.total_training_pairs >= 1
    assert summary.verified_lessons_count >= 1
    assert Path(summary.output_path).exists()

    # Verify JSONL lines can be parsed
    with open(summary.output_path, "r", encoding="utf-8") as f:
        first_line = json.loads(f.readline())
        assert "instruction" in first_line
        assert "output" in first_line


def test_omarchy_hud_and_packaging_configs():
    # 1. Memory telemetry
    used_gb, total_gb = get_system_memory_gb()
    assert used_gb > 0.0
    assert total_gb > 0.0

    # 2. Waybar status payload
    status = build_waybar_status(check_network=False)
    assert "text" in status
    assert "tooltip" in status
    assert "󰚩" in status["text"]
    assert "UMA" in status["text"]

    # 3. Check packaging files
    base_dir = Path(__file__).resolve().parent.parent
    waybar_cfg = base_dir / "packaging" / "waybar-omarchy.jsonc"
    hypr_cfg = base_dir / "packaging" / "hyprland-omarchy.conf"
    dream_service = base_dir / "packaging" / "omarchy-dream.service"
    dream_timer = base_dir / "packaging" / "omarchy-dream.timer"

    assert waybar_cfg.exists()
    assert hypr_cfg.exists()
    assert dream_service.exists()
    assert dream_timer.exists()

    assert "omarchy-hud" in waybar_cfg.read_text(encoding="utf-8")
    assert "SPACE" in hypr_cfg.read_text(encoding="utf-8")
    assert "OnCalendar" in dream_timer.read_text(encoding="utf-8")
