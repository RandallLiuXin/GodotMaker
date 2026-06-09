"""Tests for check_worker_report.py hook."""
import pytest
from .helpers import run_hook, is_blocked, cleanup_metrics, write_current_role

HOOK = "check_worker_report.py"

COMPLETE_WORKER = (
    "## Report: PlayerMovement\n\n"
    "### Status: DONE\n\n"
    "### Files Changed\n- player_system.gd: created\n\n"
    "### Tests\n#### Unit Tests\n- test/test_player.gd: 3 tests, 3 passed\n"
    "- Commands run: godot --headless\n\n"
    "### Build\n- Status: PASS\n\n"
    "### Memory Entry\nLearned about movement"
)

COMPLETE_VERIFIER = (
    "## Verification Report: Integration\n\n"
    "### Overall: PASS\n\n"
    "### Results\n### Check: build\n**Command run:** godot --headless\n\n"
    "### Adversarial Probes\n### Check: boundary\n**Command run:** test edge"
)

COMPLETE_REVIEWER = (
    "## Review Report: PlayerSystem\n\n"
    "### Reviewers Matched\n| physics | yes | uses CharacterBody2D |\n\n"
    "### ECS Review\n- Components pure data: PASS — C_Velocity and C_Health contain only exported vars, no logic\n"
    "- System read/write declarations match actual usage in process() — verified DAG is clean\n\n"
    "### Issues Found\n| # | Severity | Domain | Issue | Location |\n"
    "| 1 | minor | physics | collision mask not set for enemy layer | player.gd:10 |\n\n"
    "### Summary\n1 minor issue found, no critical blockers"
)

COMPLETE_ASSET_PRODUCER = (
    "## Asset Producer Report: ui_kit\n\n"
    "### Status: DONE\n\n"
    "### Production Unit\n- First Entry Document: references/production-units/ui-kit.md\n\n"
    "### Outputs\n- Sources: .godotmaker/asset-generation/sources/ui_source.png\n\n"
    "### Tools\n- python tools/asset_sheet_process.py --snap-mode autoslice\n\n"
    "### Validation\n- File existence: PASS\n\n"
    "### Handoff\nUpdate ASSETS.md row ui_kit to generated."
)

COMPLETE_ANALYST = (
    "## Analyst Report:\n\n"
    "### Status: DONE\n\n"
    "### Candidate Summary\n"
    "- Images: 1\n"
    "- Audio: 0\n"
    "- Matched ASSETS rows: 1\n"
    "- Uncertain: 0\n\n"
    "### Manifest\n"
    "- Path: assets/manifest.json\n"
    "- Status: updated\n\n"
    "### Row Matches\n"
    "- player_idle: assets/player.png (high; dimensions match)\n\n"
    "### Processing Sources\n"
    "- assets/ui/source.png: ui; run curation\n\n"
    "### Uncertain Files\n"
    "- none\n"
)


@pytest.fixture(autouse=True)
def clean():
    cleanup_metrics()
    write_current_role("build")
    yield
    cleanup_metrics()


class TestWorkerReport:
    def test_complete_report_allowed(self):
        _, _, parsed = run_hook(HOOK, {
            "hook_event_name": "SubagentStop",
            "agent_id": "w1",
            "last_assistant_message": COMPLETE_WORKER,
        })
        assert not is_blocked(parsed)

    @pytest.mark.parametrize("missing_section,remove", [
        ("Status", "### Status: DONE"),
        ("Tests", "### Tests"),
        ("Build", "### Build"),
        ("Memory Entry", "### Memory Entry"),
    ])
    def test_missing_section_blocked(self, missing_section, remove):
        msg = COMPLETE_WORKER.replace(remove, "### REMOVED")
        _, _, parsed = run_hook(HOOK, {
            "hook_event_name": "SubagentStop",
            "agent_id": "w1",
            "last_assistant_message": msg,
        })
        assert is_blocked(parsed), f"Should block when {missing_section} missing"

    def test_empty_tests_section_blocked(self):
        msg = COMPLETE_WORKER.replace(
            "#### Unit Tests\n- test/test_player.gd: 3 tests, 3 passed\n"
            "- Commands run: godot --headless",
            "Nothing here"
        )
        _, _, parsed = run_hook(HOOK, {
            "hook_event_name": "SubagentStop",
            "agent_id": "w1",
            "last_assistant_message": msg,
        })
        assert is_blocked(parsed), "Should block when Tests section has no substance"

    def test_unittest_only_allowed(self):
        """Worker report with unit tests but no e2e content is allowed.

        E2E is owned by the Evaluator (gm-evaluate); workers are forbidden
        from writing to e2e/ by check_file_permissions. The report hook
        must not demand e2e content from workers.
        """
        _, _, parsed = run_hook(HOOK, {
            "hook_event_name": "SubagentStop",
            "agent_id": "w1",
            "last_assistant_message": COMPLETE_WORKER,
        })
        assert not is_blocked(parsed), (
            "Worker report without e2e mention should be allowed"
        )


