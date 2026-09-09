"""Focused tests for Worker-only failure diagnostics."""
import json
import os
import sys
from types import SimpleNamespace

import pytest

HOOKS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "hooks",
)
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

from log_subagent import handle_stop  # noqa: E402
from metrics.diagnostics import (  # noqa: E402
    LARGE_OUTPUT_THRESHOLD_BYTES,
    MAX_EVIDENCE_PATHS,
    MAX_OUTPUT_TAIL_CHARS,
    MAX_SUMMARY_CHARS,
    build_worker_error_event,
    record_worker_error,
)

from .helpers import read_metrics, write_current_role  # noqa: E402


def worker_report(status="FAILED", blocker="gdUnit4 v6 missing"):
    handoff = "none" if status == "DONE" else "tool_or_environment_error"
    classification = "verified_success" if status == "DONE" else "orchestration_failure"
    return (
        "## Report: M01 movement\n\n"
        f"### Status: {status}\n\n"
        "### Files Changed\n- src/s_movement.gd\n\n"
        "### Tests\n- Output: tests passed, exit code 0\n"
        "- Evidence: reports/unit.log\n\n"
        "### Build\n- Output: gdUnit exited with code 1\n"
        "- Evidence: .godotmaker/traces/build.log\n\n"
        "### Repair Attempt Evidence\n"
        f"- Handoff condition: {handoff}\n"
        f"- Suggested classification: {classification}\n\n"
        f"### Notes\n- Blocker: {blocker}\n\n"
        "### Memory Entry\nOld note in reports/old.log\n"
    )


@pytest.fixture(autouse=True)
def isolated_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_current_role("build")
    yield


def test_clean_worker_produces_no_error_event():
    event = build_worker_error_event(
        message=worker_report(status="DONE"),
        status="DONE",
        outcome_kind="terminal",
        agent_id="worker-1",
        stage="build",
    )
    assert event is None


def test_failed_worker_event_uses_only_worker_owned_sections():
    event = build_worker_error_event(
        message=worker_report(),
        status="FAILED",
        outcome_kind="terminal",
        agent_id="worker-1",
        run_id="run-1",
        trace_id="trace-1",
        stage="build",
    )

    assert event is not None
    assert event["role"] == "worker"
    assert event["task_id"] == "M01"
    assert event["error_type"] == "tool_or_environment_error"
    assert event["classification"] == "orchestration_failure"
    assert event["summary"] == "gdUnit4 v6 missing"
    assert event["exit_code"] == 1
    assert event["run_id"] == "run-1"
    assert event["trace_id"] == "trace-1"
    assert event["evidence_paths"] == [
        "reports/unit.log",
        ".godotmaker/traces/build.log",
    ]
    assert "reports/old.log" not in event["evidence_paths"]


@pytest.mark.parametrize(
    ("status", "outcome_kind", "expected"),
    [
        ("PARTIAL", "terminal", "tool_or_environment_error"),
        ("UNKNOWN", "rejected_attempt", "report_rejected"),
        ("UNKNOWN", "unverified", "tool_or_environment_error"),
    ],
)
def test_unsuccessful_worker_states_are_recorded(status, outcome_kind, expected):
    event = build_worker_error_event(
        message=worker_report(status=status),
        status=status,
        outcome_kind=outcome_kind,
        agent_id="worker-1",
        stage="build",
    )
    assert event is not None
    assert event["error_type"] == expected


def test_missing_optional_fields_remain_empty():
    message = (
        "## Report: M02 jump\n\n"
        "### Status: FAILED\n\n"
        "### Files Changed\n- none\n\n"
        "### Tests\n- no command output\n\n"
        "### Build\n- failed\n"
    )
    event = build_worker_error_event(
        message=message,
        status="FAILED",
        outcome_kind="terminal",
        agent_id="worker-2",
        stage="build",
    )
    assert event["classification"] == ""
    assert event["exit_code"] is None
    assert event["evidence_paths"] == []
    assert event["summary"] == "task failed"


def test_summary_and_evidence_are_bounded():
    paths = " ".join(f"reports/path-{index}.log" for index in range(8))
    message = worker_report(blocker="x" * 300).replace(
        "- Evidence: reports/unit.log",
        f"- Evidence: {paths}",
    )
    event = build_worker_error_event(
        message=message,
        status="FAILED",
        outcome_kind="terminal",
        agent_id="worker-1",
        stage="build",
    )
    assert len(event["summary"]) == MAX_SUMMARY_CHARS
    assert len(event["evidence_paths"]) == MAX_EVIDENCE_PATHS


