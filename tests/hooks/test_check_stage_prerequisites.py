"""Tests for check_stage_prerequisites.py hook (role-based pipeline).

This hook only enforces for build/fixgap roles before Agent dispatch.
It checks that the prerequisite role is completed and its outputs exist.
"""
import os
import shutil
import pytest
import tempfile
from .helpers import (
    run_hook, is_blocked, cleanup_metrics,
    write_completed_roles, write_current_role,
)

SCHEMA_SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config", "stage_schemas.json"
)

HOOK = "check_stage_prerequisites.py"

AGENT_INPUT = {
    "tool_name": "Agent",
    "tool_input": {"prompt": "implement player"},
    "agent_id": "",
}


@pytest.fixture(autouse=True)
def clean():
    yield
    cleanup_metrics()


@pytest.fixture
def project_dir():
    """Create a temp directory with role-based stage_schemas.json and chdir."""
    original = os.getcwd()
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        os.makedirs(".godotmaker", exist_ok=True)
        shutil.copy(SCHEMA_SRC, ".godotmaker/stage_schemas.json")
        yield tmpdir
        os.chdir(original)


class TestRoleSkipping:
    @pytest.mark.parametrize("role",
                             ["scaffold", "gdd", "asset", "verify", "evaluate", "accept", "finalize"])
    def test_non_dispatch_roles_pass_through(self, project_dir, role):
        write_current_role(role)
        _, code, parsed = run_hook(HOOK, AGENT_INPUT)
        assert code == 0
        assert not is_blocked(parsed)

    def test_no_role_passes_through(self, project_dir):
        _, code, parsed = run_hook(HOOK, AGENT_INPUT)
        assert code == 0
        assert not is_blocked(parsed)


class TestAssetIntentionallyUnenforced:
    """Asset role dispatches analyst, not workers; this hook does NOT check
    asset's preconditions (project.godot / ASSETS.md). Asset self-validates
    via SKILL.md Resume Check. These tests pin that intentional design — if
    asset is later added to PREREQ_ROLE in check_stage_prerequisites.py, the
    bypass tests below will start failing (because the hook will then look up
    a prereq role and enforce its files exist)."""

    def test_asset_passes_with_no_prereqs_at_all(self, project_dir):
        write_current_role("asset")
        # No project.godot, no completed gdd, no GDD.md/PLAN.md/STRUCTURE.md.
        # Hook still allows because asset is not in WORKER_DISPATCH_ROLES.
        _, code, parsed = run_hook(HOOK, AGENT_INPUT)
        assert code == 0
        assert not is_blocked(parsed)

    def test_asset_passes_even_when_only_scaffold_missing(self, project_dir):
        write_current_role("asset")
        write_completed_roles(["gdd"])
        for f in ["GDD.md", "PLAN.md", "STRUCTURE.md", "STYLE.md", "ASSETS.md", "SCENES.md", "TOC.md", "ROADMAP.md"]:
            open(f, "w").close()
        # project.godot deliberately absent — would block build, but asset is
        # exempt from the SCAFFOLD_REQUIRED check.
        _, code, parsed = run_hook(HOOK, AGENT_INPUT)
        assert code == 0
        assert not is_blocked(parsed)


class TestBuildPrerequisites:
    def test_block_when_scaffold_artifact_missing(self, project_dir):
        write_current_role("build")
        write_completed_roles(["gdd"])
        for f in ["GDD.md", "PLAN.md", "STRUCTURE.md", "STYLE.md", "ASSETS.md", "SCENES.md", "TOC.md", "ROADMAP.md"]:
            open(f, "w").close()
        # No project.godot
        _, _, parsed = run_hook(HOOK, AGENT_INPUT)
        assert is_blocked(parsed)
        reason = parsed.get(
            "hookSpecificOutput", {}).get("permissionDecisionReason", "").lower()
        assert "project.godot" in reason or "scaffold" in reason

    def test_block_when_gdd_not_complete(self, project_dir):
        write_current_role("build")
        open("project.godot", "w").close()
        # No completed roles
        _, _, parsed = run_hook(HOOK, AGENT_INPUT)
        assert is_blocked(parsed)
        assert "gdd" in parsed.get(
            "hookSpecificOutput", {}).get("permissionDecisionReason", "").lower()

    def test_block_when_gdd_complete_but_files_missing(self, project_dir):
        write_current_role("build")
        open("project.godot", "w").close()
        write_completed_roles(["gdd"])
        _, _, parsed = run_hook(HOOK, AGENT_INPUT)
        assert is_blocked(parsed)

    def test_allow_when_gdd_files_and_scaffold_present(self, project_dir):
        write_current_role("build")
        open("project.godot", "w").close()
        write_completed_roles(["gdd"])
        for f in ["GDD.md", "PLAN.md", "STRUCTURE.md", "STYLE.md", "ASSETS.md", "SCENES.md", "TOC.md", "ROADMAP.md"]:
            open(f, "w").close()
        _, code, parsed = run_hook(HOOK, AGENT_INPUT)
        assert code == 0
        assert not is_blocked(parsed)


class TestFixgapPrerequisites:
    def test_block_when_evaluate_not_complete(self, project_dir):
        write_current_role("fixgap")
        write_completed_roles(["gdd", "build", "verify"])  # no evaluate
        _, _, parsed = run_hook(HOOK, AGENT_INPUT)
        assert is_blocked(parsed)

    def test_block_when_evaluation_json_missing(self, project_dir):
        write_current_role("fixgap")
        write_completed_roles(["gdd", "build", "verify", "evaluate"])
        # but no evaluation.json
        _, _, parsed = run_hook(HOOK, AGENT_INPUT)
        assert is_blocked(parsed)

    def test_allow_when_evaluation_complete(self, project_dir):
        write_current_role("fixgap")
        write_completed_roles(["gdd", "build", "verify", "evaluate"])
        with open(".godotmaker/evaluation.json", "w") as f:
            f.write('{"result": "reject"}')
        _, code, parsed = run_hook(HOOK, AGENT_INPUT)
        assert code == 0
        assert not is_blocked(parsed)


class TestNonAgentTool:
    def test_write_tool_ignored(self, project_dir):
        write_current_role("build")
        _, code, parsed = run_hook(HOOK, {
            "tool_name": "Write",
            "tool_input": {"file_path": "foo.gd"},
            "agent_id": "",
        })
        assert code == 0
        assert not is_blocked(parsed)

    def test_subagent_dispatch_ignored(self, project_dir):
        write_current_role("build")
        _, code, parsed = run_hook(HOOK, {
            "tool_name": "Agent",
            "tool_input": {"prompt": "verify build"},
            "agent_id": "worker-123",
        })
        assert code == 0
        assert not is_blocked(parsed)
