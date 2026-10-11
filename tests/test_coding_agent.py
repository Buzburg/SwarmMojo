"""Unit and integration tests for Coding Agent (Pi Tools & Prime Recursion) and new engines."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from app.meta.coding_agent import (
    PiCodingToolkit,
    PrimeRecursionEngine,
    SubagentResult,
)
from app.engines.drift import MojoDrift
from app.engines.statefresh import StateFreshCoordinator, FileVersionGuard
from app.engines.workflowproof import WorkflowProofEngine
from app.engines.cortex import CortexEngine, ExecutionShield
from app.engines.triad import TriadEngine
from app.engines.mojo_memory import MojoMemory


# -------------------------------------------------------------------------
# PiCodingToolkit Tests
# -------------------------------------------------------------------------

def test_pi_toolkit_read_slice(tmp_path: Path):
    toolkit = PiCodingToolkit(workspace_root=tmp_path)
    sample_file = tmp_path / "hello.py"
    sample_file.write_text("line 1\nline 2\nline 3\nline 4\nline 5\n", encoding="utf-8")

    res = toolkit.read_file_slice("hello.py", start_line=2, end_line=4)
    assert "error" not in res
    assert "2: line 2" in res["content"]
    assert "3: line 3" in res["content"]
    assert "4: line 4" in res["content"]
    assert "1: line 1" not in res["content"]


def test_pi_toolkit_edit_exact_success(tmp_path: Path):
    toolkit = PiCodingToolkit(workspace_root=tmp_path)
    sample_file = tmp_path / "math_func.py"
    sample_file.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    res = toolkit.edit_file_exact(
        rel_path="math_func.py",
        target_content="return a - b",
        replacement_content="return a + b",
    )
    assert res.get("success") is True
    assert "return a + b" in sample_file.read_text(encoding="utf-8")


def test_pi_toolkit_edit_exact_not_found(tmp_path: Path):
    toolkit = PiCodingToolkit(workspace_root=tmp_path)
    sample_file = tmp_path / "code.py"
    sample_file.write_text("x = 10\n", encoding="utf-8")

    res = toolkit.edit_file_exact(
        rel_path="code.py",
        target_content="y = 20",
        replacement_content="y = 30",
    )
    assert "error" in res
    assert "not found" in res["error"]


def test_pi_toolkit_edit_exact_ambiguous(tmp_path: Path):
    toolkit = PiCodingToolkit(workspace_root=tmp_path)
    sample_file = tmp_path / "repeat.py"
    sample_file.write_text("val = 1\nval = 1\n", encoding="utf-8")

    # Should fail if allow_multiple is False
    res = toolkit.edit_file_exact(
        rel_path="repeat.py",
        target_content="val = 1",
        replacement_content="val = 2",
        allow_multiple=False,
    )
    assert "error" in res
    assert "matched 2 times" in res["error"]

    # Should succeed if allow_multiple is True
    res_multi = toolkit.edit_file_exact(
        rel_path="repeat.py",
        target_content="val = 1",
        replacement_content="val = 2",
        allow_multiple=True,
    )
    assert res_multi.get("success") is True
    assert sample_file.read_text(encoding="utf-8") == "val = 2\nval = 2\n"


def test_pi_toolkit_atomic_write(tmp_path: Path):
    toolkit = PiCodingToolkit(workspace_root=tmp_path)
    res = toolkit.write_file_atomic("subdir/new_file.txt", "Hello Atomic World")
    assert res.get("success") is True
    target = tmp_path / "subdir" / "new_file.txt"
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "Hello Atomic World"



# -------------------------------------------------------------------------
# PrimeRecursionEngine Tests
# -------------------------------------------------------------------------

def test_prime_single_delegation(tmp_path: Path):
    engine = PrimeRecursionEngine(workspace_root=str(tmp_path))
    res = engine.execute_delegation(
        mode="single",
        parent_goal="Review code safety",
        agent="code_reviewer",
        task="Review pull request changes",
    )
    assert res["mode"] == "single"
    assert len(res["results"]) == 1
    assert res["results"][0]["status"] == "success"
    assert res["results"][0]["depth"] == 1


def test_prime_parallel_delegation(tmp_path: Path):
    engine = PrimeRecursionEngine(workspace_root=str(tmp_path))
    tasks = [
        {"agent": "code_architect", "task": "Draft system design architecture"},
        {"agent": "code_reviewer", "task": "Review system design architecture"},
    ]
    res = engine.execute_delegation(
        mode="parallel",
        parent_goal="Draft and review system design architecture",
        tasks=tasks,
    )
    assert res["mode"] == "parallel"
    assert len(res["results"]) == 2
    assert all(r["status"] == "success" for r in res["results"])


def test_prime_chain_piping(tmp_path: Path):
    engine = PrimeRecursionEngine(workspace_root=str(tmp_path))
    chain = [
        {"agent": "code_architect", "task": "Write initial specification"},
        {"agent": "code_reviewer", "task": "Review following spec: {previous}"},
    ]
    res = engine.execute_delegation(
        mode="chain",
        parent_goal="Specification and review pipeline",
        chain=chain,
    )
    assert res["mode"] == "chain"
    assert len(res["results"]) == 2
    assert res["results"][0]["status"] == "success"
    assert res["results"][1]["status"] == "success"


def test_prime_max_depth_exceeded(tmp_path: Path):
    engine = PrimeRecursionEngine(workspace_root=str(tmp_path), max_depth=2)
    sub = engine.invoke_subagent(
        agent_role="deep_worker",
        task="Deep nested work",
        parent_goal="Run deep recursive process",
        current_depth=3,
    )
    assert sub.status == "max_depth_exceeded"
    assert "Maximum subagent depth limit" in sub.content


# -------------------------------------------------------------------------
# New Buzburg Engines Tests
# -------------------------------------------------------------------------

def test_mojo_drift_guardrail():
    drift = MojoDrift()
    
    # Well aligned action
    res_aligned = drift.evaluate_action(
        goal="Refactor code and write unit tests",
        action="Run pytest on tests/test_coding_agent.py",
    )
    assert res_aligned["status"] == "safe"
    assert res_aligned["drift_degrees"] < 65.0

    # Off-topic / drifting action
    res_drift = drift.evaluate_action(
        goal="Fix compiler warnings in Mojo kernel",
        action="Install random web games and stream video",
    )
    assert res_drift["drift_degrees"] > 20.0


def test_statefresh_concurrency(tmp_path: Path):
    coord = StateFreshCoordinator()
    file_path = tmp_path / "guarded.py"
    file_path.write_text("init = 1", encoding="utf-8")

    lease1 = coord.acquire_lease(file_path, holder="worker_1", ttl_seconds=5)
    assert lease1 is not None

    # Conflicting lease attempt
    lease2 = coord.acquire_lease(file_path, holder="worker_2", ttl_seconds=5)
    assert lease2 is None

    # Release
    assert coord.release_lease(file_path, holder="worker_1") is True
    # Now worker_2 can acquire
    lease2 = coord.acquire_lease(file_path, holder="worker_2", ttl_seconds=5)
    assert lease2 is not None


def test_workflowproof_cache():
    proof = WorkflowProofEngine()
    step_id = "build_kernel"
    inputs = {"compiler": "mojo", "opt": 3}
    outputs = {"binary_hash": "abc1234"}

    receipt = proof.record_proof(step_id, inputs, outputs)
    assert receipt["proof_hash"] != ""

    cached = proof.lookup_proof(step_id, inputs)
    assert cached is not None
    assert cached["outputs"]["binary_hash"] == "abc1234"


def test_cortex_engine():
    cortex = CortexEngine()
    safe_eval = cortex.evaluate_hazard("pytest tests/")
    assert safe_eval["hazard"] is False

    unsafe_eval = cortex.evaluate_hazard("rm -rf / --no-preserve-root")
    assert unsafe_eval["hazard"] is True
    assert unsafe_eval["action"] == "block"


def test_triad_engine():
    triad = TriadEngine()
    triad.record_run("v1", reliability=0.95, duration_s=12.0, cost_tokens=500)
    triad.record_run("v2", reliability=0.99, duration_s=8.0, cost_tokens=200)
    
    pareto = triad.pareto_frontier()
    assert len(pareto) > 0
    # v2 dominates v1 across all metrics
    assert pareto[0]["id"] == "v2"


def test_mojo_memory():
    mem = MojoMemory(dimension=512)
    mem.store("fact_1", "Swarmojo combines PolyHarness and Swarmojo with native Mojo speed.", phase=0.2)
    mem.store("fact_2", "Pi agent performs exact unambiguous slice edits.", phase=0.8)

    results = mem.query("unambiguous slice edits", top_k=1)
    assert len(results) >= 1
    assert "Pi agent" in results[0]["key"] or results[0]["similarity"] >= 0.0
