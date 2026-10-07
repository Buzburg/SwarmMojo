"""Adapted playbooks retain source attribution and remain compact, untrusted text."""
import hashlib
import json
from pathlib import Path

import pytest

from app.harness import prepare_request

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "config/skill_sources.json").read_text(encoding="utf-8"))
UPSTREAM_HASHES = {
    "agency-code-reviewer": "7509fcc3ea1dda46511b2801996305bf3d4a125576f9655ff0b63df25602f446",
    "agency-software-architect": "b85121691776147bacde26673e68fbbacd6a7f0816d1ca8e203c264d25ce1d30",
    "agency-technical-writer": "bf5c809977e10904b988ab8b218853ce8dfa38b2cbd89a7d2cfadba44ac25761",
}


def test_adapted_playbooks_keep_distinct_upstream_provenance_and_local_hashes():
    assert len(MANIFEST["commit"]) == 40
    assert MANIFEST["license"] == "MIT"
    assert MANIFEST["execution_allowed"] is False
    license_bytes = (ROOT / MANIFEST["license_path"]).read_bytes()
    assert hashlib.sha256(license_bytes).hexdigest() == MANIFEST["license_sha256"]
    assert {skill["name"] for skill in MANIFEST["skills"]} == set(UPSTREAM_HASHES)
    assert sum(skill["bytes"] for skill in MANIFEST["skills"]) <= 4096
    for skill in MANIFEST["skills"]:
        path = ROOT / skill["path"]
        assert path.parent == ROOT / "skills"
        assert path.name == skill["name"] + ".md"
        raw = path.read_bytes()
        assert len(raw) == skill["bytes"] <= 1600
        assert hashlib.sha256(raw).hexdigest() == skill["sha256"]
        assert skill["upstream_sha256"] == UPSTREAM_HASHES[skill["name"]]
        assert skill["sha256"] != skill["upstream_sha256"]
        assert skill["bytes"] < skill["upstream_bytes"]
        assert "not an exact copy" in skill["adaptation"]
        assert b"Local adaptation of Agency Agents, under MIT" in raw
        assert MANIFEST["commit"] in skill["source_url"]


@pytest.mark.parametrize("skill", MANIFEST["skills"], ids=lambda value: value["name"])
def test_adapted_role_is_readable_but_cannot_supply_evidence_or_permission(tmp_path, skill):
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


def test_adapted_role_still_reports_small_budget_truncation(tmp_path):
    result = prepare_request({"goal": "Review documentation", "options": {
        "review": "Review documentation", "wait": "Wait for observations"},
        "skills": ["agency-technical-writer"], "max_context_chars": 512},
        db_path=tmp_path / "absent.db", skills_dir=ROOT / "skills")
    assert result["context"]["skills"][0]["truncated"]
    assert result["context"]["coverage"]["supplied_text_chars"] == 512
    assert "skills://agency-technical-writer" in result["context"]["coverage"]["truncated_sources"]
    assert result["status"] == "abstained"


def test_all_compact_playbooks_fit_default_context_budget(tmp_path):
    result = prepare_request({"goal": "Review a design and its documentation", "options": {
        "review": "Review the change", "wait": "Wait for evidence"},
        "skills": [skill["name"] for skill in MANIFEST["skills"]]},
        db_path=tmp_path / "absent.db", skills_dir=ROOT / "skills")
    assert len(result["context"]["skills"]) == 3
    assert not result["context"]["coverage"]["truncated"]
    assert result["status"] == "abstained"
    assert not result["execution_allowed"]
