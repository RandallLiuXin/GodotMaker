"""Tests for the reminder-only stage_reminder.py hook."""
import json
import os
import tempfile

import pytest

from .helpers import cleanup_metrics, is_blocked, run_hook


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
        os.makedirs(".godotmaker", exist_ok=True)
        yield tmpdir
        os.chdir(original)


def payload(event: dict, *, tool_name: str = "Write", windows_path: bool = False):
    content_key = "content" if tool_name == "Write" else "new_string"
    file_path = ".godotmaker\\stage.jsonl" if windows_path else ".godotmaker/stage.jsonl"
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": {
            "file_path": file_path,
            content_key: json.dumps(event) + "\n",
        },
    }


def test_ignores_non_write_tool(project_dir):
    _, code, parsed = run_hook(HOOK, {
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "tool_input": {"file_path": ".godotmaker/stage.jsonl"},
    })
    assert code == 0
    assert parsed is None


def test_ignores_non_stage_file(project_dir):
    _, code, parsed = run_hook(HOOK, {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "src/main.gd", "content": "extends Node"},
    })
    assert code == 0
    assert parsed is None


@pytest.mark.parametrize(
    "role,next_command",
    [
        ("scaffold", "/gm-gdd"),
        ("gdd", "/gm-asset"),
        ("asset", "/gm-build"),
        ("build", "/gm-verify"),
        ("verify", "/gm-evaluate"),
        ("evaluate", "/gm-accept"),
        ("fixgap", "/gm-verify"),
        ("accept", "/gm-finalize"),
    ],
)
def test_role_completion_reminds_next_command(project_dir, role, next_command):
    _, code, parsed = run_hook(
        HOOK,
        payload({"role": role, "ts": "2026-01-01T00:00:00Z"}),
    )
    assert code == 0
    assert not is_blocked(parsed)
    assert next_command in parsed["hookSpecificOutput"]["additionalContext"]


def test_missing_outputs_do_not_turn_reminder_into_enforcement(project_dir):
    _, code, parsed = run_hook(
        HOOK,
        payload({"role": "gdd", "ts": "2026-01-01T00:00:00Z"}),
    )
    assert code == 0
    assert not is_blocked(parsed)
    assert "/gm-asset" in parsed["hookSpecificOutput"]["additionalContext"]


def test_fixgap_handoff_uses_event_next_role(project_dir):
    with open("GAP.md", "w", encoding="utf-8") as handle:
        handle.write("# Evaluator-owned gap\n")
    _, code, parsed = run_hook(
        HOOK,
        payload({
            "role": "fixgap",
            "ts": "2026-01-01T00:00:00Z",
            "outcome": "handoff",
            "next_role": "evaluate",
        }),
    )
    assert code == 0
    assert not is_blocked(parsed)
    assert parsed["hookSpecificOutput"]["additionalContext"].endswith(
        "Next: /gm-evaluate"
    )


def test_finalize_has_no_next_role(project_dir):
    _, code, parsed = run_hook(
        HOOK,
        payload({"role": "finalize", "ts": "2026-01-01T00:00:00Z"}),
    )
    assert code == 0
    assert parsed is None


@pytest.mark.parametrize("tool_name,windows_path", [("Edit", False), ("Write", True)])
def test_edit_and_windows_paths_are_supported(project_dir, tool_name, windows_path):
    _, code, parsed = run_hook(
        HOOK,
        payload(
            {"role": "gdd", "ts": "2026-01-01T00:00:00Z"},
            tool_name=tool_name,
            windows_path=windows_path,
        ),
    )
    assert code == 0
    assert "/gm-asset" in parsed["hookSpecificOutput"]["additionalContext"]


def test_invalid_json_is_ignored(project_dir):
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
