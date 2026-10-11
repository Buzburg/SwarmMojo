"""Tests for Swarmojo Studio Agent Engine."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from app.engines.studio import (
    StudioAgentEngine,
    StudioPromptCompiler,
    StoryboardDirector,
    ComfyUIBridge,
    ASPECT_RATIOS,
)
from app.meta.premade import PREMADE_AGENTS, PREMADE_TEAMS


def test_studio_prompt_compiler_cinematic():
    res = StudioPromptCompiler.compile_cinematic_prompt(
        subject="Lone warrior standing atop a cliff overlooking neo-Tokyo",
        camera="grand_format_70mm",
        lens="classic_anamorphic",
        focal_length_mm=40,
        aperture="f/1.4",
        lighting="cyberpunk_neon",
        motion="slow dramatic upward tilt",
    )
    prompt = res["prompt"]
    assert "Lone warrior" in prompt
    assert "grand format 70mm" in prompt
    assert "classic 2x anamorphic lens" in prompt
    assert "40mm focal length" in prompt
    assert "f/1.4 aperture" in prompt
    assert "cyberpunk_neon" in res["camera_rig"]["lighting"] or "neon" in prompt
    assert "camera motion: slow dramatic upward tilt" in prompt
    assert res["negative_prompt"] != ""


def test_storyboard_director(tmp_path: Path):
    director = StoryboardDirector(title="Sci-Fi Chase Sequence")
    director.add_shot(
        duration_seconds=3.5,
        description="Establishing shot of hovering spacecraft over rain-soaked neon highway",
        camera="modular_8k_digital",
        lens="classic_anamorphic",
        lighting="cyberpunk_neon",
        camera_movement="high-angle sweeping crane shot",
    )
    director.add_shot(
        duration_seconds=2.0,
        description="Close-up of pilot engaging thruster ignition switches",
        camera="super_35_digital",
        lens="extreme_macro",
        lighting="cinematic_rembrandt",
        camera_movement="dramatic rapid push-in",
    )

    board = director.compile_storyboard()
    assert board["title"] == "Sci-Fi Chase Sequence"
    assert board["total_shots"] == 2
    assert board["total_duration_seconds"] == 5.5
    assert len(board["shots"]) == 2
    assert board["shots"][0]["shot_number"] == 1
    assert "high-angle sweeping crane shot" in board["shots"][0]["camera_movement"]


def test_comfyui_flux_graph_export(tmp_path: Path):
    studio = StudioAgentEngine(workspace_root=str(tmp_path))
    res = studio.export_comfyui_workflow(
        prompt="Award-winning wildlife portrait of an arctic fox in snowstorm",
        aspect_ratio="16:9",
        steps=28,
    )
    assert res["status"] == "ready"
    assert res["aspect_ratio"] == "16:9"
    workflow = res["workflow"]
    # Verify node structure
    assert "1" in workflow and workflow["1"]["class_type"] == "CheckpointLoaderSimple"
    assert "2" in workflow and workflow["2"]["class_type"] == "CLIPTextEncode"
    assert "5" in workflow and workflow["5"]["class_type"] == "KSampler"
    assert workflow["5"]["inputs"]["steps"] == 28


def test_banner_spec_craft(tmp_path: Path):
    studio = StudioAgentEngine(workspace_root=str(tmp_path))
    banner = studio.craft_banner_spec(
        platform="youtube_banner",
        headline="Deep Agent Swarms",
        subtext="Zero-overhead autonomous coding & studio pipeline",
    )
    assert banner["platform"] == "youtube_banner"
    assert banner["dimensions"]["width"] == 2560
    assert banner["dimensions"]["height"] == 1440
    assert "safe zone" in banner["safe_zone"]
    assert banner["typography"]["headline"] == "Deep Agent Swarms"


def test_studio_premade_agent_and_team():
    agents_map = {a.id: a for a in PREMADE_AGENTS}
    assert "studio_director" in agents_map
    studio_agent = agents_map["studio_director"]
    assert studio_agent.division == "design"
    assert "studio_compile_prompt" in studio_agent.tools
    assert "studio_export_comfyui_graph" in studio_agent.tools

    teams_map = {t.id: t for t in PREMADE_TEAMS}
    assert "studio_production_team" in teams_map
    studio_team = teams_map["studio_production_team"]
    assert "studio_director" in studio_team.member_ids
