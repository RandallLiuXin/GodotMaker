#!/usr/bin/env python3
"""Verification backend selection for GodotMaker projects."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class BackendSelectionError(ValueError):
    """Raised when verification backend selection is ambiguous or invalid."""


@dataclass(frozen=True)
class VerificationSelection:
    language_backend: str
    unit_test_backend: str
    source: str
    dotnet_target: Path | None
    godot_csharp_project: Path | None


CONFIG_KEYS = {
    "language_backend",
    "unit_test_backend",
    "dotnet_target",
    "godot_csharp_project",
}
LANGUAGE_BACKENDS = {"auto", "gdscript", "csharp"}
UNIT_TEST_BACKENDS = {"auto", "gdunit", "dotnet"}
DOTNET_SUFFIXES = {".sln", ".csproj"}
IGNORED_DIRS = {
    ".agents",
    ".claude",
    ".codex",
    ".git",
    ".godot",
    ".godotmaker",
    "addons",
    "bin",
    "obj",
}
SUPPORTED_BACKEND_PAIRS = {("gdscript", "gdunit"), ("csharp", "dotnet")}


def _read_config(project_dir: Path) -> dict[str, str]:
    path = project_dir / ".godotmaker" / "config.yaml"
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key not in CONFIG_KEYS:
            continue
        value = value.strip()
        if "#" in value:
            value = value.split("#", 1)[0].strip()
        values[key] = value.strip("'\"")
    return values


def _project_files(project_dir: Path) -> list[Path]:
    files: list[Path] = []
    for root, dirs, filenames in os.walk(project_dir):
        dirs[:] = [
            dirname for dirname in dirs
            if dirname not in IGNORED_DIRS
        ]
        root_path = Path(root)
        for filename in filenames:
            files.append((root_path / filename).relative_to(project_dir))
    return files


def _read_project_file(project_dir: Path, rel: Path) -> str:
    return (project_dir / rel).read_text(encoding="utf-8", errors="replace")


def _is_dotnet_test_project(project_dir: Path, rel: Path) -> bool:
    if rel.suffix.lower() != ".csproj":
        return False
    text = _read_project_file(project_dir, rel).lower()
    markers = (
        "<istestproject>true</istestproject>",
        "microsoft.net.test.sdk",
        'include="xunit"',
        'include="nunit"',
        'include="mstest.testframework"',
    )
    return any(marker in text for marker in markers)


def _is_godot_csharp_project(project_dir: Path, rel: Path) -> bool:
    if rel.suffix.lower() != ".csproj":
        return False
    return "godot.net.sdk" in _read_project_file(project_dir, rel).lower()


def _validate_backend(name: str, value: str, allowed: set[str]) -> str:
    normalized = (value or "auto").strip().lower()
    if normalized not in allowed:
        expected = ", ".join(sorted(allowed))
        raise BackendSelectionError(
            f"{name} must be one of: {expected}; got {value!r}"
        )
    return normalized


def _validate_dotnet_path(
    project_dir: Path, field: str, value: str | None
) -> Path | None:
    if not value:
        return None

    candidate = Path(value)
    if candidate.is_absolute():
        raise BackendSelectionError(f"{field} must be a project-relative path")
    if candidate.suffix.lower() not in DOTNET_SUFFIXES:
        raise BackendSelectionError(f"{field} must point to a .sln or .csproj file")

    root = project_dir.resolve()
    resolved = (project_dir / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise BackendSelectionError(
            f"{field} must stay inside the project"
        ) from exc
    if not resolved.is_file():
        raise BackendSelectionError(f"{field} must exist inside the project")
    return candidate


def _is_gdunit_test_file(project_dir: Path, rel: Path) -> bool:
    if rel.suffix.lower() != ".gd" or "test" not in rel.parts:
        return False
    return "extends GdUnitTestSuite" in _read_project_file(project_dir, rel)


def _auto_language_backend(files: list[Path]) -> str:
    has_gdscript = any(
        path.suffix.lower() == ".gd" and "test" not in path.parts
        for path in files
    )
    has_csharp = any(
        path.suffix.lower() in {".cs", ".csproj", ".sln"}
        for path in files
    )

    if has_gdscript and has_csharp:
        raise BackendSelectionError("auto detected mixed language backends")
    if has_csharp:
        return "csharp"
    if has_gdscript:
        return "gdscript"
    raise BackendSelectionError("could not auto-detect language_backend")


def _solution_includes_project(
    project_dir: Path,
    solution: Path,
    project: Path,
) -> bool:
    solution_path = project_dir / solution
    try:
        text = solution_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    relative = os.path.relpath(
        project_dir / project,
        solution_path.parent,
    ).replace("/", "\\")
    return (
        project.name in text
        or relative in text
        or relative.replace("\\", "/") in text
    )


def _auto_dotnet_target(project_dir: Path, files: list[Path]) -> Path | None:
    solutions = sorted(path for path in files if path.suffix.lower() == ".sln")
    test_projects = sorted(
        path for path in files if _is_dotnet_test_project(project_dir, path)
    )

    if not test_projects:
        return None
    if len(solutions) > 1:
        raise BackendSelectionError("auto detected multiple dotnet solutions")
    if not solutions:
        if len(test_projects) > 1:
            raise BackendSelectionError(
                "auto detected multiple dotnet test projects"
            )
        return test_projects[0]

    solution = solutions[0]
    included = [
        project for project in test_projects
        if _solution_includes_project(project_dir, solution, project)
    ]
    if len(included) == len(test_projects):
        return solution
    if len(test_projects) == 1:
        return test_projects[0]
    raise BackendSelectionError(

        "dotnet solution does not include every detected test project; "
        "configure dotnet_target explicitly"
    )

def _auto_godot_csharp_project(project_dir: Path, files: list[Path]) -> Path | None:
    projects = sorted(
        path for path in files if _is_godot_csharp_project(project_dir, path)
    )
    if len(projects) > 1:
        raise BackendSelectionError("auto detected multiple Godot C# projects")
    return projects[0] if projects else None


def _auto_unit_test_backend(
    project_dir: Path, files: list[Path]
) -> tuple[str, Path | None]:
    has_gdunit = any(
        _is_gdunit_test_file(project_dir, path) for path in files
    )
    dotnet_target = _auto_dotnet_target(project_dir, files)
    has_dotnet = dotnet_target is not None

    if has_gdunit and has_dotnet:
        raise BackendSelectionError("auto detected mixed unit test backends")
    if has_dotnet:
        return "dotnet", dotnet_target
    if has_gdunit:
        return "gdunit", None
    raise BackendSelectionError("could not auto-detect unit test backend")


def _validate_supported_pair(language_backend: str, unit_test_backend: str) -> None:
    pair = (language_backend, unit_test_backend)
    if pair not in SUPPORTED_BACKEND_PAIRS:
        raise BackendSelectionError(
            f"unsupported backend combination: {language_backend}+{unit_test_backend}"
        )


def select_verification_backend(project_dir: Path) -> VerificationSelection:
    project_dir = Path(project_dir)
    config = _read_config(project_dir)
    files = _project_files(project_dir)

    configured_language = config.get("language_backend", "auto")
    configured_unit = config.get("unit_test_backend", "auto")
    language_backend = _validate_backend(
        "language_backend", configured_language, LANGUAGE_BACKENDS
    )
    unit_test_backend = _validate_backend(
        "unit_test_backend", configured_unit, UNIT_TEST_BACKENDS
    )
    dotnet_target = _validate_dotnet_path(
        project_dir, "dotnet_target", config.get("dotnet_target")
    )
    godot_csharp_project = _validate_dotnet_path(
        project_dir, "godot_csharp_project", config.get("godot_csharp_project")
    )

    source = "config" if (
        language_backend != "auto"
        or unit_test_backend != "auto"
        or dotnet_target is not None
        or godot_csharp_project is not None
    ) else "auto"

    if language_backend == "auto":
        try:
            language_backend = _auto_language_backend(files)
        except BackendSelectionError as exc:
            if unit_test_backend == "auto" and "could not auto-detect" in str(exc):
                return VerificationSelection(
                    language_backend="gdscript",
                    unit_test_backend="gdunit",
                    source="legacy-default",
                    dotnet_target=None,
                    godot_csharp_project=None,
                )
            raise

    if unit_test_backend == "auto":
        unit_test_backend, auto_target = _auto_unit_test_backend(project_dir, files)
        if dotnet_target is None:
            dotnet_target = auto_target
    elif unit_test_backend == "dotnet" and dotnet_target is None:
        dotnet_target = _auto_dotnet_target(project_dir, files)
        if dotnet_target is None:
            raise BackendSelectionError("could not auto-detect dotnet_target")

    if language_backend == "csharp" and godot_csharp_project is None:
        godot_csharp_project = _auto_godot_csharp_project(project_dir, files)

    _validate_supported_pair(language_backend, unit_test_backend)

    return VerificationSelection(
        language_backend=language_backend,
        unit_test_backend=unit_test_backend,
        source=source,
        dotnet_target=dotnet_target,
        godot_csharp_project=godot_csharp_project,
    )
