"""Unit and integration tests for SwarmMojo MetaHarness."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from app.meta.models import ModelConfig, ModelRegistry, ModelClient
from app.meta.manifest import AgentManifest, EnvironmentConfig, AgentTeamConfig
from app.meta.builder import AgentBuilder, EnvironmentBuilder, TeamBuilder
from app.meta.environment import ExecutionEnvironment
from app.meta.agent import MetaAgentInstance
from app.meta.premade import PREMADE_AGENTS, PREMADE_TEAMS
from app.meta.harness import MetaHarness


def test_model_registry_and_client():
    registry = ModelRegistry()
    profiles = registry.list_profiles()
    assert "mock" in profiles
    assert "ollama-qwen-coder" in profiles
    assert "ollama-deepseek-r1" in profiles

    # Register custom profile
    custom_cfg = ModelConfig(
        model_id="custom-local",
        backend="openai_compatible",
        base_url="http://localhost:5000/v1",
    )
    registry.register("custom-profile", custom_cfg)
    assert registry.get("custom-profile").model_id == "custom-local"

    # Client generation via mock
    client = ModelClient(registry=registry)
    res = client.generate(
        registry.get("mock"),
        [{"role": "user", "content": "Explain architecture"}],
    )
    assert res["content"] != ""
    assert res["backend"] == "mock"
    assert res["latency_ms"] >= 0


def test_manifest_serialization(tmp_path: Path):
    manifest = AgentManifest(
        id="test_agent",
        name="Test Agent",
        role="Unit Tester",
        description="Runs test checks",
        division="quality",
        tools=["symdex_query"],
    )
    json_str = manifest.to_json()
    reloaded = AgentManifest.from_json(json_str)
    assert reloaded.id == "test_agent"
    assert reloaded.tools == ["symdex_query"]

    # File save and load
    file_path = tmp_path / "agent.json"
    manifest.save_to_file(file_path)
    from_file = AgentManifest.load_from_file(file_path)
    assert from_file.name == "Test Agent"


def test_builders(tmp_path: Path):
    # AgentBuilder
    agent = (
        AgentBuilder("sec_specialist")
        .name("Security Specialist")
        .role("Auditor")
        .division("security")
        .model_profile("mock")
        .add_tool("path_carry_audit")
        .system_prompt("Enforce path validation")
        .build()
    )
    assert agent.id == "sec_specialist"
    assert "path_carry_audit" in agent.tools

    # EnvironmentBuilder
    env = (
        EnvironmentBuilder("sandbox_1")
        .name("Sandbox 1")
        .root_path(str(tmp_path))
        .snapshot_on_action(True)
        .circuit_breaker_enabled(True)
        .build()
    )
    assert env.id == "sandbox_1"
    assert env.snapshot_on_action is True

    # TeamBuilder
    team = (
        TeamBuilder("t1")
        .name("Team 1")
        .coordinator("sec_specialist")
        .add_member("coder")
        .mode("coordinator_worker")
        .build()
    )
    assert team.id == "t1"
    assert "sec_specialist" in team.member_ids
    assert "coder" in team.member_ids


def test_execution_environment_sandbox(tmp_path: Path):
    env_cfg = EnvironmentConfig(
        id="test_env",
        name="Test Env",
        root_path=str(tmp_path),
        snapshot_on_action=True,
        path_audit_enabled=True,
        log_compaction=True,
        circuit_breaker_enabled=True,
    )
    env = ExecutionEnvironment(env_cfg)

    # Test file write with automatic snapshot
    write_res = env.write_file("module.py", "x = 42")
    assert write_res["success"] is True
    assert write_res["snapshot"] is not None

    # Test file read
    read_res = env.read_file("module.py")
    assert read_res["success"] is True
    assert read_res["content"] == "x = 42"

    # Test path traversal prevention
    bad_res = env.read_file("../../../secret.txt")
    assert "error" in bad_res

    # Test command execution
    cmd_res = env.execute_command(["python", "-c", "print('hello from sandbox')"])
    assert cmd_res["success"] is True
    assert "hello from sandbox" in cmd_res["output"]


def test_meta_agent_instance(tmp_path: Path):
    manifest = AgentManifest(
        id="architect",
        name="System Architect",
        role="Principal Architect",
        description="Designs modular architectures",
        division="engineering",
        model_profile="mock",
        memory_policy="compact_kv",
    )
    agent = MetaAgentInstance(manifest=manifest, workspace_root=str(tmp_path))
    turn = agent.execute_turn("Design a high-speed telemetry pipeline")
    assert turn["agent_id"] == "architect"
    assert turn["role"] == "Principal Architect"
    assert turn["content"] != ""
    assert len(agent.history) == 2


def test_meta_harness_multi_agent_execution(tmp_path: Path):
    harness = MetaHarness(workspace_root=str(tmp_path))

    # Verify premade catalog
    agents = harness.list_agents()
    assert len(agents) >= 7
    teams = harness.list_teams()
    assert len(teams) >= 4

    # 1. Run coordinator_worker mode with heterogeneous model overrides
    report_cw = harness.run_task(
        task="Implement streaming event aggregator",
        team_id="fullstack_team",
        model_overrides={
            "coordinator": "mock",
            "code_architect": "mock",
            "code_reviewer": "mock",
            "devops_operator": "mock",
        },
    )
    assert report_cw["team_id"] == "fullstack_team"
    assert report_cw["mode"] == "coordinator_worker"
    assert len(report_cw["turns"]) >= 4
    assert report_cw["synthesis"] != ""
    assert report_cw["approval_required"] is True

    # 2. Run deliberation mode
    report_delib = harness.run_task(
        task="Audit new crypto module for timing attacks",
        team_id="review_audit_team",
        model_overrides={"all": "mock"},
    )
    assert report_delib["mode"] == "deliberation"
    assert len(report_delib["turns"]) >= 3

    # 3. Run pipeline mode
    report_pipe = harness.run_task(
        task="Extract lessons and curate into memory",
        team_id="research_synthesis_team",
        model_overrides={"all": "mock"},
    )
    assert report_pipe["mode"] == "pipeline"
    assert len(report_pipe["turns"]) == 3


def test_server_fastmcp_meta_tools():
    import asyncio
    from fastmcp import Client
    from app import server

    async def run():
        async with Client(server.mcp) as client:
            tools = await client.list_tools()
            tool_names = [t.name for t in tools]

            assert "meta_list_agents" in tool_names
            assert "meta_list_teams" in tool_names
            assert "meta_list_models" in tool_names
            assert "meta_run_team" in tool_names
            assert "meta_create_agent" in tool_names
            assert "meta_create_environment" in tool_names

            # Test meta_list_agents
            res_agents = await client.call_tool("meta_list_agents", {})
            agents_data = json.loads(res_agents.content[0].text)
            assert len(agents_data) >= 7

            # Test meta_run_team
            res_run = await client.call_tool("meta_run_team", {
                "task": "Test fastmcp meta run",
                "team_id": "review_audit_team",
                "model_override": "mock",
            })
            run_data = json.loads(res_run.content[0].text)
            assert run_data["team_id"] == "review_audit_team"
            assert run_data["synthesis"] != ""

    asyncio.run(run())
