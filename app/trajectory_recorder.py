"""UpSkill-Inspired Trajectory Recording & Automated Skill Brewing Engine.

Captures agent task execution trajectories (user intent, tool calls, arguments, outputs, error recoveries),
and automatically distills successful multi-turn workflows into standardized procedural SOP playbooks
under skills/_candidates/<skill_name>.md for review.

Optimized for local LLMs:
- Microsecond in-memory step recording with on-demand durability flushing
- Automatic error-recovery pattern extraction (converts failures into troubleshooting playbooks)
"""

import json
from pathlib import Path
from app.safe_paths import markdown_path
from typing import Any, Dict, List, Optional
from app.config import SKILLS_DIR
from app.db import get_connection

# In-memory buffer for active trajectories (avoids disk sync on every single agent tool step)
_ACTIVE_SESSIONS: Dict[str, Dict[str, Any]] = {}


def start_session(
    session_id: str,
    goal: str,
    db_path: Path | str | None = None,
) -> str:
    """Begins recording an agent task trajectory."""
    _ACTIVE_SESSIONS[session_id] = {
        "session_id": session_id,
        "goal": goal,
        "steps": [],
        "success": False,
        "final_result": "",
        "db_path": db_path,
        "dirty": True,
    }

    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR REPLACE INTO agent_trajectories (session_id, goal, steps_json, success, final_result)
        VALUES (?, ?, '[]', 0, '')
        """,
        (session_id, goal),
    )
    conn.commit()
    return f"Trajectory session '{session_id}' started for goal: {goal}"


def record_step(
    session_id: str,
    action: str,
    input_params: Any,
    output_result: Any,
    error: Optional[str] = None,
    db_path: Path | str | None = None,
) -> None:
    """Appends an execution step (tool call, parameters, result, or error) to the session trajectory.

    Executes in microseconds via in-memory session buffer.
    """
    if session_id not in _ACTIVE_SESSIONS:
        # Load from DB if session exists
        conn = get_connection(db_path)
        cur = conn.cursor()
        cur.execute("SELECT goal, steps_json, success, final_result FROM agent_trajectories WHERE session_id = ?", (session_id,))
        row = cur.fetchone()
        if row:
            _ACTIVE_SESSIONS[session_id] = {
                "session_id": session_id,
                "goal": row[0],
                "steps": json.loads(row[1]) if row[1] else [],
                "success": bool(row[2]),
                "final_result": row[3],
                "db_path": db_path,
                "dirty": False,
            }
        else:
            _ACTIVE_SESSIONS[session_id] = {
                "session_id": session_id,
                "goal": "Ad-hoc task execution",
                "steps": [],
                "success": False,
                "final_result": "",
                "db_path": db_path,
                "dirty": True,
            }

    sess = _ACTIVE_SESSIONS[session_id]
    step_num = len(sess["steps"]) + 1
    step_entry = {
        "step_number": step_num,
        "action": action,
        "input": input_params,
        "output": str(output_result)[:1000],  # bounded sample
        "error": error,
        "status": "FAILED" if error else "SUCCESS",
    }
    sess["steps"].append(step_entry)
    sess["dirty"] = True


def _flush_session(session_id: str, db_path: Path | str | None = None) -> None:
    """Flushes buffered in-memory trajectory steps to SQLite."""
    sess = _ACTIVE_SESSIONS.get(session_id)
    if not sess or not sess.get("dirty", False):
        return

    active_db = db_path or sess.get("db_path")
    conn = get_connection(active_db)
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE agent_trajectories
        SET steps_json = ?, success = ?, final_result = ?
        WHERE session_id = ?
        """,
        (
            json.dumps(sess["steps"]),
            1 if sess["success"] else 0,
            sess["final_result"],
            session_id,
        ),
    )
    conn.commit()
    sess["dirty"] = False


