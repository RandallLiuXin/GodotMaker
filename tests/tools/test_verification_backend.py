from pathlib import Path
import sys

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from verification_backend import (
    BackendSelectionError,
    VerificationSelection,
    select_verification_backend,
)


def write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_config(project: Path, text: str) -> None:
    write(project / ".godotmaker" / "config.yaml", text)


def test_explicit_config_selects_dotnet_backend(tmp_path: Path):
    write(tmp_path / "Game.csproj", '<Project Sdk="Godot.NET.Sdk/4.5.0" />')
    write(tmp_path / "Game.Tests" / "Game.Tests.csproj", "<Project />")
    write_config(
        tmp_path,
        "\n".join(
            [
                "language_backend: csharp",
                "unit_test_backend: dotnet",
                "dotnet_target: Game.Tests/Game.Tests.csproj",
                "godot_csharp_project: Game.csproj",
            ]
        ),
    )

    selection = select_verification_backend(tmp_path)

    assert selection == VerificationSelection(
        language_backend="csharp",
        unit_test_backend="dotnet",
        source="config",
        dotnet_target=Path("Game.Tests/Game.Tests.csproj"),
        godot_csharp_project=Path("Game.csproj"),
    )


def test_auto_detects_csharp_dotnet_project(tmp_path: Path):
    write(tmp_path / "Game.csproj", '<Project Sdk="Godot.NET.Sdk/4.5.0" />')
    write(
        tmp_path / "Game.Tests" / "Game.Tests.csproj",
        '<Project><PropertyGroup><IsTestProject>true</IsTestProject></PropertyGroup></Project>',
    )

    selection = select_verification_backend(tmp_path)

    assert selection == VerificationSelection(
        language_backend="csharp",
        unit_test_backend="dotnet",
        source="auto",
        dotnet_target=Path("Game.Tests/Game.Tests.csproj"),
        godot_csharp_project=Path("Game.csproj"),
    )


def test_auto_detects_gdscript_gdunit_project(tmp_path: Path):
    write(tmp_path / "src" / "s_movement.gd", "extends System\n")
    write(tmp_path / "test" / "test_s_movement.gd", "extends GdUnitTestSuite\n")

    selection = select_verification_backend(tmp_path)

    assert selection == VerificationSelection(
        language_backend="gdscript",
        unit_test_backend="gdunit",
        source="auto",
        dotnet_target=None,
        godot_csharp_project=None,
    )


def test_auto_ignores_generated_and_addon_directories(tmp_path: Path):
    write(tmp_path / "addons" / "plugin" / "tool.gd", "extends Node\n")
    write(tmp_path / ".godot" / "imported" / "Generated.cs", "class Generated {}")
    write(tmp_path / "bin" / "Debug" / "Game.csproj", "<Project />")
    write(tmp_path / "obj" / "Debug" / "Game.Tests.csproj", "<Project />")
    write(tmp_path / "src" / "s_score.gd", "extends System\n")
    write(tmp_path / "test" / "test_s_score.gd", "extends GdUnitTestSuite\n")

    selection = select_verification_backend(tmp_path)

    assert selection.language_backend == "gdscript"
    assert selection.unit_test_backend == "gdunit"


def test_auto_ignores_metadata_and_agent_directories(tmp_path: Path):
    ignored_dirs = [".git", ".godotmaker", ".agents", ".claude", ".codex"]
    for dirname in ignored_dirs:
        write(tmp_path / dirname / "Game.csproj", "Godot.NET.Sdk")
        write(
            tmp_path / dirname / "test" / "test_hidden.gd",
            "extends GdUnitTestSuite\n",
        )
        write(
            tmp_path / dirname / "Hidden.Tests.csproj",
            "Microsoft.NET.Test.Sdk",
        )

    write(tmp_path / "src" / "s_visible.gd", "extends System\n")
    write(tmp_path / "test" / "test_s_visible.gd", "extends GdUnitTestSuite\n")

    selection = select_verification_backend(tmp_path)

    assert selection == VerificationSelection(
        "gdscript", "gdunit", "auto", None, None
    )


