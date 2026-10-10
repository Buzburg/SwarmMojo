"""Fluent Builders for Custom Agents, Environments, and Teams in SwarmMojo MetaHarness."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.meta.manifest import AgentManifest, EnvironmentConfig, AgentTeamConfig


class AgentBuilder:
    """Builder for custom autonomous agents."""

    def __init__(self, agent_id: str):
        self._id = agent_id
        self._name = agent_id.replace("_", " ").title()
        self._role = "Specialist Agent"
        self._description = f"Autonomous specialist agent ({agent_id})"
        self._division = "engineering"
        self._system_prompt = ""
        self._model_profile = "mock"
        self._model_override: Optional[Dict[str, Any]] = None
        self._tools: List[str] = []
        self._skills: List[str] = []
        self._memory_policy = "compact_kv"
        self._temperature = 0.2
        self._metadata: Dict[str, Any] = {}

    def name(self, name: str) -> AgentBuilder:
        self._name = name
        return self

    def role(self, role: str) -> AgentBuilder:
        self._role = role
        return self

    def description(self, description: str) -> AgentBuilder:
        self._description = description
        return self

    def division(self, division: str) -> AgentBuilder:
        self._division = division
        return self

    def system_prompt(self, prompt: str) -> AgentBuilder:
        self._system_prompt = prompt
        return self

    def model_profile(self, profile: str) -> AgentBuilder:
        self._model_profile = profile
        return self

    def model_override(self, config_dict: Dict[str, Any]) -> AgentBuilder:
        self._model_override = config_dict
        return self

    def tools(self, tools: List[str]) -> AgentBuilder:
        self._tools = list(tools)
        return self

    def add_tool(self, tool_name: str) -> AgentBuilder:
        if tool_name not in self._tools:
            self._tools.append(tool_name)
        return self

    def skills(self, skills: List[str]) -> AgentBuilder:
        self._skills = list(skills)
        return self

    def memory_policy(self, policy: str) -> AgentBuilder:
        self._memory_policy = policy
        return self

    def temperature(self, temp: float) -> AgentBuilder:
        self._temperature = temp
        return self

    def build(self) -> AgentManifest:
        return AgentManifest(
            id=self._id,
            name=self._name,
            role=self._role,
            description=self._description,
            division=self._division,
            system_prompt=self._system_prompt,
            model_profile=self._model_profile,
            model_override=self._model_override,
            tools=self._tools,
            skills=self._skills,
            memory_policy=self._memory_policy,
            temperature=self._temperature,
            metadata=self._metadata,
        )

    def save(self, target_dir: Optional[Path] = None) -> Path:
        manifest = self.build()
        out_dir = target_dir or (Path.home() / ".swarmmojo" / "agents")
        out_path = out_dir / f"{self._id}.json"
        manifest.save_to_file(out_path)
        return out_path


class EnvironmentBuilder:
    """Builder for custom execution environments and sandboxes."""

    def __init__(self, env_id: str):
        self._id = env_id
        self._name = env_id.replace("_", " ").title()
        self._description = f"Custom execution environment ({env_id})"
        self._root_path = "."
        self._isolated_branch: Optional[str] = None
        self._snapshot_on_action = True
        self._path_audit_enabled = True
        self._log_compaction = True
        self._circuit_breaker_enabled = True
        self._allowed_tools: List[str] = []
        self._env_vars: Dict[str, str] = {}
        self._metadata: Dict[str, Any] = {}

    def name(self, name: str) -> EnvironmentBuilder:
        self._name = name
        return self

    def description(self, description: str) -> EnvironmentBuilder:
        self._description = description
        return self

    def root_path(self, root: str) -> EnvironmentBuilder:
        self._root_path = root
        return self

    def isolated_branch(self, branch: Optional[str]) -> EnvironmentBuilder:
        self._isolated_branch = branch
        return self

    def snapshot_on_action(self, enabled: bool) -> EnvironmentBuilder:
        self._snapshot_on_action = enabled
        return self

    def path_audit_enabled(self, enabled: bool) -> EnvironmentBuilder:
        self._path_audit_enabled = enabled
        return self

    def log_compaction(self, enabled: bool) -> EnvironmentBuilder:
        self._log_compaction = enabled
        return self

    def circuit_breaker_enabled(self, enabled: bool) -> EnvironmentBuilder:
        self._circuit_breaker_enabled = enabled
        return self

    def allowed_tools(self, tools: List[str]) -> EnvironmentBuilder:
        self._allowed_tools = list(tools)
        return self

    def set_env(self, key: str, val: str) -> EnvironmentBuilder:
        self._env_vars[key] = val
        return self

    def build(self) -> EnvironmentConfig:
        return EnvironmentConfig(
            id=self._id,
            name=self._name,
            description=self._description,
            root_path=self._root_path,
            isolated_branch=self._isolated_branch,
            snapshot_on_action=self._snapshot_on_action,
            path_audit_enabled=self._path_audit_enabled,
            log_compaction=self._log_compaction,
            circuit_breaker_enabled=self._circuit_breaker_enabled,
            allowed_tools=self._allowed_tools,
            env_vars=self._env_vars,
            metadata=self._metadata,
        )

    def save(self, target_dir: Optional[Path] = None) -> Path:
        cfg = self.build()
        out_dir = target_dir or (Path.home() / ".swarmmojo" / "envs")
        out_path = out_dir / f"{self._id}.json"
        cfg.save_to_file(out_path)
        return out_path


class TeamBuilder:
    """Builder for custom multi-agent teams."""

    def __init__(self, team_id: str):
        self._id = team_id
        self._name = team_id.replace("_", " ").title()
        self._description = f"Custom multi-agent team ({team_id})"
        self._coordinator_id = "coordinator"
        self._member_ids: List[str] = ["coordinator"]
        self._environment_id = "default"
        self._mode = "coordinator_worker"
        self._metadata: Dict[str, Any] = {}

    def name(self, name: str) -> TeamBuilder:
        self._name = name
        return self

    def description(self, desc: str) -> TeamBuilder:
        self._description = desc
        return self

    def coordinator(self, coordinator_id: str) -> TeamBuilder:
        self._coordinator_id = coordinator_id
        if coordinator_id not in self._member_ids:
            self._member_ids.append(coordinator_id)
        return self

    def add_member(self, member_id: str) -> TeamBuilder:
        if member_id not in self._member_ids:
            self._member_ids.append(member_id)
        return self

    def members(self, member_ids: List[str]) -> TeamBuilder:
        self._member_ids = list(member_ids)
        return self

    def environment(self, env_id: str) -> TeamBuilder:
        self._environment_id = env_id
        return self

    def mode(self, mode: str) -> TeamBuilder:
        self._mode = mode
        return self

    def build(self) -> AgentTeamConfig:
        return AgentTeamConfig(
            id=self._id,
            name=self._name,
            description=self._description,
            coordinator_id=self._coordinator_id,
            member_ids=self._member_ids,
            environment_id=self._environment_id,
            mode=self._mode,
            metadata=self._metadata,
        )

    def save(self, target_dir: Optional[Path] = None) -> Path:
        team = self.build()
        out_dir = target_dir or (Path.home() / ".swarmmojo" / "teams")
        out_path = out_dir / f"{self._id}.json"
        team.save_to_file(out_path)
        return out_path
