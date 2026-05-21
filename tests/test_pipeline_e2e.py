"""End-to-end tests for the gm-* role-based pipeline.

Simulates the full scaffold → gdd → asset → build → verify → evaluate →
accept → finalize lifecycle by writing state files and invoking hooks.
Verifies that hooks enforce the right rules at each transition and that
role permissions align with each gm-* skill's contract.

These tests don't run real Claude sessions — they exercise the file-state
machinery (current_role, stage.jsonl, evaluation.json, final_report.json)
and the hooks that police it.
"""
import json
import os
import shutil
import tempfile

import pytest

from tests.hooks.helpers import (
    run_hook as _run_hook,
    is_blocked,
    write_current_role,
    write_completed_roles,
    write_metrics,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_SRC = os.path.join(REPO_ROOT, "config", "stage_schemas.json")


# ---------------------------------------------------------------------------
# Local thin wrapper: e2e tests use (code, parsed) signature
# ---------------------------------------------------------------------------

def run_hook(script: str, payload: dict) -> tuple[int, dict | None]:
    """Run a hook script against the current working directory."""
    _, code, parsed = _run_hook(script, payload)
    return code, parsed


# ---------------------------------------------------------------------------
# E2E-specific payload builders (not duplicated in helpers)
# ---------------------------------------------------------------------------

def write_stage_payload(events) -> dict:
    """Produce a Write tool_input payload that records role completion events.

    Accepts:
    - dict {role: ts}: convenience form, expanded to one event per pair
      (chronological order via dict iteration / insertion order)
    - list[dict]: explicit list of {"role": X, "ts": Y} events
    """
    if isinstance(events, dict):
        events = [{"role": r, "ts": ts} for r, ts in events.items()]
    content = "".join(json.dumps(e) + "\n" for e in events)
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {
            "file_path": ".godotmaker/stage.jsonl",
            "content": content,
        },
    }


def agent_dispatch_payload() -> dict:
    return {
        "tool_name": "Agent",
        "tool_input": {"prompt": "implement system"},
        "agent_id": "",
    }


def file_write_payload(file_path: str, agent_id: str = "") -> dict:
    return {
        "tool_name": "Write",
        "tool_input": {"file_path": file_path},
        "agent_id": agent_id,
    }


def _minimal_pass_report() -> dict:
    """Schema-valid verify_report.json with all checks passing.

    Mirrors the schema in skills/core/gm-verify/SKILL.md Output Format
    Section B — every required field present, all arrays empty. Used by
    fixtures that need the verify-completion gate to pass without
    asserting on per-check content.
    """
    return {
        "result": "pass",
        "ts": "2026-01-01T03:00:00Z",
        "checks": {
            "build": {"result": "pass", "errors": []},
            "unit_tests": {
                "result": "pass",
                "passed": 0,
                "failed": 0,
                "failures": [],
            },
            "lint": {
                "result": "pass",
                "issues": [],
                "format_drift": None,
            },
            "static_check": {"result": "pass", "issues": []},
        },
        "tooling_notes": [],
    }


def _write_minimal_playable_unit_plan_and_evaluation(result: str = "approve"):
    """Write the smallest PLAN/evaluation pair accepted by the evaluate gate."""
    with open("PLAN.md", "w", encoding="utf-8") as f:
        f.write("""# Game Plan

**Tag:** v0.1.0

## Playable Unit

- **Player experience:** start a run
- **Unit outcome:** exit reached through normal play
- **Scenes involved:** Main

| Mechanic | Player operation / content | Expected effect | Required visible content | Evidence |
|----------|----------------------------|-----------------|--------------------------|----------|
| [v0.1.0-M1] | Press Start | Gameplay scene opens | Player visible | e2e assertion |

## Main Build

| # | Task | Status | Notes |
|---|------|--------|-------|
| M | Main build | verified | |
""")
    os.makedirs("e2e", exist_ok=True)
    with open("e2e/test_v0_1_0_playable_unit_start.py", "w", encoding="utf-8") as f:
        f.write("def test_placeholder():\n    assert True\n")
    with open(".godotmaker/evaluation.json", "w", encoding="utf-8") as f:
        json.dump({
            "tag": "v0.1.0",
            "result": result,
            "playable_closed_loop": {
                "builds_clean": True,
                "boots_main_scene": True,
                "playable_unit_coverage": True,
                "completion_fail_or_exit_reached": True,
            },
            "playable_unit": {
                "result": "pass",
                "rows": {
                    "v0.1.0-M1": {
                        "result": "pass",
                        "test": "e2e/test_v0_1_0_playable_unit_start.py",
                        "evidence": ["e2e/screenshots/start.png"],
                    },
                },
            },
            "critical_issues": [],
        }, f)