def test_auto_rejects_mixed_language_backends(tmp_path: Path):
    write(tmp_path / "src" / "s_movement.gd", "extends System\n")
    write(tmp_path / "Game.csproj", '<Project Sdk="Godot.NET.Sdk/4.5.0" />')
    write(tmp_path / "test" / "test_s_movement.gd", "extends GdUnitTestSuite\n")

    with pytest.raises(BackendSelectionError, match="mixed language"):
        select_verification_backend(tmp_path)


def test_auto_rejects_mixed_unit_test_backends(tmp_path: Path):
    write(tmp_path / "Game.csproj", '<Project Sdk="Godot.NET.Sdk/4.5.0" />')
    write(
        tmp_path / "Game.Tests" / "Game.Tests.csproj",
        '<Project Sdk="Microsoft.NET.Sdk"><ItemGroup><PackageReference Include="Microsoft.NET.Test.Sdk" /></ItemGroup></Project>',
    )
    write(tmp_path / "test" / "test_game.gd", "extends GdUnitTestSuite\n")

    with pytest.raises(BackendSelectionError, match="mixed unit test"):
        select_verification_backend(tmp_path)


def test_auto_rejects_missing_unit_tests(tmp_path: Path):
    write(tmp_path / "Game.csproj", '<Project Sdk="Godot.NET.Sdk/4.5.0" />')

    with pytest.raises(BackendSelectionError, match="unit test backend"):
        select_verification_backend(tmp_path)


def test_explicit_dotnet_target_must_be_project_relative(tmp_path: Path):
    write_config(
        tmp_path,
        "\n".join(
            [
                "language_backend: csharp",
                "unit_test_backend: dotnet",
                "dotnet_target: ../outside.sln",
            ]
        ),
    )

    with pytest.raises(BackendSelectionError, match="dotnet_target"):
        select_verification_backend(tmp_path)


def test_explicit_godot_csharp_project_rejects_absolute_path(tmp_path: Path):
    absolute = tmp_path / "Game.csproj"
    write_config(
        tmp_path,
        "\n".join(
            [
                "language_backend: csharp",
                "unit_test_backend: dotnet",
                f"godot_csharp_project: {absolute}",
            ]
        ),
    )

    with pytest.raises(BackendSelectionError, match="godot_csharp_project"):
        select_verification_backend(tmp_path)


def test_explicit_dotnet_paths_must_be_solution_or_project_files(tmp_path: Path):
    write_config(
        tmp_path,
        "\n".join(
            [
                "language_backend: csharp",
                "unit_test_backend: dotnet",
                "dotnet_target: test/results.trx",
            ]
        ),
    )

    with pytest.raises(BackendSelectionError, match=".sln or .csproj"):
        select_verification_backend(tmp_path)


def test_explicit_dotnet_backend_without_target_auto_selects_unique_test_project(
    tmp_path: Path,
):
    write(tmp_path / "Game.csproj", '<Project Sdk="Godot.NET.Sdk/4.5.0" />')
    write(
        tmp_path / "Game.Tests" / "Game.Tests.csproj",
        '<Project><PropertyGroup><IsTestProject>true</IsTestProject></PropertyGroup></Project>',
    )
    write_config(
        tmp_path,
        "\n".join(
            [
                "language_backend: csharp",
                "unit_test_backend: dotnet",
            ]
        ),
    )

    selection = select_verification_backend(tmp_path)

    assert selection.dotnet_target == Path("Game.Tests/Game.Tests.csproj")


def test_explicit_dotnet_target_must_exist(tmp_path: Path):
    write_config(
        tmp_path,
        "\n".join(
            [
                "language_backend: csharp",
                "unit_test_backend: dotnet",
                "dotnet_target: Missing.Tests.csproj",
            ]
        ),
    )

    with pytest.raises(BackendSelectionError, match="dotnet_target"):
        select_verification_backend(tmp_path)