def finish_session(
    session_id: str,
    success: bool,
    final_result: str,
    db_path: Path | str | None = None,
) -> str:
    """Finalizes an agent trajectory session with success status and summary."""
    if session_id in _ACTIVE_SESSIONS:
        sess = _ACTIVE_SESSIONS[session_id]
        sess["success"] = success
        sess["final_result"] = final_result
        sess["dirty"] = True
        _flush_session(session_id, db_path=db_path)
    else:
        conn = get_connection(db_path)
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE agent_trajectories
            SET success = ?, final_result = ?
            WHERE session_id = ?
            """,
            (1 if success else 0, final_result, session_id),
        )
        conn.commit()

    return f"Trajectory session '{session_id}' finalized (Success: {success})."


def get_trajectory(
    session_id: str,
    db_path: Path | str | None = None,
) -> Optional[Dict[str, Any]]:
    """Retrieves full trajectory data for a given session."""
    if session_id in _ACTIVE_SESSIONS:
        _flush_session(session_id, db_path=db_path)
        sess = _ACTIVE_SESSIONS[session_id]
        return {
            "session_id": sess["session_id"],
            "goal": sess["goal"],
            "steps": list(sess["steps"]),
            "success": sess["success"],
            "final_result": sess["final_result"],
        }

    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT session_id, goal, steps_json, success, final_result, created_at FROM agent_trajectories WHERE session_id = ?",
        (session_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "session_id": row[0],
        "goal": row[1],
        "steps": json.loads(row[2]) if row[2] else [],
        "success": bool(row[3]),
        "final_result": row[4],
        "created_at": str(row[5]),
    }


def distill_trajectory_to_skill(
    session_id: str,
    skill_name: str,
    description: str = "",
    target_skills_dir: Optional[Path] = None,
    db_path: Path | str | None = None,
) -> str:
    """Drafts a playbook from a recorded session without asserting that it is verified.

    Defaults to skills/_candidates; explicit target directories are for trusted callers.
    """
    traj = get_trajectory(session_id, db_path=db_path)
    if not traj:
        return f"Error: No trajectory found for session '{session_id}'."

    clean_name = skill_name.replace(".md", "").strip().lower().replace(" ", "_")
    title = clean_name.replace("_", " ").title()
    goal = traj["goal"]
    steps = traj["steps"]

    # Extract distinct tools used
    tools_used = sorted(list({s["action"] for s in steps if s.get("action")}))

    # Extract any troubleshooting/recovered steps for smart error guidance
    failed_steps = [s for s in steps if s.get("status") == "FAILED" or s.get("error")]

    # Generate procedural markdown content
    lines = [
        "---",
        'skill_version: "1.0"',
        'review_status: "candidate"',
        f'title: "{title} SOP"',
        f'origin_task: "{goal}"',
        'type: "procedural_sop"',
        f'tags: ["auto-distilled", "upskill", "{clean_name}"]',
        "---",
        "",
        f"# {title} Standard Operating Procedure",
        "",
        "## 1. Objective",
        description if description else f"Unreviewed procedural draft from a recorded trajectory for: {goal}",
        "",
        "## 2. Required Tools",
    ]
    for tool in tools_used:
        lines.append(f"- `{tool}`")

    lines.extend([
        "",
        "## 3. Step-by-Step Execution Procedure",
    ])

    for s in steps:
        step_num = s.get("step_number", 1)
        action = s.get("action", "unknown_action")
        inp = s.get("input", {})
        out = s.get("output", "")
        status = s.get("status", "SUCCESS")

        lines.append(f"### Step {step_num}: Execute `{action}`")
        lines.append(f"- **Status Target**: `{status}`")
        if inp:
            inp_str = json.dumps(inp, indent=2) if isinstance(inp, (dict, list)) else str(inp)
            lines.append("- **Input Specification**:")
            lines.append("```json")
            lines.append(inp_str)
            lines.append("```")
        if out:
            sample_out = out[:300].strip()
            lines.append(f"- **Expected Output Sample**: `{sample_out}`")
        lines.append("")

    lines.extend([
        "## 4. Error Handling & Recovery Protocols",
    ])
    if failed_steps:
        lines.append("### Observed Pitfalls & Self-Healing Workarounds:")
        for fs in failed_steps:
            lines.append(f"- **Observed Issue in Step {fs.get('step_number')} (`{fs.get('action')}`)**: {fs.get('error')}")
            lines.append("  - *Correction Protocol*: Validate inputs against tool schema via `search_tools` and retry.")
    else:
        lines.append("- **Tool Schema Mismatch**: Invoke `search_tools(query=...)` to retrieve the latest parameter contract.")
        lines.append("- **Operational Failure**: Escalate ticket status or notify human supervisor.")

    lines.extend([
        "",
        "## 5. Verification Checklist",
        "- [ ] Step-by-step tool outputs confirmed.",
        "- [ ] Database state consistent with execution outcome.",
        f"- [ ] Final result fulfills: {goal}.",
        "",
    ])

    sop_content = "\n".join(lines)

    dest_dir = target_skills_dir if target_skills_dir is not None else SKILLS_DIR / "_candidates"
    dest_dir.mkdir(parents=True, exist_ok=True)
    sop_file = markdown_path(dest_dir, clean_name)
    sop_file.write_text(sop_content, encoding="utf-8")

    review_note = "It is not active; review before publishing." if target_skills_dir is None else "Review before using as an active playbook."
    return f"Candidate skill '{clean_name}' saved to {sop_file}. {review_note}"