def test_large_command_output_is_not_copied_into_event():
    raw_output = (
        "BEGIN_RAW_OUTPUT\n"
        + ("x" * (LARGE_OUTPUT_THRESHOLD_BYTES + 1000))
        + "\nFATAL_END"
    )
    message = worker_report().replace(
        "- Output: tests passed, exit code 0",
        f"- Output: {raw_output}",
    )
    event = build_worker_error_event(
        message=message,
        status="FAILED",
        outcome_kind="terminal",
        agent_id="worker-1",
        stage="build",
    )
    serialized = json.dumps(event)
    assert raw_output not in serialized
    assert "BEGIN_RAW_OUTPUT" not in event["output_tail"]
    assert "FATAL_END" in event["output_tail"]
    assert len(event["output_tail"]) == MAX_OUTPUT_TAIL_CHARS
    assert event["output_digest"].startswith("sha256:")
    assert len(event["output_digest"]) == len("sha256:") + 64
    assert event["output_bytes"] > LARGE_OUTPUT_THRESHOLD_BYTES
    assert event["summary"] == "gdUnit4 v6 missing"


def test_exit_code_is_part_of_the_error_fingerprint():
    first = worker_report(blocker="")
    second = first.replace(
        "gdUnit exited with code 1", "gdUnit exited with code 3221225477")
    first_event = build_worker_error_event(
        message=first,
        status="FAILED",
        outcome_kind="terminal",
        agent_id="worker-1",
        stage="build",
    )
    second_event = build_worker_error_event(
        message=second,
        status="FAILED",
        outcome_kind="terminal",
        agent_id="worker-1",
        stage="build",
    )
    assert first_event["summary"] == second_event["summary"]
    assert first_event["error_fingerprint"] != second_event["error_fingerprint"]


def test_duplicate_stop_writes_one_event_and_next_attempt_is_counted():
    first = build_worker_error_event(
        message=worker_report(),
        status="FAILED",
        outcome_kind="terminal",
        agent_id="worker-1",
        stage="build",
    )
    assert record_worker_error(first) is True
    assert record_worker_error(first) is False

    second = build_worker_error_event(
        message=worker_report(),
        status="FAILED",
        outcome_kind="terminal",
        agent_id="worker-2",
        stage="build",
    )
    assert second["attempt"] == 2
    assert second["repeat_count"] == 1
    assert len(read_metrics("worker_error")) == 1


def test_runtime_comes_from_top_level_agent_config(tmp_path):
    config = tmp_path / ".godotmaker" / "config.yaml"
    config.write_text("pipeline:\n  agent: pi\nagent: codex\n", encoding="utf-8")
    event = build_worker_error_event(
        message=worker_report(),
        status="FAILED",
        outcome_kind="terminal",
        agent_id="worker-1",
        stage="build",
    )
    assert event["runtime"] == "codex"


def test_log_subagent_does_not_diagnose_other_roles():
    handle_stop({
        "hook_event_name": "SubagentStop",
        "agent_id": "analyst-1",
        "agent_type": "analyst",
        "last_assistant_message": (
            "## Analyst Report:\n\n### Status: FAILED\n\n"
            "### Notes\n- Blocker: provider failed"
        ),
    })
    assert read_metrics("worker_error") == []


def test_codex_reviewer_embedding_worker_report_is_not_diagnosed(tmp_path):
    config = tmp_path / ".godotmaker" / "config.yaml"
    config.write_text("agent: codex\n", encoding="utf-8")
    handle_stop({
        "hook_event_name": "SubagentStop",
        "agent_id": "reviewer-1",
        "agent_type": "worker",
        "last_assistant_message": (
            "## Review Report:\n\n"
            "### Reviewers Matched\n- gameplay\n\n"
            "### ECS Review\n- quoted handoff:\n\n"
            "## Report: M01 movement\n"
            "### Status: FAILED\n\n"
            "### Issues Found\n- malformed worker handoff\n\n"
            "### Summary\n- request a retry\n"
        ),
    }, verdict=SimpleNamespace(
        rejected=True,
        reason="review report rejected by worker gate",
    ))
    assert read_metrics("worker_error") == []


def test_non_worker_role_does_not_diagnose_worker_shaped_report():
    handle_stop({
        "hook_event_name": "SubagentStop",
        "agent_id": "reviewer-1",
        "agent_type": "reviewer",
        "last_assistant_message": worker_report(),
    }, verdict=SimpleNamespace(
        rejected=True,
        reason="worker report rejected for reviewer",
    ))
    assert read_metrics("worker_error") == []


def test_silent_codex_generic_delegate_is_not_classified_as_worker(tmp_path):
    config = tmp_path / ".godotmaker" / "config.yaml"
    config.write_text("agent: codex\n", encoding="utf-8")
    handle_stop({
        "hook_event_name": "SubagentStop",
        "agent_id": "generic-1",
        "agent_type": "worker",
        "last_assistant_message": "",
    })
    assert read_metrics("worker_error") == []


def test_silent_worker_in_an_active_pipeline_is_unverified():
    handle_stop({
        "hook_event_name": "SubagentStop",
        "agent_id": "worker-1",
        "agent_type": "worker",
        "last_assistant_message": "  \n ",
    })
    events = read_metrics("worker_error")
    assert len(events) == 1
    assert events[0]["error_type"] == "unverified_handoff"
    assert events[0]["summary"] == "stopped without producing a report"
