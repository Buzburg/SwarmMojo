"""FastMCP Tool Registrations for SwarmMojo MetaHarness."""
from __future__ import annotations

import json
from fastmcp import FastMCP

from app.meta.harness import MetaHarness
from app.meta.builder import AgentBuilder, EnvironmentBuilder


def register_meta_tools(server: FastMCP) -> None:
    harness = MetaHarness()

    @server.tool()
    def meta_list_agents() -> str:
        """Lists all registered premade and custom specialist agents in the MetaHarness."""
        return json.dumps(harness.list_agents(), indent=2)

    @server.tool()
    def meta_list_teams() -> str:
        """Lists all registered multi-agent team topologies in the MetaHarness."""
        return json.dumps(harness.list_teams(), indent=2)

    @server.tool()
    def meta_list_models() -> str:
        """Lists all registered local and remote model profiles (Ollama, LM Studio, vLLM, SGLang, mock)."""
        return json.dumps(harness.list_models(), indent=2)

    @server.tool()
    def meta_run_team(
        task: str,
        team_id: str = "fullstack_team",
        env_id: str = "default",
        model_override: str = "",
    ) -> str:
        """Executes a task across a multi-agent team, coordinating specialists across their configured local models."""
        overrides = {"all": model_override} if model_override else {}
        report = harness.run_task(
            task=task,
            team_id=team_id,
            env_id=env_id,
            model_overrides=overrides,
        )
        return json.dumps(report, indent=2)

    @server.tool()
    def meta_create_agent(
        id: str,
        name: str,
        role: str,
        division: str = "engineering",
        model_profile: str = "mock",
        tools_csv: str = "",
        prompt: str = "",
    ) -> str:
        """Builds and registers a custom agent manifest with tools, models, and system directives."""
        tools_list = [t.strip() for t in tools_csv.split(",") if t.strip()]
        builder = (
            AgentBuilder(id)
            .name(name)
            .role(role)
            .division(division)
            .model_profile(model_profile)
            .tools(tools_list)
            .system_prompt(prompt)
        )
        manifest = builder.build()
        harness.register_agent(manifest)
        saved_path = builder.save()
        return json.dumps({
            "status": "created",
            "agent": manifest.to_dict(),
            "saved_path": str(saved_path),
        }, indent=2)

    @server.tool()
    def meta_create_environment(
        id: str,
        name: str,
        root_path: str = ".",
    ) -> str:
        """Builds and registers an execution sandbox environment bound to Rewind and PathCarry safety engines."""
        builder = (
            EnvironmentBuilder(id)
            .name(name)
            .root_path(root_path)
            .snapshot_on_action(True)
            .circuit_breaker_enabled(True)
        )
        cfg = builder.build()
        harness.register_environment(cfg)
        saved_path = builder.save()
        return json.dumps({
            "status": "created",
            "environment": cfg.to_dict(),
            "saved_path": str(saved_path),
        }, indent=2)