class TestVerifierReport:
    def test_complete_report_allowed(self):
        _, _, parsed = run_hook(HOOK, {
            "hook_event_name": "SubagentStop",
            "agent_id": "v1",
            "last_assistant_message": COMPLETE_VERIFIER,
        })
        assert not is_blocked(parsed)

    def test_missing_adversarial_blocked(self):
        msg = COMPLETE_VERIFIER.replace("### Adversarial Probes", "### REMOVED")
        _, _, parsed = run_hook(HOOK, {
            "hook_event_name": "SubagentStop",
            "agent_id": "v1",
            "last_assistant_message": msg,
        })
        assert is_blocked(parsed)


class TestReviewerReport:
    def test_complete_report_allowed(self):
        _, _, parsed = run_hook(HOOK, {
            "hook_event_name": "SubagentStop",
            "agent_id": "r1",
            "last_assistant_message": COMPLETE_REVIEWER,
        })
        assert not is_blocked(parsed)

    @pytest.mark.parametrize("section", [
        "### Reviewers Matched", "### ECS Review",
        "### Issues Found", "### Summary",
    ])
    def test_missing_section_blocked(self, section):
        msg = COMPLETE_REVIEWER.replace(section, "### REMOVED")
        _, _, parsed = run_hook(HOOK, {
            "hook_event_name": "SubagentStop",
            "agent_id": "r1",
            "last_assistant_message": msg,
        })
        assert is_blocked(parsed)


class TestAssetProducerReport:
    def test_complete_report_allowed(self):
        _, _, parsed = run_hook(HOOK, {
            "hook_event_name": "SubagentStop",
            "agent_id": "ap1",
            "agent_type": "asset-producer",
            "last_assistant_message": COMPLETE_ASSET_PRODUCER,
        })
        assert not is_blocked(parsed)

    @pytest.mark.parametrize("section", [
        "### Production Unit", "### Outputs", "### Tools",
        "### Validation", "### Handoff",
    ])
    def test_missing_section_blocked(self, section):
        msg = COMPLETE_ASSET_PRODUCER.replace(section, "### REMOVED")
        _, _, parsed = run_hook(HOOK, {
            "hook_event_name": "SubagentStop",
            "agent_id": "ap1",
            "agent_type": "asset-producer",
            "last_assistant_message": msg,
        })
        assert is_blocked(parsed)


class TestAnalystReport:
    def test_complete_report_allowed(self):
        _, _, parsed = run_hook(HOOK, {
            "hook_event_name": "SubagentStop",
            "agent_id": "a1",
            "agent_type": "analyst",
            "last_assistant_message": COMPLETE_ANALYST,
        })
        assert not is_blocked(parsed)

    @pytest.mark.parametrize("section", [
        "### Candidate Summary", "### Manifest",
        "### Row Matches", "### Processing Sources", "### Uncertain Files",
    ])
    def test_missing_section_blocked(self, section):
        msg = COMPLETE_ANALYST.replace(section, "### REMOVED")
        _, _, parsed = run_hook(HOOK, {
            "hook_event_name": "SubagentStop",
            "agent_id": "a1",
            "agent_type": "analyst",
            "last_assistant_message": msg,
        })
        assert is_blocked(parsed)


