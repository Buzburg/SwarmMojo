"""Autonomous Continuous Memory Reflection & Buzburg LLM Knowledge Wiki Export.

Directly implements the failure-to-patch pair recording for sovereign agent workflows.
Provides:
1. ContinuousMemoryReflector: Outcome-weighted reflection (Retain, Recall, Reflect).
2. LLMWikiExporter: Serializes active project lessons into compact, auto-linked Markdown wikis.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from typing import Optional

from app.memory import retain_memory, record_memory_verification, recall_memory, _connection, _scope, _now


@dataclass
class TaskOutcome:
    project_id: str
    target_file: str
    action_taken: str
    succeeded: bool
    task_id: str = ""
    revision: str = ""
    error_log: Optional[str] = None
    patch_summary: Optional[str] = None


class ContinuousMemoryReflector:
    """Implements autonomous outcome reflection for task executions."""

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = db_path

    def reflect(self, outcome: TaskOutcome) -> dict[str, object]:
        """Reflects on task outcome and updates persistent lesson memory."""
        project = _scope(outcome.project_id)
        clean_target = outcome.target_file.strip()

        if outcome.succeeded:
            # Positive outcome: retain verified lesson
            summary = (
                f"VERIFIED WORKFLOW for {clean_target}: {outcome.action_taken}. "
                f"Patch validated cleanly."
            )
            record = retain_memory(
                project_id=project,
                summary=summary[:3900],
                source_ref=f"task:{outcome.task_id or 'direct'}:{clean_target}",
                revision=outcome.revision,
                session_id=outcome.task_id,
                db_path=self.db_path,
            )
            # Mark verified
            verified_record = record_memory_verification(
                project_id=project,
                memory_id=str(record["id"]),
                command=f"validate {clean_target}",
                exit_code=0,
                evidence_ref=f"patch_success:{outcome.patch_summary or 'clean'}",
                db_path=self.db_path,
            )
            return {"status": "reflected_success", "memory": verified_record}

        else:
            # Negative outcome (Autonomous anti-pattern reflection)
            error_snippet = (outcome.error_log or "Unknown error").strip()[:300]
            summary = (
                f"AVOID ANTI-PATTERN for {clean_target}: {outcome.action_taken}. "
                f"Failed with error: {error_snippet}."
            )
            record = retain_memory(
                project_id=project,
                summary=summary[:3900],
                source_ref=f"task:{outcome.task_id or 'direct'}:{clean_target}",
                revision=outcome.revision,
                session_id=outcome.task_id,
                db_path=self.db_path,
            )
            # Mark as verified failure so it acts as an active constraint
            verified_record = record_memory_verification(
                project_id=project,
                memory_id=str(record["id"]),
                command=f"validate {clean_target}",
                exit_code=1,
                evidence_ref=f"patch_failure:{error_snippet}",
                db_path=self.db_path,
            )
            return {"status": "reflected_failure", "memory": verified_record}


class LLMWikiExporter:
    """Exports ROMS memory records into compact, human-readable Markdown LLM Wikis.

    Follows the Karpathy LLM Wiki / AgentMemory pattern to minimize token usage
    when injecting project state into small local models like RWKV-7.
    """

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = db_path

    def export_project_wiki(self, project_id: str, output_dir: Path | str) -> dict[str, str]:
        """Dumps compact LESSONS.md and ANTI_PATTERNS.md into target directory."""
        project = _scope(project_id)
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        with _connection(self.db_path) as conn:
            # Fetch verified successes
            successes = conn.execute(
                "SELECT id, summary, source_ref, created_at FROM lesson_memories "
                "WHERE project_id = ? AND status = 'verified' AND outcome = 'success' "
                "ORDER BY created_at DESC LIMIT 50",
                (project,),
            ).fetchall()

            # Fetch verified failures (anti-patterns)
            failures = conn.execute(
                "SELECT id, summary, source_ref, created_at FROM lesson_memories "
                "WHERE project_id = ? AND status = 'verified' AND outcome = 'failure' "
                "ORDER BY created_at DESC LIMIT 50",
                (project,),
            ).fetchall()

        lessons_file = out_path / "LESSONS.md"
        anti_patterns_file = out_path / "ANTI_PATTERNS.md"

        # Generate LESSONS.md
        lessons_md = [
            f"# Verified Project Lessons: {project}",
            f"*Auto-generated from ROMS persistent memory on {_now()}*\n",
        ]
        if not successes:
            lessons_md.append("No verified success lessons recorded yet.")
        else:
            for row in successes:
                lessons_md.append(f"- **{row['source_ref']}** ({row['created_at'][:10]}): {row['summary']}")

        # Generate ANTI_PATTERNS.md
        anti_md = [
            f"# Known Anti-Patterns & Failures: {project}",
            f"*Auto-generated from ROMS persistent memory on {_now()}*\n",
            "> [!CAUTION] The following operations previously failed validation and must be avoided:\n",
        ]
        if not failures:
            anti_md.append("No verified failure patterns recorded yet.")
        else:
            for row in failures:
                anti_md.append(f"- **{row['source_ref']}** ({row['created_at'][:10]}): {row['summary']}")

        lessons_content = "\n".join(lessons_md) + "\n"
        anti_content = "\n".join(anti_md) + "\n"

        lessons_file.write_text(lessons_content, encoding="utf-8")
        anti_patterns_file.write_text(anti_content, encoding="utf-8")

        return {
            "lessons_path": str(lessons_file.resolve()),
            "anti_patterns_path": str(anti_patterns_file.resolve()),
            "success_count": str(len(successes)),
            "failure_count": str(len(failures)),
        }
