"""Premade Specialist Agents and Teams for SwarmMojo MetaHarness.

Curated from inspiration repos:
- agency-agents (Engineering, Quality, Operations, Design, Security divisions)
- paperclip (Company/Task coordinator, e2e runner, PR reviewer)
- OpenHarness & ClawTeam (Code implementation, review gates, frontend architecture)
- FastAgent & herdr-projects (DAG Coordinator-Worker thread topology)
- TencentDB-Agent-Memory & HMS (Holographic and Titans memory curation)
"""
from __future__ import annotations

from typing import Dict, List
from app.meta.manifest import AgentManifest, AgentTeamConfig


PREMADE_AGENTS: List[AgentManifest] = [
    AgentManifest(
        id="coordinator",
        name="Atlas Coordinator",
        role="Lead System Coordinator & Task Dispatcher",
        description="Deconstructs high-level objectives into atomic subtasks, constructs execution DAGs, routes to specialists, and synthesizes outputs.",
        division="orchestration",
        system_prompt=(
            "You are Atlas, the lead meta-harness coordinator. Your duty is to analyze user goals, "
            "break them into structured atomic milestones, select appropriate specialist agents, "
            "and ensure deterministic verification before presenting proposals to the operator."
        ),
        model_profile="ollama-deepseek-r1",
        tools=["horizon_record_step", "fastgate_triage_tools", "compact_kv_scratchpad", "cortex_shield_forecast", "drift_evaluate_action"],
        skills=["swarm-rehearsal", "horizon-circuit-breaker"],
        memory_policy="compact_kv",
        temperature=0.2,
    ),
    AgentManifest(
        id="code_architect",
        name="Daedalus Architect",
        role="Principal Software Engineer & Prime/Pi Coding Specialist",
        description="High-precision autonomous coding agent with Pi-style exact editing, Prime recursive subagent delegation, StateFresh concurrency locks, and Mojo Drift guardrails.",
        division="engineering",
        system_prompt=(
            "You are Daedalus, Principal Systems Architect and Prime/Pi Coding Specialist. "
            "Follow Pi-agent precision: inspect files with line slices, make exact unique substring edits, "
            "verify StateFresh concurrency locks before mutating files, and delegate subtasks recursively via Prime delegation. "
            "Never allow angular spec drift beyond 65°."
        ),
        model_profile="ollama-qwen-coder",
        tools=[
            "coding_read_slice",
            "coding_edit_exact",
            "coding_write_atomic",
            "coding_find_files",
            "coding_grep",
            "coding_subagent_delegate",
            "coding_drift_evaluate",
            "symdex_query",
            "rewind_snapshot_workspace",
        ],
        skills=["symdex-indexer", "rewind-snapshotter"],
        memory_policy="compact_kv",
        temperature=0.1,
    ),
    AgentManifest(
        id="code_reviewer",
        name="Argus Reviewer",
        role="Senior QA & PTRM Verification Specialist",
        description="Source-grounded code reviewer and regression detector. Verifies correctness, edge cases, test coverage, and WorkflowProof cached verification.",
        division="quality",
        system_prompt=(
            "You are Argus, Senior QA Reviewer. Review all proposed modifications with extreme diligence. "
            "Verify StateFresh version lease agreements and WorkflowProof cryptographic step receipts."
        ),
        model_profile="ollama-llama3",
        tools=["symdex_query", "sieve_compact_logs", "workflowproof_verify_step", "statefresh_check_update", "triad_evaluate_workflow"],
        skills=["sieve-compactor"],
        memory_policy="compact_kv",
        temperature=0.1,
    ),
    AgentManifest(
        id="researcher",
        name="Hypatia Researcher",
        role="Knowledge & Semantic Retrieval Specialist",
        description="Searches local documentation, vector indices, OKF knowledge files, and symbol definitions to provide grounded context.",
        division="research",
        system_prompt=(
            "You are Hypatia, Knowledge and Retrieval Specialist. Extract line-level facts and ground all conclusions "
            "in repository documentation, docstrings, and verified project lessons."
        ),
        model_profile="ollama-deepseek-r1",
        tools=["symdex_query", "compact_kv_scratchpad", "titans_memory_recall"],
        skills=["titans-memory"],
        memory_policy="titans",
        temperature=0.2,
    ),
    AgentManifest(
        id="devops_operator",
        name="Vulcan DevOps",
        role="CLI & Execution Environment Operator",
        description="Manages sandbox commands, compiler dumps, build scripts, and test suite execution with 95%+ Sieve log compaction.",
        division="operations",
        system_prompt=(
            "You are Vulcan, DevOps & Terminal Operator. Execute commands safely in the environment sandbox. "
            "Compact verbose compiler dumps through Sieve to preserve error traces while suppressing noise."
        ),
        model_profile="ollama-qwen-coder",
        tools=["sieve_compact_logs", "rewind_snapshot_workspace", "rewind_rollback_workspace"],
        skills=["sieve-compactor", "rewind-snapshotter"],
        memory_policy="compact_kv",
        temperature=0.1,
    ),
    AgentManifest(
        id="security_auditor",
        name="Aegis Security",
        role="Path Safety & Cross-Platform Security Auditor",
        description="Audits paths for Windows reserved device names, path traversal hazards, illegal characters, and secret leaks via PathCarry.",
        division="security",
        system_prompt=(
            "You are Aegis, Security Auditor. Enforce strict filesystem sanitization and verify paths "
            "against Windows reserved device names, directory traversal, and permission leaks."
        ),
        model_profile="ollama-llama3",
        tools=["path_carry_audit", "rewind_snapshot_workspace"],
        skills=["polyharness-builder"],
        memory_policy="compact_kv",
        temperature=0.1,
    ),
    AgentManifest(
        id="memory_curator",
        name="Mnemosyne Curator",
        role="Titans Neural & Long-Term Memory Curator",
        description="Maintains test-time neural memory updates, associative key-value recall, and rolling scratchpad compaction across long horizons.",
        division="research",
        system_prompt=(
            "You are Mnemosyne, Memory Curator. Track state transitions, extract durable facts into Titans neural memory, "
            "and compact working memory to prevent context saturation."
        ),
        model_profile="ollama-deepseek-r1",
        tools=["titans_memory_update", "titans_memory_recall", "compact_kv_scratchpad"],
        skills=["titans-memory"],
        memory_policy="titans",
        temperature=0.2,
    ),
]


