"""Tests for Workflow Automation Engine by Buzburg AI."""
import json
import pytest
from app.engines.workflow_automation import (
    ConstitutionalGovernor,
    RiskLevel,
    WorkflowAutomationEngine,
    WorkflowDAG,
    WorkflowStep,
)


def test_constitutional_governor_blocking():
    # Destructive commands must be blocked
    res = ConstitutionalGovernor.evaluate_action("exec_shell", "rm -rf /")
    assert res.is_blocked
    assert res.risk_level == RiskLevel.CRITICAL

    res2 = ConstitutionalGovernor.evaluate_action("sql_query", "DROP DATABASE production;")
    assert res2.is_blocked
    assert res2.risk_level == RiskLevel.CRITICAL

    # Safe actions must pass
    res3 = ConstitutionalGovernor.evaluate_action("read_file", {"path": "README.md"})
    assert not res3.is_blocked
    assert res3.risk_level == RiskLevel.LOW


def test_workflow_pipeline_execution():
    engine = WorkflowAutomationEngine()
    dag = engine.create_workflow(
        workflow_id="test_wf_1",
        name="Test Verification DAG",
        steps_data=[
            {"id": "step_a", "name": "Step A", "action": "read_data", "params": {"k": "v"}},
            {"id": "step_b", "name": "Step B", "action": "process_data", "params": {}, "depends_on": ["step_a"]},
        ],
    )

    result = engine.run_workflow(dag)
    assert result["status"] == "COMPLETED"
    assert len(result["steps"]) == 2
    assert result["steps"][0]["status"] == "COMPLETED"
    assert result["steps"][0]["proof_hash"] is not None
    assert result["steps"][1]["status"] == "COMPLETED"
    assert result["steps"][1]["proof_hash"] is not None


def test_workflow_pipeline_blocks_destructive_step():
    engine = WorkflowAutomationEngine()
    dag = engine.create_workflow(
        workflow_id="test_wf_unsafe",
        name="Unsafe Workflow DAG",
        steps_data=[
            {"id": "step_bad", "name": "Bad Step", "action": "shell", "params": "rm -rf /*"},
        ],
    )

    result = engine.run_workflow(dag)
    assert result["status"] == "FAILED"
    assert result["steps"][0]["status"] == "FAILED"
    assert "Constitutional block" in result["steps"][0]["error"]


def test_routine_scheduler():
    engine = WorkflowAutomationEngine()
    routine = engine.schedule_routine(
        routine_id="test_daily_check",
        name="Test Daily Check",
        schedule="@daily",
        workflow_id="test_wf_1",
    )
    assert routine["id"] == "test_daily_check"
    assert routine["enabled"]

    routines = engine.list_routines()
    assert any(r["id"] == "test_daily_check" for r in routines)
