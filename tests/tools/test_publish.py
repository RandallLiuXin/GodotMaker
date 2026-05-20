"""Tests for publish.py."""
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tools",
))

import publish
import agent_runtime
from project_config import DEFAULT_CONFIG_TEMPLATE, ProjectConfigResult
from publish import (
    read_godot_path,
    create_godotmaker_yaml,
    create_project_config,
    deploy_agent_instructions,
    render_agent_instructions,
    ensure_gitattributes,
    ensure_gitignore,
    ensure_worktreeinclude,
    publish_skills,
    register_codex_mcp,
    register_godot_permissions,
    rmtree_force,
    _verify_godot_path,
)


PRIMARY_ROLE_SKILLS = [
    "gm-scaffold",
    "gm-gdd",
    "gm-asset",
    "gm-build",
    "gm-verify",
    "gm-evaluate",
    "gm-fixgap",
    "gm-accept",
    "gm-finalize",
]

CODEX_RUNTIME_TEXT_SUFFIXES = {
    ".md",
    ".yaml",
    ".yml",
    ".json",
    ".sh",
    ".ps1",
    ".txt",
    ".tmpl",
}

FORBIDDEN_CODEX_RUNTIME_REFS = [
    ".claude/skills",
    ".claude/agents",
    ".claude/templates",
    ".claude/godotmaker.yaml",
    "CLAUDE.md",
    "${CLAUDE_SKILL_DIR}",
]

LITERAL_SLASH_GM_EXECUTION = re.compile(
    r"\b(?:run|invoke|execute|call|use|start|launch)\s+`/gm-[^`]+`",
    re.IGNORECASE,
)


def _runtime_text_files(root: Path):
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in CODEX_RUNTIME_TEXT_SUFFIXES:
            yield path, path.read_text(encoding="utf-8")


def _publish_codex_project(tmp_path, monkeypatch):
    from _version import SemVer

    target = tmp_path / "target"
    config_dir = target / ".agents"
    config_dir.mkdir(parents=True)
    (config_dir / "godotmaker.yaml").write_text(
        'godot_path: "/test/godot"\n',
        encoding="utf-8",
    )

    codex_mcp_calls = []

    def _record_codex_mcp(*args, **kwargs):
        codex_mcp_calls.append((args, kwargs))
        return True

    monkeypatch.setattr(
        publish,
        "check_version_upgrade",
        lambda *_args, **_kwargs: (True, "FRESH", None, SemVer(0, 3, 5)),
    )
    monkeypatch.setattr(publish, "register_codex_mcp", _record_codex_mcp)
    monkeypatch.setattr(publish, "register_mcp",
                        lambda *_args, **_kwargs: None)
    monkeypatch.setattr(publish, "register_godot_permissions",
                        lambda *_args, **_kwargs: None)
    monkeypatch.setattr(publish, "ensure_git_repo",
                        lambda *_args, **_kwargs: None)
    monkeypatch.setattr(publish, "baseline_applied",
                        lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(publish, "run_migrations",
                        lambda *_args, **_kwargs: True)
    monkeypatch.setattr(sys, "argv",
                        [
                            "publish.py",
                            "--agent", "codex",
                            "--force",
                            "--no-config-review",
                            str(target),
                        ])

    publish.main()
    return target, codex_mcp_calls


class TestReadGodotPath:
    def test_missing_file(self, tmp_path):
        assert read_godot_path(tmp_path / "nope.yaml") == "godot"

    def test_quoted_path(self, tmp_path):
        f = tmp_path / "godotmaker.yaml"
        f.write_text('godot_path: "C:/Godot/godot.exe"\n')
        assert read_godot_path(f) == "C:/Godot/godot.exe"

    def test_unquoted_path(self, tmp_path):
        f = tmp_path / "godotmaker.yaml"
        f.write_text("godot_path: /usr/bin/godot\n")
        assert read_godot_path(f) == "/usr/bin/godot"

    def test_empty_value_returns_default(self, tmp_path):
        f = tmp_path / "godotmaker.yaml"
        f.write_text("godot_path:\n")
        assert read_godot_path(f) == "godot"

    def test_single_quoted(self, tmp_path):
        f = tmp_path / "godotmaker.yaml"
        f.write_text("godot_path: 'C:/Godot/godot.exe'\n")
        assert read_godot_path(f) == "C:/Godot/godot.exe"


def _ok_run(stdout="Godot Engine v4.4-stable\n"):
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def _fail_run(returncode=1, stderr="boom"):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout="", stderr=stderr)


class TestVerifyGodotPath:
    def test_returns_ok_when_godot_runs(self):
        with patch.object(publish.subprocess, "run", return_value=_ok_run()):
            ok, msg = _verify_godot_path("/fake/godot")
        assert ok is True
        assert "v4.4" in msg

    def test_returns_failure_when_executable_missing(self):
        with patch.object(publish.subprocess, "run", side_effect=FileNotFoundError):
            ok, msg = _verify_godot_path("/no/such/godot")
        assert ok is False
        assert "not found" in msg

    def test_returns_failure_when_godot_exits_nonzero(self):
        with patch.object(publish.subprocess, "run", return_value=_fail_run()):
            ok, msg = _verify_godot_path("/fake/godot")
        assert ok is False
        assert "exited" in msg

    def test_returns_failure_on_timeout(self):
        with patch.object(
            publish.subprocess, "run",
            side_effect=subprocess.TimeoutExpired(cmd="godot", timeout=15),
        ):
            ok, msg = _verify_godot_path("/slow/godot")
        assert ok is False
        assert "did not return" in msg

    def test_zero_exit_with_empty_stdout_is_accepted(self):
        """Lock-in: an executable that exits 0 but prints no version line
        is treated as 'verified' with `?` as the version. This is
        intentional — wrapper scripts (`godot.cmd`, ssh wrappers, sandbox
        runners) sometimes suppress stdout while still launching Godot
        correctly. If you ever decide to tighten this and require a
        version pattern in stdout, change this test deliberately."""
        with patch.object(publish.subprocess, "run",
                          return_value=_ok_run(stdout="")):
            ok, msg = _verify_godot_path("/silent/godot")
        assert ok is True
        assert msg == "?"

    def test_zero_exit_with_non_version_stdout_is_accepted(self):
        """Lock-in counterpart to the empty-stdout case — even non-version
        text (e.g. a wrapper banner) is currently accepted as long as the
        process returns 0."""
        with patch.object(publish.subprocess, "run",
                          return_value=_ok_run(stdout="hello world\n")):
            ok, msg = _verify_godot_path("/wrapped/godot")
        assert ok is True
        assert msg == "hello world"

    def test_returns_failure_on_oserror(self):
        """An OSError other than FileNotFoundError (e.g. PermissionError,
        OSError when the path is a directory) is the third hand-written
        exception branch in `_verify_godot_path` and must surface a
        readable message instead of crashing."""
        with patch.object(publish.subprocess, "run",
                          side_effect=PermissionError("Permission denied")):
            ok, msg = _verify_godot_path("/no/perms/godot")
        assert ok is False
        assert "cannot run" in msg
        assert "Permission denied" in msg


