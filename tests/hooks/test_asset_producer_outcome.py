"""Tests for the shared asset-producer terminal outcome protocol.

Covers the parser/normalizer, the fail-closed hook gate, and the end-to-end
agreement between the hook's classification and what metrics persists —
including the case the protocol exists for: a first attempt rejected on format
followed by a valid retry must leave exactly one terminal record.
"""
import json

import pytest

from metrics.outcome import (
    OutcomeError, normalize_report, validate_outcome, extract_markdown_status,
)

from .helpers import (
    asset_producer_outcome, cleanup_metrics, is_blocked, read_metrics,
    run_hook, write_current_role,
)

DISPATCHER = "on_subagent_stop.py"


def producer_report(status="DONE", unit_id="ui_kit", drop_section=None, **kwargs):
    """A complete asset-producer report, optionally with one heading removed."""
    body = (
        f"## Asset Producer Report: {unit_id}\n\n"
        f"### Status: {status}\n\n"
        "### Production Unit\n- First-class Asset Skill: ui-kit\n\n"
        "### Outputs\n- Sources: .godotmaker/asset-generation/sources/ui_source.png\n\n"
        "### Tools\n- python tools/asset_sheet_process.py --snap-mode autoslice\n\n"
        "### Validation\n- File existence: PASS\n\n"
        "### Handoff\nRegister the ui_kit entry.\n\n"
    )
    if drop_section:
        body = body.replace(drop_section, "### Removed")
    return body + asset_producer_outcome(status=status, unit_id=unit_id, **kwargs)


def stop(agent_id, message):
    return run_hook(DISPATCHER, {
        "hook_event_name": "SubagentStop",
        "agent_id": agent_id,
        "agent_type": "asset-producer",
        "last_assistant_message": message,
    })


@pytest.fixture(autouse=True)
def clean():
    cleanup_metrics()
    write_current_role("asset")
    yield
    cleanup_metrics()


class TestOutcomeParser:
    """The single parser/normalizer every consumer shares."""

    @pytest.mark.parametrize("status", ["DONE", "PARTIAL", "FAILED"])
    def test_status_and_type_come_from_the_block(self, status):
        report = normalize_report(producer_report(status))
        assert report.report_type == "asset-producer"
        assert report.status == status
        assert report.outcome_error is None
        assert report.outcome["unit_id"] == "ui_kit"

    def test_block_wins_over_contradicting_prose(self):
        """A mangled heading no longer degrades the machine status."""
        message = (
            "Production stopped early.\n\n"
            "**Status:** DONE\n\n"
            + asset_producer_outcome("PARTIAL")
        )
        report = normalize_report(message)
        assert report.report_type == "asset-producer"
        assert report.status == "PARTIAL"
        assert report.outcome["blockers"]

    def test_blockers_survive_normalization(self):
        message = producer_report("FAILED", blockers=["provider quota exhausted"])
        report = normalize_report(message)
        assert report.outcome["blockers"] == ["provider quota exhausted"]

    def test_no_block_falls_back_to_markdown(self):
        report = normalize_report(
            "## Asset Producer Report: ui_kit\n\n### Status: PARTIAL\n"
        )
        assert report.has_outcome_block is False
        assert report.outcome is None
        assert report.report_type == "asset-producer"
        assert report.status == "PARTIAL"

    def test_markdown_status_is_case_and_level_tolerant(self):
        """The old status regex returned UNKNOWN here while the parent read PARTIAL."""
        assert extract_markdown_status("#### status: partial") == "PARTIAL"
        assert extract_markdown_status("### **Status:** FAILED") == "FAILED"
        assert extract_markdown_status("no status here") == "UNKNOWN"

    def test_unrelated_json_block_is_not_an_outcome(self):
        message = (
            "```json\n{\"asset_type\": \"ui-kit\", \"outputs\": []}\n```\n\n"
            + asset_producer_outcome("DONE")
        )
        report = normalize_report(message)
        assert report.status == "DONE"

    def test_two_blocks_are_ambiguous(self):
        message = asset_producer_outcome("DONE") + "\n\n" + asset_producer_outcome("FAILED")
        report = normalize_report(message)
        assert report.outcome is None
        assert "exactly one" in report.outcome_error

    def test_malformed_json_is_reported_not_skipped(self):
        message = "```json\n{\"gm_outcome_version\": 1, oops}\n```"
        report = normalize_report(message)
        assert report.has_outcome_block is True
        assert report.outcome is None
        assert "not valid JSON" in report.outcome_error


