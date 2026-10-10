"""Tests for SwarmMojo Design Agent Engine."""
from __future__ import annotations

from pathlib import Path
import pytest

from app.engines.design import (
    DesignAgentEngine,
    DesignTokens,
    UIComponentRegistry,
)
from app.meta.premade import PREMADE_AGENTS, PREMADE_TEAMS


def test_design_tokens_css():
    tokens = DesignTokens(
        primary="#6366F1",
        background="#0B0F19",
        text_primary="#F9FAFB",
    )
    css = tokens.to_css()
    assert "--color-primary: #6366F1;" in css
    assert "--color-bg: #0B0F19;" in css
    assert "--color-text-primary: #F9FAFB;" in css
    assert "--radius-card: 12px;" in css


def test_ui_component_registry_renders():
    navbar = UIComponentRegistry.render_navbar(
        brand_name="TestBrand",
        links=[{"label": "Home", "href": "/"}, {"label": "Docs", "href": "/docs"}],
        cta_label="Sign In",
    )
    assert "TestBrand" in navbar
    assert 'href="/docs"' in navbar
    assert "Sign In" in navbar

    hero = UIComponentRegistry.render_hero(
        badge="New Release",
        title="Epic Hero Title",
        subtitle="Detailed Subtitle Description",
        primary_cta="Start Now",
        secondary_cta="Learn More",
    )
    assert "Epic Hero Title" in hero
    assert "New Release" in hero

    grid = UIComponentRegistry.render_feature_grid([
        {"icon": "⚡", "title": "Speed", "description": "Ultra fast"},
        {"icon": "🔒", "title": "Security", "description": "Rock solid"},
    ])
    assert "Speed" in grid
    assert "Security" in grid

    metrics = UIComponentRegistry.render_metrics_panel([
        {"value": "100%", "label": "Reliability"},
    ])
    assert "100%" in metrics
    assert "Reliability" in metrics


def test_design_engine_build_landing_page(tmp_path: Path):
    engine = DesignAgentEngine(workspace_root=str(tmp_path))
    res = engine.build_landing_page(
        project_name="AeroAgent",
        headline="Autonomous Flight AI",
        subheadline="High precision drone coordination",
    )
    assert res["status"] == "ready"
    assert res["project_name"] == "AeroAgent"
    index_file = tmp_path / ".mojo_design" / "index.html"
    assert index_file.exists()
    content = index_file.read_text(encoding="utf-8")
    assert "Autonomous Flight AI" in content
    assert "<!DOCTYPE html>" in content
    assert "--color-primary:" in content


def test_design_engine_build_admin_dashboard(tmp_path: Path):
    engine = DesignAgentEngine(workspace_root=str(tmp_path))
    res = engine.build_admin_dashboard(
        dashboard_title="SwarmHQ",
        stats=[
            {"label": "Active Workers", "value": "42", "delta": "+10%"},
        ],
        recent_activity=[
            {"agent": "Daedalus", "action": "Commit patch", "status": "ok", "time": "1m ago"},
        ],
    )
    assert res["status"] == "ready"
    dash_file = tmp_path / ".mojo_design" / "dashboard.html"
    assert dash_file.exists()
    content = dash_file.read_text(encoding="utf-8")
    assert "SwarmHQ" in content
    assert "Active Workers" in content
    assert "Daedalus" in content


def test_design_premade_agent_and_team():
    agents_map = {a.id: a for a in PREMADE_AGENTS}
    assert "design_architect" in agents_map
    agent = agents_map["design_architect"]
    assert agent.division == "design"
    assert "design_build_landing_page" in agent.tools
    assert "design_build_dashboard" in agent.tools

    teams_map = {t.id: t for t in PREMADE_TEAMS}
    assert "design_site_team" in teams_map
    team = teams_map["design_site_team"]
    assert "design_architect" in team.member_ids
    assert "studio_director" in team.member_ids


def test_design_engine_build_herald_hud(tmp_path: Path):
    engine = DesignAgentEngine(workspace_root=str(tmp_path))
    res = engine.build_herald_hud(system_title="Herald OS Orbit")
    assert res["status"] == "ready"
    assert res["system_title"] == "Herald OS Orbit"
    assert res["total_agents"] == 6
    assert res["total_milestones"] == 4
    hud_file = tmp_path / ".mojo_design" / "herald_hud.html"
    assert hud_file.exists()
    content = hud_file.read_text(encoding="utf-8")
    assert "HERALD-OS" in content
    assert "SPECIALIST ROSTER" in content
    assert "Atlas" in content
    assert "TriggerTangle Offline Rehearsal" in content

