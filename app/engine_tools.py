"""FastMCP Tool Registrations for SwarmMojo Specialized Engines.

Exposes Buzburg AI specialized engines as native FastMCP tools:
- Symdex: High-speed symbol & call-graph lookup (<20 µs)
- Titans: Test-time neural memory (arXiv:2501.00663)
- ToolCall: JSON extraction, auto-repair, and schema coercion
- Sieve: Streaming terminal and compiler log compaction
- Horizon: External task graph & anti-loop circuit breaker
- Fastgate: 256-dim phase-vector System-1 tool triage router
- CompactKV: VRAM-capped rolling structured scratchpad (<800 tokens)
- Rewind: Content-addressed workspace snapshotting and microsecond rollback
- PathCarry: Filename safety, cross-platform reserved-name & path audit
"""
from __future__ import annotations

import json
from pathlib import Path
from fastmcp import FastMCP

from app.engines import (
    SymdexIndex,
    TitansMemory,
    extract_outer_json,
    repair_json_string,
    compact_text,
    HorizonManager,
    route_tools,
    CompactKVManager,
    RewindEngine,
    audit_directory,
)


def register_engine_tools(server: FastMCP) -> None:
    @server.tool()
    def symdex_query(symbol: str, query_type: str = "definitions", workspace: str = ".") -> str:
        """Fast in-memory symbol lookup. query_type can be 'definitions', 'callers', or 'callees'."""
        idx = SymdexIndex(root=workspace)
        idx.build_index()
        if query_type == "callers":
            res = idx.find_callers(symbol)
        elif query_type == "callees":
            res = idx.find_callees(symbol)
        else:
            res = idx.find_definition(symbol)
        return json.dumps(res, indent=2)

    @server.tool()
    def titans_memory_update(fact: str, workspace: str = ".") -> str:
        """Stores a fact in the Titans test-time neural memory module (arXiv:2501.00663)."""
        mem = TitansMemory(root=workspace)
        mem.load()
        loss = mem.write(fact)
        mem.save()
        return json.dumps({"status": "recorded", "fact": fact, "surprise_loss": round(loss, 6)}, indent=2)

    @server.tool()
    def titans_memory_recall(query: str, top_k: int = 5, workspace: str = ".") -> str:
        """Recalls relevant memories using associative test-time memory weights."""
        mem = TitansMemory(root=workspace)
        mem.load()
        results = mem.read(query, top_k=top_k)
        return json.dumps({"query": query, "recalled": results}, indent=2)

    @server.tool()
    def toolcall_repair_output(raw_output: str) -> str:
        """Repairs malformed JSON, fixes single-quote strings, and extracts balanced JSON from LLM text."""
        extracted = extract_outer_json(raw_output)
        if not extracted:
            return json.dumps({"error": "No JSON block found in output", "raw": raw_output})
        repaired = repair_json_string(extracted)
        try:
            parsed = json.loads(repaired)
            return json.dumps({"valid": True, "data": parsed}, indent=2)
        except Exception as e:
            return json.dumps({"valid": False, "repaired_string": repaired, "error": str(e)}, indent=2)

    @server.tool()
    def sieve_compact_logs(log_text: str, context_window: int = 2, max_lines: int = 60) -> str:
        """Compacts terminal logs down to root causes, failures, and stack traces, pruning 95%+ noise."""
        result = compact_text(log_text, context_window=context_window, max_lines=max_lines)
        return json.dumps(result, indent=2)

    @server.tool()
    def horizon_record_step(tool_name: str, arguments: str, outcome: str, workspace: str = ".") -> str:
        """Records an action in the task DAG and checks against the anti-loop circuit breaker."""
        mgr = HorizonManager(root=workspace)
        status = mgr.record_action(tool_name, arguments, outcome)
        return json.dumps(status, indent=2)

    @server.tool()
    def fastgate_triage_tools(prompt: str, tools_json: str, threshold: float = 0.15) -> str:
        """System-1 vector router that prunes unneeded tools using 256-dim phase vectors before model calls."""
        try:
            tools = json.loads(tools_json)
        except Exception:
            return json.dumps({"error": "tools_json must be a valid JSON array"})
        res = route_tools(prompt, tools, threshold=threshold)
        return json.dumps(res, indent=2)

    @server.tool()
    def compact_kv_scratchpad(action: str = "status", fact: str = "", hypothesis: str = "", workspace: str = ".") -> str:
        """Maintains a rolling VRAM-capped structured scratchpad under 800 tokens. Actions: 'status', 'add_fact', 'set_hypothesis'."""
        mgr = CompactKVManager(root=workspace)
        if action == "add_fact" and fact:
            res = mgr.add_fact(fact)
        elif action == "set_hypothesis" and hypothesis:
            res = mgr.set_hypothesis(hypothesis)
        else:
            res = mgr.get_state()
        return json.dumps(res, indent=2)

    @server.tool()
    def rewind_snapshot_workspace(message: str = "checkpoint", workspace: str = ".") -> str:
        """Captures a content-addressed snapshot of the workspace for microsecond rollback."""
        engine = RewindEngine(root=workspace)
        res = engine.snapshot(message=message)
        return json.dumps(res, indent=2)

    @server.tool()
    def rewind_rollback_workspace(checkpoint_index: int = -1, workspace: str = ".") -> str:
        """Rolls back the workspace to the specified checkpoint index (-1 for latest)."""
        engine = RewindEngine(root=workspace)
        res = engine.rollback(checkpoint_index=checkpoint_index)
        return json.dumps(res, indent=2)

    @server.tool()
    def path_carry_audit(directory: str = ".") -> str:
        """Audits directory paths for Windows reserved device names, illegal chars, and traversal risks."""
        res = audit_directory(directory)
        return json.dumps(res.to_dict(), indent=2)

    @server.tool()
    def drift_evaluate_action(goal: str, action: str) -> str:
        """Calculates trajectory angular drift in degrees [0-180] (warn >=65°, block >=80°)."""
        from app.engines import evaluate_drift
        return json.dumps(evaluate_drift(goal, action), indent=2)

    @server.tool()
    def statefresh_check_update(entity_id: str, updates_json: str, expected_version: int = 1) -> str:
        """Verifies optimistic concurrency state update against StateFresh version leases."""
        from app.engines import StateFreshStore
        store = StateFreshStore()
        try:
            updates = json.loads(updates_json)
        except Exception:
            return json.dumps({"error": "updates_json must be valid JSON"})
        decision = store.apply_update(entity_id, expected_version, updates)
        return json.dumps(decision.to_dict(), indent=2)

    @server.tool()
    def workflowproof_verify_step(step_id: str, command: str, inputs_csv: str = "") -> str:
        """Executes or retrieves cached cryptographic proof for a verified workflow step."""
        from app.engines import WorkflowProofEngine, WorkflowStep
        engine = WorkflowProofEngine()
        inputs = [i.strip() for i in inputs_csv.split(",") if i.strip()]
        cmd_parts = command.split()
        res = engine.run_step(WorkflowStep(id=step_id, command=cmd_parts, inputs=inputs, outputs=[]))
        return json.dumps(res, indent=2)

    @server.tool()
    def cortex_shield_forecast(action: str, goal: str = "") -> str:
        """Pre-simulates candidate actions against hazard rules and cyclic loops."""
        from app.engines import CortexEngine
        cortex = CortexEngine()
        return json.dumps(cortex.check_action(action, goal=goal if goal else None), indent=2)

    @server.tool()
    def triad_evaluate_workflow(workflow_id: str, reliability: float, duration_s: float, cost_tokens: int) -> str:
        """Records and evaluates Pareto efficiency across (reliability, duration, cost)."""
        from app.engines import TriadEngine
        triad = TriadEngine()
        metric = triad.record_run(workflow_id, reliability, duration_s, cost_tokens)
        rankings = triad.rank_pareto_front()
        return json.dumps({"recorded": metric.to_dict(), "pareto_rankings": rankings}, indent=2)

    @server.tool()
    def mojo_memory_store_lesson(text: str, evidence_json: str = "{}") -> str:
        """Stores a lesson and evidence in Mojo phase-vector associative memory."""
        from app.engines import MojoMemoryEngine
        mem = MojoMemoryEngine()
        try:
            ev = json.loads(evidence_json)
        except Exception:
            ev = {}
        return json.dumps(mem.put_lesson(text, evidence=ev), indent=2)

    @server.tool()
    def mojo_memory_search_lesson(query: str, limit: int = 3) -> str:
        """Recalls relevant lessons and evidence using 512-dim phase vector cosine similarity."""
        from app.engines import MojoMemoryEngine
        mem = MojoMemoryEngine()
        return json.dumps(mem.search_lessons(query, limit=limit), indent=2)

