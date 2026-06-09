"""Tests for the metrics system."""
import os
import sys
import pytest
from metrics.collector import record_event, read_events, read_current_events, start_session
from metrics.schema import EventType
from metrics.reporter import generate_report
from metrics import state as metrics_state

# Import role detection helpers from log_subagent hook
HOOKS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)
from log_subagent import detect_role_from_description, lookup_role_from_events  # noqa: E402


@pytest.fixture(autouse=True)
def temp_metrics_dir(monkeypatch, tmp_path):
    """Redirect metrics to a temp directory."""
    log_dir = str(tmp_path / ".godotmaker")
    log_file = os.path.join(log_dir, "metrics.jsonl")
    log_current = os.path.join(log_dir, "metrics_current.jsonl")
    monkeypatch.setattr("metrics.collector.LOG_DIR", log_dir)
    monkeypatch.setattr("metrics.collector.LOG_FILE", log_file)
    monkeypatch.setattr("metrics.collector.LOG_CURRENT", log_current)
    yield log_dir, log_file


class TestCollector:
    def test_record_and_read(self, temp_metrics_dir):
        _, log_file = temp_metrics_dir
        record_event(EventType.SUBAGENT_START, agent_id="w1", agent_type="worker")
        record_event(EventType.HOOK_BLOCK, hook="test", reason="blocked")

        events = read_events(log_file)
        assert len(events) == 2
        assert events[0]["event"] == "subagent_start"
        assert events[0]["agent_id"] == "w1"
        assert events[1]["event"] == "hook_block"

    def test_read_nonexistent_file(self):
        events = read_events("/nonexistent/path.jsonl")
        assert events == []

    def test_event_has_timestamp(self, temp_metrics_dir):
        _, log_file = temp_metrics_dir
        record_event(EventType.GATE_CHECK, gate="test")
        events = read_events(log_file)
        assert "ts" in events[0]
        assert "T" in events[0]["ts"]  # ISO format

    def test_dual_write(self, temp_metrics_dir):
        _, log_file = temp_metrics_dir
        record_event(EventType.SUBAGENT_START, agent_id="w1")
        # Both files should have the event
        history = read_events(log_file)
        current = read_current_events()
        assert len(history) == 1
        assert len(current) == 1
        assert history[0]["agent_id"] == current[0]["agent_id"]

    def test_start_session_clears_current(self, temp_metrics_dir):
        record_event(EventType.SUBAGENT_START, agent_id="w1")
        record_event(EventType.SUBAGENT_START, agent_id="w2")
        assert len(read_current_events()) == 2

        start_session()
        assert len(read_current_events()) == 0

        # History should still have both
        _, log_file = temp_metrics_dir
        assert len(read_events(log_file)) == 2


class TestReporter:
    def test_empty_events(self):
        html = generate_report([])
        assert "No events recorded" in html

    def test_generates_html(self, temp_metrics_dir):
        _, log_file = temp_metrics_dir
        record_event(EventType.SUBAGENT_START, agent_id="w1", agent_type="worker")
        record_event(EventType.SUBAGENT_STOP, agent_id="w1", status="DONE", report_type="worker")
        record_event(EventType.WORKER_DONE, agent_id="w1")
        record_event(EventType.HOOK_BLOCK, hook="test", reason="blocked")

        events = read_events(log_file)
        html = generate_report(events)
        assert "<!DOCTYPE html>" in html
        assert "Subagents" in html
        assert "Hook Blocks" in html
        assert "worker" in html

    def test_all_sections_present(self, temp_metrics_dir):
        _, log_file = temp_metrics_dir
        record_event(EventType.SUBAGENT_START, agent_id="w1", agent_type="worker")
        record_event(EventType.GATE_CHECK, gate="build", result="pass")
        record_event(EventType.FILE_WRITE, file="foo.gd", agent_id="w1")
        record_event(EventType.ERROR, error_type="build_fail")

        events = read_events(log_file)
        html = generate_report(events)
        for section in ["Overview", "Subagents", "Hook Blocks", "Gate Checks",
                         "Errors", "Worker Outcomes", "File Operations", "Event Timeline"]:
            assert section in html, f"Missing section: {section}"


class TestState:
    def test_get_set(self, tmp_path, monkeypatch):
        state_file = str(tmp_path / ".godotmaker" / "state.json")
        state_dir = str(tmp_path / ".godotmaker")
        monkeypatch.setattr("metrics.state.STATE_FILE", state_file)
        monkeypatch.setattr("metrics.state.STATE_DIR", state_dir)

        metrics_state.put("foo", 42)
        assert metrics_state.get("foo") == 42

    def test_increment(self, tmp_path, monkeypatch):
        state_file = str(tmp_path / ".godotmaker" / "state.json")
        state_dir = str(tmp_path / ".godotmaker")
        monkeypatch.setattr("metrics.state.STATE_FILE", state_file)
        monkeypatch.setattr("metrics.state.STATE_DIR", state_dir)

        assert metrics_state.increment("count") == 1
        assert metrics_state.increment("count") == 2
        assert metrics_state.increment("count") == 3

    def test_reset(self, tmp_path, monkeypatch):
        state_file = str(tmp_path / ".godotmaker" / "state.json")
        state_dir = str(tmp_path / ".godotmaker")
        monkeypatch.setattr("metrics.state.STATE_FILE", state_file)
        monkeypatch.setattr("metrics.state.STATE_DIR", state_dir)

        metrics_state.put("stop_block_count", 5)
        metrics_state.reset()
        assert metrics_state.get("stop_block_count") == 0

    def test_default_on_missing_file(self, tmp_path, monkeypatch):
        state_file = str(tmp_path / "nonexistent" / "state.json")
        state_dir = str(tmp_path / "nonexistent")
        monkeypatch.setattr("metrics.state.STATE_FILE", state_file)
        monkeypatch.setattr("metrics.state.STATE_DIR", state_dir)

        assert metrics_state.get("stop_block_count", 0) == 0