class TestCreateGodotmakerYaml:
    """create_godotmaker_yaml must reject empty / unverifiable paths and
    only write godotmaker.yaml when --version succeeds. The previous
    behaviour silently fell back to godot_path: 'godot' when the user
    pressed Enter, which then re-asked downstream in /gm-scaffold."""

    def test_skips_when_file_exists(self, tmp_path, capsys):
        config = tmp_path / "godotmaker.yaml"
        config.write_text('godot_path: "/existing"\n', encoding="utf-8")
        create_godotmaker_yaml(config)
        assert config.read_text(encoding="utf-8") == 'godot_path: "/existing"\n'

    def test_writes_yaml_when_path_verifies(self, tmp_path):
        config = tmp_path / "godotmaker.yaml"
        with patch("builtins.input", return_value="/usr/bin/godot"), \
             patch.object(publish.subprocess, "run", return_value=_ok_run()):
            create_godotmaker_yaml(config)
        assert config.exists()
        content = config.read_text(encoding="utf-8")
        assert 'godot_path: "/usr/bin/godot"' in content

    def test_strips_quotes_from_user_input(self, tmp_path):
        config = tmp_path / "godotmaker.yaml"
        with patch("builtins.input", return_value='"C:/Godot/godot.exe"'), \
             patch.object(publish.subprocess, "run", return_value=_ok_run()):
            create_godotmaker_yaml(config)
        assert 'godot_path: "C:/Godot/godot.exe"' in config.read_text(encoding="utf-8")

    def test_strips_bom_from_piped_input(self, tmp_path):
        config = tmp_path / "godotmaker.yaml"
        with patch("builtins.input", return_value="\ufeffC:/Godot/godot.exe"), \
             patch.object(publish.subprocess, "run", return_value=_ok_run()):
            create_godotmaker_yaml(config)
        assert 'godot_path: "C:/Godot/godot.exe"' in config.read_text(encoding="utf-8")

    def test_reprompts_on_empty_then_accepts_valid(self, tmp_path):
        config = tmp_path / "godotmaker.yaml"
        inputs = iter(["", "  ", "/usr/bin/godot"])
        with patch("builtins.input", side_effect=lambda _: next(inputs)), \
             patch.object(publish.subprocess, "run", return_value=_ok_run()):
            create_godotmaker_yaml(config)
        assert config.exists(), "must accept the third valid input after two empties"

    def test_reprompts_on_invalid_then_accepts_valid(self, tmp_path):
        config = tmp_path / "godotmaker.yaml"
        inputs = iter(["/bogus/path", "/usr/bin/godot"])
        runs = iter([_fail_run(), _ok_run()])
        with patch("builtins.input", side_effect=lambda _: next(inputs)), \
             patch.object(publish.subprocess, "run", side_effect=lambda *a, **k: next(runs)):
            create_godotmaker_yaml(config)
        assert 'godot_path: "/usr/bin/godot"' in config.read_text(encoding="utf-8")

    def test_interleaved_empty_invalid_valid_within_budget(self, tmp_path):
        """Mixed retry path — empty (no subprocess call), invalid (fail),
        valid (ok). Pins that the same attempt counter governs both kinds
        of rejection, so an `empty + invalid + ...` sequence still has
        budget for a final successful attempt."""
        config = tmp_path / "godotmaker.yaml"
        inputs = iter(["", "/bogus/path", "/usr/bin/godot"])
        # `_verify_godot_path` only runs subprocess for non-empty inputs,
        # so the run side_effect lines up with the 2nd and 3rd entries.
        runs = iter([_fail_run(), _ok_run()])
        with patch("builtins.input", side_effect=lambda _: next(inputs)), \
             patch.object(publish.subprocess, "run",
                          side_effect=lambda *a, **k: next(runs)):
            create_godotmaker_yaml(config)
        assert 'godot_path: "/usr/bin/godot"' in config.read_text(encoding="utf-8")

    def test_does_not_write_when_user_aborts(self, tmp_path):
        config = tmp_path / "godotmaker.yaml"
        with patch("builtins.input", side_effect=EOFError):
            create_godotmaker_yaml(config)
        assert not config.exists(), (
            "Ctrl+D / EOF must NOT silently write a fallback path — "
            "that was the original bug. Better: leave config absent so "
            "publish can be re-run."
        )

    def test_does_not_write_when_user_sigints(self, tmp_path):
        """Sibling of test_does_not_write_when_user_aborts — Ctrl+C
        (KeyboardInterrupt) must follow the same no-fallback contract.
        The exception handler catches `(EOFError, KeyboardInterrupt)`
        as a tuple, but only the EOFError half was previously tested."""
        config = tmp_path / "godotmaker.yaml"
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            create_godotmaker_yaml(config)
        assert not config.exists()

    def test_gives_up_after_max_attempts_without_writing(self, tmp_path):
        config = tmp_path / "godotmaker.yaml"
        # 5 invalid attempts in a row → no file
        with patch("builtins.input", return_value="/bogus"), \
             patch.object(publish.subprocess, "run", return_value=_fail_run()):
            create_godotmaker_yaml(config)
        assert not config.exists()


