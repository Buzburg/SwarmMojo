"""The new identity must preserve legacy contracts and approval requirements."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys

from swarmmojo import configure_environment


def test_new_environment_names_take_precedence_without_touching_other_values():
    values = {"SWARMMOJO_DB_PATH": "new.db", "ROMS_DB_PATH": "legacy.db", "PATH": "unchanged"}
    configure_environment(values)
    assert values["ROMS_DB_PATH"] == "new.db"
    assert values["PATH"] == "unchanged"
    assert values["ROMS_STATE_DIR"] == str(Path.home() / ".swarmmojo")


def test_explicit_legacy_state_location_is_preserved():
    values = {"ROMS_STATE_DIR": "/operator/selected"}
    configure_environment(values)
    assert values["ROMS_STATE_DIR"] == "/operator/selected"


def test_new_launcher_from_another_directory_loads_selected_review_role(tmp_path):
    root = Path(__file__).resolve().parents[1]
    environment = {**os.environ, "SWARMMOJO_DB_PATH": str(tmp_path / "absent.db"),
                   "SWARMMOJO_STATE_DIR": str(tmp_path / "unused-state"),
                   "SWARMMOJO_DATA_DIR": str(tmp_path / "unused-data"),
                   "PYTHONDONTWRITEBYTECODE": "1"}
    process = subprocess.run([sys.executable, "-B", str(root / "swarmmojo.py"), "harness",
                              "--request", str(root / "examples/code-review-request.json")],
                             cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=30)
    assert process.returncode == 0, process.stderr
    report = json.loads(process.stdout)
    assert report["context"]["skills"][0]["name"] == "agency-code-reviewer.md"
    assert report["decision"]["engine"] == "SwarmMojo Decision Maker"
    assert report["schema"] == "roms.harness/v1"
    assert report["approval_required"] and not report["execution_allowed"]
    assert not (tmp_path / "unused-data").exists()
    assert not (tmp_path / "unused-state").exists()


def test_preferred_mcp_tool_and_legacy_alias_share_contract(tmp_path, monkeypatch):
    from fastmcp import Client
    from app import server

    monkeypatch.setattr(server, "DB_PATH", tmp_path / "missing.db")
    monkeypatch.setattr(server, "SKILLS_DIR", tmp_path / "skills")
    request = json.dumps({"goal": "Choose an invoice review", "options": {
        "review": "Review the invoice", "publish": "Publish the website"}})

    async def call():
        async with Client(server.mcp) as client:
            results = []
            for name in ("swarmmojo_prepare_harness", "roms_prepare_harness"):
                response = await client.call_tool(name, {"request_json": request})
                results.append(json.loads(response.content[0].text))
            for report in results:
                assert report["schema"] == "roms.harness/v1"
                assert report["status"] == "abstained"
                assert report["approval_required"] and not report["execution_allowed"]
                assert report["proposed_next_step"] is None
            assert results[0]["decision"]["probabilities"] == results[1]["decision"]["probabilities"]

    asyncio.run(call())
    assert not (tmp_path / "missing.db").exists()
