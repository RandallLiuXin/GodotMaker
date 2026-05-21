"""Tests for stage_reminder.py hook (role-based pipeline)."""
import json
import os
import shutil
import pytest
import tempfile
from .helpers import run_hook, is_blocked, cleanup_metrics

SCHEMA_SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config", "stage_schemas.json"
)

HOOK = "stage_reminder.py"


@pytest.fixture(autouse=True)
def clean():
    yield
    cleanup_metrics()


@pytest.fixture
def project_dir():
    original = os.getcwd()
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        # Always provide a schema so validation can run
        os.makedirs(".godotmaker", exist_ok=True)
        shutil.copy(SCHEMA_SRC, ".godotmaker/stage_schemas.json")
        yield tmpdir
        os.chdir(original)


def stage_jsonl(events: list[dict]) -> str:
    """events is a list of {"role": X, "ts": Y} dicts."""
    return "\n".join(json.dumps(e) for e in events) + "\n"


def write_minimal_playable_unit_plan():
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
""")


def write_minimal_playable_unit_evaluation(result: str = "approve"):
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


class TestNonStageWrites:
    def test_ignores_non_write_tool(self, project_dir):
        _, code, parsed = run_hook(HOOK, {
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": ".godotmaker/stage.jsonl"},
        })
        assert code == 0
        assert parsed is None

    def test_ignores_non_stage_file(self, project_dir):
        _, code, parsed = run_hook(HOOK, {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "src/main.gd", "content": "extends Node"},
        })
        assert code == 0
        assert parsed is None

    def test_ignores_wrong_event(self, project_dir):
        _, code, parsed = run_hook(HOOK, {
            "hook_event_name": "SubagentStop",
            "tool_name": "Write",
            "tool_input": {
                "file_path": ".godotmaker/stage.jsonl",
                "content": stage_jsonl([{"role": "gdd", "ts": "2026-01-01T00:00:00Z"}]),
            },
        })
        assert code == 0
        assert parsed is None


class TestRoleReminder:
    def test_scaffold_complete_reminds_gdd(self, project_dir):
        open("project.godot", "w").close()
        _, code, parsed = run_hook(HOOK, {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": ".godotmaker/stage.jsonl",
                "content": stage_jsonl([{"role": "scaffold", "ts": "2026-01-01T00:00:00Z"}]),
            },
        })
        assert code == 0
        assert parsed is not None
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "/gm-gdd" in ctx
        assert "scaffold" in ctx

    def test_gdd_complete_reminds_asset(self, project_dir):
        for f in ["GDD.md", "PLAN.md", "STRUCTURE.md", "STYLE.md", "ASSETS.md", "SCENES.md", "TOC.md", "ROADMAP.md"]:
            open(f, "w").close()
        _, code, parsed = run_hook(HOOK, {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": ".godotmaker/stage.jsonl",
                "content": stage_jsonl([{"role": "gdd", "ts": "2026-01-01T00:00:00Z"}]),
            },
        })
        assert code == 0
        assert parsed is not None
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "/gm-asset" in ctx
        assert "gdd" in ctx

    def test_asset_complete_reminds_build(self, project_dir):
        _, code, parsed = run_hook(HOOK, {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": ".godotmaker/stage.jsonl",
                "content": stage_jsonl([{"role": "asset", "ts": "2026-01-01T00:30:00Z"}]),
            },
        })
        assert code == 0
        assert parsed is not None
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "/gm-build" in ctx

    def test_evaluate_complete_reminds_accept_or_fixgap(self, project_dir):
        write_minimal_playable_unit_plan()
        write_minimal_playable_unit_evaluation()
        _, code, parsed = run_hook(HOOK, {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": ".godotmaker/stage.jsonl",
                "content": stage_jsonl([
                    {"role": "gdd", "ts": "2026-01-01T00:00:00Z"},
                    {"role": "evaluate", "ts": "2026-01-01T05:00:00Z"},
                ]),
            },
        })
        assert code == 0
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "/gm-accept" in ctx and "/gm-fixgap" in ctx

    def test_finalize_complete_no_reminder(self, project_dir):
        with open(".godotmaker/final_report.json", "w") as f:
            f.write('{"status": "completed"}')
        _, code, parsed = run_hook(HOOK, {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": ".godotmaker/stage.jsonl",
                "content": stage_jsonl([{"role": "finalize", "ts": "2026-01-01T07:00:00Z"}]),
            },
        })
        assert code == 0
        # No next role after finalize → no additionalContext
        assert parsed is None or "additionalContext" not in parsed.get("hookSpecificOutput", {})

    def test_windows_path(self, project_dir):
        for f in ["GDD.md", "PLAN.md", "STRUCTURE.md", "STYLE.md", "ASSETS.md", "SCENES.md", "TOC.md", "ROADMAP.md"]:
            open(f, "w").close()
        _, code, parsed = run_hook(HOOK, {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": "D:\\Games\\MyGame\\.godotmaker\\stage.jsonl",
                "content": stage_jsonl([{"role": "gdd", "ts": "2026-01-01T00:00:00Z"}]),
            },
        })
        assert code == 0
        assert parsed is not None
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "/gm-asset" in ctx

    def test_edit_tool_for_gdd_event_reminds_asset(self, project_dir):
        for f in ["GDD.md", "PLAN.md", "STRUCTURE.md", "STYLE.md", "ASSETS.md", "SCENES.md", "TOC.md", "ROADMAP.md"]:
            open(f, "w").close()
        _, code, parsed = run_hook(HOOK, {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": ".godotmaker/stage.jsonl",
                "old_string": '',
                "new_string": '{"role": "gdd", "ts": "2026-01-01T00:00:00Z"}\n',
            },
        })
        assert code == 0
        assert parsed is not None
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "/gm-asset" in ctx


class TestValidation:
    def test_missing_required_files_blocked(self, project_dir):
        # No GDD/PLAN/STRUCTURE files
        _, _, parsed = run_hook(HOOK, {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": ".godotmaker/stage.jsonl",
                "content": stage_jsonl([{"role": "gdd", "ts": "2026-01-01T00:00:00Z"}]),
            },
        })
        assert is_blocked(parsed)
        reason = parsed["hookSpecificOutput"]["permissionDecisionReason"]
        assert "GDD.md" in reason or "PLAN.md" in reason

    def test_evaluate_blocks_when_playable_unit_contract_missing(self, project_dir):
        with open(".godotmaker/evaluation.json", "w", encoding="utf-8") as f:
            f.write('{"result": "approve"}')
        _, _, parsed = run_hook(HOOK, {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": ".godotmaker/stage.jsonl",
                "content": stage_jsonl([{"role": "evaluate", "ts": "2026-01-01T05:00:00Z"}]),
            },
        })
        assert is_blocked(parsed)
        reason = parsed["hookSpecificOutput"]["permissionDecisionReason"]
        assert "Playable Unit evaluation contract failed" in reason
        assert "PLAN.md" in reason

    def test_evaluate_blocks_when_playable_unit_row_uncovered(self, project_dir):
        write_minimal_playable_unit_plan()
        with open(".godotmaker/evaluation.json", "w", encoding="utf-8") as f:
            json.dump({
                "result": "approve",
                "playable_closed_loop": {
                    "playable_unit_coverage": True,
                    "completion_fail_or_exit_reached": True,
                },
                "playable_unit": {"rows": {}},
                "critical_issues": [],
            }, f)
        _, _, parsed = run_hook(HOOK, {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": ".godotmaker/stage.jsonl",
                "content": stage_jsonl([{"role": "evaluate", "ts": "2026-01-01T05:00:00Z"}]),
            },
        })
        assert is_blocked(parsed)
        reason = parsed["hookSpecificOutput"]["permissionDecisionReason"]
        assert "v0.1.0-M1 missing" in reason

    def test_build_blocked_when_plan_has_pending(self, project_dir):
        with open("PLAN.md", "w") as f:
            f.write("# Plan\n| 1 | move | pending |\n")
        _, _, parsed = run_hook(HOOK, {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": ".godotmaker/stage.jsonl",
                "content": stage_jsonl([{"role": "build", "ts": "2026-01-01T01:00:00Z"}]),
            },
        })
        assert is_blocked(parsed)

    def test_build_passes_when_plan_all_verified(self, project_dir):
        with open("PLAN.md", "w") as f:
            f.write("# Plan\n| 1 | move | verified |\n")
        _, code, parsed = run_hook(HOOK, {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": ".godotmaker/stage.jsonl",
                "content": stage_jsonl([{"role": "build", "ts": "2026-01-01T01:00:00Z"}]),
            },
        })
        assert code == 0
        # Should produce a reminder, not block
        assert not is_blocked(parsed)


class TestTagArchived:
    """check_tag_archived runs at finalize completion. Reads PLAN.md's
    `**Tag:**` header to know which docs/tags/<Tag>/ archive to verify.
    """

    REQUIRED_FILES = [
        "GDD-snapshot.md", "PLAN.md", "STRUCTURE.md", "STYLE.md", "SCENES.md",
        "MEMORY.md", "evaluation-final.json", "CHANGELOG.md",
    ]

    def _write_finalize_event(self) -> dict:
        return {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": ".godotmaker/stage.jsonl",
                "content": stage_jsonl([{"role": "finalize", "ts": "2026-05-07T12:00:00Z"}]),
            },
        }

    def test_blocks_when_plan_md_missing(self, project_dir):
        _, _, parsed = run_hook(HOOK, self._write_finalize_event())
        assert is_blocked(parsed)
        reason = parsed["hookSpecificOutput"]["permissionDecisionReason"]
        assert "PLAN.md" in reason

    def test_blocks_when_plan_lacks_tag_header(self, project_dir):
        with open("PLAN.md", "w", encoding="utf-8") as f:
            f.write("# Plan\nno tag header here\n")
        _, _, parsed = run_hook(HOOK, self._write_finalize_event())
        assert is_blocked(parsed)
        reason = parsed["hookSpecificOutput"]["permissionDecisionReason"]
        assert "Tag" in reason

    def test_blocks_when_tag_directory_missing(self, project_dir):
        with open("PLAN.md", "w", encoding="utf-8") as f:
            f.write("# Plan\n\n**Tag:** v0.3.0\n")
        _, _, parsed = run_hook(HOOK, self._write_finalize_event())
        assert is_blocked(parsed)
        reason = parsed["hookSpecificOutput"]["permissionDecisionReason"]
        assert "docs/tags/v0.3.0/" in reason

    def test_blocks_when_archive_files_missing(self, project_dir):
        with open("PLAN.md", "w", encoding="utf-8") as f:
            f.write("# Plan\n\n**Tag:** v0.1.0\n")
        os.makedirs(os.path.join("docs", "tags", "v0.1.0"), exist_ok=True)
        # Create only some files
        for f in ["GDD-snapshot.md", "PLAN.md"]:
            open(os.path.join("docs", "tags", "v0.1.0", f), "w").close()
        _, _, parsed = run_hook(HOOK, self._write_finalize_event())
        assert is_blocked(parsed)
        reason = parsed["hookSpecificOutput"]["permissionDecisionReason"]
        # Should list missing files
        assert "STRUCTURE.md" in reason or "evaluation-final.json" in reason

    def test_passes_when_archive_complete(self, project_dir):
        with open("PLAN.md", "w", encoding="utf-8") as f:
            f.write("# Plan\n\n**Tag:** v0.1.0\n")
        archive = os.path.join("docs", "tags", "v0.1.0")
        os.makedirs(archive, exist_ok=True)
        for f in self.REQUIRED_FILES:
            open(os.path.join(archive, f), "w").close()
        # finalize schema also requires final_report.json
        with open(".godotmaker/final_report.json", "w") as f:
            f.write('{"status": "tag_sealed"}')
        _, code, parsed = run_hook(HOOK, self._write_finalize_event())
        assert code == 0
        assert not is_blocked(parsed)


class TestEdgeCases:
    def test_invalid_json_content(self, project_dir):
        _, code, parsed = run_hook(HOOK, {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": ".godotmaker/stage.jsonl",
                "content": "not json",
            },
        })
        assert code == 0
        assert parsed is None

    def test_lines_without_role_or_ts_ignored(self, project_dir):
        """JSONL lines that lack role/ts fields should be skipped (no reminder)."""
        _, code, parsed = run_hook(HOOK, {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": ".godotmaker/stage.jsonl",
                "content": '{"other_field": 1}\n{"only_role": "setup"}\n',
            },
        })
        assert code == 0
        assert parsed is None
