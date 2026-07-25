"""Shared fixtures for the asset skill test suites.

The Godot integration tests need a real engine binary. CI installs only pytest
and pillow, so they skip there and run wherever a Godot 4.4+ build is reachable.
``GODOT_PATH`` is the environment variable the rest of this ecosystem already
uses (``tools/publish.py`` passes it to the Godot MCP server), so it is honoured
here rather than inventing a second name.
"""
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "skills" / "assets" / "_shared"
for _directory in (SHARED_DIR, REPO_ROOT / "tools"):
    if str(_directory) not in sys.path:
        sys.path.insert(0, str(_directory))

from asset_validation import find_godot  # noqa: E402

PROJECT_GODOT = """config_version=5

[application]

config/name="validation-fixture"
config/features=PackedStringArray("4.4")

[debug]

file_logging/enable_file_logging=false
"""


@pytest.fixture(scope="session")
def godot_bin() -> str:
    """An absolute path to a Godot binary, or skip the test."""
    resolved = find_godot(os.environ.get("GODOT_PATH"))
    if not resolved:
        pytest.skip(
            "no Godot binary found; set GODOT_PATH or put godot on PATH to run "
            "the L3 integration tests"
        )
    return resolved


@pytest.fixture
def godot_project(tmp_path: Path) -> Path:
    """A minimal, importable Godot project rooted in a temp directory."""
    root = tmp_path / "game"
    root.mkdir()
    (root / "project.godot").write_text(PROJECT_GODOT, encoding="utf-8")
    return root