def test_auto_gdunit_requires_actual_gdunit_suite(tmp_path: Path):
    write(tmp_path / "src" / "s_movement.gd", "extends System\n")
    write(
        tmp_path / "test" / "test_s_movement.gd",
        "extends RefCounted\nfunc test_placeholder(): pass\n",
    )

    with pytest.raises(BackendSelectionError, match="unit test backend"):
        select_verification_backend(tmp_path)


def test_auto_empty_project_uses_legacy_gdscript_gdunit_default(tmp_path: Path):
    selection = select_verification_backend(tmp_path)

    assert selection == VerificationSelection(
        language_backend="gdscript",
        unit_test_backend="gdunit",
        source="legacy-default",
        dotnet_target=None,
        godot_csharp_project=None,
    )


def test_explicit_gdscript_dotnet_backend_is_rejected(tmp_path: Path):
    write(tmp_path / "Game.Tests" / "Game.Tests.csproj", "Microsoft.NET.Test.Sdk")
    write_config(
        tmp_path,
        "\n".join(
            [
                "language_backend: gdscript",
                "unit_test_backend: dotnet",
            ]
        ),
    )

    with pytest.raises(BackendSelectionError, match="unsupported backend"):
        select_verification_backend(tmp_path)


def test_explicit_csharp_gdunit_backend_is_rejected(tmp_path: Path):
    write(tmp_path / "Game.csproj", '<Project Sdk="Godot.NET.Sdk/4.5.0" />')
    write(tmp_path / "test" / "test_game.gd", "extends GdUnitTestSuite\n")
    write_config(
        tmp_path,
        "\n".join(
            [
                "language_backend: csharp",
                "unit_test_backend: gdunit",
            ]
        ),
    )

    with pytest.raises(BackendSelectionError, match="unsupported backend"):
        select_verification_backend(tmp_path)


def test_auto_solution_omitting_unique_test_project_selects_test_project(
    tmp_path: Path,
):
    write(tmp_path / "Game.csproj", '<Project Sdk="Godot.NET.Sdk/4.5.0" />')
    write(
        tmp_path / "Game.sln",
        'Project("{GUID}") = "Game", "Game.csproj", "{GUID2}"\n',
    )
    write(
        tmp_path / "Game.Tests" / "Game.Tests.csproj",
        '<Project><PropertyGroup><IsTestProject>true</IsTestProject></PropertyGroup></Project>',
    )

    selection = select_verification_backend(tmp_path)

    assert selection.dotnet_target == Path("Game.Tests/Game.Tests.csproj")


def test_auto_solution_including_test_project_selects_solution(tmp_path: Path):
    write(tmp_path / "Game.csproj", '<Project Sdk="Godot.NET.Sdk/4.5.0" />')
    write(
        tmp_path / "Game.sln",
        'Project("{GUID}") = "Tests", "Game.Tests\\\\Game.Tests.csproj", "{GUID2}"\n',
    )
    write(
        tmp_path / "Game.Tests" / "Game.Tests.csproj",
        '<Project><PropertyGroup><IsTestProject>true</IsTestProject></PropertyGroup></Project>',
    )

    selection = select_verification_backend(tmp_path)

    assert selection.dotnet_target == Path("Game.sln")


def test_auto_solution_without_test_project_is_not_a_test_backend(tmp_path: Path):
    write(tmp_path / "Game.csproj", '<Project Sdk="Godot.NET.Sdk/4.5.0" />')
    write(
        tmp_path / "Game.sln",
        'Project("{GUID}") = "Game", "Game.csproj", "{GUID2}"\n',
    )

    with pytest.raises(BackendSelectionError, match="unit test backend"):
        select_verification_backend(tmp_path)


def test_auto_multiple_test_projects_without_covering_solution_is_ambiguous(
    tmp_path: Path,
):
    write(tmp_path / "Game.csproj", '<Project Sdk="Godot.NET.Sdk/4.5.0" />')
    for name in ("Unit.Tests", "Integration.Tests"):
        write(
            tmp_path / name / f"{name}.csproj",
            '<Project><PropertyGroup><IsTestProject>true</IsTestProject></PropertyGroup></Project>',
        )

    with pytest.raises(BackendSelectionError, match="multiple dotnet test projects"):
        select_verification_backend(tmp_path)
