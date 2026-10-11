"""Tests for Meta-Agent Comparison documentation, author configuration, and native Mojo kernels."""
import subprocess
import sys
from pathlib import Path


def test_meta_agent_comparison_document_exists():
    root = Path(__file__).resolve().parent.parent
    doc_path = root / "docs" / "meta_agent_comparison.md"
    assert doc_path.exists(), "docs/meta_agent_comparison.md must exist"

    content = doc_path.read_text(encoding="utf-8")
    assert "Swarmojo" in content or "SwarmMojo" in content
    assert "Conventional Cloud Orchestrators" in content
    assert "Generic CLI Seat Wrappers" in content
    assert "buzburgai@gmail.com" in content
    assert "Buzburg AI" in content
    assert "fastgate_core.mojo" in content
    assert "Titans DeltaNet" in content
    assert "StateFresh OCC" in content
    assert "mojo-drift" in content


def test_swarmmojo_compare_cli():
    root = Path(__file__).resolve().parent.parent
    cmd = [sys.executable, str(root / "swarmmojo.py"), "compare"]
    result = subprocess.run(cmd, cwd=str(root), capture_output=True, text=False)
    assert result.returncode == 0
    output = result.stdout.decode("utf-8", errors="replace")
    assert "Swarmojo (Buzburg AI)" in output or "SwarmMojo (Buzburg AI)" in output
    assert "buzburgai@gmail.com" in output


def test_native_mojo_kernels_exist():
    root = Path(__file__).resolve().parent.parent
    mojo_dir = root / "app_mojo"

    expected_kernels = [
        ("writer_core.mojo", "SlopFilterEngine"),
        ("prose_metric.mojo", "calculate_rhythm_metrics"),
        ("design_core.mojo", "calculate_contrast_ratio"),
        ("studio_core.mojo", "compute_safe_zones"),
        ("drift_core.mojo", "calculate_angular_drift"),
        ("symdex_core.mojo", "embed_symbol"),
        ("titans_core.mojo", "test_time_memorize_step"),
        ("fastgate_core.mojo", "route_tools"),
        ("workflow_core.mojo", "ConstitutionalGovernor"),
        ("assistant_core.mojo", "calculate_pcm16_energy"),
        ("coding_core.mojo", "find_unique_substring"),
        ("statefresh_core.mojo", "validate_and_commit_cas"),
        ("workflowproof_core.mojo", "verify_step_transition"),
        ("triad_core.mojo", "dominates"),
        ("localdoc_core.mojo", "score_bm25_term"),
        ("antibody_core.mojo", "hash_error_signature"),
        ("once_core.mojo", "hash_command_key"),
        ("screenhand_core.mojo", "clip_coordinate_to_bounds"),
    ]

    for fname, expected_sym in expected_kernels:
        fpath = mojo_dir / fname
        assert fpath.exists(), f"Kernel {fname} must exist in app_mojo/"
        content = fpath.read_text(encoding="utf-8")
        assert len(content) > 100
        assert expected_sym in content, f"{expected_sym} must be present in {fname}"


def test_pyproject_author():
    root = Path(__file__).resolve().parent.parent
    pyproject = root / "pyproject.toml"
    assert pyproject.exists()
    content = pyproject.read_text(encoding="utf-8")
    assert "buzburgai@gmail.com" in content
    assert "Buzburg AI" in content


def test_readme_author_and_comparison():
    root = Path(__file__).resolve().parent.parent
    readme = root / "README.md"
    assert readme.exists()
    content = readme.read_text(encoding="utf-8")
    assert "buzburgai@gmail.com" in content
    assert "Buzburg AI" in content
    assert "Meta-Agent Architecture Comparison: Swarmojo vs Conventional Frameworks" in content or "Meta-Agent Architecture Comparison: SwarmMojo vs Conventional Frameworks" in content
    assert "docs/meta_agent_comparison.md" in content
