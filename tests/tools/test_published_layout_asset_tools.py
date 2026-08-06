"""The published project exposes only the direct asset-registration CLI."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import publish  # noqa: E402


@pytest.fixture(scope="module")
def published(tmp_path_factory) -> Path:
    target = tmp_path_factory.mktemp("published-project")
    publish.publish_directory(ROOT / "tools", target / "tools", "tools/")
    publish.publish_skills(ROOT, target / ".claude" / "skills", agent="claude-code")
    publish.publish_shared_refs(ROOT, target / ".claude" / "skills", agent="claude-code")
    publish.publish_directory(ROOT / "templates", target / ".claude" / "templates", "templates/")
    publish.publish_asset_runtime(ROOT, target)
    return target


def test_direct_result_registration_cli_runs_in_published_layout(published: Path):
    completed = subprocess.run(
        [sys.executable, str(published / "tools" / "asset_result_registration.py"), "--help"],
        cwd=published,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_retired_registration_tools_are_not_published(published: Path):
    retired = (
        "asset_stable_entry.py",
        "asset_generation_index.py",
        "asset_runtime_resolver.py",
        "asset_action_entry_draft.py",
        "asset_assets_md_update.py",
    )
    assert all(not (published / "tools" / name).exists() for name in retired)


def test_published_asset_contract_text_has_no_retired_handoff_instruction(published: Path):
    """Published instructions must route generic results directly to ASSETS.md."""
    retired_instruction = re.compile(
        r"\b(?:producer adapter|stable[ -]entry|entry draft|anchor entry)\b",
        re.IGNORECASE,
    )
    asset_skill_names = [
        path.name for path in (ROOT / "skills" / "assets").iterdir()
        if path.is_dir() and not path.name.startswith("_")
    ]
    reviewer_dispatch = (
        published / ".claude" / "skills" / "gm-build" / "references" / "reviewer-dispatch.md"
    )
    text_paths = [
        *(published / ".claude" / "skills" / name / "SKILL.md" for name in asset_skill_names),
        *(
            (published / ".claude" / "skills").glob("*/references/*dispatch.md")
        ),
        *(published / ".claude" / "templates").rglob("*.md"),
    ]
    for path in text_paths:
        text = path.read_text(encoding="utf-8")
        assert retired_instruction.search(text) is None, path

    reviewer_dispatch = reviewer_dispatch.read_text(encoding="utf-8")
    assert "asset_result_registration.py --assets-md ASSETS.md --tag <tag>" in reviewer_dispatch
    assert "godot_artifact.type" in reviewer_dispatch
    assert "godot_artifact.path" in reviewer_dispatch
    for retired_field in (
        "Stable entry `godot_artifact`",
        "source_layout.type values",
        "frame_count,\nand the",
        "support\nmetadata paths used",
    ):
        assert retired_field not in reviewer_dispatch


def test_release_notes_do_not_describe_retired_asset_handoff_as_current():
    """Release notes may contrast the retired contract, never prescribe it."""
    release_notes = (ROOT / "docs" / "update" / "next.md").read_text(encoding="utf-8")
    # This single contrast sentence is intentionally allowed: it describes the
    # current ASSETS.md catalog as replacing the old layer.
    current_contract = release_notes.replace(
        "separate stable-entry or manifest layer", ""
    ).lower()
    for retired_behavior in (
        "stable entry",
        "stable entries",
        "entry builder",
        "pointer-only bundle manifest",
        ".godotmaker/asset-generation/manifest.json",
    ):
        assert retired_behavior not in current_contract
