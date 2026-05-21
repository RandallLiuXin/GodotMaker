"""Tests for the playable-unit planning and evaluation contract."""
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def test_roadmap_template_defines_playable_unit_tag_contract():
    roadmap = _read("templates/ROADMAP.md")

    assert "Every tag is a minimal playable unit" in roadmap
    assert "player-experienced game content" in roadmap
    assert "reachable through play" in roadmap


def test_gdd_collects_playable_unit_candidates_without_ordering_buckets():
    gdd = _read("templates/GDD.md")

    assert "## 10. Scope & Playable Units" in gdd
    assert "### Playable Unit Candidates" in gdd
    assert "Player Experience" in gdd
    assert "Mechanics Included" in gdd
    assert "Completion / Fail / Exit" in gdd


def test_plan_template_defines_playable_unit_contract():
    plan = _read("templates/PLAN.md")

    assert "## Playable Unit" in plan
    for token in [
        "Player experience",
        "Unit outcome",
        "Player operation / content",
        "Expected effect",
        "Required visible content",
        "Review focus",
    ]:
        assert token in plan


def test_decomposer_must_generate_playable_unit():
    decomposer = _read("agents/decomposer.md")

    assert "Every tag's mechanics MUST combine into one playable unit" in decomposer
    assert "player operation or content, expected effect, required visible content" in decomposer
    assert "ROADMAP.md needs a playable-unit tag" in decomposer


def test_gdd_gate_checks_playable_unit():
    gdd = _read("skills/core/gm-gdd/SKILL.md")

    assert "Every tag is a minimal playable unit" in gdd
    assert "Playable Unit section is populated" in gdd
    assert "Playable Unit scene check" in gdd


def test_build_and_reviewer_check_playable_unit_authenticity():
    build = _read("skills/core/gm-build/SKILL.md")
    reviewer = _read("agents/reviewer.md")

    assert "**Build the Playable Unit.**" in build
    assert "Ask the reviewer to check gameplay authenticity" in build
    assert "### Gameplay Authenticity Review" in reviewer
    assert "Running the game or test suite" in reviewer
    assert "Tests avoid gameplay-bypassing shortcuts" in reviewer


def test_evaluate_requires_runtime_playable_unit_proof():
    evaluate = _read("skills/core/gm-evaluate/SKILL.md")
    schema = _read("config/stage_schemas.json")
    fixgap = _read("skills/core/gm-fixgap/SKILL.md")

    assert "Playable Unit coverage passes" in evaluate
    assert "Static code evidence is not enough" in evaluate
    assert "Key `playable_unit.rows` by mechanic id" in evaluate
    assert "write one `playable_unit.rows` entry for" in evaluate
    assert '"playable_unit"' in evaluate
    assert "completion_fail_or_exit_reached" in evaluate
    assert "every Playable Unit table row has passing E2E coverage" in evaluate
    assert '"evaluation_playable_unit"' in schema
    assert "playable_unit.rows.*" in fixgap
