"""Contract tests for gm-evaluate's freshness-aware verify prerequisite."""
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EVALUATE = REPO_ROOT / "skills" / "core" / "gm-evaluate" / "SKILL.md"


def _resume_check() -> str:
    text = EVALUATE.read_text(encoding="utf-8")
    return text.split("## Resume Check", 1)[1].split(
        "## Resolve `godot` binary", 1
    )[0]


def test_resume_check_defines_a_verify_freshness_boundary():
    resume = _resume_check()

    assert "**latest state-changing event**" in resume
    assert "whose `role` is `fixgap` unless it is\n  an evaluator-owned handoff" in resume
    assert "A bare `fixgap` event" in resume
    assert "**fresh successful verify**" in resume
    assert "appears later in file order" in resume
    assert "appends a verify event only on PASS" in resume
    assert "An older verify anywhere else in the history does not" in resume


def test_resume_check_pins_fresh_and_stale_event_sequences():
    resume = _resume_check()

    expected_rows = {
        "| `build → verify` | proceed |",
        "| `verify → build` | STOP: run `/gm-verify` |",
        "| `build → verify → fixgap` | STOP: run `/gm-verify` |",
        "| `build → verify → fixgap → verify` | proceed |",
    }

    for row in expected_rows:
        assert row in resume


def test_evaluator_owned_handoff_requires_freshness_and_survives_reverify():
    resume = _resume_check()

    handoff_definition = resume.index("**evaluator-owned handoff**")
    other_outcome = resume.index("but is not an\n  evaluator-owned handoff")
    freshness = resume.index("**latest state-changing event**")
    freshness_gate = resume.index("If there is no fresh successful verify")
    handoff_branch = resume.index("If a pending evaluator handoff exists")
    repeated_evaluate = resume.index(
        'If the **last event** has `role == "evaluate"`'
    )

    assert handoff_definition < other_outcome < freshness
    assert freshness < freshness_gate < handoff_branch < repeated_evaluate
    assert "**pending evaluator handoff**" in resume
    assert "appears after the latest state-changing event" in resume
    assert "not followed\n  by any event with `role == \"evaluate\"`" in resume
    assert "A verify event appended after the\n  handoff does not consume it" in resume

    expected_rows = {
        "| `build → verify → evaluate → fixgap(handoff=evaluator_owned_e2e) "
        "→ evaluate` | proceed through the handoff branch |",
        "| `build → verify → evaluate → fixgap → "
        "fixgap(handoff=evaluator_owned_e2e) → evaluate` | STOP: run "
        "`/gm-verify` |",
        "| `build → verify → evaluate → fixgap → "
        "fixgap(handoff=evaluator_owned_e2e) → verify → evaluate` | proceed "
        "through the handoff branch |",
        "| `build → verify → evaluate → fixgap(handoff=evaluator_owned_e2e) "
        "→ evaluate → evaluate` | STOP: evaluate already ran |",
    }

    for row in expected_rows:
        assert row in resume
