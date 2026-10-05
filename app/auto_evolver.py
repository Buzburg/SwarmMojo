"""Draft playbooks from recorded trajectories; never auto-activate generated skills."""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from app.config import SKILLS_DIR
from app.db import get_connection
from app.trajectory_recorder import distill_trajectory_to_skill


def clean_skill_slug(goal: str) -> str:
    """Derives a clean, readable skill slug from a task goal."""
    clean = re.sub(r"[^a-zA-Z0-9\s]", "", goal.lower())
    words = [w for w in clean.split() if w not in {"the", "a", "an", "for", "to", "in", "and", "or", "of", "with"}]
    slug = "_".join(words[:4])
    return slug if slug else "auto_synthesized_task"


def scan_and_evolve_skills(
    min_steps: int = 2,
    target_skills_dir: Optional[Path] = None,
    db_path: Path | str | None = None,
) -> List[Dict[str, Any]]:
    """Draft playbooks from sessions marked successful; that flag does not prove task correctness."""
    skills_dir = target_skills_dir if target_skills_dir is not None else SKILLS_DIR / "_candidates"
    skills_dir.mkdir(parents=True, exist_ok=True)
    existing_skills = {f.stem.lower() for f in skills_dir.glob("*.md")}

    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT session_id, goal, steps_json, final_result
        FROM agent_trajectories
        WHERE success = 1
        ORDER BY created_at DESC
        LIMIT 50
        """
    )
    rows = cur.fetchall()

    evolved_skills = []

    for row in rows:
        session_id, goal, steps_json, final_result = row
        try:
            steps = json.loads(steps_json) if steps_json else []
        except Exception:
            continue

        if len(steps) < min_steps:
            continue

        skill_slug = clean_skill_slug(goal)
        if skill_slug in existing_skills:
            continue

        # Synthesize procedural SOP
        distill_msg = distill_trajectory_to_skill(
            session_id=session_id,
            skill_name=skill_slug,
            description=f"Unreviewed candidate distilled from session {session_id} for goal: {goal}",
            target_skills_dir=skills_dir,
            db_path=db_path,
        )

        existing_skills.add(skill_slug)
        evolved_skills.append({
            "skill_name": skill_slug,
            "session_id": session_id,
            "goal": goal,
            "step_count": len(steps),
            "status": distill_msg,
        })

    return evolved_skills
