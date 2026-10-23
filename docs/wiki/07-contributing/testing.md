# Testing

Run the suite on the supported baseline: Python 3.10+, Node.js 22+, and Godot
4.5+. Tests under `tests/` cover hooks, asset/runtime contracts, publish and
migration tools, project checks, and the end-to-end pipeline. Run the full suite
with:

```bash
python -m pytest tests/ -x -q
```

The `-x` flag stops at the first failure. Drop it to see all failures at once. `pyproject.toml` sets `pythonpath = ["hooks"]` so that `from metrics import ...` resolves in hook tests without any install step.

---

## Test layout

```
tests/
├── assets/                               Asset family and compiler contracts
├── agent_runtimes/                       Runtime adapter contracts
├── hooks/                                Hook behavior and shared helpers
├── tools/                                CLI and publishing tests
└── test_*.py                             Cross-layer and pipeline contracts
```

Test modules are grouped by the behavior they prove; they do not maintain a
one-file-per-production-file mirror. Use `pytest --collect-only` or `rg --files
tests` when you need the current inventory. `test_pipeline_e2e.py` exercises the
publish → session start → role sequence at a coarse level.

---

## Adding tests for a new hook

Hook tests follow a consistent pattern: build a synthetic JSON payload, run the hook as a subprocess, and assert whether it blocked.

### The helpers

`tests/hooks/helpers.py` provides four utilities used by every hook test:

**`run_hook(script_name, input_data)`** — spawns the hook script as a subprocess, sends `input_data` as JSON on stdin, and returns `(stdout_text, exit_code, parsed_json)`. Locates the script in `hooks/` relative to the project root. Uses a 10-second timeout.

**`is_blocked(parsed)`** — checks whether the parsed JSON response is a block decision. Handles both the PreToolUse format (`hookSpecificOutput.permissionDecision == "deny"`) and the Stop/SubagentStop format (`decision == "block"`).

**`write_completed_roles(roles)`** — writes `.godotmaker/stage.jsonl` with role-completion events. Accepts a list of role name strings, a dict of `{role: timestamp}`, or a list of raw event dicts.

**`write_current_role(role)`** — writes `.godotmaker/current_role` with the given role name.

**`write_metrics(events)`** — writes `.godotmaker/metrics_current.jsonl` with the given event list.

**`cleanup_metrics()`** — removes `.godotmaker/` entirely. Call this in `teardown_method` to keep tests isolated.

### Example: a hook test

```python
import os
import pytest
from helpers import (
    run_hook, is_blocked,
    write_current_role, write_completed_roles, cleanup_metrics
)


class TestMyHook:
    def setup_method(self):
        # Set up the filesystem state the hook expects
        write_completed_roles(["scaffold", "gdd"])
        write_current_role("build")

    def teardown_method(self):
        cleanup_metrics()

    def test_allows_valid_write(self):
        event = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "src/player.gd", "content": "extends Node"},
            "agent_id": "worker-1"
        }
        stdout, code, parsed = run_hook("my_hook.py", event)
        assert not is_blocked(parsed)

    def test_blocks_protected_path(self):
        event = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "PLAN.md", "content": "# Plan"},
            "agent_id": "worker-1"
        }
        stdout, code, parsed = run_hook("my_hook.py", event)
        assert is_blocked(parsed)
```

Key points:
- Every test is self-contained: set up in `setup_method`, tear down in `teardown_method`.
- Use `write_completed_roles` to control which roles have completed in `stage.jsonl`.
- Use `write_current_role` to control the active role for permission checks.
- `is_blocked` handles both response formats; do not inspect the raw JSON structure directly.

---

## Adding tests for a new tool

Tool tests use standard pytest patterns. `tests/tools/conftest.py` provides shared fixtures.

```python
from pathlib import Path


def test_my_tool_feature(tmp_path):
    # Create minimal fixture files
    (tmp_path / "project.godot").write_text("[gd_resource]")

    # Import and call the function directly
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tools"))
    from my_tool import my_function

    result = my_function(tmp_path)
    assert result == expected_value
```

Use `tmp_path` (pytest's built-in fixture) for filesystem isolation. If the tool calls subprocesses, mock them with `unittest.mock.patch`. If the tool requires a network call (e.g., API key checks), mark the test:

```python
import pytest

@pytest.mark.network
def test_requires_api():
    ...
```

Skip network tests locally with:

```bash
python -m pytest tests/ -m "not network" -x -q
```

---

## Pre-commit and CI

The repository pre-commit hook runs fast staged checks: Python lint for staged files, user-doc Chinese mirror checks, and secret scanning when the local tools are installed. Tests run on every pull request via CI. Running the full suite locally before opening a PR is expected:

```bash
python -m pytest tests/ -x -q
```

If you are adding a new hook, also run the shared-refs publish test to confirm the manifest is valid:

```bash
python -m pytest tests/tools/test_publish_shared.py -q
```