PREMADE_TEAMS: List[AgentTeamConfig] = [
    AgentTeamConfig(
        id="fullstack_team",
        name="Fullstack Engineering Team",
        description="Full-lifecycle software engineering: coordination, architectural coding, rigorous review, and build verification.",
        coordinator_id="coordinator",
        member_ids=["coordinator", "code_architect", "code_reviewer", "devops_operator"],
        mode="coordinator_worker",
    ),
    AgentTeamConfig(
        id="review_audit_team",
        name="Quality & Security Audit Team",
        description="Deep verification squad for patch review, regression checking, and cross-platform path safety audit.",
        coordinator_id="coordinator",
        member_ids=["coordinator", "code_reviewer", "security_auditor"],
        mode="deliberation",
    ),
    AgentTeamConfig(
        id="research_synthesis_team",
        name="Knowledge Research & Memory Team",
        description="Information discovery, documentation chunking, and associative long-term memory curation.",
        coordinator_id="coordinator",
        member_ids=["coordinator", "researcher", "memory_curator"],
        mode="pipeline",
    ),
    AgentTeamConfig(
        id="autonomous_delivery_team",
        name="Autonomous Delivery Squad",
        description="Complete meta-harness collective covering coordination, implementation, QA, security audit, and devops.",
        coordinator_id="coordinator",
        member_ids=["coordinator", "code_architect", "code_reviewer", "security_auditor", "devops_operator"],
        mode="coordinator_worker",
    ),
]


def get_premade_agents_dict() -> Dict[str, AgentManifest]:
    return {agent.id: agent for agent in PREMADE_AGENTS}


def get_premade_teams_dict() -> Dict[str, AgentTeamConfig]:
    return {team.id: team for team in PREMADE_TEAMS}