class TestOutcomeValidation:
    """Fail closed, and name the offending field."""

    def _payload(self, **overrides):
        block = asset_producer_outcome(**overrides)
        return json.loads(block.split("```json\n", 1)[1].rsplit("\n```", 1)[0])

    @pytest.mark.parametrize("field", [
        "gm_outcome_version", "report_type", "status", "unit_id",
        "outputs", "validation", "blockers",
    ])
    def test_missing_field_rejected(self, field):
        payload = self._payload()
        del payload[field]
        with pytest.raises(OutcomeError) as exc:
            validate_outcome(payload)
        assert field in str(exc.value)

    def test_unknown_top_level_field_rejected(self):
        payload = self._payload()
        payload["tag"] = "v0.1.0"
        with pytest.raises(OutcomeError) as exc:
            validate_outcome(payload)
        assert "tag" in str(exc.value)

    def test_bad_status_rejected(self):
        payload = self._payload()
        payload["status"] = "SUCCESS"
        with pytest.raises(OutcomeError) as exc:
            validate_outcome(payload)
        assert "status" in str(exc.value)

    def test_lowercase_status_normalized(self):
        payload = self._payload()
        payload["status"] = "done"
        assert validate_outcome(payload)["status"] == "DONE"

    def test_empty_unit_id_rejected(self):
        payload = self._payload()
        payload["unit_id"] = "   "
        with pytest.raises(OutcomeError) as exc:
            validate_outcome(payload)
        assert "unit_id" in str(exc.value)

    def test_unknown_output_category_rejected(self):
        payload = self._payload()
        payload["outputs"]["manifest_entry"] = []
        with pytest.raises(OutcomeError) as exc:
            validate_outcome(payload)
        assert "manifest_entry" in str(exc.value)

    def test_non_bool_validation_passed_rejected(self):
        payload = self._payload()
        payload["validation"]["passed"] = "true"
        with pytest.raises(OutcomeError) as exc:
            validate_outcome(payload)
        assert "validation.passed" in str(exc.value)

    def test_done_with_failed_validation_rejected(self):
        payload = self._payload(status="DONE", passed=False)
        with pytest.raises(OutcomeError) as exc:
            validate_outcome(payload)
        assert "validation.passed" in str(exc.value)

    def test_done_with_blockers_rejected(self):
        payload = self._payload(status="DONE", blockers=["still missing frames"])
        with pytest.raises(OutcomeError) as exc:
            validate_outcome(payload)
        assert "blockers" in str(exc.value)

    @pytest.mark.parametrize("status", ["PARTIAL", "FAILED"])
    def test_non_done_without_blockers_rejected(self, status):
        payload = self._payload(status=status, blockers=[])
        with pytest.raises(OutcomeError) as exc:
            validate_outcome(payload)
        assert "blockers" in str(exc.value)


