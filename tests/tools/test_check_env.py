"""Tests for check_env.py."""
import os
import sys
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tools",
))

from check_env import EnvCheck, get_version, parse_version


class TestEnvCheck:
    def test_initial_state(self):
        r = EnvCheck()
        assert r.passed == []
        assert r.failed == []
        assert r.warnings == []

    def test_ok_records(self):
        r = EnvCheck()
        r.ok("test passed")
        assert "test passed" in r.passed
        assert len(r.failed) == 0

    def test_fail_records(self):
        r = EnvCheck()
        r.fail("test failed")
        assert "test failed" in r.failed
        assert len(r.passed) == 0

    def test_warn_records(self):
        r = EnvCheck()
        r.warn("test warning")
        assert "test warning" in r.warnings

    def test_mixed(self):
        r = EnvCheck()
        r.ok("a")
        r.fail("b")
        r.warn("c")
        assert len(r.passed) == 1
        assert len(r.failed) == 1
        assert len(r.warnings) == 1


class TestParseVersion:
    def test_three_part(self):
        assert parse_version("4.4.1") == (4, 4, 1)

    def test_two_part(self):
        assert parse_version("3.9") == (3, 9)

    def test_comparison(self):
        assert parse_version("4.4.0") >= (4, 4)
        assert parse_version("4.3.9") < (4, 4)
        assert parse_version("2.30.0") >= (2, 30)
        assert parse_version("2.29.0") < (2, 30)

    def test_major_version(self):
        assert parse_version("18.0.0") >= (18,)
        assert parse_version("16.5.0") < (18,)


class TestGetVersion:
    @patch("check_env.subprocess.run")
    def test_extracts_version(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="git version 2.37.3.windows.1\n",
            stderr="",
        )
        assert get_version("git") == "2.37.3"

    @patch("check_env.subprocess.run")
    def test_version_from_stderr(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="",
            stderr="Python 3.10.9\n",
        )
        assert get_version("python") == "3.10.9"

    @patch("check_env.subprocess.run")
    def test_no_match_returns_none(self, mock_run):
        mock_run.return_value = MagicMock(stdout="no version here\n", stderr="")
        assert get_version("foo") is None

    @patch("check_env.subprocess.run", side_effect=FileNotFoundError)
    def test_missing_command_returns_none(self, mock_run):
        assert get_version("nonexistent") is None

    @patch("check_env.subprocess.run", side_effect=subprocess.TimeoutExpired("x", 10))
    def test_timeout_returns_none(self, mock_run):
        assert get_version("slow") is None

    @patch("check_env.subprocess.run")
    def test_node_version(self, mock_run):
        mock_run.return_value = MagicMock(stdout="v24.14.0\n", stderr="")
        assert get_version("node") == "24.14.0"

    @patch("check_env.subprocess.run")
    def test_godot_version(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="Godot Engine v4.4.stable.official\n",
            stderr="",
        )
        assert get_version("godot") == "4.4"


