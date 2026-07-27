"""Standalone L0-L4 execution for the TileSet Asset Skill.

This module deliberately does not use ``ValidationLadder``. That shared ladder
validates a registered stable entry, whereas a first-class asset skill receives
only the public request and result contract. The two boundaries must stay
separate: this runner proves a standalone call without inventing tag, manifest,
or processing-status state.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import sys
from pathlib import Path
from typing import Any


def _configure_runtime_imports() -> None:
    """Add the source or published shared runtime to the import path.

    Source skills keep their runtime beside the family directories. Published
    skills are flattened into an adapter-specific skill root, while their
    runtime is deliberately deployed once at ``.godotmaker/asset-runtime``.
    """
    runner = Path(__file__).resolve()
    project_root = runner.parents[3]
    source_runtime = runner.parents[1] / "_shared"
    runtime_candidates = (
        project_root / ".godotmaker" / "asset-runtime",
        source_runtime,
    )
    source_layout = (
        runner.parents[1].name == "assets"
        and runner.parents[2].name == "skills"
    )
    runtime = next(
        (
            path for path in runtime_candidates
            if path.is_dir() and (path != source_runtime or source_layout)
        ),
        None,
    )
    tools = project_root / "tools"
    if runtime is None:
        raise ImportError(
            "GodotMaker asset runtime is missing for standalone tileset validation: "
            "checked " + ", ".join(str(path) for path in runtime_candidates)
        )
    if not tools.is_dir():
        raise ImportError(
            "GodotMaker tools directory is missing for standalone tileset validation: "
            f"expected {tools}"
        )
    # Appended, never inserted: these flat directories must not shadow the
    # standard library or installed packages for the rest of the process.
    for path in (str(runtime), str(tools)):
        if path not in sys.path:
            sys.path.append(path)


_configure_runtime_imports()

from asset_compiler import CompileRequest, CompilerError, CompilerRegistry  # noqa: E402
from asset_compiler import tileset as tileset_compiler  # noqa: E402
from asset_compiler._stable_entry import (  # noqa: E402
    StableEntryError,
    assert_within_output_dir,
    resolve_res_path,
)
from asset_validation import GodotProbe, ProbeRequest, ValidationError  # noqa: E402
from asset_validation import tileset as tileset_structures  # noqa: E402
from asset_validation.structure import (  # noqa: E402
    StructureRequest,
    StructureValidatorRegistry,
)
from asset_skill_contract_check import (  # noqa: E402
    AssetContractError,
    check_request,
    check_result,
)


class TileSetSkillError(Exception):
    """Raised when a standalone request/result pair cannot enter L0."""


_LEVELS = ("L0", "L1", "L2", "L3", "L4")


def _runtime_output(result: Mapping[str, Any]) -> Mapping[str, Any]:
    outputs = [output for output in result["outputs"] if output["role"] == "runtime"]
    if len(outputs) != 1 or outputs[0].get("godot_type") != "TileSet":
        raise TileSetSkillError(
            "v1 standalone tileset supports exactly one runtime output, and it must be TileSet"
        )
    return outputs[0]


def _atlas_sources(request: Mapping[str, Any], result: Mapping[str, Any]) -> list[str]:
    recipe_sources = request.get("spec", {}).get("sources")
    if not isinstance(recipe_sources, list) or not recipe_sources:
        raise TileSetSkillError("tileset spec requires a non-empty sources list")
    declared = {
        source["path"]
        for source in result["sources"]
        if source.get("layout") == "tile_atlas"
    }
    paths: list[str] = []
    for source in recipe_sources:
        if not isinstance(source, Mapping) or not isinstance(source.get("texture"), str):
            raise TileSetSkillError("every tileset recipe source requires a texture path")
        texture = source["texture"]
        if texture not in declared:
            raise TileSetSkillError(
                "every tileset recipe texture must be declared as a tile_atlas result source"
            )
        paths.append(texture)
    return paths


def _mapped_result(
    result: Mapping[str, Any],
    levels: Mapping[str, bool],
    *,
    error: str | None = None,
) -> dict[str, Any]:
    mapped = deepcopy(dict(result))
    mapped["validation"] = {
        "passed": all(levels.values()),
        "levels": dict(levels),
    }
    if error:
        mapped["validation"]["notes"] = error
    try:
        check_result(mapped)
    except AssetContractError as exc:  # pragma: no cover - protected by L0 input check
        raise TileSetSkillError(f"cannot map standalone validation result: {exc}") from exc
    return mapped


def _failure(result: Mapping[str, Any], passed: list[str], level: str, error: Exception) -> dict[str, Any]:
    levels = {name: name in passed for name in _LEVELS}
    levels[level] = False
    return _mapped_result(result, levels, error=f"{level} failed: {error}")


def compile_and_validate(
    request: Mapping[str, Any],
    result: Mapping[str, Any],
    *,
    project_root: Path,
    godot_path: str,
) -> dict[str, Any]:
    """Compile one standalone TileSet request and map L0-L4 into its result.

    L0 checks only the public request/result schemas and their TileSet-specific
    links. L1 checks every declared atlas path. L2 compiles through a fresh
    registry and keeps its receipt inside this invocation. L3 asks headless
    Godot to load the returned runtime path, and L4 runs the registered TileSet
    structure validator against the same explicit recipe. No stable entry is
    constructed or read at any point.
    """
    try:
        check_request(request)
        check_result(result)
        if request["asset_type"] != "tileset" or result["asset_type"] != "tileset":
            raise TileSetSkillError("standalone TileSet validation requires asset_type 'tileset'")
        output = _runtime_output(result)
        atlas_paths = _atlas_sources(request, result)
    except (AssetContractError, TileSetSkillError) as exc:
        raise TileSetSkillError(f"L0 standalone contract failed: {exc}") from exc

    root = Path(project_root)
    asset_id = request["asset_id"]
    passed = ["L0"]
    try:
        for atlas_path in atlas_paths:
            source_file = assert_within_output_dir(
                root,
                resolve_res_path(root, atlas_path, label="tileset atlas source"),
                production_family="tileset",
                asset_id=asset_id,
                label="tileset atlas source",
            )
            if not source_file.is_file() or source_file.stat().st_size <= 0:
                raise ValidationError(f"tileset atlas source is not a non-empty file: {atlas_path}")
    except (OSError, StableEntryError, ValidationError) as exc:
        return _failure(result, passed, "L1", exc)

    passed.append("L1")
    primary_source = atlas_paths[0]
    compile_request = CompileRequest(
        production_family="tileset",
        asset_id=asset_id,
        source_layout_type="tile_atlas",
        source_path=primary_source,
        artifact_type="TileSet",
        artifact_path=output["path"],
        project_root=root,
        spec=request["spec"],
    )
    registry = CompilerRegistry()
    tileset_compiler.register_into(registry)
    try:
        compiled = registry.compile(compile_request)
        if compiled.godot_artifact.to_dict() != {
            "type": output["godot_type"],
            "path": output["path"],
        }:
            raise ValidationError("TileSet compiler returned an artifact that does not match the result")
    except (CompilerError, ValidationError) as exc:
        return _failure(result, passed, "L2", exc)

    passed.append("L2")
    structures = StructureValidatorRegistry()
    tileset_structures.register_into(structures)
    try:
        probe = GodotProbe(godot_path)
        report = probe.probe(
            root,
            [
                ProbeRequest(
                    res_path=output["path"],
                    expected_type="TileSet",
                    checks=structures.checks_for("TileSet"),
                )
            ],
        )
        loaded = report.resources[0]
        if not loaded.loaded or not loaded.type_matches:
            raise ValidationError(
                loaded.error
                or f"Godot did not load {output['path']} as TileSet"
            )
    except ValidationError as exc:
        return _failure(result, passed, "L3", exc)

    passed.append("L3")
    try:
        structures.validate(
            StructureRequest(
                production_family="tileset",
                asset_id=asset_id,
                source_layout_type="tile_atlas",
                source_path=primary_source,
                artifact_type="TileSet",
                artifact_path=output["path"],
                project_root=root,
                probe=loaded,
                spec=request["spec"],
            )
        )
    except ValidationError as exc:
        return _failure(result, passed, "L4", exc)

    return _mapped_result(result, {level: True for level in _LEVELS})
