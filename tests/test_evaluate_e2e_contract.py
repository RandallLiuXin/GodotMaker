"""Contract tests for gm-evaluate's canonical Python E2E output."""

import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EVALUATE_SKILL = REPO_ROOT / "skills" / "core" / "gm-evaluate" / "SKILL.md"
CHECK_PROJECT = REPO_ROOT / "tools" / "check_project.py"
SAMPLE_NAME = "test_v0_1_0_M1_jump.py"
SAMPLE_TEST = """\
def test_player_jump_changes_vertical_position():
    starting_height = 128
    height_after_jump = 96
    assert height_after_jump < starting_height
"""


def test_evaluator_requires_canonical_python_e2e_files():
    instructions = EVALUATE_SKILL.read_text(encoding="utf-8")

    assert "All evaluator-owned E2E tests are Python pytest modules" in instructions
    assert "Never create or update `.gd` E2E tests." in instructions
    assert "e2e/test_<tag_slug>_M<N>_<mechanic_slug>.py" in instructions
    assert "e2e/test_<tag_slug>_playable_unit_<slug>.py" in instructions
    assert "python -m pytest --collect-only e2e/ -q" in instructions
    assert not re.search(r"e2e/test_[^`\s]*\.gd", instructions)
    assert "(or `.py`)" not in instructions


def test_generated_sample_is_collected_by_pytest_and_project_checker(tmp_path: Path):
    e2e_dir = tmp_path / "e2e"
    e2e_dir.mkdir()
    (e2e_dir / "conftest.py").write_text(
        "# Canonical pytest E2E root.\n",
        encoding="utf-8",
    )
    sample = e2e_dir / SAMPLE_NAME
    sample.write_text(SAMPLE_TEST, encoding="utf-8")
    (tmp_path / "project.godot").write_text(
        "[editor_plugins]\n"
        'enabled=PackedStringArray("res://addons/godot_e2e/plugin.cfg")\n',
        encoding="utf-8",
    )

    collected = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", str(e2e_dir)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert collected.returncode == 0, collected.stdout + collected.stderr
    assert f"{SAMPLE_NAME}::test_player_jump_changes_vertical_position" in collected.stdout

    checked = subprocess.run(
        [sys.executable, str(CHECK_PROJECT), str(tmp_path), "--e2e"],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert f"Found 1 e2e test file(s): {SAMPLE_NAME}" in checked.stdout