@pytest.fixture
def project_dir():
    """Temp project with deployed stage_schemas.json. Auto-restores cwd."""
    original = os.getcwd()
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        os.makedirs(".godotmaker", exist_ok=True)
        shutil.copy(SCHEMA_SRC, ".godotmaker/stage_schemas.json")
        yield tmpdir
        os.chdir(original)


# ---------------------------------------------------------------------------
# Phase 1 — Scaffold + GDD + Asset (replaces old monolithic Setup)
# ---------------------------------------------------------------------------

def scaffold_done():
    """Mark scaffold artifacts present (project.godot is the canonical marker)."""
    open("project.godot", "w").close()


class TestScaffoldPhase:
    def test_scaffold_completion_requires_project_godot(self, project_dir):
        """stage_reminder blocks scaffold completion until project.godot exists."""
        code, parsed = run_hook("stage_reminder.py",
                                write_stage_payload({"scaffold": "2026-01-01T00:00:00Z"}))
        assert is_blocked(parsed)

    def test_scaffold_completion_succeeds_with_project_godot(self, project_dir):
        scaffold_done()
        code, parsed = run_hook("stage_reminder.py",
                                write_stage_payload({"scaffold": "2026-01-01T00:00:00Z"}))
        assert code == 0
        assert not is_blocked(parsed)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "/gm-gdd" in ctx


class TestGDDPhase:
    def test_build_blocked_before_gdd(self, project_dir):
        """Worker dispatch in build role must fail until gdd completes."""
        scaffold_done()
        write_current_role("build")
        code, parsed = run_hook("check_stage_prerequisites.py", agent_dispatch_payload())
        assert is_blocked(parsed)

    def test_gdd_completion_requires_files(self, project_dir):
        code, parsed = run_hook("stage_reminder.py",
                                write_stage_payload({"gdd": "2026-01-01T01:00:00Z"}))
        assert is_blocked(parsed)

    def test_gdd_completion_succeeds_with_files(self, project_dir):
        for f in ["GDD.md", "PLAN.md", "STRUCTURE.md", "STYLE.md", "ASSETS.md", "SCENES.md", "TOC.md", "ROADMAP.md"]:
            open(f, "w").close()
        code, parsed = run_hook("stage_reminder.py",
                                write_stage_payload({"gdd": "2026-01-01T01:00:00Z"}))
        assert code == 0
        assert not is_blocked(parsed)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "/gm-asset" in ctx


