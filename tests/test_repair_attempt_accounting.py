"""Contract tests for evidence-based repair accounting in build stages."""
from pathlib import Path
import json


REPO_ROOT = Path(__file__).resolve().parents[1]
ACCOUNTING = REPO_ROOT / "skills" / "core" / "_shared" / "repair-attempt-accounting.md"
MANIFEST = REPO_ROOT / "skills" / "core" / "_shared" / "manifest.json"
BUILD = REPO_ROOT / "skills" / "core" / "gm-build" / "SKILL.md"
FIXGAP = REPO_ROOT / "skills" / "core" / "gm-fixgap" / "SKILL.md"
WORKER = REPO_ROOT / "agents" / "worker.md"
CODEX_MAPPING = REPO_ROOT / "agent-runtimes" / "codex" / "references" / "runtime-mapping.md"


def _apply(outcomes: list[str]) -> dict[str, int | bool]:
    """Exercise the counters specified by the shared accounting contract."""
    state: dict[str, int | bool] = {
        "dispatch_count": 0,
        "repair_attempt_count": 0,
        "no_progress_count": 0,
        "orchestration_incident": False,
        "failed": False,
    }
    for outcome in outcomes:
        state["dispatch_count"] += 1
        if outcome == "effective_repair":
            state["repair_attempt_count"] += 1
            state["no_progress_count"] = 0
        elif outcome == "verified_success":
            state["no_progress_count"] = 0
        else:
            state["no_progress_count"] += 1
            if state["no_progress_count"] >= 3:
                state["orchestration_incident"] = True
        state["failed"] = state["repair_attempt_count"] == 5
    return state


def test_five_analysis_only_handoffs_do_not_fail_the_business_task():
    state = _apply(["incomplete_handoff"] * 5)

    assert state["dispatch_count"] == 5
    assert state["repair_attempt_count"] == 0
    assert state["no_progress_count"] == 5
    assert state["orchestration_incident"] is True
    assert state["failed"] is False


def test_five_evidence_complete_production_repairs_reach_the_existing_limit():
    state = _apply(["effective_repair"] * 5)

    assert state["dispatch_count"] == 5
    assert state["repair_attempt_count"] == 5
    assert state["no_progress_count"] == 0
    assert state["failed"] is True


def test_contract_excludes_incomplete_and_tooling_outcomes_from_repair_budget():
    accounting = ACCOUNTING.read_text(encoding="utf-8")

    for required in (
        "dispatch_count",
        "repair_attempt_count",
        "no_progress_count",
        "relevant production implementation diff",
        "focused verification",
        "failure fingerprint",
        "test discovery/parser",
        "environment/network/permission failure",
        "At 3 consecutive no-progress outcomes",
        "repair_attempt_count == 5",
        "do not mark it `failed`",
    ):
        assert required in accounting


def test_both_stages_share_the_same_source_contract_and_worker_evidence():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["files"]["repair-attempt-accounting.md"] == [
        "gm-build",
        "gm-fixgap",
    ]

    for stage in (BUILD, FIXGAP):
        assert "references/repair-attempt-accounting.md" in stage.read_text(
            encoding="utf-8"
        )

    worker = WORKER.read_text(encoding="utf-8")
    for field in (
        "### Repair Attempt Evidence",
        "Production diff:",
        "Focused verification:",
        "Failure fingerprint:",
        "Handoff condition:",
        "Suggested classification:",
    ):
        assert field in worker


def test_codex_mapping_preserves_evidence_based_counting():
    mapping = CODEX_MAPPING.read_text(encoding="utf-8")

    assert "`classify_repair_attempt`" in mapping
    assert "Repair Attempt Evidence" in mapping
    assert "dispatch_count" in mapping
    assert "repair_attempt_count" in mapping
