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
    assert "whose `role` is `build` or `fixgap`" in resume
    assert "an evaluator-owned handoff are state-changing" in resume
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


def test_evaluator_owned_handoff_requires_its_own_fresh_verify():
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
    assert "latest state-changing\n  event is itself an evaluator-owned handoff" in resume
    assert "no later event has\n  `role == \"evaluate\"`" in resume
    assert "A verify event appended after the handoff does not\n  consume it" in resume
    assert "which is not included as a trailing event in the history" in resume

    expected_rows = {
        "| `build → verify → evaluate → fixgap(handoff=evaluator_owned_e2e)` "
        "| STOP: run `/gm-verify` |",
        "| `build → verify → evaluate → fixgap(handoff=evaluator_owned_e2e) "
        "→ verify` | proceed through the handoff branch |",
        "| `build → verify → evaluate → fixgap → "
        "fixgap(handoff=evaluator_owned_e2e)` | STOP: run "
        "`/gm-verify` |",
        "| `build → verify → evaluate → fixgap → "
        "fixgap(handoff=evaluator_owned_e2e) → verify` | proceed "
        "through the handoff branch |",
        "| `build → verify → evaluate → fixgap(handoff=evaluator_owned_e2e) "
        "→ verify → evaluate` | STOP: evaluate already ran |",
    }

    for row in expected_rows:
        assert row in resume
