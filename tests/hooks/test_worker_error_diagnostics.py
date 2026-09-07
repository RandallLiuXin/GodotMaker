"""Tests for the structured failure diagnostics that replaced worker memory."""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

from .helpers import (
    run_hook, cleanup_metrics, write_current_role, read_metrics, write_metrics,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = str(REPO_ROOT / "hooks")
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

from metrics import diagnostics  # noqa: E402


def _import_agent_runtime():
    """`tools/agent_runtime.py`, which hooks deliberately cannot import."""
    tools_dir = str(REPO_ROOT / "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    import agent_runtime
    return agent_runtime


DISPATCHER = "on_subagent_stop.py"


def worker_report(status="FAILED", task="M01 PlayerMovement", extra=""):
    return (
        f"## Report: {task}\n\n"
        f"### Status: {status}\n\n"
        "### Files Changed\n- player_system.gd: created\n\n"
        "### Tests\n#### Unit Tests\n- test/test_player.gd: 3 tests, 2 passed\n"
        "- Commands run: godot --headless\n\n"
        "### Build\n- Status: FAIL\n"
        "- Output: see .godotmaker/traces/build_m01.log\n\n"
        + extra
    )


REPAIR_EVIDENCE = (
    "### Repair Attempt Evidence\n"
    "- Production diff: src/s_movement.gd\n"
    "- Focused verification: godot --headless -- FAIL\n"
    "- Failure fingerprint: none\n"
    "- Handoff condition: tool_or_environment_error\n"
    "- Suggested classification: orchestration_failure\n\n"
)


@pytest.fixture
def project_dir():
    original = os.getcwd()
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        yield tmpdir
        os.chdir(original)
        cleanup_metrics()


class TestNormalization:
    def test_task_id_prefers_plan_task_id(self):
        assert diagnostics.extract_task_id("## Report: M01 Player movement") == "M01"
        assert diagnostics.extract_task_id("## Report: [R2] Terrain") == "R2"

    def test_task_id_falls_back_to_a_bounded_slug(self):
        task_id = diagnostics.extract_task_id("## Report: Player movement")
        assert task_id == "player-movement"
        long_name = "x" * 200
        assert len(diagnostics.extract_task_id(f"## Report: {long_name}")) \
            <= diagnostics.MAX_TASK_ID_CHARS

    def test_task_id_unknown_without_a_report_heading(self):
        assert diagnostics.extract_task_id("no heading here") == "unknown"

    def test_handoff_condition_outranks_status(self):
        assert diagnostics.resolve_error_type(
            "FAILED", "terminal", "timeout", "worker") == diagnostics.ERROR_TIMEOUT

    def test_rejected_report_outranks_everything(self):
        assert diagnostics.resolve_error_type(
            "DONE", "rejected_attempt", "timeout",
            "worker") == diagnostics.ERROR_REPORT_REJECTED

    @pytest.mark.parametrize("status,expected", [
        ("FAILED", diagnostics.ERROR_TASK_FAILED),
        ("PARTIAL", diagnostics.ERROR_TASK_PARTIAL),
    ])
    @pytest.mark.parametrize("role", ["worker", "asset-producer", "analyst"])
    def test_status_maps_when_no_handoff_condition(self, role, status, expected):
        assert diagnostics.resolve_error_type(
            status, "terminal", "", role) == expected

    def test_clean_run_has_no_error_type(self):
        assert diagnostics.resolve_error_type(
            "DONE", "terminal", "", "worker") is None

    def test_exit_code_read_when_named(self):
        assert diagnostics.extract_exit_code("godot exited 1") == 1
        assert diagnostics.extract_exit_code("no code here") is None

    def test_unknown_classification_is_dropped(self, project_dir):
        event = diagnostics.build_error_event(
            message=worker_report(extra="- Suggested classification: vibes\n"),
            role="worker", status="FAILED", outcome_kind="terminal", stage="build")
        assert event["classification"] == ""


class TestRepairFieldScope:
    """`Handoff condition` is read from its own section, nowhere else.

    Tests and Build come first in the report and carry pasted command output,
    so a whole-message scan let a log line claim the field and outrank the
    report's real statement below it.
    """

    NOISE = (
        "- Output:\n"
        "  Handoff condition: timeout\n"
        "  Suggested classification: verified_success\n"
    )

    def test_pasted_output_does_not_outrank_the_evidence_section(self, project_dir):
        message = worker_report(status="PARTIAL", extra=REPAIR_EVIDENCE).replace(
            "- Commands run: godot --headless\n", self.NOISE)
        fields = diagnostics.extract_repair_fields(message)
        assert fields["handoff_condition"] == "tool_or_environment_error"
        assert fields["suggested_classification"] == "orchestration_failure"

    def test_the_recorded_error_type_follows_the_section(self, project_dir):
        evidence = (
            "### Repair Attempt Evidence\n"
            "- Production diff: src/s_movement.gd\n"
            "- Handoff condition: partial\n"
            "- Suggested classification: incomplete_handoff\n\n"
        )
        message = worker_report(status="PARTIAL", extra=evidence).replace(
            "- Commands run: godot --headless\n", self.NOISE)
        event = diagnostics.build_error_event(
            message=message, role="worker", status="PARTIAL",
            outcome_kind="terminal", stage="build")
        assert event["error_type"] == diagnostics.ERROR_TASK_PARTIAL
        assert event["retryable"] is False

    def test_no_section_means_no_fields(self, project_dir):
        """Status decides instead — what the accounting doc already says for
        a handoff whose evidence fields are missing."""
        message = worker_report(status="FAILED").replace(
            "- Commands run: godot --headless\n", self.NOISE)
        assert diagnostics.extract_repair_fields(message) == {}
        event = diagnostics.build_error_event(
            message=message, role="worker", status="FAILED",
            outcome_kind="terminal", stage="build")
        assert event["error_type"] == diagnostics.ERROR_TASK_FAILED

    def test_the_section_is_still_read_when_it_is_the_only_source(self, project_dir):
        fields = diagnostics.extract_repair_fields(
            worker_report(extra=REPAIR_EVIDENCE))
        assert fields["handoff_condition"] == "tool_or_environment_error"


class TestVerifierVocabulary:
    """`PASS | FAIL | PARTIAL` is a verdict about the project, not the run.

    A verifier that reports FAIL did its job — that outcome already travels as
    `verifier_fail`. Deriving an error type from any of its three words would
    file a working run as a failure; deriving one from only some of them would
    file the pipeline's clearest failure signal as nothing while its weaker
    sibling got a record. Neither is right, so status is not read at all for
    this role — but every run-level fault still is.
    """

    @pytest.mark.parametrize("status", ["PASS", "FAIL", "PARTIAL"])
    def test_no_status_derives_an_error_type(self, status):
        assert diagnostics.resolve_error_type(
            status, "terminal", "", "verifier") is None

    @pytest.mark.parametrize("outcome_kind,expected", [
        ("rejected_attempt", diagnostics.ERROR_REPORT_REJECTED),
        ("unverified", diagnostics.ERROR_UNVERIFIED),
    ])
    def test_run_level_faults_still_recorded(self, outcome_kind, expected):
        assert diagnostics.resolve_error_type(
            "FAIL", outcome_kind, "", "verifier") == expected

    def test_a_timeout_is_still_recorded(self):
        assert diagnostics.resolve_error_type(
            "FAIL", "terminal", "timeout", "verifier") == diagnostics.ERROR_TIMEOUT

    @pytest.mark.parametrize("status", ["PASS", "FAIL", "PARTIAL"])
    def test_verifier_report_writes_no_event(self, project_dir, status):
        report = (
            "## Verification Report: Integration\n\n"
            f"### Overall: {status}\n\n"
            "### Results\n### Check: build\n**Command run:** godot --headless\n\n"
            "### Adversarial Probes\n### Check: boundary\n**Command run:** edge\n"
        )
        assert diagnostics.build_error_event(
            message=report, role="verifier", status=status,
            outcome_kind="terminal", stage="verify") is None

    def test_an_unknown_role_derives_nothing_from_status(self):
        """A generic subagent is not on the diagnostics contract."""
        assert diagnostics.resolve_error_type(
            "FAILED", "terminal", "", "unknown") is None


class TestBounds:
    def test_summary_is_clipped(self, project_dir):
        event = diagnostics.build_error_event(
            message=worker_report(extra="- Blocker: " + "x" * 900 + "\n"),
            role="worker", status="FAILED", outcome_kind="terminal", stage="build")
        assert len(event["summary"]) <= diagnostics.MAX_SUMMARY_CHARS

    def test_evidence_paths_are_bounded_and_scoped(self, project_dir):
        noise = "\n".join(
            f"- .godotmaker/traces/t{i}.log" for i in range(20)
        )
        event = diagnostics.build_error_event(
            message=worker_report(extra=noise + "\n- src/player.gd\n"),
            role="worker", status="FAILED", outcome_kind="terminal", stage="build")
        assert len(event["evidence_paths"]) == diagnostics.MAX_EVIDENCE_PATHS
        assert all(p.startswith(diagnostics.EVIDENCE_PREFIXES)
                   for p in event["evidence_paths"])
        assert "src/player.gd" not in event["evidence_paths"]

    def test_large_output_travels_as_a_digest_not_a_copy(self, project_dir):
        pasted_log = "\n".join(f"  ERROR line {i}: boom" for i in range(5000))
        message = (
            "## Report: M01 PlayerMovement\n\n"
            "### Status: FAILED\n\n"
            "### Files Changed\n- player_system.gd: created\n\n"
            "### Build\n- Status: FAIL\n- Output:\n" + pasted_log + "\n\n"
            "### Notes\nbuild broke\n"
        )
        event = diagnostics.build_error_event(
            message=message, role="worker", status="FAILED",
            outcome_kind="terminal", stage="build")
        digest = event["output_digest"]
        assert digest["bytes"] > len(pasted_log) / 2
        assert len(digest["tail"]) <= diagnostics.MAX_DIGEST_TAIL_CHARS
        assert digest["tail"].strip() in pasted_log
        assert len(json.dumps(event)) < 2000

    def test_small_output_gets_no_digest(self, project_dir):
        event = diagnostics.build_error_event(
            message=worker_report(), role="worker", status="FAILED",
            outcome_kind="terminal", stage="build")
        assert "output_digest" not in event

    def test_command_output_section_includes_the_unit_tests_subsection(self):
        captured = diagnostics.extract_command_output(worker_report())
        assert "#### Unit Tests" in captured
        assert "- Status: FAIL" in captured
        assert "### Status: FAILED" not in captured

    def test_no_event_carries_the_report_body(self, project_dir):
        message = worker_report(extra="- Blocker: headless load failed\n")
        event = diagnostics.build_error_event(
            message=message, role="worker", status="FAILED",
            outcome_kind="terminal", stage="build")
        assert message not in json.dumps(event)


class TestFingerprintAndDedupe:
    def test_fingerprint_ignores_digit_noise(self):
        a = diagnostics.error_fingerprint("M01", "build", "task_failed",
                                          "load failed at line 42 after 1200ms")
        b = diagnostics.error_fingerprint("M01", "build", "task_failed",
                                          "load failed at line 87 after 30ms")
        assert a == b

    def test_fingerprint_separates_different_failures(self):
        a = diagnostics.error_fingerprint("M01", "build", "task_failed", "load failed")
        b = diagnostics.error_fingerprint("M01", "build", "timeout", "load failed")
        assert a != b

    def test_same_agent_and_fingerprint_recorded_once(self, project_dir):
        event = diagnostics.build_error_event(
            message=worker_report(), role="worker", status="FAILED",
            outcome_kind="terminal", agent_id="w1", stage="build")
        assert diagnostics.record_error_event(event) is True
        assert diagnostics.record_error_event(dict(event)) is False
        assert len(read_metrics("worker_error")) == 1

    def test_attempt_and_repeat_count_grow_across_attempts(self, project_dir):
        for agent_id in ("w1", "w2", "w3"):
            event = diagnostics.build_error_event(
                message=worker_report(), role="worker", status="FAILED",
                outcome_kind="terminal", agent_id=agent_id, stage="build")
            diagnostics.record_error_event(event)
        events = read_metrics("worker_error")
        assert [e["attempt"] for e in events] == [1, 2, 3]
        assert [e["repeat_count"] for e in events] == [0, 1, 2]
        assert len({e["error_fingerprint"] for e in events}) == 1


def _write_config(agent_line: str) -> None:
    os.makedirs(".godotmaker", exist_ok=True)
    with open(".godotmaker/config.yaml", "w", encoding="utf-8") as f:
        f.write(f"{agent_line}godot_path: godot\n")


class TestRuntimeField:
    @pytest.mark.parametrize("agent", ["claude-code", "codex", "opencode", "pi"])
    def test_runtime_read_from_project_config(self, project_dir, agent):
        _write_config(f"agent: {agent}\n")
        event = diagnostics.build_error_event(
            message=worker_report(), role="worker", status="FAILED",
            outcome_kind="terminal", stage="build")
        assert event["runtime"] == agent

    @pytest.mark.parametrize("configured,expected", [
        ("claude", "claude-code"),
        ("anthropic-claude-code", "claude-code"),
        ("openai-codex", "codex"),
        ("open-code", "opencode"),
        ("pi-coding-agent", "pi"),
        ("Codex", "codex"),
        ("pi_coding", "pi"),
    ])
    def test_aliases_are_normalized(self, project_dir, configured, expected):
        """`agent: claude` must correlate with `claude-code`, not become a
        fourth spelling of it."""
        _write_config(f"agent: {configured}\n")
        assert diagnostics.read_runtime() == expected

    @pytest.mark.parametrize("directory,expected", [
        (".agents", "codex"),
        (".opencode", "opencode"),
        (".pi", "pi"),
    ])
    def test_directory_fallback_for_projects_predating_the_agent_key(
            self, project_dir, directory, expected):
        _write_config("")
        os.makedirs(directory, exist_ok=True)
        assert diagnostics.read_runtime() == expected

    def test_an_indented_agent_key_is_not_the_runtime(self, project_dir):
        """Only a top-level `agent:` selects the runtime."""
        _write_config("models:\n  agent: codex\n")
        assert diagnostics.read_runtime() == "claude-code"

    def test_matches_the_tool_that_actually_picks_the_runtime(self, project_dir):
        """`read_runtime` is a copy of `tools/agent_runtime.detect_agent`.

        The hook cannot import `tools/`, so this pins the copy to its source:
        if one grows a spelling or a fallback the other lacks, this fails.
        """
        agent_runtime = _import_agent_runtime()
        scenarios = [
            ("agent: claude\n", None),
            ("agent: openai-codex\n", None),
            ("agent: opencode\n", None),
            ("agent: pi-coding-agent\n", None),
            ("agent: nonsense\n", None),
            ("", ".agents"),
            ("", ".opencode"),
            ("", ".pi"),
            ("", None),
        ]
        for agent_line, directory in scenarios:
            shutil.rmtree(".godotmaker", ignore_errors=True)
            for existing in (".agents", ".opencode", ".pi"):
                shutil.rmtree(existing, ignore_errors=True)
            _write_config(agent_line)
            if directory:
                os.makedirs(directory, exist_ok=True)
            assert diagnostics.read_runtime() == agent_runtime.detect_agent(
                Path(os.getcwd())), f"drift for {agent_line!r} / {directory}"


class TestThroughTheStopHook:
    """The dispatcher is what actually writes these events in a live run."""

    def test_failed_worker_writes_one_diagnostic(self, project_dir):
        write_current_role("build")
        run_hook(DISPATCHER, {
            "hook_event_name": "SubagentStop",
            "agent_id": "w1",
            "agent_type": "worker",
            "session_id": "sess-1",
            "last_assistant_message": worker_report(extra=REPAIR_EVIDENCE),
        })
        events = read_metrics("worker_error")
        assert len(events) == 1
        event = events[0]
        assert event["task_id"] == "M01"
        assert event["stage"] == "build"
        assert event["role"] == "worker"
        assert event["run_id"] == "sess-1"
        assert event["error_type"] == "tool_or_environment_error"
        assert event["classification"] == "orchestration_failure"
        assert event["retryable"] is True
        assert ".godotmaker/traces/build_m01.log" in event["evidence_paths"]

    def test_successful_worker_writes_no_diagnostic(self, project_dir):
        write_current_role("build")
        clean = (
            "## Report: M01 PlayerMovement\n\n"
            "### Status: DONE\n\n"
            "### Files Changed\n- player_system.gd: created\n\n"
            "### Tests\n#### Unit Tests\n- test/test_player.gd: 3 tests, 3 passed\n"
            "- Commands run: godot --headless\n\n"
            "### Build\n- Status: PASS\n"
        )
        run_hook(DISPATCHER, {
            "hook_event_name": "SubagentStop",
            "agent_id": "w1",
            "agent_type": "worker",
            "last_assistant_message": clean,
        })
        assert read_metrics("worker_error") == []

    def test_rejected_report_is_recorded_as_an_orchestration_fault(self, project_dir):
        write_current_role("build")
        # Missing Build section → the report hook blocks this stop.
        broken = (
            "## Report: M01 PlayerMovement\n\n"
            "### Status: DONE\n\n"
            "### Files Changed\n- player_system.gd: created\n\n"
            "### Tests\n#### Unit Tests\n- test/test_player.gd: 3 tests, 3 passed\n"
            "- Commands run: godot --headless\n"
        )
        run_hook(DISPATCHER, {
            "hook_event_name": "SubagentStop",
            "agent_id": "w1",
            "agent_type": "worker",
            "last_assistant_message": broken,
        })
        events = read_metrics("worker_error")
        assert len(events) == 1
        assert events[0]["error_type"] == "report_rejected"
        assert events[0]["retryable"] is True

    def test_legacy_memory_entry_does_not_change_the_record(self, project_dir):
        write_current_role("build")
        legacy = worker_report(status="PARTIAL") + (
            "### Memory Entry\nCharacterBody2D needs move_and_slide\n"
        )
        run_hook(DISPATCHER, {
            "hook_event_name": "SubagentStop",
            "agent_id": "w1",
            "agent_type": "worker",
            "last_assistant_message": legacy,
        })
        events = read_metrics("worker_error")
        assert len(events) == 1
        assert "CharacterBody2D" not in json.dumps(events[0])
        assert not os.path.exists("MEMORY.md")
        assert not os.path.exists("memory")

    def test_diagnostics_are_not_injected_into_the_next_prompt(self, project_dir):
        """A validated stop injects progress counts only — never failure text."""
        write_current_role("build")
        write_metrics([
            {"event": "worker_error", "task_id": "M01", "stage": "build",
             "summary": "headless godot load failed", "attempt": 1},
        ])
        clean = (
            "## Report: M02 Jump\n\n"
            "### Status: DONE\n\n"
            "### Files Changed\n- jump_system.gd: created\n\n"
            "### Tests\n#### Unit Tests\n- test/test_jump.gd: 2 tests, 2 passed\n"
            "- Commands run: godot --headless\n\n"
            "### Build\n- Status: PASS\n"
        )
        stdout, _, parsed = run_hook(DISPATCHER, {
            "hook_event_name": "SubagentStop",
            "agent_id": "w2",
            "agent_type": "worker",
            "last_assistant_message": clean,
        })
        context = ""
        if parsed:
            context = parsed.get("hookSpecificOutput", {}).get("additionalContext", "")
        assert "worker_error" not in stdout
        assert "headless godot load failed" not in stdout
        assert "M01" not in context
