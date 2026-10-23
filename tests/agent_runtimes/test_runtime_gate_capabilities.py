"""Contract tests for runtime-specific enforcement classes."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
RUNTIMES = ("claude-code", "codex", "opencode", "pi")
EXPECTED = {
    "claude-code": {
        "worker_dispatch_prerequisites": "native",
        "delegated_write_boundaries": "native",
        "stage_completion": "tool-owned",
    },
    "codex": {
        "worker_dispatch_prerequisites": "prompt-level",
        "delegated_write_boundaries": "prompt-level",
        "stage_completion": "tool-owned",
    },
    "opencode": {
        "worker_dispatch_prerequisites": "native",
        "delegated_write_boundaries": "native",
        "stage_completion": "tool-owned",
    },
    "pi": {
        "worker_dispatch_prerequisites": "prompt-level",
        "delegated_write_boundaries": "prompt-level",
        "stage_completion": "tool-owned",
    },
}
ROW = re.compile(
    r"^\| `(?P<gate>[^`]+)` \| `(?P<class>native|tool-owned|prompt-level|unsupported)` \|",
    re.MULTILINE,
)


def _mapping(runtime: str) -> str:
    return (
        ROOT / "agent-runtimes" / runtime / "references" / "runtime-mapping.md"
    ).read_text(encoding="utf-8")


def test_runtime_gate_matrix_declares_real_enforcement_classes():
    for runtime in RUNTIMES:
        rows = {match["gate"]: match["class"] for match in ROW.finditer(_mapping(runtime))}
        assert rows == EXPECTED[runtime], runtime


def test_completion_authority_is_portable_and_not_a_parity_hook():
    for runtime in RUNTIMES:
        mapping = _mapping(runtime)
        completion_row = next(
            line for line in mapping.splitlines()
            if line.startswith("| `stage_completion` |")
        )
        assert "tools/append_stage_event.py" in completion_row
        assert "WOR-464" in completion_row
        assert "hook parity" not in completion_row.lower()


def test_runtime_invocation_surfaces_match_the_matrix():
    claude_settings = (
        ROOT / "agent-runtimes" / "claude-code" / "config" / "settings.json"
    ).read_text(encoding="utf-8")
    codex_hooks = (
        ROOT / "agent-runtimes" / "codex" / "config" / "hooks.json"
    ).read_text(encoding="utf-8")
    opencode_plugin = (
        ROOT / "agent-runtimes" / "opencode" / "plugins" / "godotmaker-hooks.js"
    ).read_text(encoding="utf-8")
    pi_extension = (
        ROOT / "agent-runtimes" / "pi" / "extensions" / "godotmaker-runtime.ts"
    ).read_text(encoding="utf-8")

    assert '"matcher": "Agent|Task"' in claude_settings
    assert '"PreToolUse"' not in codex_hooks
    assert 'if (tool === "task")' in opencode_plugin
    assert '"check_stage_prerequisites.py"' in opencode_plugin
    assert "check_stage_prerequisites.py" not in pi_extension
    assert "check_file_permissions.py" not in pi_extension