class TestAssetPhase:
    def test_asset_dispatch_passes_through_with_no_prereqs(self, project_dir):
        """Asset role self-validates via SKILL.md Resume Check; the dispatch
        hook does NOT enforce stage-schema prereqs for asset. This test pins
        the intentional design — even with project.godot, gdd, and required
        files all missing, the hook lets the dispatch through. If asset is
        ever added back to WORKER_DISPATCH_ROLES, this test starts failing."""
        write_current_role("asset")
        # No project.godot, no completed gdd, no GDD.md / PLAN.md / STRUCTURE.md.
        code, parsed = run_hook("check_stage_prerequisites.py", agent_dispatch_payload())
        assert code == 0
        assert not is_blocked(parsed)

    def test_asset_main_can_only_write_assets_md(self, project_dir):
        write_current_role("asset")
        _, parsed = run_hook("check_file_permissions.py",
                             file_write_payload("ASSETS.md"))
        assert not is_blocked(parsed)
        for path in ["assets/sprite.png", "PLAN.md", "src/x.gd"]:
            _, parsed = run_hook("check_file_permissions.py",
                                 file_write_payload(path))
            assert is_blocked(parsed), f"asset main must block {path}"

    def test_asset_completion_reminds_build(self, project_dir):
        _, parsed = run_hook("stage_reminder.py",
                             write_stage_payload({"asset": "2026-01-01T01:30:00Z"}))
        assert not is_blocked(parsed)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "/gm-build" in ctx


# ---------------------------------------------------------------------------
# Phase 2 — Build dispatch + diligence
# ---------------------------------------------------------------------------

class TestBuildPhase:
    def gdd_complete(self):
        scaffold_done()
        for f in ["GDD.md", "PLAN.md", "STRUCTURE.md", "STYLE.md", "ASSETS.md", "SCENES.md", "TOC.md", "ROADMAP.md"]:
            open(f, "w").close()
        write_completed_roles({"gdd": "2026-01-01T01:00:00Z"})

    def test_worker_dispatch_allowed_after_gdd(self, project_dir):
        self.gdd_complete()
        write_current_role("build")
        code, parsed = run_hook("check_stage_prerequisites.py", agent_dispatch_payload())
        assert code == 0
        assert not is_blocked(parsed)

    def test_build_role_cannot_write_game_code(self, project_dir):
        self.gdd_complete()
        write_current_role("build")
        for ext in [".gd", ".tscn", ".tres"]:
            _, parsed = run_hook("check_file_permissions.py",
                                 file_write_payload(f"systems/x{ext}"))
            assert is_blocked(parsed), f"build role must not write {ext}"

    def test_build_role_can_update_plan(self, project_dir):
        self.gdd_complete()
        write_current_role("build")
        _, parsed = run_hook("check_file_permissions.py",
                             file_write_payload("PLAN.md"))
        assert not is_blocked(parsed)

    def test_worker_blocked_from_e2e(self, project_dir):
        self.gdd_complete()
        write_current_role("build")
        _, parsed = run_hook("check_file_permissions.py",
                             file_write_payload("e2e/test_x.py", agent_id="w1"))
        assert is_blocked(parsed)

    def test_build_completion_blocks_with_pending_tasks(self, project_dir):
        self.gdd_complete()
        with open("PLAN.md", "w") as f:
            f.write("# Plan\n| 1 | move | pending |\n")
        _, parsed = run_hook("stage_reminder.py",
                             write_stage_payload({"build": "2026-01-01T02:00:00Z"}))
        assert is_blocked(parsed)

    def test_build_completion_succeeds_when_all_verified(self, project_dir):
        self.gdd_complete()
        with open("PLAN.md", "w") as f:
            f.write("# Plan\n| 1 | move | verified |\n| 2 | jump | verified |\n")
        _, parsed = run_hook("stage_reminder.py",
                             write_stage_payload({"build": "2026-01-01T02:00:00Z"}))
        assert not is_blocked(parsed)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "/gm-verify" in ctx


# ---------------------------------------------------------------------------
# Phase 3 — Verify transition
# ---------------------------------------------------------------------------

