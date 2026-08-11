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

    @pytest.mark.parametrize("agent", publish.AGENT_CHOICES)
    def test_subset_adopts_matching_files_from_same_version_full_install(
        self, tmp_path, agent
    ):
        target = tmp_path / "target"
        adapter = publish.get_agent_adapter(agent)
        publish.publish_skills(REPO_ROOT, adapter.skill_dir(target), agent)
        publish.publish_asset_runtime(REPO_ROOT, target)
        publish.publish_directory(
            REPO_ROOT / "tools", target / "tools", "tools/"
        )
        source_version = publish.read_source_version(REPO_ROOT)
        assert source_version is not None
        version = target / ".godotmaker" / "version"
        version.parent.mkdir(parents=True, exist_ok=True)
        version.write_text(f"{source_version}\n", encoding="utf-8")
        managed = publish._asset_subset_managed_files(REPO_ROOT, agent)
        before = {
            relative: (target / relative).read_bytes()
            for relative in managed
        }
        full_only_skill = adapter.skill_dir(target) / "gm-build" / "SKILL.md"
        full_only_tool = target / "tools" / "publish.py"
        assert full_only_skill.is_file()
        assert full_only_tool.is_file()
        assert not (target / publish.ASSET_SUBSET_STATE_TARGET).exists()

        publish.publish_asset_subset(REPO_ROOT, target, agent=agent)

        state = json.loads(
            (target / publish.ASSET_SUBSET_STATE_TARGET).read_text(
                encoding="utf-8"
            )
        )
        assert state["agent"] == agent
        assert state["managed_files"] == [
            path.as_posix() for path in managed
        ]
        assert {
            relative: (target / relative).read_bytes()
            for relative in managed
        } == before
        assert full_only_skill.is_file()
        assert full_only_tool.is_file()
        assert full_only_skill.relative_to(target).as_posix() not in state[
            "managed_files"
        ]
        assert full_only_tool.relative_to(target).as_posix() not in state[
            "managed_files"
        ]
        assert version.read_text(encoding="utf-8") == f"{source_version}\n"

    @pytest.mark.parametrize(
        "surface",
        ["skill", "runtime", "provider", "runtime_claim", "declared_tool"],
    )
    def test_full_install_adoption_rejects_changed_managed_file(
        self, tmp_path, surface
    ):
        target = tmp_path / "target"
        agent = publish.AGENT_CODEX
        adapter = publish.get_agent_adapter(agent)
        publish.publish_skills(REPO_ROOT, adapter.skill_dir(target), agent)
        publish.publish_asset_runtime(REPO_ROOT, target)
        publish.publish_directory(
            REPO_ROOT / "tools", target / "tools", "tools/"
        )
        source_version = publish.read_source_version(REPO_ROOT)
        assert source_version is not None
        version = target / ".godotmaker" / "version"
        version.parent.mkdir(parents=True, exist_ok=True)
        version.write_text(f"{source_version}\n", encoding="utf-8")
        candidates = {
            "skill": adapter.skill_dir(target) / "tileset" / "SKILL.md",
            "runtime": (
                target
                / publish.ASSET_RUNTIME_TARGET
                / "animation-planning.md"
            ),
            "provider": (
                target
                / publish.ASSET_RUNTIME_TARGET
                / "references"
                / "providers"
                / "openai.md"
            ),
            "runtime_claim": (
                target
                / publish.ASSET_RUNTIME_TARGET
                / "tools"
                / "codex_image_claim.py"
            ),
            "declared_tool": (
                target
                / publish._asset_subset_tool_paths(REPO_ROOT)[0]
            ),
        }
        changed = candidates[surface]
        assert changed.is_file()
        changed.write_bytes(changed.read_bytes() + b"\nuser-owned change\n")
        before = {
            path.relative_to(target): path.read_bytes()
            for path in target.rglob("*")
            if path.is_file()
        }

        with pytest.raises(ValueError, match="unowned file") as exc_info:
            publish.publish_asset_subset(REPO_ROOT, target, agent=agent)

        assert changed.relative_to(target).as_posix() in str(exc_info.value)
        after = {
            path.relative_to(target): path.read_bytes()
            for path in target.rglob("*")
            if path.is_file()
        }
        assert after == before
        assert not (target / publish.ASSET_SUBSET_STATE_TARGET).exists()

    def test_first_install_rejects_identical_file_without_full_version(
        self, tmp_path
    ):
        target = tmp_path / "target"
        agent = publish.AGENT_CODEX
        destination = (
            publish.get_agent_adapter(agent).skill_dir(target)
            / "tileset"
            / "SKILL.md"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        source = REPO_ROOT / "skills" / "assets" / "tileset" / "SKILL.md"
        shutil.copy2(source, destination)
        before = destination.read_bytes()

        with pytest.raises(ValueError, match="unowned file"):
            publish.publish_asset_subset(REPO_ROOT, target, agent=agent)

        assert destination.read_bytes() == before
        assert not (target / publish.ASSET_SUBSET_STATE_TARGET).exists()

    def test_existing_subset_state_prevents_implicit_full_install_adoption(
        self, tmp_path
    ):
        target = tmp_path / "target"
        agent = publish.AGENT_CODEX
        destination = (
            publish.get_agent_adapter(agent).skill_dir(target)
            / "tileset"
            / "SKILL.md"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        source = REPO_ROOT / "skills" / "assets" / "tileset" / "SKILL.md"
        shutil.copy2(source, destination)
        source_version = publish.read_source_version(REPO_ROOT)
        assert source_version is not None
        version = target / ".godotmaker" / "version"
        version.parent.mkdir(parents=True, exist_ok=True)
        version.write_text(f"{source_version}\n", encoding="utf-8")
        state = target / publish.ASSET_SUBSET_STATE_TARGET
        state.write_text(
            json.dumps({
                "schema_version": 1,
                "subset": "assets",
                "agent": agent,
                "managed_files": [],
            }),
            encoding="utf-8",
        )
        before = destination.read_bytes()

        with pytest.raises(ValueError, match="unowned file"):
            publish.publish_asset_subset(REPO_ROOT, target, agent=agent)

        assert destination.read_bytes() == before
        installed_state = json.loads(state.read_text(encoding="utf-8"))
        assert installed_state["managed_files"] == []

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
    @pytest.mark.parametrize("force", [False, True])
    def test_update_preserves_unowned_files_inside_subset_directories(
        self, tmp_path, force
    ):
        target = tmp_path / "target"
        publish.publish_asset_subset(
            REPO_ROOT, target, agent=publish.AGENT_CODEX
        )
        skill_note = (
            publish.get_agent_adapter(publish.AGENT_CODEX).skill_dir(target)
            / "tileset"
            / "user-note.md"
        )
        runtime_note = (
            target / publish.ASSET_RUNTIME_TARGET / "user-runtime-note.txt"
        )
        provider_note = (
            target
            / publish.ASSET_RUNTIME_TARGET
            / "references"
            / "providers"
            / "user-provider-note.txt"
        )
        skill_note.write_text("keep skill note\n", encoding="utf-8")
        runtime_note.write_text("keep runtime note\n", encoding="utf-8")
        provider_note.write_text("keep provider note\n", encoding="utf-8")

        publish.publish_asset_subset(
            REPO_ROOT,
            target,
            agent=publish.AGENT_CODEX,
            force=force,
        )

        assert skill_note.read_text(encoding="utf-8") == "keep skill note\n"
        assert runtime_note.read_text(encoding="utf-8") == "keep runtime note\n"
        assert provider_note.read_text(
            encoding="utf-8"
        ) == "keep provider note\n"

    def test_first_install_rejects_unowned_file_collision(self, tmp_path):
        target = tmp_path / "target"
        skill_file = (
            publish.get_agent_adapter(publish.AGENT_CODEX).skill_dir(target)
            / "tileset"
            / "SKILL.md"
        )
        skill_file.parent.mkdir(parents=True)
        skill_file.write_text("user-owned skill\n", encoding="utf-8")

        with pytest.raises(ValueError, match="unowned file"):
            publish.publish_asset_subset(
                REPO_ROOT,
                target,
                agent=publish.AGENT_CODEX,
                force=True,
            )

        assert skill_file.read_text(encoding="utf-8") == "user-owned skill\n"
        assert not (target / publish.ASSET_SUBSET_STATE_TARGET).exists()

    @pytest.mark.parametrize("force", [False, True])
    def test_update_removes_retired_inventory_entries(
        self, tmp_path, monkeypatch, force
    ):
        target = tmp_path / "target"
        manifest = json.loads(
            (REPO_ROOT / publish.ASSET_SUBSET_MANIFEST_SOURCE).read_text(
                encoding="utf-8"
            )
        )
        manifest["retired_files"] = {
            "skills": ["tileset/retired-skill-file.md"],
            "runtime": ["retired-runtime-file.py"],
            "tools": ["tools/retired_asset_tool.py"],
        }
        monkeypatch.setattr(
            publish, "_read_asset_subset_manifest", lambda _repo: manifest
        )
        publish.publish_asset_subset(
            REPO_ROOT, target, agent=publish.AGENT_CODEX
        )

        adapter = publish.get_agent_adapter(publish.AGENT_CODEX)
        retired = (
            Path(adapter.skill_root) / "tileset" / "retired-skill-file.md",
            publish.ASSET_RUNTIME_TARGET / "retired-runtime-file.py",
            Path("tools") / "retired_asset_tool.py",
        )
        state_path = target / publish.ASSET_SUBSET_STATE_TARGET
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["managed_files"].extend(path.as_posix() for path in retired)
        state_path.write_text(json.dumps(state), encoding="utf-8")
        for relative in retired:
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text("obsolete\n", encoding="utf-8")

        publish.publish_asset_subset(
            REPO_ROOT,
            target,
            agent=publish.AGENT_CODEX,
            force=force,
        )

        assert all(not (target / relative).exists() for relative in retired)
        updated_state = json.loads(state_path.read_text(encoding="utf-8"))
        assert all(
            relative.as_posix() not in updated_state["managed_files"]
            for relative in retired
        )

    @pytest.mark.parametrize(
        ("category", "path"),
        [
            ("skills", "../outside.md"),
            ("runtime", "../outside.py"),
            ("tools", "README.md"),
        ],
    )
    def test_manifest_rejects_unsafe_retired_files(
        self, tmp_path, monkeypatch, category, path
    ):
        manifest = json.loads(
            (REPO_ROOT / publish.ASSET_SUBSET_MANIFEST_SOURCE).read_text(
                encoding="utf-8"
            )
        )
        manifest["retired_files"] = {
            "skills": [],
            "runtime": [],
            "tools": [],
        }
        manifest["retired_files"][category] = [path]
        monkeypatch.setattr(
            publish, "_read_asset_subset_manifest", lambda _repo: manifest
        )

        with pytest.raises(ValueError, match="retired"):
            publish.publish_asset_subset(
                REPO_ROOT,
                tmp_path / "target",
                agent=publish.AGENT_CODEX,
            )

    @pytest.mark.parametrize(
        "relative",
        [
            Path(".agents") / "skills" / "tileset" / "user-note.md",
            publish.ASSET_RUNTIME_TARGET / "user-runtime.py",
            Path("tools") / "user_asset_tool.py",
        ],
    )
    def test_force_rejects_unlisted_files_inside_subset_boundaries(
        self, tmp_path, relative
    ):
        target = tmp_path / "target"
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("keep\n", encoding="utf-8")
        state = target / publish.ASSET_SUBSET_STATE_TARGET
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(
            json.dumps({
                "schema_version": 1,
                "subset": "assets",
                "agent": publish.AGENT_CODEX,
                "managed_files": [relative.as_posix()],
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

        assert destination.read_text(encoding="utf-8") == "keep\n"

    @pytest.mark.parametrize(
        "blocking_path",
        [
            Path(".godotmaker"),
            Path("tools"),
            Path(".agents") / "skills",
        ],
    )
    def test_first_install_rejects_non_directory_parent_without_partial_publish(
        self, tmp_path, blocking_path
    ):
        target = tmp_path / "target"
        blocker = target / blocking_path
        blocker.parent.mkdir(parents=True, exist_ok=True)
        blocker.write_text("keep blocker\n", encoding="utf-8")
        before = {
            path.relative_to(target)
            for path in target.rglob("*")
            if path.is_file()
        }

        with pytest.raises(ValueError, match="parent must be a directory"):
            publish.publish_asset_subset(
                REPO_ROOT,
                target,
                agent=publish.AGENT_CODEX,
                force=True,
            )

        after = {
            path.relative_to(target)
            for path in target.rglob("*")
            if path.is_file()
        }
        assert after == before
        assert blocker.read_text(encoding="utf-8") == "keep blocker\n"

    def test_update_between_agent_layouts_preserves_unowned_files(
        self, tmp_path
    ):
        target = tmp_path / "target"
        publish.publish_asset_subset(
            REPO_ROOT, target, agent=publish.AGENT_CODEX
        )
        codex_skills = publish.get_agent_adapter(
            publish.AGENT_CODEX
        ).skill_dir(target)
        custom_note = codex_skills / "tileset" / "user-note.md"
        custom_note.write_text("keep\n", encoding="utf-8")

        publish.publish_asset_subset(
            REPO_ROOT,
            target,
            agent=publish.AGENT_CLAUDE_CODE,
            force=True,
        )

        claude_skills = publish.get_agent_adapter(
            publish.AGENT_CLAUDE_CODE
        ).skill_dir(target)
        state = json.loads(
            (target / publish.ASSET_SUBSET_STATE_TARGET).read_text(
                encoding="utf-8"
            )
        )
        assert custom_note.read_text(encoding="utf-8") == "keep\n"
        assert not (codex_skills / "tileset" / "SKILL.md").exists()
        assert (claude_skills / "tileset" / "SKILL.md").is_file()
        assert state["agent"] == publish.AGENT_CLAUDE_CODE

    @pytest.mark.parametrize(
        ("agent", "config_root"),
        [
            (publish.AGENT_OPENCODE, ".opencode"),
            (publish.AGENT_PI, ".pi"),
        ],
    )
    def test_agent_switch_runtime_uses_recorded_subset_agent(
        self, tmp_path, agent, config_root
    ):
        target = tmp_path / "target"
        publish.publish_asset_subset(
            REPO_ROOT, target, agent=publish.AGENT_CODEX
        )
        old_config = target / ".agents" / "godotmaker.yaml"
        old_config.write_text("godot_path: old-codex\n", encoding="utf-8")
        selected_config = target / config_root / "godotmaker.yaml"
        selected_config.parent.mkdir(parents=True, exist_ok=True)
        selected_config.write_text(
            f"godot_path: selected-{agent}\n", encoding="utf-8"
        )

        publish.publish_asset_subset(
            REPO_ROOT, target, agent=agent, force=True
        )

        result = subprocess.run(
            [
                sys.executable,
                str(target / "tools" / "agent_runtime.py"),
                "godot_path",
                "--project",
                str(target),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == f"selected-{agent}"
        assert old_config.read_text(encoding="utf-8") == (
            "godot_path: old-codex\n"
        )

    def test_agent_switch_preflights_old_layout_before_removing_files(
        self, tmp_path, monkeypatch
    ):
        target = tmp_path / "target"
        publish.publish_asset_subset(
            REPO_ROOT, target, agent=publish.AGENT_CODEX
        )
        previous = publish._asset_subset_managed_files(
            REPO_ROOT, publish.AGENT_CODEX
        )
        blocked = Path(".agents/skills/tileset/SKILL.md")
        preserved_relative = next(
            path for path in previous
            if path.name == "SKILL.md" and path.as_posix() < blocked.as_posix()
        )
        preserved = target / preserved_relative
        preserved_content = preserved.read_bytes()
        original_safe_target = publish._safe_subset_target

        def reject_late_old_layout_path(project, relative):
            normalized = publish.validate_asset_subset_path(relative)
            if normalized == blocked:
                raise ValueError("simulated unsafe old-layout parent")
            return original_safe_target(project, normalized)

        monkeypatch.setattr(
            publish, "_safe_subset_target", reject_late_old_layout_path
        )

        with pytest.raises(ValueError, match="unsafe old-layout parent"):
            publish.publish_asset_subset(
                REPO_ROOT,
                target,
                agent=publish.AGENT_CLAUDE_CODE,
                force=True,
            )

        assert preserved.read_bytes() == preserved_content
        assert not (target / ".claude").exists()

    @pytest.mark.parametrize("force", [False, True])
    def test_copy_failure_rolls_back_files_and_state(
        self, tmp_path, monkeypatch, force
    ):
        target = tmp_path / "target"
        publish.publish_asset_subset(
            REPO_ROOT, target, agent=publish.AGENT_CODEX
        )
        managed = publish._asset_subset_managed_files(
            REPO_ROOT, publish.AGENT_CODEX
        )
        first_target = target / managed[0]
        first_target.write_text("preserve previous content\n", encoding="utf-8")
        before = {
            path.relative_to(target): path.read_bytes()
            for path in target.rglob("*")
            if path.is_file()
        }
        fail_at = target / managed[1]
        original_copy2 = publish.shutil.copy2
        failed = False

        def fail_once_during_target_copy(source, destination, *args, **kwargs):
            nonlocal failed
            if Path(destination) == fail_at and not failed:
                failed = True
                raise OSError("simulated target copy failure")
            return original_copy2(source, destination, *args, **kwargs)

        monkeypatch.setattr(
            publish.shutil, "copy2", fail_once_during_target_copy
        )

        with pytest.raises(OSError, match="target copy failure"):
            publish.publish_asset_subset(
                REPO_ROOT,
                target,
                agent=publish.AGENT_CODEX,
                force=force,
            )

        after = {
            path.relative_to(target): path.read_bytes()
            for path in target.rglob("*")
            if path.is_file()
        }
        assert failed
        assert after == before

    def test_state_write_failure_rolls_back_published_files(
        self, tmp_path, monkeypatch
    ):
        target = tmp_path / "target"
        publish.publish_asset_subset(
            REPO_ROOT, target, agent=publish.AGENT_CODEX
        )
        managed = publish._asset_subset_managed_files(
            REPO_ROOT, publish.AGENT_CODEX
        )
        changed_target = target / managed[0]
        changed_target.write_text(
            "preserve previous content\n", encoding="utf-8"
        )
        before = {
            path.relative_to(target): path.read_bytes()
            for path in target.rglob("*")
            if path.is_file()
        }
        state_parent = target / ".godotmaker"
        original_write_text = Path.write_text

        def fail_subset_state_write(path, content, *args, **kwargs):
            if (
                path.parent == state_parent
                and '"managed_files"' in content
            ):
                raise OSError("simulated state write failure")
            return original_write_text(path, content, *args, **kwargs)

        monkeypatch.setattr(Path, "write_text", fail_subset_state_write)

        with pytest.raises(OSError, match="state write failure"):
            publish.publish_asset_subset(
                REPO_ROOT, target, agent=publish.AGENT_CODEX
            )

        after = {
            path.relative_to(target): path.read_bytes()
            for path in target.rglob("*")
            if path.is_file()
        }
        assert after == before

    def test_source_tree_rejects_symlinks(self, tmp_path, monkeypatch):
        source = tmp_path / "source"
        source.mkdir()
        linked = source / "linked.py"
        linked.write_text("external content\n", encoding="utf-8")
        original_is_symlink = Path.is_symlink
        monkeypatch.setattr(
            Path,
            "is_symlink",
            lambda path: path == linked or original_is_symlink(path),
        )

        with pytest.raises(ValueError, match="source must not contain symlinks"):
            publish._source_tree_files(source)


    def _make_synthetic_subset_repo(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        family = "fixture-skill"
        skill = repo / "skills" / "assets" / family
        runtime = repo / publish.ASSET_RUNTIME_SOURCE
        providers = repo / publish.ASSET_PROVIDER_REFERENCES_SOURCE
        tools = repo / "tools"
        config = repo / "config"
        for directory in (skill, runtime, providers, tools, config):
            directory.mkdir(parents=True, exist_ok=True)

        (skill / "SKILL.md").write_text("fixture skill\n", encoding="utf-8")
        (skill / "claude.md.tmpl").write_text(
            "Write CLAUDE.md\n", encoding="utf-8"
        )
        (runtime / "runtime.py").write_text("RUNTIME = 1\n", encoding="utf-8")
        (providers / "provider.md").write_text("provider\n", encoding="utf-8")
        (tools / "codex_image_claim.py").write_text(
            "CLAIM = 1\n", encoding="utf-8"
        )
        (tools / "asset_demo.py").write_text("TOOL = 1\n", encoding="utf-8")
        (config / "asset_subset_manifest.json").write_text(
            json.dumps({
                "schema_version": 1,
                "tools": ["tools/asset_demo.py"],
                "retired_files": {
                    "skills": [],
                    "runtime": [],
                    "tools": [],
                },
            }),
            encoding="utf-8",
        )
        monkeypatch.setattr(publish, "FAMILY_NAMES", (family,))
        sources = {
            "skill": skill / "SKILL.md",
            "runtime": runtime / "runtime.py",
            "provider": providers / "provider.md",
            "tool": tools / "asset_demo.py",
            "claim": tools / "codex_image_claim.py",
            "manifest": config / "asset_subset_manifest.json",
        }
        return repo, family, sources

    @pytest.mark.parametrize(
        "agent",
        [
            publish.AGENT_CODEX,
            publish.AGENT_OPENCODE,
            publish.AGENT_PI,
        ],
    )
    def test_rendered_template_path_is_recorded_in_managed_inventory(
        self, tmp_path, monkeypatch, agent
    ):
        repo, family, _ = self._make_synthetic_subset_repo(
            tmp_path, monkeypatch
        )
        target = tmp_path / "target"

        publish.publish_asset_subset(repo, target, agent=agent)

        adapter = publish.get_agent_adapter(agent)
        skill = adapter.skill_dir(target) / family
        rendered = skill / "agents.md.tmpl"
        state = json.loads(
            (target / publish.ASSET_SUBSET_STATE_TARGET).read_text(
                encoding="utf-8"
            )
        )
        rendered_relative = rendered.relative_to(target).as_posix()
        source_relative = (
            skill / "claude.md.tmpl"
        ).relative_to(target).as_posix()
        assert rendered.read_text(encoding="utf-8") == (
            f"Write {adapter.root_instruction_filename}\n"
        )
        assert not (skill / "claude.md.tmpl").exists()
        assert rendered_relative in state["managed_files"]
        assert source_relative not in state["managed_files"]

    @pytest.mark.parametrize("agent", publish.AGENT_CHOICES)
    def test_retired_template_removes_rendered_agent_path(
        self, tmp_path, monkeypatch, agent
    ):
        repo, family, _ = self._make_synthetic_subset_repo(
            tmp_path, monkeypatch
        )
        target = tmp_path / "target"
        publish.publish_asset_subset(repo, target, agent=agent)
        adapter = publish.get_agent_adapter(agent)
        template_name = (
            "claude.md.tmpl"
            if agent == publish.AGENT_CLAUDE_CODE
            else "agents.md.tmpl"
        )
        installed_template = (
            adapter.skill_dir(target) / family / template_name
        )
        assert installed_template.is_file()

        (repo / "skills" / "assets" / family / "claude.md.tmpl").unlink()
        manifest_path = repo / publish.ASSET_SUBSET_MANIFEST_SOURCE
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["retired_files"]["skills"] = [
            f"{family}/claude.md.tmpl"
        ]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        publish.publish_asset_subset(repo, target, agent=agent)

        state = json.loads(
            (target / publish.ASSET_SUBSET_STATE_TARGET).read_text(
                encoding="utf-8"
            )
        )
        assert not installed_template.exists()
        assert installed_template.relative_to(target).as_posix() not in state[
            "managed_files"
        ]

    @pytest.mark.parametrize(
        "agent",
        [publish.AGENT_CODEX, publish.AGENT_OPENCODE, publish.AGENT_PI],
    )
    def test_retired_template_mapping_rejects_duplicate_targets(
        self, tmp_path, monkeypatch, agent
    ):
        repo, family, _ = self._make_synthetic_subset_repo(
            tmp_path, monkeypatch
        )
        (repo / "skills" / "assets" / family / "claude.md.tmpl").unlink()
        manifest_path = repo / publish.ASSET_SUBSET_MANIFEST_SOURCE
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["retired_files"]["skills"] = [
            f"{family}/claude.md.tmpl",
            f"{family}/agents.md.tmpl",
        ]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        with pytest.raises(ValueError, match="duplicate"):
            publish._asset_subset_retired_files(repo, agent)

    @pytest.mark.parametrize(
        "agent",
        [publish.AGENT_CODEX, publish.AGENT_OPENCODE, publish.AGENT_PI],
    )
    def test_retired_template_mapping_rejects_current_target_overlap(
        self, tmp_path, monkeypatch, agent
    ):
        repo, family, _ = self._make_synthetic_subset_repo(
            tmp_path, monkeypatch
        )
        manifest_path = repo / publish.ASSET_SUBSET_MANIFEST_SOURCE
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["retired_files"]["skills"] = [
            f"{family}/claude.md.tmpl"
        ]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        with pytest.raises(ValueError, match="still current"):
            publish._asset_subset_retired_files(repo, agent)

    @pytest.mark.parametrize(
        "agent",
        [
            publish.AGENT_CODEX,
            publish.AGENT_OPENCODE,
            publish.AGENT_PI,
        ],
    )
    def test_subset_adopts_identical_rendered_template_from_full_install(
        self, tmp_path, monkeypatch, agent
    ):
        repo, family, _ = self._make_synthetic_subset_repo(
            tmp_path, monkeypatch
        )
        (repo / "VERSION").write_text("1.0.0\n", encoding="utf-8")
        target = tmp_path / "target"
        adapter = publish.get_agent_adapter(agent)
        publish.publish_skills(repo, adapter.skill_dir(target), agent)
        publish.publish_asset_runtime(repo, target)
        publish.publish_directory(repo / "tools", target / "tools", "tools/")
        version = target / ".godotmaker" / "version"
        version.parent.mkdir(parents=True, exist_ok=True)
        version.write_text("1.0.0\n", encoding="utf-8")
        rendered = adapter.skill_dir(target) / family / "agents.md.tmpl"
        expected = f"Write {adapter.root_instruction_filename}\n"
        assert rendered.read_text(encoding="utf-8") == expected
        assert not (target / publish.ASSET_SUBSET_STATE_TARGET).exists()

        publish.publish_asset_subset(repo, target, agent=agent)

        state = json.loads(
            (target / publish.ASSET_SUBSET_STATE_TARGET).read_text(
                encoding="utf-8"
            )
        )
        rendered_relative = rendered.relative_to(target).as_posix()
        source_relative = (
            rendered.with_name("claude.md.tmpl")
            .relative_to(target)
            .as_posix()
        )
        assert rendered.read_text(encoding="utf-8") == expected
        assert rendered_relative in state["managed_files"]
        assert source_relative not in state["managed_files"]

    def test_rendered_template_collision_is_rejected_before_target_mutation(
        self, tmp_path, monkeypatch
    ):
        repo, family, _ = self._make_synthetic_subset_repo(
            tmp_path, monkeypatch
        )
        (repo / "skills" / "assets" / family / "agents.md.tmpl").write_text(
            "existing target\n", encoding="utf-8"
        )
        target = tmp_path / "target"
        target.mkdir()
        marker = target / "keep.txt"
        marker.write_text("keep\n", encoding="utf-8")

        with pytest.raises(ValueError, match="same target"):
            publish.publish_asset_subset(
                repo, target, agent=publish.AGENT_CODEX
            )

        assert marker.read_text(encoding="utf-8") == "keep\n"
        assert {path for path in target.rglob("*") if path.is_file()} == {
            marker
        }

    @pytest.mark.parametrize(
        "surface",
        ["skill", "runtime", "provider", "tool", "claim", "manifest"],
    )
    def test_symlinked_source_is_rejected_before_target_mutation(
        self, tmp_path, monkeypatch, surface
    ):
        repo, _, sources = self._make_synthetic_subset_repo(
            tmp_path, monkeypatch
        )
        linked = sources[surface]
        original_is_symlink = Path.is_symlink
        monkeypatch.setattr(
            Path,
            "is_symlink",
            lambda path: path == linked or original_is_symlink(path),
        )
        target = tmp_path / "target"
        target.mkdir()
        marker = target / "keep.txt"
        marker.write_text("keep\n", encoding="utf-8")

        with pytest.raises(ValueError, match="symlink"):
            publish.publish_asset_subset(
                repo, target, agent=publish.AGENT_CODEX
            )

        assert marker.read_text(encoding="utf-8") == "keep\n"
        assert {path for path in target.rglob("*") if path.is_file()} == {
            marker
        }


    def test_first_install_copy_failure_leaves_no_partial_layout(
        self, tmp_path, monkeypatch
    ):
        target = tmp_path / "target"
        target.mkdir()
        marker = target / "keep.txt"
        marker.write_text("keep\n", encoding="utf-8")
        before = {
            path.relative_to(target): (
                "directory" if path.is_dir() else path.read_bytes()
            )
            for path in target.rglob("*")
        }
        managed = publish._asset_subset_managed_files(
            REPO_ROOT, publish.AGENT_CODEX
        )
        fail_at = target / managed[0]
        original_copy2 = publish.shutil.copy2
        failed = False

        def fail_once_during_target_copy(source, destination, *args, **kwargs):
            nonlocal failed
            if Path(destination) == fail_at and not failed:
                failed = True
                raise OSError("simulated first-install copy failure")
            return original_copy2(source, destination, *args, **kwargs)

        monkeypatch.setattr(
            publish.shutil, "copy2", fail_once_during_target_copy
        )

        with pytest.raises(OSError, match="first-install copy failure"):
            publish.publish_asset_subset(
                REPO_ROOT, target, agent=publish.AGENT_CODEX
            )

        assert failed
        assert {
            path.relative_to(target): (
                "directory" if path.is_dir() else path.read_bytes()
            )
            for path in target.rglob("*")
        } == before

    @pytest.mark.parametrize("force", [False, True])
    def test_retired_removal_failure_rolls_back_files_and_state(
        self, tmp_path, monkeypatch, force
    ):
        target = tmp_path / "target"
        manifest = json.loads(
            (REPO_ROOT / publish.ASSET_SUBSET_MANIFEST_SOURCE).read_text(
                encoding="utf-8"
            )
        )
        retired = [
            Path("tools/retired-a.py"),
            Path("tools/retired-z.py"),
        ]
        manifest["retired_files"] = {
            "skills": [],
            "runtime": [],
            "tools": [path.as_posix() for path in retired],
        }
        monkeypatch.setattr(
            publish, "_read_asset_subset_manifest", lambda _repo: manifest
        )
        publish.publish_asset_subset(
            REPO_ROOT, target, agent=publish.AGENT_CODEX
        )
        state_path = target / publish.ASSET_SUBSET_STATE_TARGET
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["managed_files"].extend(path.as_posix() for path in retired)
        state_path.write_text(json.dumps(state), encoding="utf-8")
        for relative in retired:
            destination = target / relative
            destination.write_text(
                f"preserve {relative.name}\n", encoding="utf-8"
            )
        before = {
            path.relative_to(target): path.read_bytes()
            for path in target.rglob("*")
            if path.is_file()
        }
        original_remove = publish._remove_asset_subset_files

        def fail_after_first_removal(project, paths):
            ordered = sorted(paths, key=lambda item: item.as_posix())
            original_remove(project, {ordered[0]})
            raise OSError("simulated retired removal failure")

        monkeypatch.setattr(
            publish, "_remove_asset_subset_files", fail_after_first_removal
        )

        with pytest.raises(OSError, match="retired removal failure"):
            publish.publish_asset_subset(
                REPO_ROOT,
                target,
                agent=publish.AGENT_CODEX,
                force=force,
            )

        after = {
            path.relative_to(target): path.read_bytes()
            for path in target.rglob("*")
            if path.is_file()
        }
        assert after == before
