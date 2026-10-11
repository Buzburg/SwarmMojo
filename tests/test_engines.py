"""Unit tests for Swarmojo's 10 specialized engines and FastMCP engine tools."""

import json
from pathlib import Path

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
    audit_filename,
    PathAuditResult,
    chunk_document,
)
from app.engines.localdoc_search import Passage, keyword_search


def test_symdex_index(tmp_path: Path):
    src_file = tmp_path / "example.py"
    src_file.write_text(
        "def compute_total(x, y):\n"
        "    return x + y\n\n"
        "def process():\n"
        "    return compute_total(1, 2)\n",
        encoding="utf-8",
    )
    idx = SymdexIndex(root=str(tmp_path))
    duration_ms = idx.build_index()
    assert duration_ms >= 0

    defs = idx.find_definition("compute_total")
    assert len(defs) == 1
    assert defs[0]["line"] == 1

    callers = idx.find_callers("compute_total")
    assert len(callers) >= 1
    assert callers[0]["caller"] == "process"

    callees = idx.find_callees("process")
    assert "compute_total" in callees


def test_titans_memory(tmp_path: Path):
    mem = TitansMemory(root=str(tmp_path))
    mem.init()
    
    # Test write/memorize
    loss = mem.write("Swarmojo combines ROMS, Aeon, PolyHarness, and 10 engines.", key="swarmojo_core")
    assert isinstance(loss, float)

    # Test read/recall
    results = mem.read("Swarmojo engines")
    assert len(results) >= 1
    assert "swarmojo_core" == results[0]["key"]


def test_toolcall_repair():
    raw_markdown = "Thought: I should call the tool\n```json\n{'tool': 'search', 'query': 'Buzburg', 'limit': '5', 'active': True,}\n```"
    extracted = extract_outer_json(raw_markdown)
    assert extracted != ""
    repaired = repair_json_string(extracted)
    parsed = json.loads(repaired)
    assert parsed["tool"] == "search"
    assert parsed["query"] == "Buzburg"
    assert parsed["active"] is True


def test_sieve_compaction():
    log_data = "\n".join([
        "Starting build pipeline...",
        "Fetching dependencies...",
        "downloading 12% [===>       ]",
        "downloading 45% [=======>   ]",
        "downloading 100% [==========]",
        "Traceback (most recent call last):",
        '  File "test.py", line 42, in <module>',
        "    raise ValueError('Critical failure in module')",
        "ValueError: Critical failure in module",
        *(["ok"] * 80),
        "Process exited with error code 1.",
    ])
    result = compact_text(log_data, context_window=2, max_lines=20)
    assert result["compression_ratio_pct"] > 0
    assert "ValueError: Critical failure" in result["text"]


def test_horizon_circuit_breaker(tmp_path: Path):
    mgr = HorizonManager(root=str(tmp_path))
    mgr.init("Build and test task DAG")

    # Success step
    step1 = mgr.record_action("pytest tests/test_unit.py", success=True)
    assert not step1["is_loop"]

    # Failed step 1
    step2 = mgr.record_action("cargo build --release", success=False)
    assert not step2["is_loop"]

    # Exact duplicate fail triggers anti-loop breaker
    step3 = mgr.record_action("cargo build --release", success=False)
    assert step3["is_loop"]


def test_fastgate_tool_triage():
    tools = [
        "web_search",
        "weather_lookup",
        "calculate_sum",
        "git_commit_file",
        "read_repository_file",
        "database_migrate_schema",
    ]
    prompt = "Please read the repository file app/server.py and check git status"
    res = route_tools(prompt, tools, threshold=0.1)
    assert "read_repository_file" in res["retained_tools"]
    assert res["token_savings_pct"] > 0


def test_compact_kv_scratchpad(tmp_path: Path):
    mgr = CompactKVManager(root=str(tmp_path))
    mgr.init("Implement local engines in Swarmojo")

    assert mgr.add_fact("Swarmojo engine suite verified.")
    # Deduplicate check
    assert not mgr.add_fact("Swarmojo engine suite verified.")

    mgr.set_hypothesis("Integrate native Mojo kernels into app_mojo/")
    mgr.touch_file("roms.py")

    preamble = mgr.generate_compact_preamble()
    assert "COMPACT-KV" in preamble
    assert "Swarmojo engine suite verified." in preamble
    assert "roms.py" in preamble


def test_rewind_snapshot_and_rollback(tmp_path: Path):
    test_file = tmp_path / "agent_code.py"
    test_file.write_text("v1 = 'initial'", encoding="utf-8")

    engine = RewindEngine(root=str(tmp_path))
    snap1 = engine.snapshot("Initial code state")
    assert snap1["file_count"] >= 1

    # Mutate file
    test_file.write_text("v1 = 'corrupted'", encoding="utf-8")
    assert test_file.read_text(encoding="utf-8") == "v1 = 'corrupted'"

    # Rollback to checkpoint
    res = engine.rollback(cp_id=snap1["checkpoint"])
    assert res["success"]
    assert test_file.read_text(encoding="utf-8") == "v1 = 'initial'"


def test_path_carry_safety_audit(tmp_path: Path):
    result = PathAuditResult()
    audit_filename("clean_filename.py", "clean_filename.py", result)
    assert result.is_clean

    # Reserved device name
    audit_filename("nul.txt", "nul.txt", result)
    assert not result.is_clean
    assert any(err["rule"] == "WINDOWS_RESERVED_NAME" for err in result.errors)

    # Clean directory audit
    dir_audit = audit_directory(str(tmp_path))
    assert dir_audit.is_clean


def test_localdoc_search_chunking():
    doc = (
        "Heading 1\n"
        "This is paragraph one explaining how Swarmojo orchestrates autonomous agents.\n\n"
        "Heading 2\n"
        "This is paragraph two explaining the high-speed local engines.\n"
    )
    passages = chunk_document("guide.md", doc)
    assert len(passages) >= 2
    assert passages[0].source == "guide.md"

    matches = keyword_search(passages, "Swarmojo engines", limit=2)
    assert len(matches) >= 1


def test_server_engine_tools(tmp_path: Path):
    from fastmcp import Client
    import asyncio
    from app import server

    async def run():
        async with Client(server.mcp) as client:
            tools = await client.list_tools()
            tool_names = [t.name for t in tools]
            assert "symdex_query" in tool_names
            assert "titans_memory_update" in tool_names
            assert "titans_memory_recall" in tool_names
            assert "toolcall_repair_output" in tool_names
            assert "sieve_compact_logs" in tool_names
            assert "horizon_record_step" in tool_names
            assert "fastgate_triage_tools" in tool_names
            assert "compact_kv_scratchpad" in tool_names
            assert "rewind_snapshot_workspace" in tool_names
            assert "rewind_rollback_workspace" in tool_names
            assert "path_carry_audit" in tool_names

            # Test toolcall_repair_output
            res = await client.call_tool("toolcall_repair_output", {"raw_output": "{'foo': 'bar',}"})
            data = json.loads(res.content[0].text)
            assert data["valid"] is True
            assert data["data"]["foo"] == "bar"

            # Test fastgate_triage_tools
            res2 = await client.call_tool("fastgate_triage_tools", {
                "prompt": "inspect files and run tests",
                "tools_json": json.dumps(["run_tests", "weather_report", "browse_web"])
            })
            data2 = json.loads(res2.content[0].text)
            assert "run_tests" in data2["retained_tools"]

    asyncio.run(run())

