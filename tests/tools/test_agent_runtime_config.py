"""`.godotmaker/config.yaml` reads resolve top-level keys only.

The config template documents a `pipeline:` block carrying its own keys, so a
reader that strips a line before matching treats those as project settings.
That let a nested `godot_path:` shadow the real one and a nested `agent:`
decide the project's runtime.
"""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import agent_runtime


def _project(tmp_path: Path, body: str) -> Path:
    (tmp_path / ".godotmaker").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".godotmaker" / "config.yaml").write_text(body, encoding="utf-8")
    return tmp_path


NESTED_BLOCK = (
    "# GodotMaker project configuration\n"
    "pipeline:\n"
    "  model: sonnet\n"
    "  godot_path: /nested/wrong\n"
    "  agent: codex\n"
)


def test_a_nested_key_does_not_shadow_the_top_level_one(tmp_path):
    config = _project(tmp_path, NESTED_BLOCK + "godot_path: /real/godot\n")
    assert agent_runtime._read_yaml_scalar(
        config / ".godotmaker" / "config.yaml", "godot_path") == "/real/godot"


def test_a_key_that_only_exists_nested_is_not_read(tmp_path):
    config = _project(tmp_path, NESTED_BLOCK)
    path = config / ".godotmaker" / "config.yaml"
    assert agent_runtime._read_yaml_scalar(path, "agent") is None
    assert agent_runtime._read_yaml_scalar(path, "model") is None


def test_a_nested_agent_does_not_select_the_runtime(tmp_path):
    """Without a real top-level key, detection falls through to its default."""
    assert agent_runtime.detect_agent(_project(tmp_path, NESTED_BLOCK)) == \
        agent_runtime.AGENT_CLAUDE_CODE


def test_a_top_level_agent_still_wins_over_a_nested_one(tmp_path):
    assert agent_runtime.detect_agent(
        _project(tmp_path, NESTED_BLOCK + "agent: opencode\n")
    ) == agent_runtime.AGENT_OPENCODE


@pytest.mark.parametrize("body,expected", [
    ("agent: codex\n", "codex"),
    ("agent: claude\n", "claude-code"),
    ('agent: "pi"\n', "pi"),
    ("# agent: codex\n", "claude-code"),
])
def test_ordinary_top_level_reads_are_unchanged(tmp_path, body, expected):
    assert agent_runtime.detect_agent(_project(tmp_path, body)) == expected
