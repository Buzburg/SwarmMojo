"""SwarmMojo MetaHarness Package.

Multi-agent, multi-model orchestration harness supporting heterogeneous local models,
declarative agent/environment builders, and SwarmMojo specialized engines.
"""
from app.meta.manifest import AgentManifest, EnvironmentConfig, AgentTeamConfig
from app.meta.models import ModelConfig, ModelRegistry, ModelClient
from app.meta.environment import ExecutionEnvironment
from app.meta.agent import MetaAgentInstance
from app.meta.premade import PREMADE_AGENTS, PREMADE_TEAMS, get_premade_agents_dict, get_premade_teams_dict
from app.meta.builder import AgentBuilder, EnvironmentBuilder, TeamBuilder
from app.meta.harness import MetaHarness
from app.meta.meta_tools import register_meta_tools
from app.meta.antibody import AntibodyRegistry, AntibodySignature
from app.meta.once_cache import OnceExecutionCache
from app.meta.printing_press import CliPrintingPress
from app.meta.screenhand import ScreenhandDesktopBridge
from app.meta.everywhere import EverywhereDispatcher

__all__ = [
    "MetaHarness",
    "AgentManifest",
    "EnvironmentConfig",
    "AgentTeamConfig",
    "AgentBuilder",
    "EnvironmentBuilder",
    "TeamBuilder",
    "ModelConfig",
    "ModelRegistry",
    "ModelClient",
    "ExecutionEnvironment",
    "MetaAgentInstance",
    "PREMADE_AGENTS",
    "PREMADE_TEAMS",
    "get_premade_agents_dict",
    "get_premade_teams_dict",
    "register_meta_tools",
    "AntibodyRegistry",
    "AntibodySignature",
    "OnceExecutionCache",
    "CliPrintingPress",
    "ScreenhandDesktopBridge",
    "EverywhereDispatcher",
]