class TestFlexibleMarkerDetection:
    """Tests that report type is detected even with heading level variations."""

    def test_single_hash_worker(self):
        msg = COMPLETE_WORKER.replace("## Report:", "# Report:")
        _, _, parsed = run_hook(HOOK, {
            "hook_event_name": "SubagentStop",
            "agent_id": "w1",
            "last_assistant_message": msg,
        })
        assert not is_blocked(parsed)

    def test_triple_hash_worker(self):
        msg = COMPLETE_WORKER.replace("## Report:", "### Report:")
        _, _, parsed = run_hook(HOOK, {
            "hook_event_name": "SubagentStop",
            "agent_id": "w1",
            "last_assistant_message": msg,
        })
        assert not is_blocked(parsed)

    def test_triple_hash_verifier(self):
        msg = COMPLETE_VERIFIER.replace("## Verification Report:", "### Verification Report:")
        _, _, parsed = run_hook(HOOK, {
            "hook_event_name": "SubagentStop",
            "agent_id": "v1",
            "last_assistant_message": msg,
        })
        assert not is_blocked(parsed)

    def test_triple_hash_reviewer(self):
        msg = COMPLETE_REVIEWER.replace("## Review Report:", "### Review Report:")
        _, _, parsed = run_hook(HOOK, {
            "hook_event_name": "SubagentStop",
            "agent_id": "r1",
            "last_assistant_message": msg,
        })
        assert not is_blocked(parsed)

    def test_fallback_worker_by_status_section(self):
        """Worker detected by Status section when heading is missing entirely."""
        msg = (
            "Here is my report.\n\n"
            "### Status: DONE\n\n"
            "### Files Changed\n- player_system.gd: created\n\n"
            "### Tests\n#### Unit Tests\n- test/test_player.gd: 3 tests, 3 passed\n"
            "- Commands run: godot --headless\n\n"
            "### Build\n- Status: PASS\n\n"
            "### Memory Entry\nLearned about movement"
        )
        _, _, parsed = run_hook(HOOK, {
            "hook_event_name": "SubagentStop",
            "agent_id": "w1",
            "last_assistant_message": msg,
        })
        assert not is_blocked(parsed)

    def test_fallback_verifier_by_overall_section(self):
        """Verifier detected by Overall section when heading is missing."""
        msg = (
            "Verification complete.\n\n"
            "### Overall: PASS\n\n"
            "### Results\n### Check: build\n**Command run:** godot --headless\n\n"
            "### Adversarial Probes\n### Check: boundary\n**Command run:** test edge"
        )
        _, _, parsed = run_hook(HOOK, {
            "hook_event_name": "SubagentStop",
            "agent_id": "v1",
            "last_assistant_message": msg,
        })
        assert not is_blocked(parsed)


class TestEdgeCases:
    def test_no_current_role_allows_regular_subagent_output(self):
        cleanup_metrics()
        _, code, parsed = run_hook(HOOK, {
            "hook_event_name": "SubagentStop",
            "agent_id": "x1",
            "last_assistant_message": COMPLETE_WORKER.replace("### Tests", "### REMOVED"),
        })
        assert code == 0
        assert not is_blocked(parsed)

    def test_unknown_report_type_allowed(self):
        _, code, parsed = run_hook(HOOK, {
            "hook_event_name": "SubagentStop",
            "agent_id": "x1",
            "last_assistant_message": "Just a regular message",
        })
        assert code == 0
        assert not is_blocked(parsed)

    def test_non_stop_event_ignored(self):
        _, code, _ = run_hook(HOOK, {
            "hook_event_name": "SubagentStart",
            "agent_id": "w1",
        })
        assert code == 0

    def test_empty_message(self):
        _, code, _ = run_hook(HOOK, {
            "hook_event_name": "SubagentStop",
            "agent_id": "w1",
            "last_assistant_message": "",
        })
        assert code == 0


class TestDeadloopProtection:
    """Tests for per-agent block counter and force-allow after BLOCK_LIMIT."""

    def _block_agent_n_times(self, agent_id: str, n: int):
        """Send a bad report n times to accumulate blocks."""
        msg = COMPLETE_WORKER.replace("### Status: DONE", "### REMOVED")
        for _ in range(n):
            run_hook(HOOK, {
                "hook_event_name": "SubagentStop",
                "agent_id": agent_id,
                "last_assistant_message": msg,
            })

    def test_blocks_under_limit(self):
        """Agent blocked fewer than BLOCK_LIMIT (2) times is still blocked."""
        msg = COMPLETE_WORKER.replace("### Status: DONE", "### REMOVED")
        self._block_agent_n_times("dl1", 1)
        _, _, parsed = run_hook(HOOK, {
            "hook_event_name": "SubagentStop",
            "agent_id": "dl1",
            "last_assistant_message": msg,
        })
        assert is_blocked(parsed), "Should still block under limit"

    def test_force_allow_at_limit(self):
        """Agent blocked BLOCK_LIMIT (2) times is force-allowed."""
        msg = COMPLETE_WORKER.replace("### Status: DONE", "### REMOVED")
        self._block_agent_n_times("dl2", 2)
        # Next attempt should be force-allowed (output on stderr, not stdout)
        _, code, parsed = run_hook(HOOK, {
            "hook_event_name": "SubagentStop",
            "agent_id": "dl2",
            "last_assistant_message": msg,
        })
        assert code == 0
        assert not is_blocked(parsed), "Should force-allow after BLOCK_LIMIT"

    def test_per_agent_isolation(self):
        """Block count for one agent does not affect another."""
        msg = COMPLETE_WORKER.replace("### Status: DONE", "### REMOVED")
        self._block_agent_n_times("dl3", 2)
        # Different agent should still be blocked normally
        _, _, parsed = run_hook(HOOK, {
            "hook_event_name": "SubagentStop",
            "agent_id": "dl4",
            "last_assistant_message": msg,
        })
        assert is_blocked(parsed), "Different agent should not be affected"
