"""Contract tests for publishing only standalone Asset Skills."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tools",
))

import publish
from asset_family_registry import FAMILY_NAMES


REPO_ROOT = Path(__file__).resolve().parents[2]


class TestAssetSubsetPublishing:
    @pytest.mark.parametrize("agent", publish.AGENT_CHOICES)
    def test_publishes_only_registered_asset_skills(self, tmp_path, agent):
        target = tmp_path / "target"
        skills_target = publish.get_agent_adapter(agent).skill_dir(target)

        count = publish.publish_asset_skills(REPO_ROOT, skills_target, agent)

        published = {
            path.name for path in skills_target.iterdir() if path.is_dir()
        }
        assert count == len(FAMILY_NAMES)
        assert published == set(FAMILY_NAMES)
        assert not (skills_target / "_shared").exists()

    def test_rejects_unsafe_manifest_paths(self):
        for path in (
            Path("../escape.py"),
            Path("tools/../../escape.py"),
            Path("C:/outside.py"),
            Path("/outside.py"),
        ):
            with pytest.raises(ValueError, match="relative"):
                publish.validate_asset_subset_path(path)

    @pytest.mark.parametrize(
        ("tool_paths", "message"),
        [
            (["tools/asset_demo.py", "tools/asset_demo.py"], "duplicate"),
            (["tools/missing.py"], "missing"),
            (["docs/tool.py"], "under tools"),
        ],
    )
    def test_manifest_rejects_invalid_tool_declarations(
        self, tmp_path, tool_paths, message
    ):
        repo = tmp_path / "repo"
        (repo / "config").mkdir(parents=True)
        (repo / "tools").mkdir()
        (repo / "tools" / "asset_demo.py").write_text(
            "VALUE = 1\n", encoding="utf-8"
        )
        (repo / "config" / "asset_subset_manifest.json").write_text(
            json.dumps({"schema_version": 1, "tools": tool_paths}),
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match=message):
            publish._asset_subset_tool_paths(repo)

    @pytest.mark.parametrize("agent", publish.AGENT_CHOICES)
    def test_subset_main_has_no_full_pipeline_side_effects(
        self, tmp_path, monkeypatch, agent
    ):
        target = tmp_path / "target"
        target.mkdir()

        forbidden_calls = (
            "check_version_upgrade",
            "publish_shared_refs",
            "publish_runtime_references",
            "publish_agents",
            "publish_agent_plugins",
            "deploy_agent_hook_config",
            "deploy_agent_instructions",
            "deploy_stage_schemas",
            "register_mcp",
            "register_codex_mcp",
            "register_opencode_mcp",
            "ensure_git_repo",
            "baseline_applied",
            "run_migrations",
            "write_target_version",
        )

        def _unexpected(name):
            def _fail(*_args, **_kwargs):
                pytest.fail(f"asset subset must not call {name}")
            return _fail

        for name in forbidden_calls:
            monkeypatch.setattr(publish, name, _unexpected(name))
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "publish.py",
                "--agent", agent,
                "--subset", "assets",
                "--no-config-review",
                str(target),
            ],
        )

        publish.main()

        adapter = publish.get_agent_adapter(agent)
        published = {
            path.name for path in adapter.skill_dir(target).iterdir()
            if path.is_dir()
        }
        assert published == set(FAMILY_NAMES)
        assert (target / ".godotmaker" / "asset-runtime").is_dir()
        assert (target / ".godotmaker" / "asset-subset.json").is_file()
        assert not (target / ".godotmaker" / "version").exists()
        assert not (target / ".godotmaker" / "applied_migrations.json").exists()
        assert not adapter.agents_dir(target).exists()
        assert not adapter.templates_dir(target).exists()
        assert not (target / ".godotmaker" / "hooks").exists()

    def test_force_preserves_unrelated_target_content(self, tmp_path, monkeypatch):
        target = tmp_path / "target"
        custom_skill = target / ".agents" / "skills" / "custom-skill"
        custom_skill.mkdir(parents=True)
        (custom_skill / "SKILL.md").write_text("custom\n", encoding="utf-8")
        custom_tool = target / "tools" / "custom_tool.py"
        custom_tool.parent.mkdir(parents=True)
        custom_tool.write_text("CUSTOM = True\n", encoding="utf-8")
        custom_hook = target / ".godotmaker" / "hooks" / "custom.py"
        custom_hook.parent.mkdir(parents=True)
        custom_hook.write_text("custom\n", encoding="utf-8")

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "publish.py", "--agent", "codex", "--subset", "assets",
                "--force", "--no-config-review", str(target),
            ],
        )

        publish.main()

        assert (custom_skill / "SKILL.md").read_text(encoding="utf-8") == "custom\n"
        assert custom_tool.read_text(encoding="utf-8") == "CUSTOM = True\n"
        assert custom_hook.read_text(encoding="utf-8") == "custom\n"

    def test_subset_publishes_only_declared_tool_files(self, tmp_path):
        target = tmp_path / "target"

        publish.publish_asset_subset(
            REPO_ROOT, target, agent=publish.AGENT_CODEX, force=False
        )

        manifest = json.loads(
            (target / ".godotmaker" / "asset-subset.json").read_text(
                encoding="utf-8"
            )
        )
        declared_tools = {
            Path(path).name for path in manifest["managed_files"]
            if Path(path).parts[:1] == ("tools",)
        }
        published_tools = {
            path.name for path in (target / "tools").iterdir() if path.is_file()
        }

        assert published_tools == declared_tools
        assert "publish.py" not in published_tools
        assert "agent_runtime.py" in published_tools
        assert "asset_tileset_profile.py" in published_tools

    @pytest.mark.parametrize("agent", publish.AGENT_CHOICES)
    def test_published_workspace_imports_without_source_checkout(
        self, tmp_path, agent
    ):
        target = tmp_path / "target"
        publish.publish_asset_subset(
            REPO_ROOT, target, agent=agent, force=False
        )
        skill_root = publish.get_agent_adapter(agent).skill_root
        script = f'''\
import importlib.util
import sys
from pathlib import Path

target = Path.cwd().resolve()
tools = target / "tools"
runtime = target / ".godotmaker" / "asset-runtime"
skills = target / {skill_root!r}
sys.path.extend((str(runtime), str(tools)))

for tool in sorted(tools.glob("*.py")):
    spec = importlib.util.spec_from_file_location(tool.stem, tool)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)

for family in {sorted(FAMILY_NAMES)!r}:
    runner = skills / family / "standalone_validation.py"
    spec = importlib.util.spec_from_file_location(
        "published_" + family.replace("-", "_"), runner
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert callable(module.compile_and_validate)
'''
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=target,
            text=True,
            capture_output=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr

    @pytest.mark.parametrize("agent", publish.AGENT_CHOICES)
    def test_published_skill_instructions_use_portable_paths(
        self, tmp_path, agent
    ):
        target = tmp_path / "target"
        publish.publish_asset_subset(
            REPO_ROOT, target, agent=agent, force=False
        )
        skills = publish.get_agent_adapter(agent).skill_dir(target)
        forbidden = (
            "skills/core/gm-asset",
            ".agents/skills",
            ".claude/godotmaker.yaml",
        )

        for family in FAMILY_NAMES:
            content = (skills / family / "SKILL.md").read_text(encoding="utf-8")
            for reference in forbidden:
                assert reference not in content, (
                    f"{family} contains agent- or source-specific path {reference}"
                )

    def test_force_rejects_tampered_installed_state(self, tmp_path):
        target = tmp_path / "target"
        state = target / ".godotmaker" / "asset-subset.json"
        state.parent.mkdir(parents=True)
        state.write_text(
            json.dumps({
                "schema_version": 1,
                "subset": "assets",
                "agent": publish.AGENT_CODEX,
                "managed_files": ["../outside.txt"],
            }),
            encoding="utf-8",
        )
        outside = tmp_path / "outside.txt"
        outside.write_text("keep\n", encoding="utf-8")

        with pytest.raises(ValueError, match="relative"):
            publish.publish_asset_subset(
                REPO_ROOT,
                target,
                agent=publish.AGENT_CODEX,
                force=True,
            )

        assert outside.read_text(encoding="utf-8") == "keep\n"

    def test_force_rejects_project_internal_path_not_owned_by_subset(
        self, tmp_path
    ):
        target = tmp_path / "target"
        readme = target / "README.md"
        readme.parent.mkdir(parents=True)
        readme.write_text("keep\n", encoding="utf-8")
        state = target / ".godotmaker" / "asset-subset.json"
        state.parent.mkdir(parents=True)
        state.write_text(
            json.dumps({
                "schema_version": 1,
                "subset": "assets",
                "agent": publish.AGENT_CODEX,
                "managed_files": ["README.md"],
            }),
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="not owned"):
            publish.publish_asset_subset(
                REPO_ROOT,
                target,
                agent=publish.AGENT_CODEX,
                force=True,
            )

        assert readme.read_text(encoding="utf-8") == "keep\n"

    def test_subset_rejects_version_skew_with_full_install(self, tmp_path):
        target = tmp_path / "target"
        version = target / ".godotmaker" / "version"
        version.parent.mkdir(parents=True)
        version.write_text("0.0.0\n", encoding="utf-8")
        runtime_marker = target / ".godotmaker" / "asset-runtime" / "marker.txt"
        runtime_marker.parent.mkdir(parents=True)
        runtime_marker.write_text("full install\n", encoding="utf-8")

        with pytest.raises(ValueError, match="full installation version"):
            publish.publish_asset_subset(
                REPO_ROOT,
                target,
                agent=publish.AGENT_CODEX,
            )

        assert runtime_marker.read_text(encoding="utf-8") == "full install\n"

    def test_subset_coexists_with_same_version_full_install(self, tmp_path):
        target = tmp_path / "target"
        version = target / ".godotmaker" / "version"
        version.parent.mkdir(parents=True)
        source_version = publish.read_source_version(REPO_ROOT)
        assert source_version is not None
        version.write_text(f"{source_version}\n", encoding="utf-8")
        full_marker = target / ".godotmaker" / "hooks" / "full-install.py"
        full_marker.parent.mkdir(parents=True)
        full_marker.write_text("keep\n", encoding="utf-8")

        publish.publish_asset_subset(
            REPO_ROOT,
            target,
            agent=publish.AGENT_CODEX,
        )

        assert version.read_text(encoding="utf-8") == f"{source_version}\n"
        assert full_marker.read_text(encoding="utf-8") == "keep\n"
        assert (target / ".godotmaker" / "asset-runtime").is_dir()

    def test_subset_rejects_project_internal_parent_symlink_before_writing(
        self, tmp_path, monkeypatch
    ):
        target = tmp_path / "target"
        redirect = target / "redirect"
        target.mkdir()
        redirect.mkdir()
        marker = redirect / "keep.txt"
        marker.write_text("keep\n", encoding="utf-8")
        try:
            (target / "tools").symlink_to(redirect, target_is_directory=True)
        except OSError:
            original_is_symlink = Path.is_symlink
            monkeypatch.setattr(
                Path, "is_symlink",
                lambda path: path == target / "tools" or original_is_symlink(path))

        with pytest.raises(ValueError, match="parent must not be a symlink"):
            publish.publish_asset_subset(
                REPO_ROOT,
                target,
                agent=publish.AGENT_CODEX,
            )

        assert marker.read_text(encoding="utf-8") == "keep\n"
        assert not (target / ".godotmaker" / "asset-subset.json").exists()
        assert not (target / ".agents").exists()

    @pytest.mark.skipif(
        shutil.which("powershell") is None,
        reason="PowerShell wrapper is only executable when powershell is installed",
    )
    def test_powershell_wrapper_executes_subset_publish(self, tmp_path):
        target = tmp_path / "target"
        result = subprocess.run(
            [
                shutil.which("powershell"),
                "-NoProfile",
                "-File",
                str(REPO_ROOT / "shell" / "publish.ps1"),
                "--agent",
                "codex",
                "--subset",
                "assets",
                "--no-config-review",
                str(target),
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        assert (target / ".godotmaker" / "asset-subset.json").is_file()

    def test_shell_wrappers_expose_subset_option(self):
        ps1 = (REPO_ROOT / "shell" / "publish.ps1").read_text(encoding="utf-8")
        sh = (REPO_ROOT / "shell" / "publish.sh").read_text(encoding="utf-8")

        assert '$a -eq "--subset"' in ps1
        assert '$pyArgs += @("--subset", $Subset)' in ps1
        assert '"$@"' in sh and "--subset assets" in sh
