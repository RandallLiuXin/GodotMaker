"""Every runtime must deny delegated roles the project memory notebook.

The enforcement surface differs — Claude Code and OpenCode have a hook on the
write path, Codex and Pi have only the prompt — so this asserts each runtime's
*effective* permission path actually carries the rule, rather than assuming one
runtime's mechanism covers the rest.
"""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import publish  # noqa: E402

RUNTIMES = ["claude-code", "codex", "opencode", "pi"]


def _read(*parts: str) -> str:
    return REPO_ROOT.joinpath(*parts).read_text(encoding="utf-8")


def test_shared_worker_role_states_the_rule():
    worker = _read("agents", "worker.md")
    assert "MEMORY.md" in worker
    assert "memory/" in worker
    assert "Never write project memory" in worker


def test_worker_role_no_longer_asks_for_a_memory_entry():
    worker = _read("agents", "worker.md")
    assert "### Memory Entry" not in worker
    assert "MEMORY entry" not in worker


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_published_worker_role_keeps_the_rule(runtime):
    """Publish rewrites frontmatter and paths; the rule must survive that."""
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
    settings = json.loads(
        _read("agent-runtimes", "claude-code", "config", "settings.json"))
    commands = [
        hook["command"]
        for entry in settings["hooks"]["PreToolUse"]
        if entry["matcher"] == "Write|Edit"
        for hook in entry["hooks"]
    ]
    assert any("check_file_permissions.py" in c for c in commands)


def test_opencode_plugin_gates_child_session_writes():
    plugin = _read("agent-runtimes", "opencode", "plugins", "godotmaker-hooks.js")
    assert 'permission_scope: "memory"' in plugin
    assert "is_subagent: true" in plugin


@pytest.mark.parametrize("runtime", ["codex", "opencode", "pi"])
def test_runtime_mapping_documents_the_boundary(runtime):
    mapping = _read("agent-runtimes", runtime, "references", "runtime-mapping.md")
    assert "MEMORY.md" in mapping
    assert "memory" in mapping


def test_pi_delegate_prompt_carries_the_rule():
    """Pi has no write hook, so the delegate prompt is the only surface."""
    extension = _read("agent-runtimes", "pi", "extensions", "godotmaker-runtime.ts")
    assert "Never write the project memory notebook" in extension


def test_dispatch_protocol_forbids_memory_writes_and_asks_for_no_learnings():
    dispatch = _read("skills", "core", "_shared", "worker-dispatch.md")
    assert "DO NOT write `MEMORY.md`" in dispatch
    assert "MEMORY entry: discoveries" not in dispatch
    assert "MEMORY entry is mandatory" not in dispatch


@pytest.mark.parametrize("skill", ["gm-build", "gm-fixgap"])
def test_worker_dispatch_skills_own_memory_themselves(skill):
    text = _read("skills", "core", skill, "SKILL.md")
    assert "Never transcribe a worker report into memory." in text
    assert "worker_error" in text
