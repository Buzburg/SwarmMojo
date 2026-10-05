"""ROMS FastMCP Unified Server Entrypoint."""

import importlib.util
import os
import sys
from pathlib import Path
from app.safe_paths import markdown_path
from fastmcp import FastMCP

from app.config import SKILLS_DIR, KNOWLEDGE_DIR, BASE_DIR
from app.db import init_database
from app.okf_loader import ingest_okf_directory
from app.rag_engine import (
    search_knowledge_base as _search_knowledge_base,
    search_grounded_context as _search_grounded_context,
)
from app.watcher import start_watcher, get_watcher_status as _get_watcher_status
from app.throttle import tool_limiter
from app.tools import (
    create_support_ticket as _create_ticket,
    get_support_ticket as _get_ticket,
    update_ticket_status as _update_ticket_status,
    list_support_tickets as _list_tickets,
    run_sandboxed_command as _run_sandboxed_command,
    list_skills as _list_skills,
    add_skill as _add_skill,
    list_knowledge_documents as _list_docs,
    add_knowledge_document as _add_doc,
    reload_knowledge as _reload_knowledge,
    get_system_metrics as _get_metrics,
)

from app.memory_tools import register_memory_tools

mcp = FastMCP("ROMS-Engine")
register_memory_tools(mcp)


# ============================================================================
# [O] & [R] OKF INGESTION & RAG RETRIEVAL TOOLS
# ============================================================================


@mcp.tool()
def search_knowledge_base(query: str, limit: int = 3) -> str:
    """Semantic vector search across ingested OKF markdown documentation."""
    return _search_knowledge_base(query=query, limit=limit)


@mcp.tool()
def search_grounded_context(query: str, limit: int = 3, max_tokens: int = 512) -> str:
    """Retrieves high-precision knowledge context formatted in clean XML tags specifically for local LLMs."""
    return _search_grounded_context(query=query, limit=limit, max_tokens=max_tokens)


@mcp.tool()
def add_knowledge_document(filename: str, content: str, title: str = "", doc_type: str = "general") -> str:
    """Adds a new OKF Markdown document to knowledge/ and indexes it in the vector DB in real time."""
    return _add_doc(filename=filename, content=content, title=title, doc_type=doc_type)


@mcp.tool()
def reload_knowledge() -> str:
    """Re-scans knowledge/ directory and updates vector embeddings for new or modified markdown files."""
    return _reload_knowledge()


@mcp.tool()
def list_knowledge_documents() -> str:
    """Lists all registered OKF documents, titles, and SHA-256 checksums."""
    docs = _list_docs()
    if not docs:
        return "No documents found in knowledge base."
    lines = [f"- [{d['doc_id']}] {d['title']} ({d['doc_type']}) - Last indexed: {d['last_indexed']}" for d in docs]
    return "\n".join(lines)


@mcp.tool()
def get_file_watcher_status() -> str:
    """Returns real-time status of the background file watcher (auto-indexing knowledge, skills, and tools)."""
    status = _get_watcher_status()
    paths = ", ".join(status.get("monitored_paths", []))
    return (
        f"Active: {status.get('is_running', False)}\n"
        f"Reload Events: {status.get('reloads_count', 0)}\n"
        f"Last Action: {status.get('last_event', 'None')}\n"
        f"Watched Directories: {paths}"
    )


# ============================================================================
# [M] OPERATIONAL MCP TOOLS (BUSINESS ACTIONS & SANDBOXING)
# ============================================================================


@mcp.tool()
def create_support_ticket(ticket_id: str, email: str, summary: str) -> str:
    """Inserts a verified customer support ticket into the operational database."""
    return _create_ticket(ticket_id=ticket_id, customer_email=email, issue_summary=summary)


@mcp.tool()
def get_ticket(ticket_id: str) -> str:
    """Retrieves current details and status for a given support ticket ID."""
    ticket = _get_ticket(ticket_id)
    if not ticket:
        return f"Ticket '{ticket_id}' not found."
    return (
        f"Ticket ID: {ticket['ticket_id']}\n"
        f"Customer Email: {ticket['customer_email']}\n"
        f"Status: {ticket['status']}\n"
        f"Created At: {ticket['created_at']}\n"
        f"Summary: {ticket['issue_summary']}"
    )


@mcp.tool()
def update_ticket_status(ticket_id: str, status: str) -> str:
    """Updates the operational status of an existing ticket (e.g., OPEN, URGENT, RESOLVED, CLOSED)."""
    return _update_ticket_status(ticket_id, status)


@mcp.tool()
def list_tickets(status: str = "") -> str:
    """Lists recent support tickets, optionally filtered by status (e.g. 'OPEN', 'URGENT')."""
    filter_status = status.strip() if status and status.strip() else None
    tickets = _list_tickets(filter_status)
    if not tickets:
        return "No support tickets found."
    lines = []
    for t in tickets:
        lines.append(f"[{t['ticket_id']}] ({t['status']}) - {t['customer_email']}: {t['issue_summary']}")
    return "\n".join(lines)