class TestVerifyPhase:
    def test_verify_is_read_only_main(self, project_dir):
        write_current_role("verify")
        for path in ["systems/x.gd", "PLAN.md", "MEMORY.md", "e2e/test.py"]:
            _, parsed = run_hook("check_file_permissions.py",
                                 file_write_payload(path))
            assert is_blocked(parsed), f"verify must block {path}"

    def test_verify_can_write_verify_report(self, project_dir):
        """Verify role's third write exception (per gm-verify SKILL.md
        'Session Setup'). The other two — stage.jsonl and current_role —
        are covered in tests/hooks/test_check_file_permissions.py."""
        write_current_role("verify")
        _, parsed = run_hook("check_file_permissions.py",
                             file_write_payload(".godotmaker/verify_report.json"))
        assert not is_blocked(parsed)

    def test_verify_does_not_run_diligence_check(self, project_dir):
        """verify role skips check_completion entirely."""
        write_current_role("verify")
        write_metrics([
            {"event": "subagent_start", "agent_id": "w1", "role": "worker"},
        ])
        code, parsed = run_hook("check_completion.py", {
            "hook_event_name": "Stop",
            "agent_id": "",
        })
        assert code == 0
        assert not is_blocked(parsed)

    def test_verify_completion_blocks_without_report(self, project_dir):
        """stage_reminder must block the verify completion event when
        .godotmaker/verify_report.json is missing — that file is the
        feedback channel /gm-build and /gm-fixgap consume to know
        what failed last verify."""
        _, parsed = run_hook("stage_reminder.py",
                             write_stage_payload({"verify": "2026-01-01T03:00:00Z"}))
        assert is_blocked(parsed)
        assert "verify_report.json" in parsed.get(
            "hookSpecificOutput", {}).get("permissionDecisionReason", "")

    def test_verify_completion_succeeds_with_report(self, project_dir):
        with open(".godotmaker/verify_report.json", "w", encoding="utf-8") as f:
            json.dump(_minimal_pass_report(), f)
        code, parsed = run_hook("stage_reminder.py",
                                write_stage_payload({"verify": "2026-01-01T03:00:00Z"}))
        assert code == 0
        assert not is_blocked(parsed)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "/gm-evaluate" in ctx


# ---------------------------------------------------------------------------
# Phase 4 — Evaluate isolation
# ---------------------------------------------------------------------------

class TestEvaluatePhase:
    def test_evaluate_blocked_from_game_code(self, project_dir):
        write_current_role("evaluate")
        for path in ["systems/x.gd", "scenes/y.tscn"]:
            _, parsed = run_hook("check_file_permissions.py",
                                 file_write_payload(path))
            assert is_blocked(parsed)

    def test_evaluate_can_write_e2e(self, project_dir):
        write_current_role("evaluate")
        _, parsed = run_hook("check_file_permissions.py",
                             file_write_payload("e2e/test_game.py"))
        assert not is_blocked(parsed)

    def test_evaluate_can_write_evaluation_json(self, project_dir):
        write_current_role("evaluate")
        _, parsed = run_hook("check_file_permissions.py",
                             file_write_payload(".godotmaker/evaluation.json"))
        assert not is_blocked(parsed)

    def test_evaluate_completion_requires_evaluation_json(self, project_dir):
        _, parsed = run_hook("stage_reminder.py",
                             write_stage_payload({"evaluate": "2026-01-01T05:00:00Z"}))
        assert is_blocked(parsed)

    def test_evaluate_completion_reminds_both_branches(self, project_dir):
        _write_minimal_playable_unit_plan_and_evaluation()
        _, parsed = run_hook("stage_reminder.py",
                             write_stage_payload({"evaluate": "2026-01-01T05:00:00Z"}))
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "/gm-accept" in ctx
        assert "/gm-fixgap" in ctx


# ---------------------------------------------------------------------------
# Phase 5 — Fixgap loop
# ---------------------------------------------------------------------------

