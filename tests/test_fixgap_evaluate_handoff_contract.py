"""Contract tests for the narrow FixGap → Evaluate routing handoff."""
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXGAP = REPO_ROOT / "skills" / "core" / "gm-fixgap" / "SKILL.md"
EVALUATE = REPO_ROOT / "skills" / "core" / "gm-evaluate" / "SKILL.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_fixgap_handoff_uses_the_fixed_stage_event_contract():
    fixgap = _read(FIXGAP)

    assert "--outcome=handoff" in fixgap
    assert "--next_role=evaluate" in fixgap
    assert "--reason=evaluator_owned_e2e" in fixgap
    assert "do not archive GAP.md" in fixgap
    assert "non-`verified`" in fixgap


def test_evaluate_consumes_only_the_evaluator_owned_handoff():
    evaluate = _read(EVALUATE)

    assert 'outcome == "handoff"' in evaluate
    assert 'next_role == "evaluate"' in evaluate
    assert 'reason == "evaluator_owned_e2e"' in evaluate
    assert "repair the `e2e/` scenario/assertion/capture timing" in evaluate
    assert "Ask the user to run\n  `/gm-fixgap`." in evaluate