@mcp.tool()
def get_system_metrics() -> str:
    """Returns real-time host hardware metrics (CPU %, available RAM) and ROMS database statistics."""
    metrics = _get_metrics()
    return (
        f"Host CPU Load: {metrics['host_cpu_percent']}%\n"
        f"Available RAM: {metrics['available_ram_mb']} MB (Total: {metrics['total_ram_mb']} MB)\n"
        f"Ingested Documents: {metrics['ingested_documents']}\n"
        f"Indexed Chunks: {metrics['indexed_chunks']}\n"
        f"Cached Queries: {metrics['cached_query_embeddings']}\n"
        f"Registered Skills: {metrics['registered_skills']}\n"
        f"Open Tickets: {metrics['open_tickets']}"
    )


@mcp.tool()
@tool_limiter.guard(timeout=60.0)
async def run_sandboxed_command(image: str, command: str) -> str:
    """Executes a tool inside an isolated, hardware-capped container using Podman or Docker.

    Guarded against multi-agent swarms through hardware backoff and concurrency ceiling.
    """
    return await _run_sandboxed_command(image=image, command=command)


# ============================================================================
# [S] AGENT SKILLS & PROCEDURAL SOPs (RESOURCES & PROMPTS)
# ============================================================================


@mcp.tool()
def list_skills() -> str:
    """Lists all available agent procedural playbooks (SOPs) in the skills directory."""
    skills = _list_skills()
    if not skills:
        return "No skills currently registered."
    return "Available Skills:\n" + "\n".join(f"- {s} (accessible via skills://{s})" for s in skills)


@mcp.tool()
def add_skill(skill_name: str, content: str) -> str:
    """Creates a new agent skill SOP file in the skills directory."""
    return _add_skill(skill_name, content)


# ============================================================================
# [M] SMART TOOL RAG & ANALYTICS (AnyTool Inspired)
# ============================================================================

from app.tool_rag import (
    format_tool_search_results as _format_tool_search_results,
    get_tool_health_report as _get_tool_health_report,
    init_default_tool_registry as _init_default_tool_registry,
)
from app.trajectory_recorder import distill_trajectory_to_skill as _distill_trajectory


@mcp.tool()
def search_tools(query: str, category: str = "", limit: int = 3) -> str:
    """AnyTool Smart Tool RAG: retrieves exact tool schemas on-demand instead of crowding context."""
    return _format_tool_search_results(query=query, category=category, limit=limit)


@mcp.tool()
def get_tool_health_report() -> str:
    """Returns reliability metrics, call counts, average latency, and recent errors for all tools."""
    return _get_tool_health_report()


# ============================================================================
# [S] UPSKILL TRAJECTORY-TO-SKILL BREWER
# ============================================================================


@mcp.tool()
def distill_trajectory_to_skill(session_id: str, skill_name: str, description: str = "") -> str:
    """Draft a candidate playbook from a recorded trajectory; review is required before activation."""
    return _distill_trajectory(session_id=session_id, skill_name=skill_name, description=description)


# ============================================================================
# [R] ZG-SEARCH (ZERO-GRAVITY FUZZY & FACETED HYBRID ENGINE)
# ============================================================================

from app.tools import (
    zg_search_engine as _zg_search_engine,
    get_zg_search_facets as _get_zg_search_facets,
    list_knowledge_topics as _list_knowledge_topics,
    search_knowledge_by_topic as _search_knowledge_by_topic,
    generate_synthetic_dataset as _generate_synthetic_dataset,
    optimize_agent_prompt as _optimize_agent_prompt,
    evaluate_cartridge_health as _evaluate_cartridge_health,
)


@mcp.tool()
def zg_search(query: str, doc_type: str = "", fuzzy: bool = True, limit: int = 5) -> str:
    """Zero-Gravity Typo-Tolerant Hybrid Search: handles misspellings and facet filtering."""
    return _zg_search_engine(query=query, doc_type=doc_type, fuzzy=fuzzy, limit=limit)


@mcp.tool()
def get_zg_facets() -> str:
    """Returns document type counts and knowledge facet distribution for zero-latency UI filters."""
    import json
    return json.dumps(_get_zg_search_facets(), indent=2)


# ============================================================================
# [O] TOPIC TAXONOMY & ROUTED RAG
# ============================================================================


@mcp.tool()
def list_topics() -> str:
    """Lists all auto-extracted hierarchical knowledge topics and chunk counts."""
    import json
    return json.dumps(_list_knowledge_topics(), indent=2)


@mcp.tool()
def search_by_topic(topic: str, query: str, limit: int = 3) -> str:
    """Topic-routed semantic search: pre-filters candidates to a topic subgraph to stop hallucination."""
    return _search_knowledge_by_topic(topic=topic, query=query, limit=limit)


# ============================================================================
# [A] AUTOKARPATHY SYNTHETIC DATA & EVALS
# ============================================================================