class TestHookGate:
    """The hook is fail-closed on the block, with a locatable diagnostic."""

    def test_valid_report_allowed(self):
        _, _, parsed = stop("ap-ok", producer_report("DONE"))
        assert not is_blocked(parsed)

    def test_missing_outcome_block_blocked(self):
        message = producer_report("DONE").split("### Machine Outcome")[0]
        _, _, parsed = stop("ap-noblock", message)
        assert is_blocked(parsed)
        assert "outcome block" in parsed["reason"]

    def test_invalid_field_diagnostic_names_the_field(self):
        message = producer_report("PARTIAL", blockers=[], passed=False)
        _, _, parsed = stop("ap-noblockers", message)
        assert is_blocked(parsed)
        assert "blockers" in parsed["reason"]

    def test_other_roles_are_unaffected(self):
        """Only asset-producer must carry a block; the worker protocol is untouched."""
        worker = (
            "## Report: PlayerMovement\n\n"
            "### Status: DONE\n\n"
            "### Files Changed\n- player_system.gd: created\n\n"
            "### Tests\n- test/test_player.gd: 3 tests, 3 passed\n"
            "- Commands run: godot --headless\n\n"
            "### Build\n- Status: PASS\n\n"
            "### Memory Entry\nLearned about movement"
        )
        _, _, parsed = run_hook(DISPATCHER, {
            "hook_event_name": "SubagentStop",
            "agent_id": "w-plain",
            "agent_type": "worker",
            "last_assistant_message": worker,
        })
        assert not is_blocked(parsed)


class TestTerminalConsistency:
    """Hook classification, metrics, and the outcome block agree."""

    @pytest.mark.parametrize("status,event", [
        ("DONE", "asset_producer_done"),
        ("PARTIAL", "asset_producer_partial"),
        ("FAILED", "asset_producer_failed"),
    ])
    def test_status_classified_identically_everywhere(self, status, event):
        _, _, parsed = stop(f"ap-{status}", producer_report(status))
        assert not is_blocked(parsed)

        stops = read_metrics("subagent_stop")
        assert len(stops) == 1
        assert stops[0]["report_type"] == "asset-producer"
        assert stops[0]["status"] == status
        assert stops[0]["outcome_kind"] == "terminal"
        assert stops[0]["unit_id"] == "ui_kit"

        outcomes = read_metrics(event)
        assert len(outcomes) == 1
        assert outcomes[0]["agent_id"] == f"ap-{status}"

    def test_valid_partial_is_never_unknown(self):
        """The upstream symptom: parent read PARTIAL, metrics wrote UNKNOWN."""
        stop("ap-partial", producer_report("PARTIAL"))
        record = read_metrics("subagent_stop")[0]
        assert record["status"] == "PARTIAL"
        assert record["report_type"] == "asset-producer"

    def test_blockers_reach_the_persisted_record(self):
        stop("ap-blocked", producer_report("FAILED", blockers=["provider quota exhausted"]))
        assert read_metrics("subagent_stop")[0]["blockers"] == ["provider quota exhausted"]
        assert read_metrics("asset_producer_failed")[0]["blockers"] == [
            "provider quota exhausted"
        ]


class TestRejectedAttempt:
    """A format rejection is an attempt, not a terminal outcome."""

    def test_format_rejection_then_valid_retry(self):
        rejected = producer_report("DONE", drop_section="### Handoff")
        _, _, parsed = stop("ap-retry", rejected)
        assert is_blocked(parsed), "missing heading must still fail closed"

        _, _, parsed = stop("ap-retry", producer_report("DONE"))
        assert not is_blocked(parsed)

        stops = read_metrics("subagent_stop")
        assert len(stops) == 2
        assert stops[0]["outcome_kind"] == "rejected_attempt"
        assert stops[1]["outcome_kind"] == "terminal"

        terminal = [s for s in stops if s["outcome_kind"] == "terminal"]
        assert len(terminal) == 1, "a retried run has exactly one terminal record"
        assert len(read_metrics("asset_producer_done")) == 1

    def test_rejected_attempt_is_still_classified_not_unknown(self):
        """A rejected attempt keeps its identity, so it never reads as a failure."""
        stop("ap-attempt", producer_report("DONE", drop_section="### Tools"))
        record = read_metrics("subagent_stop")[0]
        assert record["outcome_kind"] == "rejected_attempt"
        assert record["report_type"] == "asset-producer"
        assert record["status"] == "DONE"

    def test_rejected_attempt_does_not_overwrite_the_final_result(self):
        """A DONE attempt rejected on format must not pre-empt a PARTIAL retry."""
        stop("ap-overwrite", producer_report("DONE", drop_section="### Validation"))
        assert read_metrics("asset_producer_done") == []

        stop("ap-overwrite", producer_report("PARTIAL"))
        assert read_metrics("asset_producer_done") == []
        partial = read_metrics("asset_producer_partial")
        assert len(partial) == 1
        assert partial[0]["blockers"]

    def test_missing_block_is_an_attempt_too(self):
        stop("ap-noblock2", producer_report("DONE").split("### Machine Outcome")[0])
        record = read_metrics("subagent_stop")[0]
        assert record["outcome_kind"] == "rejected_attempt"
        assert read_metrics("asset_producer_done") == []

    def test_invalid_block_is_an_attempt_not_a_producer_failure(self):
        message = producer_report("DONE").replace('"unit_id": "ui_kit"', '"unit_id": ""')
        _, _, parsed = stop("ap-badblock", message)
        assert is_blocked(parsed)
        record = read_metrics("subagent_stop")[0]
        assert record["outcome_kind"] == "rejected_attempt"
        assert "unit_id" in record["outcome_error"]
        assert read_metrics("asset_producer_failed") == []