class TestCheckFunctions:
    """Test individual check functions with mocked externals."""

    @patch("check_env.get_version", return_value="2.37.3")
    @patch("check_env.subprocess.run")
    def test_check_git_pass(self, mock_run, mock_ver):
        from check_env import check_git
        mock_run.return_value = MagicMock(stdout="John\n")
        r = EnvCheck()
        check_git(r)
        assert any("Git 2.37.3" in p for p in r.passed)
        assert len(r.failed) == 0

    @patch("check_env.get_version", return_value=None)
    def test_check_git_missing(self, mock_ver):
        from check_env import check_git
        r = EnvCheck()
        check_git(r)
        assert any("not found" in f.lower() for f in r.failed)

    @patch("check_env.get_version", return_value="2.20.0")
    def test_check_git_old(self, mock_ver):
        from check_env import check_git
        r = EnvCheck()
        check_git(r)
        assert any("too old" in f for f in r.failed)

    @patch("check_env.get_version", return_value="24.14.0")
    @patch("check_env.shutil.which", return_value="/usr/bin/npx")
    def test_check_node_pass(self, mock_which, mock_ver):
        from check_env import check_node
        r = EnvCheck()
        check_node(r)
        assert any("Node.js 24.14.0" in p for p in r.passed)
        assert any("npx" in p for p in r.passed)

    @patch("check_env.get_version", return_value=None)
    def test_check_node_missing(self, mock_ver):
        from check_env import check_node
        r = EnvCheck()
        check_node(r)
        assert any("not found" in f.lower() for f in r.failed)

    def test_check_python_current(self):
        from check_env import check_python
        r = EnvCheck()
        check_python(r)
        # Current interpreter should pass version check
        assert any("Python" in p for p in r.passed)

    @patch("check_env.shutil.which", return_value="/usr/bin/claude")
    def test_check_claude_found(self, mock_which):
        from check_env import check_claude
        r = EnvCheck()
        check_claude(r)
        assert any("Claude Code found" in p for p in r.passed)

    @patch("check_env.shutil.which", return_value=None)
    def test_check_claude_missing(self, mock_which):
        from check_env import check_claude
        r = EnvCheck()
        check_claude(r)
        assert any("not found" in f.lower() for f in r.failed)

    @patch("check_env._get_version_from_path", return_value="4.5.1")
    @patch("check_env.read_godot_path", return_value="/opt/godot")
    def test_check_godot_uses_configured_agent_path(self, mock_path, mock_ver, tmp_path):
        from check_env import check_godot
        r = EnvCheck()
        check_godot(r, tmp_path)
        assert any("configured path: /opt/godot" in p for p in r.passed)
        assert len(r.failed) == 0

    @patch("check_env.check_codex")
    @patch("check_env.detect_agent", return_value="codex")
    def test_check_selected_agent_uses_codex(self, mock_detect, mock_codex, tmp_path):
        from check_env import check_selected_agent
        r = EnvCheck()
        check_selected_agent(r, tmp_path)
        mock_codex.assert_called_once_with(r, tmp_path)

    @patch("check_env.check_claude")
    @patch("check_env.detect_agent", return_value="claude-code")
    def test_check_selected_agent_uses_claude(self, mock_detect, mock_claude, tmp_path):
        from check_env import check_selected_agent
        r = EnvCheck()
        check_selected_agent(r, tmp_path)
        mock_claude.assert_called_once_with(r)

    @patch("check_env.get_version", return_value="0.99.0")
    @patch("check_env.shutil.which", return_value="/usr/bin/codex")
    @patch("check_env.subprocess.run")
    def test_check_codex_validates_runtime_files_and_mcp(
        self, mock_run, mock_which, mock_ver, tmp_path: Path
    ):
        from check_env import check_codex
        (tmp_path / ".agents" / "skills").mkdir(parents=True)
        (tmp_path / ".agents" / "references").mkdir()
        (tmp_path / ".agents" / "references" / "runtime-mapping.md").write_text("")
        (tmp_path / ".agents" / "godotmaker.yaml").write_text("godot_path: /opt/godot\n")
        mock_run.return_value = MagicMock(returncode=0, stdout="godot\n", stderr="")

        r = EnvCheck()
        check_codex(r, tmp_path)

        assert any("Codex CLI found" in p for p in r.passed)
        assert any("Codex MCP server 'godot' configured" in p for p in r.passed)
        assert len(r.failed) == 0

    @patch.dict(os.environ, {"GOOGLE_API_KEY": "AIzaSyTestKey12345678"}, clear=False)
    def test_check_api_keys_present_for_configured_gemini(self):
        from check_env import check_api_keys
        r = EnvCheck()
        check_api_keys(r, {"asset_image_model": "gemini:gemini-3.1-flash-image-preview"})
        assert any("GOOGLE_API_KEY set" in p for p in r.passed)

    @patch.dict(os.environ, {}, clear=True)
    def test_check_api_keys_missing_for_configured_gemini(self):
        from check_env import check_api_keys
        r = EnvCheck()
        # Need to also clear GEMINI_API_KEY
        os.environ.pop("GOOGLE_API_KEY", None)
        os.environ.pop("GEMINI_API_KEY", None)
        check_api_keys(r, {"asset_image_model": "gemini:gemini-3.1-flash-image-preview"})
        assert any("GOOGLE_API_KEY" in f for f in r.failed)

    @patch.dict(os.environ, {}, clear=True)
    def test_check_api_keys_without_config_uses_native_defaults(self):
        from check_env import check_api_keys

        r = EnvCheck()
        check_api_keys(r, agent="codex")

        assert not r.failed
        assert not any("GOOGLE_API_KEY" in f for f in r.failed)
        assert any("native image generation" in p for p in r.passed)

    @patch.dict(os.environ, {}, clear=True)
    def test_codex_image_model_on_codex_does_not_require_image_api_key(self):
        from check_env import check_api_keys

        r = EnvCheck()
        check_api_keys(
            r,
            {
                "asset_image_model": "codex",
                "vqa_model": "codex",
            },
            agent="codex",
        )

        assert not r.failed
        assert any("active Codex runtime" in p for p in r.passed)
        assert any("XAI_API_KEY not set" in w for w in r.warnings)

    @patch.dict(os.environ, {}, clear=True)
    def test_openai_image_model_requires_openai_api_key(self):
        from check_env import check_api_keys

        r = EnvCheck()
        check_api_keys(
            r,
            {
                "asset_image_model": "openai:gpt-image-2",
                "vqa_model": "native",
            },
        )

        assert any("OPENAI_API_KEY" in f for f in r.failed)
        assert not any("GOOGLE_API_KEY" in f for f in r.failed)

    @patch.dict(os.environ, {}, clear=True)
    def test_native_image_model_still_requires_configured_gemini_vqa_key(self):
        from check_env import check_api_keys

        r = EnvCheck()
        check_api_keys(
            r,
            {
                "asset_image_model": "native",
                "vqa_model": "gemini:gemini-2.5-flash",
            },
            agent="codex",
        )

        assert any("GOOGLE_API_KEY" in f for f in r.failed)

    @patch.dict(os.environ, {}, clear=True)
    def test_claude_native_image_generation_warns(self):
        from check_env import check_api_keys

        r = EnvCheck()
        check_api_keys(
            r,
            {
                "asset_image_model": "native",
                "vqa_model": "native",
            },
            agent="claude-code",
        )

        assert not r.failed
        assert any("native image generation for Claude Code" in w for w in r.warnings)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True)
    def test_claude_native_vqa_inspection_can_pass(self):
        from check_env import check_api_keys

        r = EnvCheck()
        check_api_keys(
            r,
            {
                "asset_image_model": "openai:gpt-image-2",
                "vqa_model": "native",
            },
            agent="claude-code",
        )

        assert not r.failed
        assert any("native image inspection" in p for p in r.passed)

    @patch("check_env.shutil.which", return_value=None)
    @patch.dict(os.environ, {}, clear=True)
    def test_claude_codex_image_model_fails_when_codex_cli_missing(self, mock_which):
        from check_env import check_api_keys

        r = EnvCheck()
        check_api_keys(
            r,
            {
                "asset_image_model": "codex",
                "vqa_model": "codex",
            },
            agent="claude-code",
        )

        assert any("Codex CLI" in f for f in r.failed)

    @patch("check_env.shutil.which", return_value="/usr/bin/codex")
    @patch.dict(os.environ, {}, clear=True)
    def test_claude_codex_image_model_accepts_codex_exec_handoff(self, mock_which):
        from check_env import check_api_keys

        r = EnvCheck()
        check_api_keys(
            r,
            {
                "asset_image_model": "codex",
                "vqa_model": "codex",
            },
            agent="claude-code",
        )

        assert not r.failed
        assert any("Codex CLI found for Codex image generation" in p for p in r.passed)

    @patch("check_env.shutil.which", return_value="/usr/bin/codex")
    @patch.dict(os.environ, {}, clear=True)
    def test_claude_codex_vqa_model_accepts_codex_exec_handoff(self, mock_which):
        from check_env import check_api_keys

        r = EnvCheck()
        check_api_keys(
            r,
            {
                "asset_image_model": "native",
                "vqa_model": "codex",
            },
            agent="claude-code",
        )

        assert not r.failed
        assert any("Codex CLI found for Codex image inspection" in p for p in r.passed)

    @patch.dict(os.environ, {}, clear=True)
    def test_non_grok_image_model_does_not_require_xai_key(self):
        from check_env import check_api_keys

        r = EnvCheck()
        check_api_keys(
            r,
            {
                "asset_image_model": "native",
                "vqa_model": "native",
            },
            agent="codex",
        )

        assert not any("XAI_API_KEY" in f for f in r.failed)

    def test_python_checks_xai_sdk_for_grok_image(self, monkeypatch):
        from check_env import check_python

        imported: list[str] = []

        def fake_import(name):
            imported.append(name)
            return object()

        monkeypatch.setattr("builtins.__import__", fake_import)
        r = EnvCheck()
        check_python(
            r,
            {
                "asset_image_model": "grok:grok-imagine-image",
                "vqa_model": "native",
            },
        )

        assert "xai_sdk" in imported
