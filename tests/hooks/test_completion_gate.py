"""Tests for side-effect-free stage completion validation."""
import json
import os
import shutil
import sys
import tempfile

import pytest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOOKS_DIR = os.path.join(REPO_ROOT, "hooks")
SCHEMA_SRC = os.path.join(REPO_ROOT, "config", "stage_schemas.json")
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

from completion_gate import _TAG_ARCHIVE_FILES, get_completion_failure  # noqa: E402


@pytest.fixture
def project_dir():
    original = os.getcwd()
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        os.makedirs(".godotmaker", exist_ok=True)
        shutil.copy2(SCHEMA_SRC, ".godotmaker/stage_schemas.json")
        yield tmpdir
        os.chdir(original)


def failure(role: str, **fields):
    return get_completion_failure({"role": role, "ts": "2026-01-01T00:00:00Z", **fields})


def test_schema_files_are_checked(project_dir):
    result = failure("gdd")
    assert result is not None
    assert "GDD.md" in result["reason"]
    assert "PLAN.md" in result["reason"]


def test_missing_schema_fails_closed(project_dir):
    os.remove(".godotmaker/stage_schemas.json")
    result = failure("asset")
    assert result is not None
    assert "stage_schemas.json is missing or invalid" in result["reason"]


def test_build_programmatic_check_blocks_pending_plan(project_dir):
    with open("PLAN.md", "w", encoding="utf-8") as handle:
        handle.write("| Task | Status |\n| movement | pending |\n")
    result = failure("build")
    assert result is not None
    assert "1 pending" in result["reason"]


def test_fixgap_handoff_preserves_open_gap(project_dir):
    with open("GAP.md", "w", encoding="utf-8") as handle:
        handle.write("# Evaluator-owned gap\n")
    assert failure("fixgap", outcome="handoff", next_role="evaluate") is None
    assert "GAP.md" in failure("fixgap")["reason"]


def test_evaluate_checks_playable_unit_contract(project_dir):
    with open(".godotmaker/evaluation.json", "w", encoding="utf-8") as handle:
        json.dump({"result": "approve"}, handle)
    result = failure("evaluate")
    assert result is not None
    assert "Playable Unit evaluation contract failed" in result["reason"]


def test_complete_sealed_tag_passes_finalize_gate(project_dir):
    tag = "v0.1.0"
    with open("PLAN.md", "w", encoding="utf-8") as handle:
        handle.write(f"# Plan\n\n**Tag:** {tag}\n")
    archive = os.path.join("docs", "tags", tag)
    os.makedirs(os.path.join(archive, "evidence"), exist_ok=True)
    for name in _TAG_ARCHIVE_FILES:
        open(os.path.join(archive, name), "w").close()
    with open(os.path.join(archive, "evidence", "manifest.json"), "w", encoding="utf-8") as handle:
        json.dump({"sealed": True}, handle)
    with open(os.path.join("docs", "tags", "README.md"), "w", encoding="utf-8") as handle:
        handle.write(f"| [{tag}]({tag}/) | complete |\n")
    with open(".godotmaker/final_report.json", "w", encoding="utf-8") as handle:
        json.dump({"status": "tag_sealed"}, handle)

    assert failure("finalize", tag=tag) is None


@pytest.mark.parametrize(
    "manifest,parent_index,expected",
    [
        (None, "| [v0.1.0](v0.1.0/) | complete |\n", "manifest.json not found"),
        ({"sealed": False}, "| [v0.1.0](v0.1.0/) | complete |\n", '"sealed": true'),
        ({"sealed": True}, None, "docs/tags/README.md not found"),
        ({"sealed": True}, "| [v0.0.9](v0.0.9/) | complete |\n", "does not list v0.1.0"),
    ],
)
def test_incomplete_tag_archive_is_rejected(
    project_dir,
    manifest,
    parent_index,
    expected,
):
    tag = "v0.1.0"
    with open("PLAN.md", "w", encoding="utf-8") as handle:
        handle.write(f"# Plan\n\n**Tag:** {tag}\n")
    archive = os.path.join("docs", "tags", tag)
    os.makedirs(os.path.join(archive, "evidence"), exist_ok=True)
    for name in _TAG_ARCHIVE_FILES:
        open(os.path.join(archive, name), "w").close()
    if manifest is not None:
        with open(
            os.path.join(archive, "evidence", "manifest.json"),
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(manifest, handle)
    if parent_index is not None:
        with open("docs/tags/README.md", "w", encoding="utf-8") as handle:
            handle.write(parent_index)
    with open(".godotmaker/final_report.json", "w", encoding="utf-8") as handle:
        json.dump({"status": "tag_sealed"}, handle)

    result = failure("finalize", tag=tag)
    assert result is not None
    assert expected in result["reason"]
