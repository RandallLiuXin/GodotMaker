"""Contract tests for gm-fixgap's pending verify feedback resume gate."""

import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
GM_FIXGAP = REPO_ROOT / "skills" / "core" / "gm-fixgap" / "SKILL.md"


def _write_resume_state(
    project: Path,
    *,
    fixgap_ts: str,
    verify_report: dict[str, str] | None,
) -> None:
    godotmaker = project / ".godotmaker"
    godotmaker.mkdir()
    (godotmaker / "stage.jsonl").write_text(
        json.dumps({"role": "evaluate", "ts": "2026-10-22T09:00:00Z"})
        + "\n"
        + json.dumps({"role": "fixgap", "ts": fixgap_ts})
        + "\n",
        encoding="utf-8",
    )
    (godotmaker / "evaluation.json").write_text(
        json.dumps({"result": "reject"}),
        encoding="utf-8",
    )
    if verify_report is not None:
        (godotmaker / "verify_report.json").write_text(
            json.dumps(verify_report),
            encoding="utf-8",
        )


def _documented_resume_decision(project: Path) -> str:
    """Reference implementation of the Markdown resume-check contract."""
    events = [
        json.loads(line)
        for line in (project / ".godotmaker" / "stage.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    report_path = project / ".godotmaker" / "verify_report.json"
    report = (
        json.loads(report_path.read_text(encoding="utf-8"))
        if report_path.exists()
        else None
    )
    latest_fixgap = next(
        (event for event in reversed(events) if event["role"] == "fixgap"),
        None,
    )
    pending_verify_feedback = (
        report is not None
        and report["result"] == "fail"
        and (latest_fixgap is None or report["ts"] > latest_fixgap["ts"])
    )

    if pending_verify_feedback:
        return "proceed"
    if events[-1]["role"] == "fixgap" and not (project / "GAP.md").exists():
        return "stop"
    return "proceed"


def test_fresh_failed_verify_report_overrides_completed_fixgap_stop(tmp_path: Path):
    _write_resume_state(
        tmp_path,
        fixgap_ts="2026-10-22T10:00:00Z",
        verify_report={"result": "fail", "ts": "2026-10-22T10:01:00Z"},
    )

    assert not (tmp_path / "GAP.md").exists()
    assert _documented_resume_decision(tmp_path) == "proceed"


@pytest.mark.parametrize(
    "verify_report",
    [
        pytest.param(
            {"result": "fail", "ts": "2026-10-22T09:59:00Z"},
            id="stale-fail",
        ),
        pytest.param(
            {"result": "pass", "ts": "2026-10-22T10:01:00Z"},
            id="fresh-pass",
        ),
        pytest.param(None, id="missing-report"),
    ],
)
def test_non_pending_verify_report_keeps_completed_fixgap_stop(
    tmp_path: Path,
    verify_report: dict[str, str] | None,
):
    _write_resume_state(
        tmp_path,
        fixgap_ts="2026-10-22T10:00:00Z",
        verify_report=verify_report,
    )

    assert not (tmp_path / "GAP.md").exists()
    assert _documented_resume_decision(tmp_path) == "stop"


def test_pending_feedback_gate_precedes_completed_fixgap_stop():
    text = GM_FIXGAP.read_text(encoding="utf-8")

    assert "Define **pending verify feedback** as:" in text
    assert 'Its top-level `result` is `"fail"`.' in text
    assert (
        'Its `ts` is later than the latest `role == "fixgap"` event in '
        "`stage.jsonl`, or there is no prior fixgap event."
    ) in text
    assert (
        "If pending verify feedback exists → proceed, even if the last event is "
        "`fixgap` and `GAP.md` is not at project root."
    ) in text

    pending_definition = text.index("Define **pending verify feedback** as:")
    pending_override = text.index("If pending verify feedback exists → proceed")
    completed_stop = text.index("Fixgap already completed for the latest evaluation")
    step_one = text.index("### Step 1 —")

    assert pending_definition < pending_override < completed_stop < step_one
