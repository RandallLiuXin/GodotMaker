from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GM_BUILD = REPO_ROOT / "skills" / "core" / "gm-build" / "SKILL.md"


def test_completed_build_resume_check_does_not_hide_newer_verify_failure():
    text = GM_BUILD.read_text(encoding="utf-8")
    assert "Define **pending verify feedback** as:" in text
    assert "If pending verify feedback exists" in text
    assert 'Its top-level `result` is `"fail"`.' in text
    assert (
        "Its `ts` is later than the latest `role == \"build\"` event in `stage.jsonl`, "
        "or there is no prior build event."
    ) in text
    assert (
        'If the **last event** has `role == "build"` AND all PLAN.md tasks are `verified`'
    ) in text

    pending_definition = text.index("Define **pending verify feedback** as:")
    gate_order = text.index("Apply the resume gates in this order:")
    pending_branch = text.index("If pending verify feedback exists")
    completed_stop = text.index('Build already completed for the current tag')
    step_zero = text.index("### Step 0")
    step_zero_condition = text.index(
        "Run this step before Step 1 only if pending verify feedback exists."
    )

    assert pending_definition < gate_order < pending_branch < completed_stop < step_zero
    assert step_zero < step_zero_condition
