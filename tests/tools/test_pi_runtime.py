"""Targeted contract tests for the Pi publish adapter."""
import json
from pathlib import Path
import re
import subprocess
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import agent_runtime
import publish
from check_env import EnvCheck, check_pi


REPO_ROOT = Path(__file__).resolve().parents[2]
PI_POLICY = REPO_ROOT / "agent-runtimes" / "pi" / "extensions" / "delegate-policy.mjs"
PRIMARY_ROLE_SKILLS = (
    "gm-scaffold", "gm-gdd", "gm-asset", "gm-build", "gm-verify",
    "gm-evaluate", "gm-fixgap", "gm-accept", "gm-finalize",
)


def _run_delegate_policy(root: Path, role: str, explicit_model: str | None = None):
    script = """
import { pathToFileURL } from "node:url";
const policy = await import(pathToFileURL(process.argv[1]).href);
const explicitModel = process.argv[4] === "__UNSET__" ? undefined : process.argv[4];
const model = policy.resolveDelegateModel(process.argv[2], process.argv[3], explicitModel);
const args = policy.buildDelegateArgs(process.argv[3], "test task", "role.md", model);
console.log(JSON.stringify({ model, args, roles: Object.keys(policy.ROLE_POLICIES) }));
"""
    result = subprocess.run(
        [
            "node", "--input-type=module", "-e", script,
            str(PI_POLICY), str(root), role, explicit_model or "__UNSET__",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def _table_roles(path: Path, heading: str) -> set[str]:
    text = path.read_text(encoding="utf-8")
    section = text.split(heading, 1)[1].split("\n## ", 1)[0]
    return set(re.findall(r"^\|\s*`?([a-z][a-z-]*)`?\s*\|", section, re.MULTILINE))


def test_pi_aliases_and_project_paths():
    assert agent_runtime.normalize_agent("pi-coding-agent") == agent_runtime.AGENT_PI
    project = Path("/tmp/pi-project")
    assert agent_runtime.agent_config_root(project, "pi") == project / ".pi"
    assert agent_runtime.agent_runtime_mapping(project, "pi") == (
        project / ".pi" / "references" / "runtime-mapping.md"
    )


def test_pi_published_runtime_contains_skills_sidecar_and_bridge(tmp_path):
    target = tmp_path / "project"
    skills = target / ".pi" / "skills"
    assert publish.publish_skills(REPO_ROOT, skills, publish.AGENT_PI) > 0
    assert publish.publish_shared_refs(REPO_ROOT, skills, publish.AGENT_PI) > 0
    assert publish.publish_runtime_references(REPO_ROOT, target, publish.AGENT_PI) == 1
    assert publish.publish_agents(REPO_ROOT, target / ".pi" / "agents", publish.AGENT_PI) == 7
    assert publish.publish_agent_plugins(REPO_ROOT, target, publish.AGENT_PI, force=True) == 2

    for name in PRIMARY_ROLE_SKILLS:
        assert (skills / name / "SKILL.md").is_file()
    mapping = (target / ".pi" / "references" / "runtime-mapping.md").read_text(encoding="utf-8")
    extension = (target / ".pi" / "extensions" / "godotmaker-runtime.ts").read_text(encoding="utf-8")
    worker = (target / ".pi" / "agents" / "worker.md").read_text(encoding="utf-8")
    assert "/skill:gm-<role>" in mapping
    assert "godotmaker_delegate" in mapping
    assert "godotmaker_runtime" in extension
    assert ".pi/skills" in worker
    assert ".claude/skills" not in worker
    assert "model: inherit" in worker
    assert "Never write project memory" not in worker
    assert "### Memory Entry" not in worker
    assert "Never write the root MEMORY.md" not in extension


def test_pi_runtime_bridge_fails_closed_for_missing_dependencies():
    runtime = REPO_ROOT / "agent-runtimes" / "pi" / "extensions" / "godotmaker-runtime.ts"
    text = runtime.read_text(encoding="utf-8")
    assert "Pi delegation failed closed" in text
    assert "Missing Pi role definition" in text
    assert "Godot unavailable" in text
    assert "worktree" in text
    assert "REQUIRED_RUNTIME_PATHS" in text
    assert "Pi worktree is missing published runtime resources" in text
    assert '"AGENTS.md"' in text
    assert '".pi/extensions/godotmaker-runtime.ts"' in text
    assert "DEFAULT_DELEGATE_TIMEOUT_SECONDS" in text
    assert "PI_PACKAGE_DIR" in text
    assert 'path.join(packageDir, "dist", "cli.js")' in text
    assert 'path.join(packageDir, "dist", "cli", "index.js")' not in text
    assert '".pi/extensions/delegate-policy.mjs"' in text
    assert "resolveDelegateModel(root, request.role, request.model)" in text
    assert "piInvocation(buildDelegateArgs(" in text


def test_pi_launcher_uses_configured_provider_model_in_default_argv(tmp_path):
    config = tmp_path / ".godotmaker" / "config.yaml"
    config.parent.mkdir()
    config.write_text("worker_model: deepseek/deepseek-v4-flash\n", encoding="utf-8")

    result = _run_delegate_policy(tmp_path, "worker")

    assert result["model"] == "deepseek/deepseek-v4-flash"
    assert result["args"] == [
        "--approve", "--mode", "json", "--no-session",
        "--model", "deepseek/deepseek-v4-flash", "-p",
        "--append-system-prompt", "role.md",
        "GodotMaker role: worker\n\nTask:\ntest task",
    ]


def test_pi_launcher_strips_yaml_inline_comment_from_configured_model(tmp_path):
    config = tmp_path / ".godotmaker" / "config.yaml"
    config.parent.mkdir()
    config.write_text(
        "worker_model: deepseek/deepseek-v4-flash # preferred\n",
        encoding="utf-8",
    )

    result = _run_delegate_policy(tmp_path, "worker")

    assert result["model"] == "deepseek/deepseek-v4-flash"
    assert result["args"][4:6] == ["--model", "deepseek/deepseek-v4-flash"]


def test_pi_launcher_strips_yaml_comment_from_claude_alias(tmp_path):
    config = tmp_path / ".godotmaker" / "config.yaml"
    config.parent.mkdir()
    config.write_text("worker_model: opus # heavier\n", encoding="utf-8")

    result = _run_delegate_policy(tmp_path, "worker")

    assert result["model"] is None
    assert "--model" not in result["args"]


def test_pi_launcher_inherits_for_template_claude_aliases(tmp_path):
    config = tmp_path / ".godotmaker" / "config.yaml"
    config.parent.mkdir()
    config.write_text(
        (REPO_ROOT / "config" / "config.yaml.default").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    for role in _run_delegate_policy(tmp_path, "worker")["roles"]:
        result = _run_delegate_policy(tmp_path, role)
        assert result["model"] is None
        assert "--model" not in result["args"]


def test_pi_launcher_inherits_when_config_is_missing(tmp_path):
    result = _run_delegate_policy(tmp_path, "worker")

    assert result["model"] is None
    assert "--model" not in result["args"]


def test_pi_launcher_explicit_model_overrides_role_policy_argv(tmp_path):
    config = tmp_path / ".godotmaker" / "config.yaml"
    config.parent.mkdir()
    config.write_text("worker_model: sonnet\n", encoding="utf-8")

    result = _run_delegate_policy(tmp_path, "worker", "openai-codex/gpt-5.3-codex")

    assert result["model"] == "openai-codex/gpt-5.3-codex"
    assert result["args"][4:6] == ["--model", "openai-codex/gpt-5.3-codex"]
    assert "sonnet" not in result["args"]


def test_pi_launcher_explicit_inherit_suppresses_configured_model(tmp_path):
    config = tmp_path / ".godotmaker" / "config.yaml"
    config.parent.mkdir()
    config.write_text("worker_model: sonnet\n", encoding="utf-8")

    result = _run_delegate_policy(tmp_path, "worker", "inherit")

    assert result["model"] is None
    assert "--model" not in result["args"]
    assert "sonnet" not in result["args"]


def test_pi_launcher_explicit_claude_alias_inherits_active_model(tmp_path):
    for alias in ("haiku", "sonnet", "opus"):
        result = _run_delegate_policy(tmp_path, "worker", alias)

        assert result["model"] is None
        assert "--model" not in result["args"]


def test_codex_and_pi_role_tables_match_all_published_agents(tmp_path):
    expected = {path.stem for path in (REPO_ROOT / "agents").glob("*.md")}
    policy = set(_run_delegate_policy(tmp_path, "worker")["roles"])
    assert policy == expected
    assert _table_roles(
        REPO_ROOT / "agent-runtimes" / "pi" / "references" / "runtime-mapping.md",
        "## Godot and delegation",
    ) == expected
    assert _table_roles(
        REPO_ROOT / "agent-runtimes" / "codex" / "references" / "runtime-mapping.md",
        "## Delegated Roles",
    ) == expected
    assert _table_roles(
        REPO_ROOT / "agent-runtimes" / "codex" / "references" / "delegation-worktree.md",
        "## Delegated Role Support",
    ) == expected


def test_pi_runtime_delegate_closes_child_stdin():
    runtime = REPO_ROOT / "agent-runtimes" / "pi" / "extensions" / "godotmaker-runtime.ts"
    text = runtime.read_text(encoding="utf-8")
    assert 'stdio: ["ignore", "pipe", "pipe"]' in text


def test_pi_gitignore_covers_runtime_state(tmp_path):
    publish.ensure_gitignore(tmp_path, publish.AGENT_PI)
    entries = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert ".godotmaker/pi-runtime.json" in entries
    assert ".godotmaker/pi-runtime.log" in entries
    assert ".godotmaker/pi-worktrees/" in entries


@patch("check_env.shutil.which", return_value="/usr/bin/pi")
@patch("check_env.get_version", return_value="0.84.1")
def test_check_pi_reports_missing_trust_and_adapter_parts(_version, _which, tmp_path):
    r = EnvCheck()
    check_pi(r, tmp_path)
    assert any(".pi/skills missing" in failure for failure in r.failed)
    assert any("require trust" in warning for warning in r.warnings)


@patch("check_env.shutil.which", return_value="/usr/bin/pi")
@patch("check_env.get_version", return_value="0.84.1")
def test_check_pi_accepts_published_layout(_version, _which, tmp_path):
    for relative in (".pi/skills", ".pi/agents", ".pi/references", ".pi/extensions"):
        (tmp_path / relative).mkdir(parents=True, exist_ok=True)
    (tmp_path / ".pi" / "references" / "runtime-mapping.md").write_text("mapping\n")
    (tmp_path / ".pi" / "godotmaker.yaml").write_text("godot_path: godot\n")
    (tmp_path / ".pi" / "extensions" / "godotmaker-runtime.ts").write_text("export default {}\n")
    (tmp_path / ".pi" / "extensions" / "delegate-policy.mjs").write_text("export {}\n")
    r = EnvCheck()
    check_pi(r, tmp_path)
    assert not r.failed
    assert any("Pi CLI found" in passed for passed in r.passed)