class TestRoleDetection:
    """Tests for role detection from subagent description field."""

    def test_worker_prefix(self):
        assert detect_role_from_description("Worker: implement MovementSystem") == "worker"

    def test_worker_keyword(self):
        assert detect_role_from_description("M2-M5 core systems worker tasks") == "worker"

    def test_verifier_prefix(self):
        assert detect_role_from_description("Verifier: check build and tests") == "verifier"

    def test_verifier_keyword(self):
        assert detect_role_from_description("Verify build output is clean") == "verifier"

    def test_reviewer_prefix(self):
        assert detect_role_from_description("Reviewer: review MovementSystem") == "reviewer"

    def test_reviewer_keyword(self):
        assert detect_role_from_description("Review the physics system code") == "reviewer"

    def test_analyst_prefix(self):
        assert detect_role_from_description("Analyst: process user assets") == "analyst"

    def test_analyst_keyword(self):
        assert detect_role_from_description("Analyze the provided sprites") == "analyst"

    def test_analyst_case_insensitive(self):
        assert detect_role_from_description("ANALYST: check assets") == "analyst"

    def test_asset_producer_prefix(self):
        assert detect_role_from_description("Asset Producer: make ui kit") == "asset-producer"

    def test_asset_producer_keyword(self):
        assert detect_role_from_description("asset-producer ui kit task") == "asset-producer"

    def test_unknown_description(self):
        assert detect_role_from_description("Run some general task") == "unknown"

    def test_empty_description(self):
        assert detect_role_from_description("") == "unknown"

    def test_none_description(self):
        assert detect_role_from_description(None) == "unknown"

    def test_case_insensitive(self):
        assert detect_role_from_description("WORKER: do stuff") == "worker"
        assert detect_role_from_description("VERIFIER: check stuff") == "verifier"
        assert detect_role_from_description("REVIEWER: look at stuff") == "reviewer"
        assert detect_role_from_description("ANALYST: check assets") == "analyst"
        assert detect_role_from_description("ASSET-PRODUCER: make assets") == "asset-producer"


class TestRoleLookup:
    """Tests for SubagentStop role lookup from current events."""

    def test_lookup_finds_matching_start(self, temp_metrics_dir):
        record_event(EventType.SUBAGENT_START, agent_id="w1", agent_type="general-purpose", role="worker")
        role = lookup_role_from_events("w1")
        assert role == "worker"

    def test_lookup_returns_unknown_when_no_match(self, temp_metrics_dir):
        record_event(EventType.SUBAGENT_START, agent_id="w1", agent_type="general-purpose", role="worker")
        role = lookup_role_from_events("w99")
        assert role == "unknown"

    def test_lookup_returns_latest_start(self, temp_metrics_dir):
        """If an agent is dispatched twice, use the most recent start event."""
        record_event(EventType.SUBAGENT_START, agent_id="a1", agent_type="general-purpose", role="worker")
        record_event(EventType.SUBAGENT_START, agent_id="a1", agent_type="general-purpose", role="verifier")
        role = lookup_role_from_events("a1")
        assert role == "verifier"

    def test_lookup_analyst_role(self, temp_metrics_dir):
        record_event(EventType.SUBAGENT_START, agent_id="a1", agent_type="general-purpose", role="analyst")
        role = lookup_role_from_events("a1")
        assert role == "analyst"

    def test_lookup_empty_events(self, temp_metrics_dir):
        role = lookup_role_from_events("w1")
        assert role == "unknown"


class TestGetCurrentTag:
    """get_current_tag() reads PLAN.md's `**Tag:** vX.Y.Z` header so
    session_start (and other helpers) can surface the active tag.
    """

    @pytest.fixture
    def in_project_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        return tmp_path

    def test_returns_empty_when_plan_missing(self, in_project_dir):
        from metrics import get_current_tag
        assert get_current_tag() == ""

    def test_returns_empty_when_no_tag_header(self, in_project_dir):
        (in_project_dir / "PLAN.md").write_text(
            "# Plan\n\nNo tag header in this file.\n", encoding="utf-8"
        )
        from metrics import get_current_tag
        assert get_current_tag() == ""

    def test_extracts_tag_from_header(self, in_project_dir):
        (in_project_dir / "PLAN.md").write_text(
            "# Plan\n\n**Tag:** v0.3.0\n\nrest of plan\n", encoding="utf-8"
        )
        from metrics import get_current_tag
        assert get_current_tag() == "v0.3.0"

    def test_handles_extra_whitespace(self, in_project_dir):
        (in_project_dir / "PLAN.md").write_text(
            "# Plan\n\n**Tag:**   v1.2.3   \n", encoding="utf-8"
        )
        from metrics import get_current_tag
        assert get_current_tag() == "v1.2.3"

    def test_ignores_non_semver_after_marker(self, in_project_dir):
        (in_project_dir / "PLAN.md").write_text(
            "# Plan\n\n**Tag:** alpha-1\n", encoding="utf-8"
        )
        from metrics import get_current_tag
        # Regex requires vX.Y.Z so this should not match
        assert get_current_tag() == ""