class TestFixgapPhase:
    def test_fixgap_blocked_without_evaluation(self, project_dir):
        write_current_role("fixgap")
        write_completed_roles({"gdd": "t1", "build": "t2", "verify": "t3"})
        _, parsed = run_hook("check_stage_prerequisites.py", agent_dispatch_payload())
        assert is_blocked(parsed)

    def test_fixgap_allowed_after_evaluation(self, project_dir):
        write_current_role("fixgap")
        write_completed_roles({
            "gdd": "t1", "build": "t2", "verify": "t3", "evaluate": "t4",
        })
        with open(".godotmaker/evaluation.json", "w") as f:
            f.write('{"result": "reject"}')
        code, parsed = run_hook("check_stage_prerequisites.py", agent_dispatch_payload())
        assert code == 0
        assert not is_blocked(parsed)

    def test_fixgap_chains_back_to_verify(self, project_dir):
        _, parsed = run_hook("stage_reminder.py",
                             write_stage_payload({"fixgap": "2026-01-01T06:00:00Z"}))
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "/gm-verify" in ctx

    def test_fixgap_requires_full_diligence(self, project_dir):
        """Fixgap diligence requires both verifier AND reviewer
        (mirrors gm-fixgap Hard Rule 6 + Step 4)."""
        write_current_role("fixgap")
        write_metrics([
            {"event": "subagent_start", "agent_id": "w1", "role": "worker"},
            {"event": "subagent_start", "agent_id": "v1", "role": "verifier"},
        ])
        code, parsed = run_hook("check_completion.py", {
            "hook_event_name": "Stop",
            "agent_id": "",
        })
        assert is_blocked(parsed), "Fixgap with no reviewer must block"
        assert "reviewer" in parsed.get("reason", "").lower()


# ---------------------------------------------------------------------------
# Phase 6 — Accept + Finalize closure
# ---------------------------------------------------------------------------

class TestClosurePhase:
    def test_accept_can_update_planning_docs(self, project_dir):
        write_current_role("accept")
        _, parsed = run_hook("check_file_permissions.py",
                             file_write_payload("GDD.md"))
        assert not is_blocked(parsed)

    def test_accept_blocked_from_game_code(self, project_dir):
        write_current_role("accept")
        _, parsed = run_hook("check_file_permissions.py",
                             file_write_payload("systems/x.gd"))
        assert is_blocked(parsed)

    def test_accept_chains_to_finalize(self, project_dir):
        _, parsed = run_hook("stage_reminder.py",
                             write_stage_payload({"accept": "2026-01-01T07:00:00Z"}))
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "/gm-finalize" in ctx

    def test_finalize_completion_requires_report(self, project_dir):
        _, parsed = run_hook("stage_reminder.py",
                             write_stage_payload({"finalize": "2026-01-01T08:00:00Z"}))
        assert is_blocked(parsed)

    def test_finalize_completion_succeeds_with_report(self, project_dir):
        with open(".godotmaker/final_report.json", "w") as f:
            f.write('{"status": "completed"}')
        code, parsed = run_hook("stage_reminder.py",
                                write_stage_payload({"finalize": "2026-01-01T08:00:00Z"}))
        assert code == 0
        # Finalize is the terminal role — no next reminder
        if parsed:
            assert "additionalContext" not in parsed.get("hookSpecificOutput", {})


# ---------------------------------------------------------------------------
# Cross-phase guarantees
# ---------------------------------------------------------------------------

class TestSessionStartClearsRole:
    """Each new session begins with a clean role lock."""

    def test_session_start_removes_stale_role(self, project_dir):
        write_current_role("build")
        assert os.path.isfile(".godotmaker/current_role")
        run_hook("session_start.py", {"hook_event_name": "SessionStart"})
        assert not os.path.isfile(".godotmaker/current_role"), \
            "session_start must delete stale current_role"


