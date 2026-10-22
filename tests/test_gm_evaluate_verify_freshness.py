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
    assert "last event in\n  file order whose `role` is `build` or `fixgap`" in resume
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


def test_evaluator_owned_handoff_remains_the_only_fixgap_bypass():
    resume = _resume_check()

    handoff = resume.index('outcome == "handoff"')
    other_outcome = resume.index("Any other `fixgap` event carrying `outcome`")
    freshness = resume.index("**latest state-changing event**")

    assert handoff < other_outcome < freshness
    assert (
        "the only `fixgap` event that does not require\n  a later verify event"
        in resume
    )
    assert (
        "| `build → verify → fixgap(outcome=handoff, next_role=evaluate, "
        "reason=evaluator_owned_e2e)` | proceed through the handoff branch |"
    ) in resume
