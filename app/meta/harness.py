"""SwarmMojo MetaHarness Multi-Agent & Multi-Model Orchestration Engine.

Orchestrates heterogeneous teams of autonomous agents across multiple local or remote
model backends, sandboxed execution environments, and SwarmMojo specialized engines.
"""
from __future__ import annotations

import os
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.meta.manifest import AgentManifest, EnvironmentConfig, AgentTeamConfig
from app.meta.models import ModelClient, ModelConfig, ModelRegistry
from app.meta.environment import ExecutionEnvironment
from app.meta.agent import MetaAgentInstance
from app.meta.premade import get_premade_agents_dict, get_premade_teams_dict
from app.meta.antibody import AntibodyRegistry, AntibodySignature
from app.meta.once_cache import OnceExecutionCache
from app.meta.printing_press import CliPrintingPress
from app.meta.screenhand import ScreenhandDesktopBridge
from app.meta.everywhere import EverywhereDispatcher


class MetaHarness:
    """Central orchestrator for multi-agent, multi-model execution."""

    def __init__(self, workspace_root: str = "."):
        self.workspace_root = Path(workspace_root).resolve()
        self.model_registry = ModelRegistry()
        self.model_client = ModelClient(registry=self.model_registry)

        self.antibody = AntibodyRegistry()
        self.once_cache = OnceExecutionCache()
        self.printing_press = CliPrintingPress()
        self.screenhand = ScreenhandDesktopBridge()
        self.everywhere = EverywhereDispatcher()

        self._agents: Dict[str, AgentManifest] = get_premade_agents_dict()
        self._teams: Dict[str, AgentTeamConfig] = get_premade_teams_dict()
        self._envs: Dict[str, EnvironmentConfig] = {
            "default": EnvironmentConfig(
                id="default",
                name="Default Workspace Sandbox",
                root_path=str(self.workspace_root),
                snapshot_on_action=True,
                path_audit_enabled=True,
                log_compaction=True,
                circuit_breaker_enabled=True,
            )
        }

        self._load_custom_definitions()

    def _load_custom_definitions(self) -> None:
        """Load user-defined agents, environments, and teams from .swarmmojo and workspace."""
        search_dirs = [
            Path.home() / ".swarmmojo",
            self.workspace_root / ".swarmmojo",
        ]
        for base in search_dirs:
            if not base.exists():
                continue

            # Agents
            agent_dir = base / "agents"
            if agent_dir.is_dir():
                for f in agent_dir.glob("*.json"):
                    try:
                        manifest = AgentManifest.load_from_file(f)
                        self._agents[manifest.id] = manifest
                    except Exception:
                        pass

            # Environments
            env_dir = base / "envs"
            if env_dir.is_dir():
                for f in env_dir.glob("*.json"):
                    try:
                        cfg = EnvironmentConfig.load_from_file(f)
                        self._envs[cfg.id] = cfg
                    except Exception:
                        pass

            # Teams
            team_dir = base / "teams"
            if team_dir.is_dir():
                for f in team_dir.glob("*.json"):
                    try:
                        team = AgentTeamConfig.load_from_file(f)
                        self._teams[team.id] = team
                    except Exception:
                        pass

    # Registry Management
    def register_agent(self, manifest: AgentManifest) -> None:
        self._agents[manifest.id] = manifest

    def register_environment(self, config: EnvironmentConfig) -> None:
        self._envs[config.id] = config

    def register_team(self, team: AgentTeamConfig) -> None:
        self._teams[team.id] = team

    def get_agent(self, agent_id: str) -> Optional[AgentManifest]:
        return self._agents.get(agent_id)

    def get_environment(self, env_id: str) -> Optional[EnvironmentConfig]:
        return self._envs.get(env_id)

    def get_team(self, team_id: str) -> Optional[AgentTeamConfig]:
        return self._teams.get(team_id)

    def list_agents(self) -> List[Dict[str, Any]]:
        return [a.to_dict() for a in self._agents.values()]

    def list_teams(self) -> List[Dict[str, Any]]:
        return [t.to_dict() for t in self._teams.values()]

    def list_environments(self) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self._envs.values()]

    def list_models(self) -> Dict[str, Dict[str, Any]]:
        return self.model_registry.list_profiles()

    def create_agent_instance(
        self,
        agent_id: str,
        model_override: Optional[str] = None,
    ) -> MetaAgentInstance:
        """Instantiate an active agent with its resolved model configuration."""
        manifest = self.get_agent(agent_id)
        if not manifest:
            raise ValueError(f"Agent '{agent_id}' not found in registry.")

        if model_override:
            manifest_dict = manifest.to_dict()
            manifest_dict["model_profile"] = model_override
            manifest = AgentManifest.from_dict(manifest_dict)

        return MetaAgentInstance(
            manifest=manifest,
            model_client=self.model_client,
            model_registry=self.model_registry,
            workspace_root=str(self.workspace_root),
        )

    # Multi-Agent Orchestration
    def run_task(
        self,
        task: str,
        team_id: str = "fullstack_team",
        env_id: str = "default",
        model_overrides: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Run a task across a multi-agent team in the selected execution environment."""
        start_time = time.perf_counter()
        team = self.get_team(team_id)
        if not team:
            raise ValueError(f"Team '{team_id}' not found.")

        env_cfg = self.get_environment(env_id) or self._envs["default"]
        env = ExecutionEnvironment(env_cfg)

        model_overrides = model_overrides or {}
        global_override = model_overrides.get("all")

        # Instantiate members
        instances: Dict[str, MetaAgentInstance] = {}
        for m_id in team.member_ids:
            override = global_override or model_overrides.get(m_id)
            instances[m_id] = self.create_agent_instance(m_id, model_override=override)

        coordinator = instances.get(team.coordinator_id)
        if not coordinator:
            coordinator = next(iter(instances.values()))

        turns: List[Dict[str, Any]] = []

        if team.mode == "pipeline":
            # Pipeline: Sequential pass-through
            current_input = task
            for m_id in team.member_ids:
                agent = instances[m_id]
                turn = agent.execute_turn(current_input, env=env)
                turns.append(turn)
                current_input = turn["content"]
            final_synthesis = current_input

        elif team.mode == "deliberation":
            # Deliberation: All agents examine task concurrently, then coordinator synthesizes
            member_reports = []
            for m_id in team.member_ids:
                if m_id == coordinator.manifest.id:
                    continue
                turn = instances[m_id].execute_turn(task, env=env)
                turns.append(turn)
                member_reports.append(f"[{turn['role']} ({turn['agent_name']})]:\n{turn['content']}")

            # Coordinator synthesis
            synth_prompt = (
                f"Synthesize consensus for objective: {task}\n\n"
                f"Specialist Peer Reviews:\n" + "\n\n".join(member_reports)
            )
            final_turn = coordinator.execute_turn(synth_prompt, env=env)
            turns.append(final_turn)
            final_synthesis = final_turn["content"]

        else:
            # coordinator_worker (Default)
            # Step 1: Coordinator decomposes task
            coord_plan = coordinator.execute_turn(
                f"Deconstruct objective into specialist milestones: {task}",
                env=env,
            )
            turns.append(coord_plan)

            # Step 2: Specialists execute subtasks
            worker_outputs = []
            for m_id in team.member_ids:
                if m_id == coordinator.manifest.id:
                    continue
                subtask_msg = f"Task: {task}\nCoordinator Guidance: {coord_plan['content']}"
                w_turn = instances[m_id].execute_turn(subtask_msg, env=env)
                turns.append(w_turn)
                worker_outputs.append(f"[{w_turn['role']} ({w_turn['agent_name']})]:\n{w_turn['content']}")

            # Step 3: Coordinator synthesizes final solution
            final_prompt = (
                f"Formulate final execution proposal for objective: {task}\n\n"
                f"Worker Outputs:\n" + "\n\n".join(worker_outputs)
            )
            final_turn = coordinator.execute_turn(final_prompt, env=env)
            turns.append(final_turn)
            final_synthesis = final_turn["content"]

        total_latency_ms = (time.perf_counter() - start_time) * 1000.0

        return {
            "task": task,
            "team_id": team_id,
            "team_name": team.name,
            "mode": team.mode,
            "environment_id": env_id,
            "total_latency_ms": round(total_latency_ms, 2),
            "participating_agents": [
                {
                    "id": a.manifest.id,
                    "name": a.manifest.name,
                    "role": a.manifest.role,
                    "model": a.model_config.model_id,
                    "backend": a.model_config.backend,
                }
                for a in instances.values()
            ],
            "turns": turns,
            "synthesis": final_synthesis,
            "approval_required": True,
            "execution_allowed": False,
        }