class TestForceAllowNeverTerminal:
    """The anti-deadloop escape hatch releases the agent, it does not accept
    the report. An unvalidated report must not claim the terminal outcome.
    """

    INVALID = producer_report("DONE", unit_id="")

    def _exhaust_block_limit(self, agent_id, message):
        """Two rejections, so the third stop hits BLOCK_LIMIT force-allow."""
        for _ in range(2):
            _, _, parsed = stop(agent_id, message)
            assert is_blocked(parsed)

    def test_third_invalid_attempt_is_unverified_not_terminal(self):
        self._exhaust_block_limit("ap-force", self.INVALID)

        _, code, parsed = stop("ap-force", self.INVALID)
        assert code == 0
        assert not is_blocked(parsed), "force-allow must release the agent"

        stops = read_metrics("subagent_stop")
        assert len(stops) == 3
        assert [s["outcome_kind"] for s in stops] == [
            "rejected_attempt", "rejected_attempt", "unverified",
        ]
        assert not [s for s in stops if s["outcome_kind"] == "terminal"]

    def test_force_allowed_report_writes_no_outcome_event(self):
        self._exhaust_block_limit("ap-force2", self.INVALID)
        stop("ap-force2", self.INVALID)

        for event in ("asset_producer_done", "asset_producer_partial",
                      "asset_producer_failed"):
            assert read_metrics(event) == [], f"{event} written for an unvalidated report"

    def test_missing_block_cannot_be_force_allowed_into_a_result(self):
        """The markdown fallback must not supply a status the block never had."""
        no_block = producer_report("DONE").split("### Machine Outcome")[0]
        self._exhaust_block_limit("ap-force3", no_block)
        stop("ap-force3", no_block)

        record = read_metrics("subagent_stop")[-1]
        assert record["outcome_kind"] == "unverified"
        assert record["status"] == "DONE", "the prose status is still recorded, just not trusted"
        assert record["unit_id"] is None
        assert read_metrics("asset_producer_done") == []

    def test_force_allow_warning_tells_the_manager_it_is_unverified(self):
        self._exhaust_block_limit("ap-force4", self.INVALID)
        stdout, _, _ = stop("ap-force4", self.INVALID)
        assert stdout == "", "force-allow must not print a block decision"

        gate = read_metrics("gate_check")[-1]
        assert gate["result"] == "force_allow"
        assert gate["report_type"] == "asset-producer"

    def test_a_valid_retry_after_force_allow_is_still_terminal(self):
        """The escape hatch must not permanently poison the agent's outcome."""
        self._exhaust_block_limit("ap-force5", self.INVALID)
        stop("ap-force5", self.INVALID)
        assert read_metrics("asset_producer_partial") == []

        stop("ap-force5", producer_report("PARTIAL"))
        stops = read_metrics("subagent_stop")
        assert stops[-1]["outcome_kind"] == "terminal"
        partial = read_metrics("asset_producer_partial")
        assert len(partial) == 1
        assert partial[0]["blockers"]
