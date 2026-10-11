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
        """Lists all registered local and remote model profiles (Ollama, LM Studio, vLLM, Deep Reasoner, mock)."""
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

    # Pi Agent Precise Coding Tools
    from app.meta.coding_agent import PiCodingToolkit, PrimeRecursionEngine

    toolkit = PiCodingToolkit()
    recursion_engine = PrimeRecursionEngine()

    @server.tool()
    def coding_read_slice(rel_path: str, start_line: int = 1, end_line: int = 200) -> str:
        """Reads a line-numbered slice of a file (Pi-agent structure)."""
        return json.dumps(toolkit.read_file_slice(rel_path, start_line, end_line), indent=2)

    @server.tool()
    def coding_edit_exact(
        rel_path: str,
        target_content: str,
        replacement_content: str,
        expected_digest: str = "",
        allow_multiple: bool = False,
    ) -> str:
        """Exact substring replacement with uniqueness validation, StateFresh OCC, and Rewind snapshots."""
        digest_arg = expected_digest if expected_digest else None
        res = toolkit.edit_file_exact(
            rel_path,
            target_content,
            replacement_content,
            expected_digest=digest_arg,
            allow_multiple=allow_multiple,
        )
        return json.dumps(res, indent=2)

    @server.tool()
    def coding_write_atomic(rel_path: str, content: str, overwrite: bool = False) -> str:
        """Atomically writes or overwrites a file with Rewind checkpointing."""
        return json.dumps(toolkit.write_file_atomic(rel_path, content, overwrite=overwrite), indent=2)

    @server.tool()
    def coding_find_files(pattern: str = "*.*", search_dir: str = ".") -> str:
        """Finds files matching pattern across workspace, ignoring noise directories."""
        return json.dumps(toolkit.find_files(pattern, search_dir), indent=2)

    @server.tool()
    def coding_grep(pattern: str, search_dir: str = ".") -> str:
        """Searches files for regex or literal pattern."""
        return json.dumps(toolkit.grep_content(pattern, search_dir), indent=2)

    @server.tool()
    def coding_symdex_callgraph(symbol: str) -> str:
        """Queries Symdex index for callers, callees, and definitions (<20 µs)."""
        return json.dumps(toolkit.symdex_callgraph(symbol), indent=2)

    @server.tool()
    def coding_subagent_delegate(
        mode: str,
        parent_goal: str,
        agent: str = "worker",
        task: str = "",
        tasks_json: str = "",
        chain_json: str = "",
        max_depth: int = 3,
    ) -> str:
        """DeepCode recursive subagent tool (single, parallel, chain with {previous} piping)."""
        tasks_list = json.loads(tasks_json) if tasks_json else None
        chain_list = json.loads(chain_json) if chain_json else None
        engine = PrimeRecursionEngine(max_depth=max_depth)
        res = engine.execute_delegation(
            mode=mode,
            parent_goal=parent_goal,
            agent=agent,
            task=task,
            tasks=tasks_list,
            chain=chain_list,
        )
        return json.dumps(res, indent=2)

    @server.tool()
    def coding_drift_evaluate(goal: str, action: str) -> str:
        """Calculates angular drift from session goal (warns >=65°, blocks >=80°)."""
        from app.engines import evaluate_drift
        return json.dumps(evaluate_drift(goal, action), indent=2)

    @server.tool()
    def coding_review_code(code: str, file_path: str = "snippet.py") -> str:
        """Performs multi-criteria security, performance, and reliability static code review."""
        from app.engines.code_review import CodeReviewEngine
        engine = CodeReviewEngine()
        report = engine.review_source(code, filename=file_path)
        return json.dumps(report.to_dict(), indent=2)

    @server.tool()
    def coding_inspect_binary(file_path: str) -> str:
        """Inspects binary magic headers, architecture, entry point, and structure."""
        from app.engines.reverse_engineering import BinaryAnalysisEngine
        engine = BinaryAnalysisEngine()
        info = engine.identify_format(file_path)
        return json.dumps(info.to_dict(), indent=2)

    @server.tool()
    def coding_repo_codemap(workspace_root: str = ".", max_files: int = 50) -> str:
        """Extracts hierarchical repository codemap with symbol nodes and imports."""
        from app.engines.code_ledger import CodeLedgerEngine
        engine = CodeLedgerEngine(workspace_root=workspace_root)
        codemap = engine.build_repo_codemap(max_files=max_files)
        return json.dumps(codemap, indent=2)

    @server.tool()
    def meta_immunity_check(error_text: str) -> str:
        """Scans error text against fleet herd immunity memory to retrieve instant remedies."""
        from app.meta.herd_immunity import HerdImmunityRegistry
        registry = HerdImmunityRegistry()
        matches = registry.check_immunity(error_text)
        return json.dumps([m.to_dict() for m in matches], indent=2)

    @server.tool()
    def meta_antibody_check(error_text: str) -> str:
        """Legacy alias: Scans error text against fleet herd immunity memory."""
        return meta_immunity_check(error_text)

    @server.tool()
    def meta_dedup_run(command: str, cwd: str = ".", ttl_seconds: float = 60.0) -> str:
        """Executes deduplicated shell command with memory-cached TTL deduplication."""
        from app.meta.dedup_cache import DeduplicatedExecutionCache
        cache = DeduplicatedExecutionCache(default_ttl_seconds=ttl_seconds)
        res = cache.get_or_run(command, cwd=cwd, ttl_seconds=ttl_seconds)
        return json.dumps(res, indent=2)

    @server.tool()
    def meta_once_run(command: str, cwd: str = ".", ttl_seconds: float = 60.0) -> str:
        """Legacy alias: Executes deduplicated shell command."""
        return meta_dedup_run(command, cwd=cwd, ttl_seconds=ttl_seconds)

    @server.tool()
    def meta_desktop_action(action_type: str, x: int = 0, y: int = 0, text: str = "", dry_run: bool = True) -> str:
        """Dispatches high-speed desktop automation action (click, move, type) with safety bounds."""
        from app.meta.desktop_bridge import DesktopAutomationBridge
        bridge = DesktopAutomationBridge(dry_run=dry_run)
        if action_type == "click":
            res = bridge.click(x, y)
        elif action_type == "type":
            res = bridge.type_text(text)
        elif action_type == "focus":
            res = bridge.focus_window(text)
        else:
            res = {"status": "unsupported", "action_type": action_type}
        return json.dumps(res, indent=2)

    @server.tool()
    def meta_screenhand_action(action_type: str, x: int = 0, y: int = 0, text: str = "", dry_run: bool = True) -> str:
        """Legacy alias: Dispatches high-speed desktop automation action."""
        return meta_desktop_action(action_type=action_type, x=x, y=y, text=text, dry_run=dry_run)

    @server.tool()
    def meta_dispatch_quick_action(action_id: str, context_text: str = "") -> str:
        """Dispatches omnipresent desktop action (explain_code, review_diff, humanize_prose, etc.)."""
        from app.meta.omnipresent_dispatcher import OmnipresentDispatcher
        dispatcher = OmnipresentDispatcher()
        res = dispatcher.dispatch_action(action_id, context_text=context_text or None)
        return json.dumps(res, indent=2)

    @server.tool()
    def meta_everywhere_dispatch(action_id: str, context_text: str = "") -> str:
        """Legacy alias: Dispatches omnipresent desktop action."""
        return meta_dispatch_quick_action(action_id=action_id, context_text=context_text)

