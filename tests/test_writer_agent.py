"""Tests for Swarmojo Writer Agent Engine."""
from __future__ import annotations

from pathlib import Path
import pytest

from app.engines.writer import (
    WriterAgentEngine,
    ProseHumanizer,
    BookOutlinePlanner,
    AI_PHRASE_BLACKLIST,
)
from app.meta.premade import PREMADE_AGENTS, PREMADE_TEAMS


def test_prose_humanizer_audit_dirty():
    slop_text = (
        "In today's digital landscape, it is crucial to delve into machine learning. "
        "Furthermore, this technology stands as a testament to human innovation. "
        "Moreover, it provides a holistic approach to foster a culture of excellence."
    )
    audit = ProseHumanizer.audit_text(slop_text)
    assert audit.score < 0.6
    assert audit.passed is False
    assert len(audit.blacklisted_phrases) >= 3
    assert "delve into" in audit.blacklisted_phrases or "in today's digital landscape" in audit.blacklisted_phrases
    assert len(audit.recommendations) > 0


def test_prose_humanizer_clean_prose():
    text = "Furthermore, in today's fast-paced world, we built a high-speed parser in 1994."
    cleaned = ProseHumanizer.humanize(text)
    assert "in today's fast-paced world" not in cleaned
    assert "Furthermore" not in cleaned
    assert "built a high-speed parser in 1994" in cleaned


def test_book_outline_planner(tmp_path: Path):
    planner = BookOutlinePlanner(book_title="Autonomous Horizon", genre="Sci-Fi")
    chap1 = planner.add_chapter(
        title="First Contact",
        summary="A rogue satellite intercepts an anomalous subspace packet.",
        target_word_count=3000,
        pov_character="Dr. Vance",
        key_conflict="Telemetry signal decrypts despite military jamming.",
    )
    chap2 = planner.add_chapter(
        title="The Vector Shift",
        summary="Deep neural models begin hallucinating coordinate vectors.",
        target_word_count=4000,
        pov_character="Captain Morales",
        key_conflict="Orbital decay forces immediate mission abort.",
    )

    plan = planner.compile_plan()
    assert plan["title"] == "Autonomous Horizon"
    assert plan["total_chapters"] == 2
    assert plan["estimated_word_count"] == 7000
    assert plan["chapters"][0]["pov_character"] == "Dr. Vance"


def test_writer_agent_engine(tmp_path: Path):
    writer = WriterAgentEngine(workspace_root=str(tmp_path))
    res = writer.plan_book(
        title="Ghost Protocol Chronicles",
        genre="Cyberpunk Thriller",
        chapters_data=[
            {"title": "Blacklist", "summary": "Eliminating synthetic linguistic markers", "words": 2800},
        ],
    )
    assert res["title"] == "Ghost Protocol Chronicles"
    assert res["total_chapters"] == 1
    assert "saved_to" in res
    assert Path(res["saved_to"]).exists()


def test_writer_premade_agent_and_team():
    agents_map = {a.id: a for a in PREMADE_AGENTS}
    assert "author_scribe" in agents_map
    agent = agents_map["author_scribe"]
    assert agent.division == "writing"
    assert "writer_audit_prose" in agent.tools
    assert "writer_clean_prose" in agent.tools
    assert "writer_plan_book" in agent.tools

    teams_map = {t.id: t for t in PREMADE_TEAMS}
    assert "editorial_publishing_team" in teams_map
    team = teams_map["editorial_publishing_team"]
    assert "author_scribe" in team.member_ids