class TestFullLifecycleHappyPath:
    """Walk through every role transition for a happy-path build."""

    def test_full_pipeline(self, project_dir):
        # Scaffold
        write_current_role("scaffold")
        open("project.godot", "w").close()
        _, parsed = run_hook("stage_reminder.py",
                             write_stage_payload({"scaffold": "t0"}))
        assert "/gm-gdd" in parsed["hookSpecificOutput"]["additionalContext"]

        # GDD
        write_completed_roles({"scaffold": "t0"})
        write_current_role("gdd")
        for f in ["GDD.md", "PLAN.md", "STRUCTURE.md", "STYLE.md", "ASSETS.md", "SCENES.md", "TOC.md", "ROADMAP.md"]:
            open(f, "w").close()
        _, parsed = run_hook("stage_reminder.py",
                             write_stage_payload({"scaffold": "t0", "gdd": "t1"}))
        assert "/gm-asset" in parsed["hookSpecificOutput"]["additionalContext"]

        # Asset
        write_completed_roles({"scaffold": "t0", "gdd": "t1"})
        write_current_role("asset")
        _, parsed = run_hook("stage_reminder.py",
                             write_stage_payload({"scaffold": "t0", "gdd": "t1", "asset": "t1b"}))
        assert "/gm-build" in parsed["hookSpecificOutput"]["additionalContext"]

        # Build
        write_completed_roles({"scaffold": "t0", "gdd": "t1", "asset": "t1b"})
        write_current_role("build")
        _, parsed = run_hook("check_stage_prerequisites.py", agent_dispatch_payload())
        assert not is_blocked(parsed)
        with open("PLAN.md", "w") as f:
            f.write("# Plan\n| 1 | x | verified |\n")
        _, parsed = run_hook("stage_reminder.py",
                             write_stage_payload({"scaffold": "t0", "gdd": "t1",
                                                  "asset": "t1b", "build": "t2"}))
        assert "/gm-verify" in parsed["hookSpecificOutput"]["additionalContext"]

        # Verify
        write_completed_roles({"scaffold": "t0", "gdd": "t1",
                               "asset": "t1b", "build": "t2"})
        write_current_role("verify")
        with open(".godotmaker/verify_report.json", "w", encoding="utf-8") as f:
            json.dump(_minimal_pass_report(), f)
        _, parsed = run_hook("stage_reminder.py", write_stage_payload(
            {"scaffold": "t0", "gdd": "t1", "asset": "t1b",
             "build": "t2", "verify": "t3"}))
        assert "/gm-evaluate" in parsed["hookSpecificOutput"]["additionalContext"]

        # Evaluate (approve)
        write_completed_roles({"scaffold": "t0", "gdd": "t1", "asset": "t1b",
                               "build": "t2", "verify": "t3"})
        write_current_role("evaluate")
        _write_minimal_playable_unit_plan_and_evaluation()
        _, parsed = run_hook("stage_reminder.py", write_stage_payload(
            {"scaffold": "t0", "gdd": "t1", "asset": "t1b",
             "build": "t2", "verify": "t3", "evaluate": "t4"}))
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "/gm-accept" in ctx

        # Accept
        write_completed_roles({
            "scaffold": "t0", "gdd": "t1", "asset": "t1b",
            "build": "t2", "verify": "t3", "evaluate": "t4",
        })
        write_current_role("accept")
        _, parsed = run_hook("stage_reminder.py", write_stage_payload({
            "scaffold": "t0", "gdd": "t1", "asset": "t1b",
            "build": "t2", "verify": "t3", "evaluate": "t4", "accept": "t5",
        }))
        assert "/gm-finalize" in parsed["hookSpecificOutput"]["additionalContext"]

        # Finalize
        write_completed_roles({
            "scaffold": "t0", "gdd": "t1", "asset": "t1b",
            "build": "t2", "verify": "t3", "evaluate": "t4", "accept": "t5",
        })
        write_current_role("finalize")
        with open(".godotmaker/final_report.json", "w") as f:
            f.write('{"status": "completed"}')
        code, parsed = run_hook("stage_reminder.py", write_stage_payload({
            "scaffold": "t0", "gdd": "t1", "asset": "t1b",
            "build": "t2", "verify": "t3", "evaluate": "t4",
            "accept": "t5", "finalize": "t6",
        }))
        assert code == 0
