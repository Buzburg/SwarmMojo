"""Swarmojo MetaHarness Package.

Multi-agent, multi-model orchestration harness supporting heterogeneous local models,
declarative agent/environment builders, and Swarmojo specialized engines by Buzburg AI.
"""
from app.meta.manifest import AgentManifest, EnvironmentConfig, AgentTeamConfig
from app.meta.models import ModelConfig, ModelRegistry, ModelClient
from app.meta.environment import ExecutionEnvironment
from app.meta.agent import MetaAgentInstance
from app.meta.premade import PREMADE_AGENTS, PREMADE_TEAMS, get_premade_agents_dict, get_premade_teams_dict
from app.meta.builder import AgentBuilder, EnvironmentBuilder, TeamBuilder
from app.meta.harness import MetaHarness
from app.meta.meta_tools import register_meta_tools
from app.meta.herd_immunity import HerdImmunityRegistry, ImmunitySignature, AntibodyRegistry, AntibodySignature
from app.meta.dedup_cache import DeduplicatedExecutionCache, DedupEntry, OnceExecutionCache, OnceEntry
from app.meta.terminal_press import TerminalPressEngine, CliPrintingPress
from app.meta.desktop_bridge import DesktopAutomationBridge, DesktopAction, ScreenhandDesktopBridge
from app.meta.omnipresent_dispatcher import OmnipresentDispatcher, QuickAction, EverywhereDispatcher, EverywhereQuickAction
from app.meta.parallel_dispatcher import ParallelToolDispatcher, TaskExecutionResult

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
    # Sovereign primary names
    "HerdImmunityRegistry",
    "ImmunitySignature",
    "DeduplicatedExecutionCache",
    "DedupEntry",
    "TerminalPressEngine",
    "DesktopAutomationBridge",
    "DesktopAction",
    "OmnipresentDispatcher",
    "QuickAction",
    "ParallelToolDispatcher",
    "TaskExecutionResult",
    # Backward-compatible aliases
    "AntibodyRegistry",
    "AntibodySignature",
    "OnceExecutionCache",
    "OnceEntry",
    "CliPrintingPress",
    "ScreenhandDesktopBridge",
    "EverywhereDispatcher",
    "EverywhereQuickAction",
]
