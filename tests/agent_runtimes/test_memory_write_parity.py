"""Memory ownership must survive each runtime's published Worker contract."""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import publish  # noqa: E402


def _read(*parts: str) -> str:
    return REPO_ROOT.joinpath(*parts).read_text(encoding="utf-8")


def test_worker_role_replaces_memory_entry_with_a_memory_prohibition():
    worker = _read("agents", "worker.md")
    assert "Never write project memory" in worker
    assert "### Memory Entry" not in worker
    assert "MEMORY entry (<100 words)" not in worker


@pytest.mark.parametrize("runtime", ["claude-code", "codex", "opencode", "pi"])
def test_published_worker_role_keeps_the_boundary(runtime):
    source = _read("agents", "worker.md")
    if runtime == "opencode":
        rendered = publish.render_opencode_agent_role_text(source, "worker")
    elif runtime == "pi":
        rendered = publish.render_pi_agent_role_text(source, "worker")
    else:
        rendered = source
    assert "Never write project memory" in rendered
    assert "### Memory Entry" not in rendered


def test_claude_code_registers_the_write_gate():
    settings = json.loads(_read(
        "agent-runtimes", "claude-code", "config", "settings.json"))
    commands = [
        hook["command"]
        for entry in settings["hooks"]["PreToolUse"]
        if entry["matcher"] == "Write|Edit"
        for hook in entry["hooks"]
    ]
    assert any("check_file_permissions.py" in command for command in commands)


def test_opencode_selects_the_identity_free_memory_scope():
    plugin = _read(
        "agent-runtimes", "opencode", "plugins", "godotmaker-hooks.js")
    assert 'permission_scope: "memory"' in plugin
    assert "is_subagent: true" in plugin


@pytest.mark.parametrize("runtime", ["codex", "opencode", "pi"])
def test_runtime_mapping_states_the_actual_boundary(runtime):
    mapping = _read(
        "agent-runtimes", runtime, "references", "runtime-mapping.md")
    assert "MEMORY.md" in mapping
    assert "memory/" in mapping


def test_pi_delegate_prompt_carries_the_prompt_level_boundary():
    extension = _read(
        "agent-runtimes", "pi", "extensions", "godotmaker-runtime.ts")
    assert "Never write the root MEMORY.md" in extension


def test_dispatch_protocol_does_not_request_learnings():
    dispatch = _read("skills", "core", "_shared", "worker-dispatch.md")
    assert "DO NOT write the root `MEMORY.md`" in dispatch
    assert "MEMORY entry: discoveries" not in dispatch
    assert "MEMORY entry is mandatory" not in dispatch
