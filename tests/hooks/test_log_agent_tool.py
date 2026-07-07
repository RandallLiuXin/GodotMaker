"""Tests for log_agent_tool.py — PreToolUse + PostToolUse Agent capture.

Covers the success path (input/output files written), the no-op paths
(non-Agent tools, empty content), and the atomicity invariant
(no 0-byte stubs, even when target name pre-exists). The 0-byte stub
regression is the failure mode the old SubagentStart/Stop logger
exhibited in the 2026-05-09 e2e session — 37 of 38 trace files were
zero bytes — so guarding against it is the primary correctness
contract this hook upholds.
"""
import json
import os
import tempfile
import pytest
from .helpers import run_hook

HOOK = "log_agent_tool.py"
TRACES = os.path.join(".godotmaker", "traces")


@pytest.fixture
def project_dir():
    original = os.getcwd()
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        yield tmpdir
        os.chdir(original)


def _input_path(tool_use_id: str) -> str:
    return os.path.join(TRACES, f"agent_{tool_use_id}_input.json")


def _output_path(tool_use_id: str) -> str:
    return os.path.join(TRACES, f"agent_{tool_use_id}_output.md")


class TestPreToolUseAgent:
    def test_saves_tool_input_as_pretty_json(self, project_dir):
        _, code, _ = run_hook(HOOK, {
            "hook_event_name": "PreToolUse",
            "tool_name": "Agent",
            "tool_use_id": "toolu_01abc",
            "tool_input": {
                "prompt": "Investigate the auth bug",
                "description": "Investigate auth bug",
                "subagent_type": "worker",
                "model": "sonnet",
            },
        })
        assert code == 0
        path = _input_path("toolu_01abc")
        assert os.path.exists(path)
        loaded = json.loads(open(path, encoding="utf-8").read())
        assert loaded["prompt"] == "Investigate the auth bug"
        assert loaded["subagent_type"] == "worker"
        assert loaded["model"] == "sonnet"

    def test_legacy_task_tool_name_also_captured(self, project_dir):
        # Anthropic's tools/AgentTool/constants.ts exports both 'Agent'
        # and 'Task' (legacy) — both should route through.
        _, code, _ = run_hook(HOOK, {
            "hook_event_name": "PreToolUse",
            "tool_name": "Task",
            "tool_use_id": "toolu_legacy",
            "tool_input": {"prompt": "do the thing", "subagent_type": "Explore"},
        })
        assert code == 0
        assert os.path.exists(_input_path("toolu_legacy"))

    def test_non_agent_tool_no_file(self, project_dir):
        _, code, _ = run_hook(HOOK, {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_use_id": "toolu_bash01",
            "tool_input": {"command": "npm test"},
        })
        assert code == 0
        assert not os.path.exists(_input_path("toolu_bash01"))
        # And the traces dir wasn't even created on a no-op.
        assert not os.path.exists(TRACES)

    def test_empty_tool_input_no_file(self, project_dir):
        _, code, _ = run_hook(HOOK, {
            "hook_event_name": "PreToolUse",
            "tool_name": "Agent",
            "tool_use_id": "toolu_empty",
            "tool_input": {},
        })
        assert code == 0
        # Empty dict is falsy in our check — same reason as 'no content'.
        assert not os.path.exists(_input_path("toolu_empty"))


class TestPostToolUseAgent:
    def test_saves_tool_response_as_string(self, project_dir):
        _, code, _ = run_hook(HOOK, {
            "hook_event_name": "PostToolUse",
            "tool_name": "Agent",
            "tool_use_id": "toolu_02xyz",
            "tool_input": {"prompt": "..."},
            "tool_response": "Subagent found 3 endpoints in src/routes/.\nDetails: ...",
        })
        assert code == 0
        path = _output_path("toolu_02xyz")
        assert os.path.exists(path)
        body = open(path, encoding="utf-8").read()
        assert "Subagent found 3 endpoints" in body
        # Must NOT be the 0-byte regression we're guarding against.
        assert os.path.getsize(path) > 0

    def test_dict_response_serialized_as_json(self, project_dir):
        # tool_response is `unknown` per schema; if Anthropic ever passes
        # a dict (or wraps the string in a structured envelope), don't
        # crash and don't leave a 0-byte stub.
        _, code, _ = run_hook(HOOK, {
            "hook_event_name": "PostToolUse",
            "tool_name": "Agent",
            "tool_use_id": "toolu_dict01",
            "tool_input": {"prompt": "..."},
            "tool_response": {"summary": "ok", "items": ["a", "b"]},
        })
        assert code == 0
        body = open(_output_path("toolu_dict01"), encoding="utf-8").read()
        assert "summary" in body and "ok" in body

    def test_empty_response_no_file(self, project_dir):
        _, code, _ = run_hook(HOOK, {
            "hook_event_name": "PostToolUse",
            "tool_name": "Agent",
            "tool_use_id": "toolu_blank",
            "tool_input": {"prompt": "..."},
            "tool_response": "",
        })
        assert code == 0
        # Empty content must NOT produce a 0-byte stub — that's the bug
        # this whole hook exists to fix.
        assert not os.path.exists(_output_path("toolu_blank"))

    def test_null_response_no_file(self, project_dir):
        _, code, _ = run_hook(HOOK, {
            "hook_event_name": "PostToolUse",
            "tool_name": "Agent",
            "tool_use_id": "toolu_null",
            "tool_input": {"prompt": "..."},
            "tool_response": None,
        })
        assert code == 0
        assert not os.path.exists(_output_path("toolu_null"))

    def test_non_agent_tool_no_file(self, project_dir):
        _, code, _ = run_hook(HOOK, {
            "hook_event_name": "PostToolUse",
            "tool_name": "Edit",
            "tool_use_id": "toolu_edit01",
            "tool_input": {"file_path": "/x"},
            "tool_response": "edit succeeded",
        })
        assert code == 0
        assert not os.path.exists(_output_path("toolu_edit01"))