class TestRegisterGodotPermissions:
    def _seed(self, tmp_path, body):
        settings = tmp_path / "settings.json"
        settings.write_text(json.dumps(body), encoding="utf-8")
        return settings

    def test_skips_when_settings_missing(self, tmp_path, capsys):
        register_godot_permissions(tmp_path / "nope.json", "/usr/bin/godot")
        assert "missing" in capsys.readouterr().out
        assert not (tmp_path / "nope.json").exists()

    def test_adds_entry_to_empty_permissions(self, tmp_path):
        settings = self._seed(tmp_path, {"hooks": {}})
        register_godot_permissions(settings, "C:/Godot/godot.exe")
        data = json.loads(settings.read_text(encoding="utf-8"))
        assert data["permissions"]["allow"] == ["Bash(C:/Godot/godot.exe:*)"]
        assert data["hooks"] == {}  # untouched

    def test_appends_alongside_existing_allow_entries(self, tmp_path):
        settings = self._seed(tmp_path, {
            "permissions": {"allow": ["Bash(npm:*)", "Bash(git:*)"]}
        })
        register_godot_permissions(settings, "/usr/bin/godot")
        allow = json.loads(settings.read_text(encoding="utf-8"))["permissions"]["allow"]
        assert allow == ["Bash(npm:*)", "Bash(git:*)", "Bash(/usr/bin/godot:*)"]

    def test_idempotent(self, tmp_path):
        settings = self._seed(tmp_path, {})
        register_godot_permissions(settings, "/usr/bin/godot")
        register_godot_permissions(settings, "/usr/bin/godot")
        register_godot_permissions(settings, "/usr/bin/godot")
        allow = json.loads(settings.read_text(encoding="utf-8"))["permissions"]["allow"]
        assert allow == ["Bash(/usr/bin/godot:*)"]

    def test_invalid_json_skipped_with_warning(self, tmp_path, capsys):
        settings = tmp_path / "settings.json"
        settings.write_text("{not json", encoding="utf-8")
        register_godot_permissions(settings, "/usr/bin/godot")
        assert "invalid JSON" in capsys.readouterr().out
        assert settings.read_text(encoding="utf-8") == "{not json"

    def test_windows_backslash_path_is_escaped(self, tmp_path):
        # claude-code's permissionRuleParser unescapes \\ -> \ on read, so we
        # must double backslashes when storing or single \X sequences inside
        # the path will be misinterpreted on round-trip.
        settings = self._seed(tmp_path, {})
        register_godot_permissions(settings, r"D:\Godot\godot.exe")
        allow = json.loads(settings.read_text(encoding="utf-8"))["permissions"]["allow"]
        assert allow == [r"Bash(D:\\Godot\\godot.exe:*)"]

    def test_path_with_parens_is_escaped(self, tmp_path):
        # `C:\Program Files (x86)\...` would break the outer Tool(...) parser
        # without escaping the embedded parentheses.
        settings = self._seed(tmp_path, {})
        register_godot_permissions(
            settings, r"C:\Program Files (x86)\Godot\godot.exe"
        )
        allow = json.loads(settings.read_text(encoding="utf-8"))["permissions"]["allow"]
        assert allow == [
            r"Bash(C:\\Program Files \(x86\)\\Godot\\godot.exe:*)"
        ]

    def test_idempotency_holds_for_escaped_path(self, tmp_path):
        # The dedupe check compares the escaped form, so re-registering the
        # same Windows path must not produce two visually-different entries.
        settings = self._seed(tmp_path, {})
        register_godot_permissions(settings, r"D:\Godot\godot.exe")
        register_godot_permissions(settings, r"D:\Godot\godot.exe")
        allow = json.loads(settings.read_text(encoding="utf-8"))["permissions"]["allow"]
        assert len(allow) == 1


