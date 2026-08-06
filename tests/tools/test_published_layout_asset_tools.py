"""The published project exposes only the direct asset-registration CLI."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import publish  # noqa: E402


@pytest.fixture(scope="module")
def published(tmp_path_factory) -> Path:
    target = tmp_path_factory.mktemp("published-project")
    publish.publish_directory(ROOT / "tools", target / "tools", "tools/")
    publish.publish_skills(ROOT, target / ".claude" / "skills", agent="claude-code")
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