class TestAtomicityAndPairing:
    def test_pair_written_under_shared_tool_use_id(self, project_dir):
        # The whole point of using PreToolUse/PostToolUse over the old
        # SubagentStart/Stop path is that tool_use_id is shared across
        # both events — pairing is trivial filename-prefix matching.
        run_hook(HOOK, {
            "hook_event_name": "PreToolUse",
            "tool_name": "Agent",
            "tool_use_id": "toolu_pair42",
            "tool_input": {"prompt": "p"},
        })
        run_hook(HOOK, {
            "hook_event_name": "PostToolUse",
            "tool_name": "Agent",
            "tool_use_id": "toolu_pair42",
            "tool_input": {"prompt": "p"},
            "tool_response": "result",
        })
        assert os.path.exists(_input_path("toolu_pair42"))
        assert os.path.exists(_output_path("toolu_pair42"))

    def test_re_fire_overwrites_cleanly_no_zero_byte(self, project_dir):
        # SubagentStop is documented as firing multiple times on retry.
        # PostToolUse can also re-fire in some circumstances; our atomic
        # tmpfile + os.replace pattern must keep the latest write whole
        # and leave no .tmp residue or 0-byte target on disk.
        for response in ["first", "second", "third final"]:
            run_hook(HOOK, {
                "hook_event_name": "PostToolUse",
                "tool_name": "Agent",
                "tool_use_id": "toolu_refire",
                "tool_input": {"prompt": "..."},
                "tool_response": response,
            })
        path = _output_path("toolu_refire")
        body = open(path, encoding="utf-8").read()
        assert body == "third final"
        assert os.path.getsize(path) == len("third final")
        # No leftover .tmp_* files in the traces dir.
        leftovers = [n for n in os.listdir(TRACES) if n.startswith(".tmp_")]
        assert leftovers == []

    def test_lone_surrogate_content_still_written(self, project_dir):
        # A lone Unicode surrogate (e.g. a byte that got surrogate-escaped
        # upstream and survived json.loads) makes a strict UTF-8 encoder raise
        # UnicodeEncodeError. That used to silently drop the whole trace file.
        # The write must succeed (backslashreplace) and leave no 0-byte stub,
        # and the input.json must still be JSON-parseable.
        _, code, _ = run_hook(HOOK, {
            "hook_event_name": "PreToolUse",
            "tool_name": "Agent",
            "tool_use_id": "toolu_surrogate",
            "tool_input": {"prompt": "bad byte here: \udce9 done"},
        })
        assert code == 0
        path = _input_path("toolu_surrogate")
        assert os.path.exists(path)
        assert os.path.getsize(path) > 0
        # Valid UTF-8 on disk (strict read must not raise) and still JSON.
        loaded = json.loads(open(path, encoding="utf-8").read())
        assert "bad byte here" in loaded["prompt"]

    def test_path_traversal_in_tool_use_id_is_neutralized(self, project_dir):
        # tool_use_id is opaque and Anthropic-controlled in practice, but
        # treat it as untrusted: a `../` should never escape the traces
        # directory.
        run_hook(HOOK, {
            "hook_event_name": "PostToolUse",
            "tool_name": "Agent",
            "tool_use_id": "../../escape",
            "tool_input": {"prompt": "..."},
            "tool_response": "should not escape",
        })
        # The sanitized id collapses '..' to '_'; the file must land
        # inside .godotmaker/traces/, not outside.
        assert not os.path.exists(os.path.abspath("escape_output.md"))
        assert not os.path.exists(os.path.abspath("../escape_output.md"))
        # And the traces dir is the only place anything got written.
        produced = os.listdir(TRACES) if os.path.exists(TRACES) else []
        assert all(n.startswith("agent_") and n.endswith("_output.md") for n in produced)


class TestNeverBlocks:
    def test_unknown_event_no_op(self, project_dir):
        # Defensive: hook is registered for PreToolUse + PostToolUse only,
        # but if a future Claude Code rev wires it elsewhere we must not
        # crash or block.
        _, code, _ = run_hook(HOOK, {
            "hook_event_name": "Mystery",
            "tool_name": "Agent",
            "tool_use_id": "toolu_x",
            "tool_input": {"prompt": "p"},
        })
        assert code == 0

    def test_malformed_stdin_no_op(self):
        # Bypass run_hook (which always JSON-encodes input) and pipe
        # garbage directly. Hook must exit 0 — never block on parse failure.
        import subprocess
        import sys
        from .helpers import HOOKS_DIR
        result = subprocess.run(
            [sys.executable, os.path.join(HOOKS_DIR, HOOK)],
            input="not json {[",
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
