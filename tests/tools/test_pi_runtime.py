"""Targeted contract tests for the Pi publish adapter."""
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import agent_runtime
import publish
from check_env import EnvCheck, check_pi


REPO_ROOT = Path(__file__).resolve().parents[2]
PRIMARY_ROLE_SKILLS = (
    "gm-scaffold", "gm-gdd", "gm-asset", "gm-build", "gm-verify",
    "gm-evaluate", "gm-fixgap", "gm-accept", "gm-finalize",
)


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
    assert publish.publish_agent_plugins(REPO_ROOT, target, publish.AGENT_PI, force=True) == 1

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
    r = EnvCheck()
    check_pi(r, tmp_path)
    assert not r.failed
    assert any("Pi CLI found" in passed for passed in r.passed)
