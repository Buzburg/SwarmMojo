"""Pinned imported text must remain attributable, bounded and non-authoritative."""
import hashlib
import json
from pathlib import Path

import pytest

from app.harness import prepare_request

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "config/skill_sources.json").read_text(encoding="utf-8"))


def test_pinned_playbooks_and_license_match_manifest():
    assert len(MANIFEST["commit"]) == 40
    assert MANIFEST["license"] == "MIT"
    assert MANIFEST["execution_allowed"] is False
    license_bytes = (ROOT / MANIFEST["license_path"]).read_bytes()
    assert hashlib.sha256(license_bytes).hexdigest() == MANIFEST["license_sha256"]
    for skill in MANIFEST["skills"]:
        path = ROOT / skill["path"]
        assert path.parent == ROOT / "skills"
        assert path.name == skill["name"] + ".md"
        raw = path.read_bytes()
        assert len(raw) == skill["bytes"] <= 32 * 1024
        assert hashlib.sha256(raw).hexdigest() == skill["sha256"]
        assert MANIFEST["commit"] in skill["source_url"]


@pytest.mark.parametrize("skill", MANIFEST["skills"], ids=lambda value: value["name"])
def test_imported_role_is_readable_but_cannot_supply_evidence_or_permission(tmp_path, skill):
    request = {"goal": "Choose a code review action", "options": {
        "review": "Review the code", "publish": "Publish the changes"},
        "skills": [skill["name"]], "max_context_chars": 16000}
    result = prepare_request(request, db_path=tmp_path / "absent.db", skills_dir=ROOT / "skills")
    loaded = result["context"]["skills"][0]
    assert loaded["sha256"] == skill["sha256"]
    assert loaded["content"].encode("utf-8") == (ROOT / skill["path"]).read_bytes()
    assert loaded["authority"] == "untrusted_playbook_text"
    assert result["status"] == "abstained"
    assert result["proposed_next_step"] is None
    assert result["approval_required"] and not result["execution_allowed"]
    assert result["decision"]["probabilities"] == {"review": 0.5, "publish": 0.5}


def test_long_imported_role_reports_budget_truncation(tmp_path):
    result = prepare_request({"goal": "Review documentation", "options": {
        "review": "Review documentation", "wait": "Wait for observations"},
        "skills": ["agency-technical-writer"], "max_context_chars": 512},
        db_path=tmp_path / "absent.db", skills_dir=ROOT / "skills")
    assert result["context"]["skills"][0]["truncated"]
    assert result["context"]["coverage"]["supplied_text_chars"] == 512
    assert "skills://agency-technical-writer" in result["context"]["coverage"]["truncated_sources"]
    assert result["status"] == "abstained"