class TestRegisterCodexMcp:
    def test_fails_when_codex_missing(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(publish.shutil, "which", lambda name: None)
        assert register_codex_mcp(tmp_path, "/usr/bin/godot") is False
        out = capsys.readouterr().out
        assert "codex CLI not found" in out
        assert "codex mcp add godot" in out

    def test_invokes_codex_mcp_add(self, tmp_path, monkeypatch):
        calls = []

        def _which(name):
            if name in ("codex", "npx"):
                return name
            return None

        def _run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            return subprocess.CompletedProcess(args=cmd, returncode=0)

        monkeypatch.setattr(publish.shutil, "which", _which)
        monkeypatch.setattr(publish.subprocess, "run", _run)
        monkeypatch.setattr(publish.sys, "platform", "linux")

        assert register_codex_mcp(tmp_path, "/usr/bin/godot") is True

        assert calls[0][0] == ["codex", "mcp", "remove", "godot"]
        assert calls[1][0] == [
            "codex", "mcp", "add", "godot",
            "--env", "GODOT_PATH=/usr/bin/godot", "--",
            "npx", "@coding-solo/godot-mcp",
        ]
        assert calls[1][1]["cwd"] == str(tmp_path)


class TestCreateProjectConfig:
    def test_creates_config_with_defaults(self, tmp_path):
        result = create_project_config(tmp_path)
        config = tmp_path / ".godotmaker" / "config.yaml"
        assert result == ProjectConfigResult(path=config, created=True)
        assert config.exists()
        content = config.read_text()
        assert "agent: claude-code" in content
        assert "vqa_model: native" in content
        assert "vqa_fallback_model: native" in content
        assert "asset_image_model: native" in content
        assert "asset_video_model: none" in content

    def test_skips_if_exists(self, tmp_path):
        config_dir = tmp_path / ".godotmaker"
        config_dir.mkdir()
        config = config_dir / "config.yaml"
        config.write_text("vqa_model: custom-model\n")
        result = create_project_config(tmp_path, publish.AGENT_CODEX)
        content = config.read_text()
        assert result == ProjectConfigResult(path=config, created=False)
        assert "vqa_model: custom-model" in content
        assert "agent: codex" in content

    def test_create_project_config_does_not_stamp_version(self, tmp_path):
        create_project_config(tmp_path)
        assert not (tmp_path / ".godotmaker" / "version").exists()

    def test_published_agent_selects_runtime_config(self, tmp_path):
        create_project_config(tmp_path, publish.AGENT_CODEX)
        (tmp_path / ".agents").mkdir()
        (tmp_path / ".agents" / "godotmaker.yaml").write_text(
            "godot_path: /opt/godot\n", encoding="utf-8"
        )

        assert agent_runtime.detect_agent(tmp_path) == publish.AGENT_CODEX
        assert agent_runtime.godotmaker_yaml(tmp_path) == (
            tmp_path / ".agents" / "godotmaker.yaml"
        )
        assert agent_runtime.read_godot_path(tmp_path) == "/opt/godot"

    def test_default_config_template_is_valid_yaml(self):
        assert DEFAULT_CONFIG_TEMPLATE.exists(), "config.yaml.default template must exist"
        content = DEFAULT_CONFIG_TEMPLATE.read_text(encoding="utf-8")
        assert "vqa_model:" in content
        assert "vqa_fallback_model:" in content
        assert "asset_image_model:" in content
        assert "asset_video_model:" in content
        assert "worker_model:" in content
        assert "agent:" in content
        lines = [line for line in content.splitlines() if line and not line.startswith("#")]
        for line in lines:
            assert ":" in line, f"Non-comment line missing ':' — {line}"


    def test_review_created_project_config_waits_for_enter(
        self, tmp_path, monkeypatch, capsys
    ):
        config = tmp_path / ".godotmaker" / "config.yaml"
        result = ProjectConfigResult(path=config, created=True)
        calls = []
        monkeypatch.setattr("builtins.input", lambda: calls.append("input") or "")

        publish.review_created_project_config(result)

        assert calls == ["input"]
        out = capsys.readouterr().out
        assert "Project config created:" in out
        assert str(config.resolve()) in out

    def test_review_created_project_config_aborts_on_eof(
        self, tmp_path, monkeypatch
    ):
        result = ProjectConfigResult(
            path=tmp_path / ".godotmaker" / "config.yaml",
            created=True,
        )

        def _raise_eof():
            raise EOFError()

        monkeypatch.setattr("builtins.input", _raise_eof)
        with pytest.raises(SystemExit) as exc:
            publish.review_created_project_config(result)
        assert exc.value.code == 1


SELECTIVE_ENTRIES = [
    ".claude/",
    ".godotmaker/state.json",
    ".godotmaker/metrics.jsonl",
    ".godotmaker/metrics_current.jsonl",
    "reports/",
    "__pycache__/",
    "*.pyc",
]


class TestEnsureGitignore:
    def test_creates_new_gitignore(self, tmp_path):
        ensure_gitignore(tmp_path)
        content = (tmp_path / ".gitignore").read_text()
        assert ".claude/" in content
        assert ".agents/" not in content
        for entry in SELECTIVE_ENTRIES:
            assert entry in content
        # Blanket ignore must NOT be present (selective entries only)
        lines = [line.strip() for line in content.splitlines()]
        assert ".godotmaker/" not in lines

    def test_appends_missing_entries(self, tmp_path):
        gi = tmp_path / ".gitignore"
        gi.write_text("*.tmp\n")
        ensure_gitignore(tmp_path)
        content = gi.read_text()
        assert "*.tmp" in content
        assert ".claude/" in content
        assert ".agents/" not in content
        for entry in SELECTIVE_ENTRIES:
            assert entry in content
        # Blanket ignore must NOT be present
        lines = [line.strip() for line in content.splitlines()]
        assert ".godotmaker/" not in lines

    def test_skips_existing_selective_entries(self, tmp_path):
        gi = tmp_path / ".gitignore"
        gi.write_text("\n".join(SELECTIVE_ENTRIES) + "\n")
        ensure_gitignore(tmp_path)
        content = gi.read_text()
        # Each selective entry should appear exactly once
        for entry in SELECTIVE_ENTRIES:
            assert content.count(entry) == 1

    def test_partial_missing(self, tmp_path):
        gi = tmp_path / ".gitignore"
        gi.write_text(".claude/\n")
        ensure_gitignore(tmp_path)
        content = gi.read_text()
        for entry in SELECTIVE_ENTRIES:
            assert entry in content
        assert content.count(".claude/") == 1

    def test_codex_does_not_ignore_agents_or_claude(self, tmp_path):
        ensure_gitignore(tmp_path, publish.AGENT_CODEX)
        content = (tmp_path / ".gitignore").read_text()
        assert ".agents/" not in content
        assert ".claude/" not in content
        for entry in SELECTIVE_ENTRIES[1:]:
            assert entry in content

    def test_codex_removes_old_agents_blanket_ignore(self, tmp_path):
        gi = tmp_path / ".gitignore"
        gi.write_text(".agents/\n*.tmp\n")
        ensure_gitignore(tmp_path, publish.AGENT_CODEX)
        content = gi.read_text()
        lines = [line.strip() for line in content.splitlines()]
        assert ".agents/" not in lines
        assert "*.tmp" in content
        for entry in SELECTIVE_ENTRIES[1:]:
            assert entry in content

    def test_migration_removes_blanket_godotmaker(self, tmp_path):
        """Old .godotmaker/ blanket line is replaced by selective entries on upgrade."""
        gi = tmp_path / ".gitignore"
        gi.write_text("*.log\n.godotmaker/\n*.tmp\n")
        ensure_gitignore(tmp_path)
        content = gi.read_text()
        # Original non-godotmaker lines must be preserved
        assert "*.log" in content
        assert "*.tmp" in content
        # Blanket ignore must be gone
        lines = [line.strip() for line in content.splitlines()]
        assert ".godotmaker/" not in lines
        # Selective entries must now be present
        for entry in SELECTIVE_ENTRIES:
            assert entry in content


class TestEnsureGitattributes:
    def test_creates_line_ending_rules(self, tmp_path):
        ensure_gitattributes(tmp_path)
        content = (tmp_path / ".gitattributes").read_text()
        assert "* text=auto eol=lf" in content
        assert "*.sh text eol=lf" in content
        assert "*.bat text eol=crlf" in content
        assert "*.cmd text eol=crlf" in content

    def test_appends_line_ending_rules(self, tmp_path):
        attrs = tmp_path / ".gitattributes"
        attrs.write_text("*.gd text\n", encoding="utf-8")
        ensure_gitattributes(tmp_path)
        content = attrs.read_text(encoding="utf-8")
        assert "*.gd text" in content
        assert "* text=auto eol=lf" in content
        assert "*.sh text eol=lf" in content
        assert "*.bat text eol=crlf" in content
        assert "*.cmd text eol=crlf" in content

    def test_keeps_existing_line_ending_rules_once(self, tmp_path):
        attrs = tmp_path / ".gitattributes"
        attrs.write_text(
            "* text=auto eol=lf\n"
            "*.sh text eol=lf\n"
            "*.bat text eol=crlf\n"
            "*.cmd text eol=crlf\n",
            encoding="utf-8",
        )
        ensure_gitattributes(tmp_path)
        content = attrs.read_text(encoding="utf-8")
        assert content.count("* text=auto eol=lf") == 1
        assert content.count("*.sh text eol=lf") == 1
        assert content.count("*.bat text eol=crlf") == 1
        assert content.count("*.cmd text eol=crlf") == 1


WORKTREEINCLUDE_ENTRIES = [".claude/", "!.claude/worktrees/"]


class TestEnsureWorktreeinclude:
    """`.worktreeinclude` carries `.claude/` (godotmaker.yaml + skills/) into
    sub-agent worktrees. Without it, sub-agents dispatched with
    `isolation: "worktree"` see only git-tracked files and miss host config.
    See https://code.claude.com/docs/en/worktrees.
    """

    def test_creates_new_file(self, tmp_path):
        ensure_worktreeinclude(tmp_path)
        wt = tmp_path / ".worktreeinclude"
        assert wt.exists()
        content = wt.read_text(encoding="utf-8")
        for entry in WORKTREEINCLUDE_ENTRIES:
            assert entry in content
        # Header should explain WHY the file exists.
        assert "worktree" in content.lower()

    def test_appends_missing_entries(self, tmp_path):
        wt = tmp_path / ".worktreeinclude"
        wt.write_text("# user-managed\nsome/custom/path\n", encoding="utf-8")
        ensure_worktreeinclude(tmp_path)
        content = wt.read_text(encoding="utf-8")
        # User content preserved
        assert "some/custom/path" in content
        assert "# user-managed" in content
        # Required entries appended
        for entry in WORKTREEINCLUDE_ENTRIES:
            assert entry in content

    def test_idempotent_when_already_present(self, tmp_path):
        wt = tmp_path / ".worktreeinclude"
        wt.write_text("\n".join(WORKTREEINCLUDE_ENTRIES) + "\n",
                      encoding="utf-8")
        ensure_worktreeinclude(tmp_path)
        content = wt.read_text(encoding="utf-8")
        # Each entry appears exactly once as a standalone line.
        # (substring count would double-count: ".claude/" is a substring
        # of "!.claude/worktrees/".)
        lines = [line.strip() for line in content.splitlines()]
        for entry in WORKTREEINCLUDE_ENTRIES:
            assert lines.count(entry) == 1

    def test_partial_missing(self, tmp_path):
        wt = tmp_path / ".worktreeinclude"
        wt.write_text(".claude/\n", encoding="utf-8")
        ensure_worktreeinclude(tmp_path)
        content = wt.read_text(encoding="utf-8")
        lines = [line.strip() for line in content.splitlines()]
        # The negation entry was missing; should be appended.
        assert "!.claude/worktrees/" in lines
        # The pre-existing entry should not be duplicated.
        assert lines.count(".claude/") == 1


class TestPublishSkills:
    def _make_repo(self, tmp_path):
        """Create a minimal repo structure with fake skills."""
        repo = tmp_path / "repo"
        # core skills
        for name in ["gecs", "gm-scaffold"]:
            skill_dir = repo / "skills" / "core" / name
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(f"# {name}\n")
        # reviewer skills
        for name in ["physics", "ui"]:
            skill_dir = repo / "skills" / "reviewer" / name
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(f"# {name}\n")
        # __pycache__ in a skill (should be cleaned)
        cache = repo / "skills" / "core" / "gecs" / "__pycache__"
        cache.mkdir()
        (cache / "mod.pyc").write_text("x")
        # _read_config.sh
        shell_dir = repo / "shell"
        shell_dir.mkdir(parents=True)
        (shell_dir / "_read_config.sh").write_text("#!/bin/bash\n")
        return repo

    def test_flattens_skills(self, tmp_path):
        repo = self._make_repo(tmp_path)
        target = tmp_path / "target"
        target.mkdir()
        count = publish_skills(repo, target)
        assert count == 4
        assert (target / "gecs" / "SKILL.md").exists()
        assert (target / "gm-scaffold" / "SKILL.md").exists()
        assert (target / "physics" / "SKILL.md").exists()
        assert (target / "ui" / "SKILL.md").exists()

    def test_codex_project_skills_keep_shared_surface_text(self, tmp_path):
        repo = self._make_repo(tmp_path)
        skill = repo / "skills" / "core" / "gm-scaffold" / "SKILL.md"
        skill.write_text(
            "Read .claude/godotmaker.yaml and ${CLAUDE_SKILL_DIR}/tools/x.sh\n",
            encoding="utf-8",
        )
        target = tmp_path / "target" / ".agents" / "skills"
        target.mkdir(parents=True)
        count = publish_skills(repo, target, publish.AGENT_CODEX)
        assert count == 4
        content = (target / "gm-scaffold" / "SKILL.md").read_text(encoding="utf-8")
        assert ".claude/godotmaker.yaml" in content
        assert "${CLAUDE_SKILL_DIR}/tools/x.sh" in content
        assert (target / "gecs" / "SKILL.md").exists()
        assert (target / "_read_config.sh").exists()

    def test_cleans_pycache(self, tmp_path):
        repo = self._make_repo(tmp_path)
        target = tmp_path / "target"
        target.mkdir()
        publish_skills(repo, target)
        assert not (target / "gecs" / "__pycache__").exists()

    def test_copies_read_config(self, tmp_path):
        repo = self._make_repo(tmp_path)
        target = tmp_path / "target"
        target.mkdir()
        publish_skills(repo, target)
        assert (target / "_read_config.sh").exists()

    def test_overwrites_existing_skill(self, tmp_path):
        repo = self._make_repo(tmp_path)
        target = tmp_path / "target"
        target.mkdir()
        # First publish
        publish_skills(repo, target)
        # Modify source
        (repo / "skills" / "core" / "gecs" / "SKILL.md").write_text("# updated\n")
        # Second publish
        publish_skills(repo, target)
        assert (target / "gecs" / "SKILL.md").read_text() == "# updated\n"


class TestDeployAgentInstructions:
    def _make_repo(self, tmp_path):
        repo = tmp_path / "repo"
        templates = repo / "templates"
        templates.mkdir(parents=True)
        (templates / "game-claude.md").write_text(
            "# CLAUDE.md\n\n"
            "The `/gm-*` skills drive the build pipeline.\n\n"
            "| Each role's full contract | `.claude/skills/gm-*/SKILL.md` |\n",
            encoding="utf-8",
        )
        codex_templates = repo / "agent-runtimes" / "codex" / "templates"
        codex_templates.mkdir(parents=True)
        (codex_templates / "agents-bootstrap.md").write_text(
            "Before executing any `$gm-*` skill, apply the GodotMaker Codex "
            "runtime mapping at `.agents/references/runtime-mapping.md`.\n\n",
            encoding="utf-8",
        )
        return repo

    def test_claude_deploys_claude_md(self, tmp_path):
        repo = self._make_repo(tmp_path)
        target = tmp_path / "target"
        target.mkdir()
        deploy_agent_instructions(repo, target, publish.AGENT_CLAUDE_CODE)
        assert (target / "CLAUDE.md").exists()
        assert not (target / "AGENTS.md").exists()

    def test_codex_derives_agents_md_from_claude_template(self, tmp_path):
        repo = self._make_repo(tmp_path)
        target = tmp_path / "target"
        target.mkdir()
        deploy_agent_instructions(repo, target, publish.AGENT_CODEX)
        content = (target / "AGENTS.md").read_text(encoding="utf-8")
        assert content.startswith("# AGENTS.md")
        assert "$gm-*" in content
        assert ".agents/references/runtime-mapping.md" in content
        assert ".claude/skills/gm-*/SKILL.md" in content
        assert not (target / "CLAUDE.md").exists()

    def test_render_codex_instructions_keeps_shared_surface_paths(self, tmp_path):
        repo = self._make_repo(tmp_path)
        content = render_agent_instructions(repo, publish.AGENT_CODEX)
        assert content is not None
        assert "CLAUDE.md" not in content
        assert "AGENTS.md" in content
        assert ".claude/skills/gm-*/SKILL.md" in content
        assert ".agents/references/runtime-mapping.md" in content
        assert "$gm-" in content
        assert "`/gm-*`" in content

    def test_claude_instructions_do_not_include_codex_bootstrap(self):
        content = render_agent_instructions(
            Path(__file__).resolve().parents[2],
            publish.AGENT_CLAUDE_CODE,
        )
        assert content is not None
        assert "If this file is rendered as `AGENTS.md`" not in content
        assert "runtime-mapping.md" not in content
        assert "Codex runtime mapping" not in content


class TestRmtreeForce:
    """Unit tests for rmtree_force().

    Cross-platform note: the read-only-file scenario only stresses the
    onerror/onexc handler on Windows, because Linux/macOS happily unlink
    read-only files when the parent dir is writable. On non-Windows
    platforms these tests just verify the helper doesn't break the
    normal-tree path; the real "is the bug fixed" assertion is
    Windows-only by nature.
    """

    def test_removes_readonly_files(self, tmp_path):
        # Mirrors the real failure: cloned godot doc source contains
        # git pack-*.idx files that git writes as r--r--r--, and
        # plain shutil.rmtree raises PermissionError on Windows.
        target = tmp_path / "doc_source"
        target.mkdir()
        nested = target / ".git" / "objects" / "pack"
        nested.mkdir(parents=True)
        pack = nested / "pack-deadbeef.idx"
        pack.write_bytes(b"fake pack idx")
        pack.chmod(stat.S_IREAD)
        try:
            rmtree_force(target)
            assert not target.exists()
        finally:
            # Best-effort cleanup if the helper itself failed.
            if pack.exists():
                pack.chmod(stat.S_IWRITE)

    def test_removes_normal_tree(self, tmp_path):
        target = tmp_path / "tree"
        (target / "a" / "b").mkdir(parents=True)
        (target / "a" / "b" / "c.txt").write_text("hi")
        rmtree_force(target)
        assert not target.exists()


class TestCodexPublishParity:
    def test_codex_publish_outputs_required_runtime_contract(self, tmp_path, monkeypatch):
        target, _calls = _publish_codex_project(tmp_path, monkeypatch)

        for skill_name in PRIMARY_ROLE_SKILLS:
            assert (
                target / ".agents" / "skills" / skill_name / "SKILL.md"
            ).exists(), f"missing Codex skill: {skill_name}"

        assert (target / ".agents" / "skills" / "gm-build" / "SKILL.md").exists()
        assert (target / "AGENTS.md").exists()
        assert not (target / "CLAUDE.md").exists()

        agents_root = target / ".agents"
        codex_mapping_refs = [
            path for path, _text in _runtime_text_files(agents_root)
            if path.name == "runtime-mapping.md"
        ]
        agents_md = (target / "AGENTS.md").read_text(encoding="utf-8")

        assert codex_mapping_refs or "runtime-mapping.md" in agents_md, (
            "Codex publish must include a Codex runtime mapping reference or "
            "index it from AGENTS.md"
        )

    def test_published_codex_mapping_preserves_surface_to_execution_mapping(
        self, tmp_path, monkeypatch
    ):
        target, _calls = _publish_codex_project(tmp_path, monkeypatch)
        mapping = (
            target / ".agents" / "references" / "runtime-mapping.md"
        ).read_text(encoding="utf-8")

        assert "`/gm-*`" in mapping
        assert "`$gm-*`" in mapping
        assert "`/gm-build` means execute `$gm-build`" in mapping
        assert "| `.claude/skills` | `.agents/skills` |" in mapping
        assert "| `.claude/agents` | `.agents/agents` |" in mapping
        assert "| `.claude/templates` | `.agents/templates` |" in mapping
        assert "| `.claude/godotmaker.yaml` | `.agents/godotmaker.yaml` |" in mapping
        assert "Apply this mapping before filesystem access" in mapping
        assert "read `.agents/godotmaker.yaml`" in mapping
        assert "Codex publish must register `godot-mcp` by default" in mapping
        assert "explicit user\n  opt-in" not in mapping

    def test_published_codex_mapping_uses_single_canonical_reference(
        self, tmp_path, monkeypatch
    ):
        target, _calls = _publish_codex_project(tmp_path, monkeypatch)

        assert (
            target / ".agents" / "references" / "runtime-mapping.md"
        ).exists()
        assert (
            target / ".agents" / "references" / "delegation-worktree.md"
        ).exists()

        for skill_name in PRIMARY_ROLE_SKILLS:
            assert not (
                target / ".agents" / "skills" / skill_name / "references" /
                "runtime-mapping.md"
            ).exists(), f"unexpected skill-local Codex mapping for {skill_name}"

    def test_codex_runtime_tree_keeps_surface_refs_with_mapping(
        self, tmp_path, monkeypatch
    ):
        target, _calls = _publish_codex_project(tmp_path, monkeypatch)
        agents_root = target / ".agents"

        runtime_texts = list(_runtime_text_files(agents_root))
        mapping = "\n".join(
            text for path, text in runtime_texts if path.name == "runtime-mapping.md"
        )
        surface_refs = [
            f"{path.relative_to(target)}"
            for path, text in runtime_texts
            if ".claude/skills" in text
        ]

        assert surface_refs, (
            "Codex publish may keep shared GodotMaker/Claude-first surface "
            "references instead of rewriting every skill inline"
        )
        assert "| `.claude/skills` | `.agents/skills` |" in mapping
        assert "| `.claude/agents` | `.agents/agents` |" in mapping
        assert "| `.claude/templates` | `.agents/templates` |" in mapping
        assert "`/gm-*`" in mapping and "`$gm-*`" in mapping

    def test_codex_literal_slash_gm_execution_requires_mapping(
        self, tmp_path, monkeypatch
    ):
        target, _calls = _publish_codex_project(tmp_path, monkeypatch)
        agents_root = target / ".agents"
        runtime_texts = list(_runtime_text_files(agents_root))
        agents_md = (target / "AGENTS.md").read_text(encoding="utf-8")
        mapping_text = "\n".join(
            [agents_md]
            + [text for path, text in runtime_texts if path.name == "runtime-mapping.md"]
        )
        has_codex_mapping = (
            "/gm-*" in mapping_text
            and "$gm-*" in mapping_text
            and "codex" in mapping_text.lower()
        )

        literal_slash_commands = []
        for path, text in runtime_texts:
            for match in LITERAL_SLASH_GM_EXECUTION.finditer(text):
                literal_slash_commands.append(
                    f"{path.relative_to(target)}: {match.group(0)}"
                )

        assert has_codex_mapping or not literal_slash_commands, (
            "Codex output must not tell Codex to literally execute /gm-* "
            "without a discoverable /gm-* to $gm-* runtime mapping:\n"
            + "\n".join(literal_slash_commands)
        )

    def test_codex_agents_md_indexes_runtime_mapping(self, tmp_path, monkeypatch):
        target, _calls = _publish_codex_project(tmp_path, monkeypatch)
        content = (target / "AGENTS.md").read_text(encoding="utf-8")
        lower = content.lower()

        assert "runtime-mapping.md" in content
        assert "$gm-*" in content
        assert "codex" in lower
        assert "mapping" in lower or "runtime" in lower


class TestPublishMainAgentBranches:
    def test_codex_publish_registers_mcp_by_default(
        self, tmp_path, monkeypatch
    ):
        from _version import SemVer

        target = tmp_path / "target"
        target.mkdir()
        calls: list[str] = []

        def _record(name):
            def _inner(*_args, **_kwargs):
                calls.append(name)
                if name in ("create_godotmaker_yaml", "register_codex_mcp"):
                    return True
                return None
            return _inner

        monkeypatch.setattr(publish, "check_version_upgrade",
                            lambda *_args, **_kwargs: (True, "FRESH", None, SemVer(0, 3, 5)))
        for name in (
            "publish_skills", "publish_shared_refs", "publish_directory",
            "deploy_settings", "deploy_agent_instructions", "create_godotmaker_yaml",
            "create_project_config", "deploy_stage_schemas", "create_project_dirs",
            "register_mcp", "register_codex_mcp", "register_godot_permissions", "ensure_gitignore",
            "ensure_gitattributes",
            "ensure_worktreeinclude", "ensure_git_repo", "write_target_version",
            "baseline_applied",
        ):
            monkeypatch.setattr(publish, name, _record(name))
        monkeypatch.setattr(publish, "read_godot_path", lambda *_args, **_kwargs: "godot")
        monkeypatch.setattr(sys, "argv",
                            ["publish.py", "--agent", "codex", "--force", str(target)])

        publish.main()

        assert "deploy_agent_instructions" in calls
        assert "deploy_settings" not in calls
        assert "register_codex_mcp" in calls
        assert "register_mcp" not in calls
        assert "register_godot_permissions" not in calls
        assert "ensure_worktreeinclude" not in calls

    def test_codex_publish_missing_yaml_does_not_register_mcp_with_fallback_godot(
        self, tmp_path, monkeypatch
    ):
        from _version import SemVer

        target = tmp_path / "target"
        target.mkdir()
        codex_mcp_calls: list[str] = []

        def _no_op(*_args, **_kwargs):
            return None

        monkeypatch.setattr(
            publish,
            "check_version_upgrade",
            lambda *_args, **_kwargs: (True, "FRESH", None, SemVer(0, 3, 5)),
        )
        for name in (
            "publish_skills", "publish_shared_refs", "publish_directory",
            "deploy_settings", "deploy_agent_instructions",
            "create_project_config", "deploy_stage_schemas", "create_project_dirs",
            "register_mcp", "register_godot_permissions", "ensure_gitignore",
            "ensure_gitattributes",
            "ensure_worktreeinclude", "ensure_git_repo", "write_target_version",
            "baseline_applied",
        ):
            monkeypatch.setattr(publish, name, _no_op)
        monkeypatch.setattr(publish, "create_godotmaker_yaml",
                            lambda *_args, **_kwargs: False)
        monkeypatch.setattr(
            publish,
            "register_codex_mcp",
            lambda _target, godot_path: codex_mcp_calls.append(godot_path),
        )
        monkeypatch.setattr(sys, "argv",
                            ["publish.py", "--agent", "codex", "--force", str(target)])

        with pytest.raises(SystemExit):
            publish.main()

        assert codex_mcp_calls == []

    def test_claude_publish_runs_claude_specific_integrations(self, tmp_path, monkeypatch):
        from _version import SemVer

        target = tmp_path / "target"
        target.mkdir()
        calls: list[str] = []

        def _record(name):
            def _inner(*_args, **_kwargs):
                calls.append(name)
                return None
            return _inner

        monkeypatch.setattr(publish, "check_version_upgrade",
                            lambda *_args, **_kwargs: (True, "FRESH", None, SemVer(0, 3, 5)))
        for name in (
            "publish_skills", "publish_shared_refs", "publish_directory",
            "deploy_settings", "deploy_agent_instructions", "create_godotmaker_yaml",
            "create_project_config", "deploy_stage_schemas", "create_project_dirs",
            "register_mcp", "register_codex_mcp", "register_godot_permissions", "ensure_gitignore",
            "ensure_gitattributes",
            "ensure_worktreeinclude", "ensure_git_repo", "write_target_version",
            "baseline_applied",
        ):
            monkeypatch.setattr(publish, name, _record(name))
        monkeypatch.setattr(publish, "read_godot_path", lambda *_args, **_kwargs: "godot")
        monkeypatch.setattr(sys, "argv", ["publish.py", "--force", str(target)])

        publish.main()

        assert "deploy_settings" in calls
        assert "register_mcp" in calls
        assert "register_codex_mcp" not in calls
        assert "register_godot_permissions" in calls
        assert "ensure_worktreeinclude" in calls


class TestPublishMainForceRmtree:
    """End-to-end: publish.main --force must survive a target whose
    .claude/skills contains read-only files (e.g. git pack-*.idx from a
    prior version that cloned godot-docs as a git repo).

    Reproduces the v0.3.2 release-blocker where Windows users upgrading
    from <=0.3.1 hit PermissionError [WinError 5] in shutil.rmtree because
    the rmtree call had no read-only handler. This test exercises the
    elif args.force branch in main(); the MAJOR-force branch above it
    rmtree's the same files via the same helper, so coverage carries.

    Cross-platform note: Linux/macOS unlink read-only files without
    needing the onerror handler, so on those platforms the test only
    proves main() doesn't otherwise break; the actual bug is
    Windows-only and only this OS exercises the fix path.
    """

    @pytest.fixture
    def env(self, tmp_path, monkeypatch):
        # Stub list mirrors every helper publish.main() calls (excluding
        # rmtree_force itself, which we want to exercise). If main() gains
        # a new helper that hits the network or filesystem and isn't stubbed
        # here, this test will start doing real work or failing — re-sync
        # with main() at that point.
        target = tmp_path / "target"
        target.mkdir()

        def _no_op(*a, **kw):
            return None

        for name in (
            "publish_skills", "publish_shared_refs", "publish_directory",
            "deploy_settings", "deploy_agent_instructions", "create_godotmaker_yaml",
            "create_project_config", "deploy_stage_schemas",
            "create_project_dirs", "register_mcp", "register_codex_mcp", "register_godot_permissions",
            "ensure_gitignore", "ensure_gitattributes",
            "ensure_worktreeinclude", "ensure_git_repo", "write_target_version",
        ):
            monkeypatch.setattr(publish, name, _no_op)
        # Migration entry points must be truthy — main() exits 1 on falsy run.
        monkeypatch.setattr(publish, "baseline_applied", lambda _: 0)
        monkeypatch.setattr(publish, "run_migrations", lambda _: True)
        monkeypatch.setattr(publish, "read_godot_path",
                            lambda *a, **kw: "godot")
        return {"target": target}

    def _seed_target_version(self, target, version):
        gm = target / ".godotmaker"
        gm.mkdir(exist_ok=True)
        (gm / "version").write_text(version + "\n")

    def _force_source_version(self, monkeypatch, major, minor, patch):
        from _version import SemVer
        monkeypatch.setattr(publish, "read_source_version",
                            lambda _: SemVer(major, minor, patch))

    def _seed_readonly_pack(self, target):
        # Mirror the actual on-disk shape: prior versions cloned the
        # godot doc repo into .claude/skills/godot-api/doc_source, and
        # git writes pack-*.idx as r--r--r--.
        pack_dir = (target / ".claude" / "skills" / "godot-api"
                    / "doc_source" / ".git" / "objects" / "pack")
        pack_dir.mkdir(parents=True)
        pack = pack_dir / "pack-deadbeef.idx"
        pack.write_bytes(b"fake pack idx")
        pack.chmod(stat.S_IREAD)
        return pack

    def test_force_patch_upgrade_clears_readonly_skill_files(
        self, env, monkeypatch
    ):
        target = env["target"]
        self._seed_target_version(target, "0.3.1")
        self._force_source_version(monkeypatch, 0, 3, 3)
        readonly_pack = self._seed_readonly_pack(target)

        monkeypatch.setattr(sys, "argv",
                            ["publish.py", str(target), "--force"])
        try:
            publish.main()  # would raise PermissionError before the fix
        finally:
            if readonly_pack.exists():
                readonly_pack.chmod(stat.S_IWRITE)

        # The elif branch in main() rmtree's only skills_target then
        # mkdir's it back empty; the seeded read-only file must be gone.
        skills = target / ".claude" / "skills"
        assert skills.exists()
        assert list(skills.iterdir()) == []
