"""Declarative Manifest schemas for Swarmojo MetaHarness.

Enables building, exporting, validating, and sharing:
- Agent manifests (specialist definitions, prompts, models, and tools)
- Environment configurations (sandboxes, path safety, snapshots, and breakers)
- Agent teams (multi-agent coordination topologies)
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
from pathlib import Path


@dataclass
class AgentManifest:
    """Specification for an autonomous specialist agent."""
    id: str
    name: str
    role: str
    description: str
    division: str = "engineering"  # engineering, orchestration, quality, research, operations, security
    system_prompt: str = ""
    model_profile: str = "mock"  # Key into ModelRegistry, e.g. "ollama-qwen-coder", "ollama-deepseek-r1"
    model_override: Optional[Dict[str, Any]] = None  # Inline ModelConfig dict
    tools: List[str] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)
    memory_policy: str = "compact_kv"  # "titans", "compact_kv", "none"
    temperature: float = 0.2
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AgentManifest:
        valid_fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in data.items() if k in valid_fields})

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> AgentManifest:
        return cls.from_dict(json.loads(json_str))

    def save_to_file(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load_from_file(cls, path: Path) -> AgentManifest:
        return cls.from_json(path.read_text(encoding="utf-8"))


@dataclass
class EnvironmentConfig:
    """Specification for an execution sandbox environment."""
    id: str
    name: str
    description: str = ""
    root_path: str = "."
    isolated_branch: Optional[str] = None  # Git worktree / branch isolation
    snapshot_on_action: bool = True       # mojo-agent-rewind microsecond snapshotting
    path_audit_enabled: bool = True       # path-carry safety & reserved-name verification
    log_compaction: bool = True           # mojo-sieve 95%+ log compaction
    circuit_breaker_enabled: bool = True  # mojo-local-horizon DAG anti-loop vector breaker
    allowed_tools: List[str] = field(default_factory=list)
    env_vars: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EnvironmentConfig:
        valid_fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in data.items() if k in valid_fields})

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> EnvironmentConfig:
        return cls.from_dict(json.loads(json_str))

    def save_to_file(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load_from_file(cls, path: Path) -> EnvironmentConfig:
        return cls.from_json(path.read_text(encoding="utf-8"))


@dataclass
class AgentTeamConfig:
    """Specification for a multi-agent team and coordination topology."""
    id: str
    name: str
    description: str
    coordinator_id: str
    member_ids: List[str]
    environment_id: str = "default"
    mode: str = "coordinator_worker"  # "coordinator_worker", "pipeline", "deliberation"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AgentTeamConfig:
        valid_fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in data.items() if k in valid_fields})

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> AgentTeamConfig:
        return cls.from_dict(json.loads(json_str))

    def save_to_file(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load_from_file(cls, path: Path) -> AgentTeamConfig:
        return cls.from_json(path.read_text(encoding="utf-8"))