@mcp.tool()
def autokarpathy_generate_dataset(output_path: str = "") -> str:
    """AutoKarpathy: Synthesizes instruction-tuning training pairs from knowledge and successful trajectories."""
    import json
    return json.dumps(_generate_synthetic_dataset(output_path=output_path), indent=2)


@mcp.tool()
def autokarpathy_optimize_prompt(task_description: str, base_prompt: str = "") -> str:
    """AutoKarpathy: Iteratively compresses and grounds system prompts for local LLMs."""
    import json
    return json.dumps(_optimize_agent_prompt(task_description=task_description, base_prompt=base_prompt), indent=2)


@mcp.tool()
def autokarpathy_eval_cartridge() -> str:
    """AutoKarpathy: Computes benchmark health and factuality score across ROMS."""
    import json
    return json.dumps(_evaluate_cartridge_health(), indent=2)


# ============================================================================
# [A] AUTORESEARCH DEEP INVESTIGATION & KNOWLEDGE COMPOUNDING
# ============================================================================

from app.tools import run_autoresearch as _run_autoresearch


@mcp.tool()
def autoresearch(topic: str, depth: int = 2, max_sources: int = 6, save_to_knowledge: bool = True) -> str:
    """AutoResearch: Deconstructs research queries, aggregates evidence across topics/vectors, synthesizes a verified dossier, and optionally compounds into knowledge/."""
    res = _run_autoresearch(topic=topic, depth=depth, max_sources=max_sources, save_to_knowledge=save_to_knowledge)
    if res.get("status") == "error":
        return f"AutoResearch Error: {res.get('message', 'Unknown failure')}"

    lines = [
        f"AutoResearch Dossier Completed: '{res['topic']}'",
        f"Analyzed Sources: {res['sources_count']} across {len(res['subqueries'])} investigative angles.",
    ]
    if res.get("saved_file_path"):
        lines.append(f"Compounded to Knowledge Base: {res['saved_file_path']}")
    lines.append("\n" + res["dossier"])
    return "\n".join(lines)


@mcp.prompt()
def autoresearch_sop() -> str:
    """Loads the AutoResearch procedural SOP playbook directly into conversation context."""
    return get_skill_resource("autoresearch")





@mcp.resource("skills://{skill_name}")
def get_skill_resource(skill_name: str) -> str:
    """Dynamically provides the procedural SOP playbook for any skill in the skills directory."""
    clean_name = skill_name.replace(".md", "").strip().lower()
    skill_file = markdown_path(SKILLS_DIR, clean_name)
    try:
        with open(skill_file, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"Skill '{clean_name}' not found. Use list_skills to see available SOPs."


@mcp.prompt()
def customer_service_sop() -> str:
    """Loads the customer service playbook directly into the conversation context."""
    return get_skill_resource("customer_service")


def get_customer_service_skill() -> str:
    """Backwards-compatible accessor for the customer service skill."""
    return get_skill_resource("customer_service")


@mcp.prompt()
def get_skill_playbook(skill_name: str) -> str:
    """Loads any available skill playbook directly into the LLM conversation context."""
    return get_skill_resource(skill_name)


# ============================================================================
# DYNAMIC CUSTOM TOOLS LOADER (custom_tools/*.py)
# ============================================================================


def load_custom_tools():
    """Auto-discovers and registers custom Python tool files from custom_tools/ directory."""
    custom_dir = BASE_DIR / "custom_tools"
    if not custom_dir.exists():
        custom_dir.mkdir(parents=True, exist_ok=True)
        return

    for py_file in custom_dir.glob("*.py"):
        if py_file.name.startswith("__"):
            continue
        try:
            module_name = f"custom_tools.{py_file.stem}"
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = mod
                spec.loader.exec_module(mod)
                if hasattr(mod, "register_tools"):
                    mod.register_tools(mcp)
                    print(f"[ROMS] Loaded custom tools plugin: {py_file.name}", file=sys.stderr)
        except Exception as e:
            print(f"[ROMS Warning] Failed to load custom tool {py_file.name}: {e}", file=sys.stderr)


# ============================================================================
# SERVER STARTUP
# ============================================================================


def start_server():
    """Bootstraps database, ingests OKF documents, loads plugins, starts watcher, and launches FastMCP."""
    print("[ROMS] Initializing database schema...", file=sys.stderr)
    init_database()
    print("[ROMS] Initializing Smart Tool RAG registry...", file=sys.stderr)
    _init_default_tool_registry()
    print("[ROMS] Ingesting OKF knowledge documents...", file=sys.stderr)
    count = ingest_okf_directory(KNOWLEDGE_DIR)
    print(f"[ROMS] OKF ingestion complete ({count} files processed).", file=sys.stderr)
    load_custom_tools()
    print("[ROMS] Starting background file watcher...", file=sys.stderr)
    start_watcher(mcp)
    print("[ROMS] Starting FastMCP server...", file=sys.stderr)
    mcp.run()


if __name__ == "__main__":
    start_server()
