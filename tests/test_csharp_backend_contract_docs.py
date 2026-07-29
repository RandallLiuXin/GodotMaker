"""Contract tests for backend-neutral C#/.NET documentation surfaces."""
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def test_config_default_declares_csharp_backend_selectors():
    text = _read("config/config.yaml.default")

    for key in [
        "language_backend: auto",
        "unit_test_backend: auto",
        "# dotnet_target: tests/MyGame.Tests/MyGame.Tests.csproj",
        "# godot_csharp_project: MyGame.csproj",
    ]:
        assert key in text

    assert "Supported values: auto, gdscript, csharp" in text
    assert "Supported values: auto, gdunit, dotnet" in text
    assert "Existing .NET projects are detected" in text
    assert "project-relative .NET solution or test project" in text
    assert "project-relative Godot C# project" in text
    assert "verification_backend" not in text
    assert "csharp_static_check" not in text
    assert "dotnet_target: auto" not in text


def test_scaffold_docs_recognize_existing_csharp_without_generating_architecture():
    scaffold = _read("skills/core/gm-scaffold/SKILL.md")
    project_scaffold = _read("skills/core/project-scaffold/SKILL.md")

    for text in (scaffold, project_scaffold):
        assert "Recognize existing C#/.NET projects" in text
        assert "Do not generate .sln/.csproj or C# ECS architecture" in text
        assert "record `language_backend: csharp`" in text

    assert "unit_test_backend: auto" in scaffold
    assert "verification_backend" not in scaffold


def test_templates_are_backend_neutral():
    plan = _read("templates/PLAN.md")
    structure = _read("templates/STRUCTURE.md")
    game_claude = _read("templates/game-claude.md")

    assert "backend-selected unit tests cover the core algorithm" in plan
    assert "All backend-selected unit tests pass" in plan
    assert "Use backend-native field types" in structure
    assert "backend-owned source files" in structure
    assert "Use the configured language backend" in game_claude
    assert "GDScript for all game logic" not in game_claude
    assert "Unit tests in `test/`, named `test_{name}.gd`" not in game_claude


def test_scaffold_addon_readiness_is_backend_branched():
    scaffold = _read("skills/core/gm-scaffold/SKILL.md")

    assert "Existing C#/.NET resume detection must not require `addons/gecs/`" in scaffold
    assert "GDScript backend required result" in scaffold
    assert "Existing C#/.NET backend required result" in scaffold
    assert "GDScript backend readiness additionally requires" in scaffold
    assert "Existing C#/.NET backend readiness additionally requires" in scaffold
    assert "Godot executable reports a Mono/.NET build" in scaffold
    assert "Missing `addons/gecs/` or `addons/gdUnit4/` must not fail existing C#/.NET scaffold readiness" in scaffold
    assert "C# projects enable only the shared `godot_e2e` plugin" in scaffold
    assert "`project.godot` exists AND `addons/gecs/` exists AND `git log`" not in scaffold


def test_project_scaffold_gdscript_ecs_stubs_are_backend_scoped():
    project_scaffold = _read("skills/core/project-scaffold/SKILL.md")

    assert "GDScript backend directory tree" in project_scaffold
    assert "Existing C#/.NET projects preserve their backend-owned source and test layout" in project_scaffold
    assert "The `gecs World setup` section applies only to the GDScript/gecs backend" in project_scaffold
    assert "Game Plan ECS stubs are GDScript/gecs-only" in project_scaffold
    assert "Existing C#/.NET projects skip these GDScript ECS stubs" in project_scaffold
    assert "For existing C#/.NET projects, install only the shared `godot_e2e` addon" in project_scaffold
    assert "missing `addons/gecs/` or `addons/gdUnit4/` is not a scaffold failure" in project_scaffold


def test_wiki_csharp_contract_is_accurate():
    faq = _read("docs/wiki/08-reference/faq.md")
    check_project = _read("docs/wiki/05-tools/check-project.md")
    roles = _read("docs/wiki/02-concepts/the-9-roles.md")
    project_config = _read("docs/wiki/06-configuration/project-config.md")

    assert "Existing Godot .NET projects are supported" in faq
    assert "C# ECS static checks are reported as N/A" in faq
    assert "does not scaffold a new C# architecture" in faq
    assert "C#/.NET backend" in check_project
    assert "C# ECS static verification is N/A" in check_project
    assert "`<godot_path> --version` must also report a Mono/.NET build" in check_project
    assert "`unit_test_backend`" in check_project
    assert "project-relative `dotnet_target`" in check_project
    assert "project-relative `godot_csharp_project`" in check_project
    assert "backend-selected source code, scenes, and unit tests" in roles
    assert "configured unit test backend" in roles
    assert "`language_backend`" in project_config
    assert "`unit_test_backend`" in project_config
    assert "`dotnet_target`" in project_config
    assert "`godot_csharp_project`" in project_config
    assert "`verification_backend`" not in project_config
    assert "`csharp_static_check`" not in project_config
    assert "dotnet_target: auto" not in project_config
