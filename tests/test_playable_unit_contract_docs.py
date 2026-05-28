"""Tests for the playable-unit planning and evaluation contract."""
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def test_roadmap_template_defines_playable_unit_tag_contract():
    roadmap = _read("templates/ROADMAP.md")

    assert "Every tag is a minimal playable unit" in roadmap
    assert "Expected player experience" in roadmap
    assert "Features / mechanics" in roadmap
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
        "player-facing state, feedback, and presentation",
        "Review focus",
    ]:
        assert token in plan


def test_decomposer_must_generate_playable_unit():
    decomposer = _read("agents/decomposer.md")

    assert "Every tag's mechanics MUST combine into one playable unit" in decomposer
    assert "player-facing state, feedback, and presentation" in decomposer
    assert "ROADMAP.md needs a playable-unit tag" in decomposer


def test_gdd_gate_checks_playable_unit():
    gdd = _read("skills/core/gm-gdd/SKILL.md")

    assert "Every tag is a minimal playable unit" in gdd
    assert "Playable Unit section is populated" in gdd
    assert "completion, fail, or exit state" in gdd
    assert "player-facing state, feedback, and presentation" in gdd
    assert "Playable Unit scene check" in gdd


def test_build_and_reviewer_check_playable_unit_authenticity():
    build = _read("skills/core/gm-build/SKILL.md")
    dispatch = _read("skills/core/_shared/worker-dispatch.md")
    plan = _read("templates/PLAN.md")
    reviewer = _read("agents/reviewer.md")
    worker = _read("agents/worker.md")

    assert "**Build the Playable Unit.**" in build
    assert "Each worker implements ONE game mechanic function + its tests" in build
    assert "ONE game mechanic function + its tests" in dispatch
    assert "Minimum 2 unit tests per changed system" in dispatch
    assert "Minimum 2 unit tests per changed system" in worker
    assert "Game Mechanic Function" in dispatch
    assert "Affected Systems / Scenes / UI" in plan
    assert "Player-Facing Outcome" in plan
    assert "Ask the reviewer to check gameplay authenticity" in build
    assert "### Gameplay Authenticity Review" in reviewer
    assert "Running the game or test suite" in reviewer
    assert "Tests avoid gameplay-bypassing shortcuts" in reviewer


def test_visual_asset_contract_flows_through_build_and_evaluate():
    plan = _read("templates/PLAN.md")
    scenes = _read("templates/SCENES.md")
    assets = _read("templates/ASSETS.md")
    decomposer = _read("agents/decomposer.md")
    dispatch = _read("skills/core/_shared/worker-dispatch.md")
    build = _read("skills/core/gm-build/SKILL.md")
    evaluate = _read("skills/core/gm-evaluate/SKILL.md")
    fixgap = _read("skills/core/gm-fixgap/SKILL.md")

    assert "Runtime Asset Assignments" in plan
    assert "Asset bindings" in scenes
    assert "Visual Asset Contract" in assets
    assert "Runtime Asset Assignments" in decomposer
    assert "Visual Asset Contract` section" in build
    assert "PLAN.md Runtime Asset Assignments" in dispatch
    assert "SCENES.md Asset" in dispatch
    assert "ASSETS.md Visual Asset Contract" in dispatch
    assert "Visual binding preflight" in evaluate
    assert "captures[]" in evaluate
    assert "Visual Verification` section" in fixgap


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
