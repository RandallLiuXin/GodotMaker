"""Executable standalone L0-L4 validation for the UI and card Asset Skills."""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from asset_compiler import CompileRequest, CompilerError, build_default_registry, theme
from asset_compiler._stable_entry import StableEntryError, assert_within_output_dir, resolve_res_path
from asset_validation import GodotProbe, ProbeRequest, ValidationError, build_default_structures
from asset_validation.structure import StructureRequest
from asset_skill_contract_check import AssetContractError, check_result
from asset_ui_card_contract_check import UICardContractError, check_ui_card_handoff


class UICardSkillError(Exception):
    """Raised when a standalone UI/card request-result pair cannot enter L0."""


_LEVELS = ("L0", "L1", "L2", "L3", "L4")


def _mapped_result(result: Mapping[str, Any], levels: Mapping[str, bool], *, error: str | None = None) -> dict[str, Any]:
    mapped = deepcopy(dict(result))
    mapped["validation"] = {"passed": all(levels.values()), "levels": dict(levels)}
    if error:
        mapped["validation"]["notes"] = error
    try:
        check_result(mapped)
    except AssetContractError as exc:  # protected by L0
        raise UICardSkillError(f"cannot map standalone validation result: {exc}") from exc
    return mapped


def _failure(result: Mapping[str, Any], passed: list[str], level: str, error: Exception) -> dict[str, Any]:
    levels = {name: name in passed for name in _LEVELS}
    levels[level] = False
    return _mapped_result(result, levels, error=f"{level} failed: {error}")


def _artifact_request(
    *, request: Mapping[str, Any], output: Mapping[str, Any], kind: str, declaration: Mapping[str, Any], root: Path
) -> CompileRequest:
    if kind == "theme":
        return CompileRequest(
            production_family=request["asset_type"], asset_id=request["asset_id"],
            source_layout_type="theme_recipe", source_path=declaration["recipe_path"],
            artifact_type="Theme", artifact_path=output["path"], project_root=root,
            spec={"variation": declaration["variation"]},
        )
    if kind == "stylebox":
        return CompileRequest(
            production_family=request["asset_type"], asset_id=request["asset_id"],
            source_layout_type=declaration["layout"], source_path=declaration["source_path"],
            artifact_type="StyleBoxTexture", artifact_path=output["path"], project_root=root,
            spec=declaration["compiler_spec"],
        )
    return CompileRequest(
        production_family=request["asset_type"], asset_id=request["asset_id"],
        source_layout_type="region_atlas", source_path=declaration["source_path"],
        artifact_type="AtlasTexture", artifact_path=output["path"], project_root=root,
        spec={"metadata_path": declaration["metadata_path"], "logical_asset_id": declaration["logical_asset_id"]},
    )


def _l1_paths(spec: Mapping[str, Any]) -> list[str]:
    paths = [spec["theme"]["recipe_path"]]
    for box in spec["styleboxes"]:
        paths.append(box["source_path"])
    for region in spec["atlas_regions"]:
        paths.extend((region["source_path"], region["metadata_path"]))
    return paths


def compile_and_validate(
    request: Mapping[str, Any], result: Mapping[str, Any], *, project_root: Path, godot_path: str,
    expected_family: str | None = None,
) -> dict[str, Any]:
    """Compile and validate every declared standalone UI/card resource.

    No stable entry, manifest, tag, or compiler receipt from another caller is
    used. The request owns all family declarations; this invocation builds its
    own registry and probes every runtime output returned to the caller.
    """
    try:
        handoff = check_ui_card_handoff(request, result)
        if expected_family is not None and (
            request["asset_type"] != expected_family
            or result["asset_type"] != expected_family
        ):
            raise UICardSkillError(
                f"standalone adapter requires asset_type {expected_family!r}"
            )
        spec = handoff["request"]["spec"]
        if not isinstance(spec, Mapping):
            raise UICardSkillError("family contract returned no normalized spec")
    except (UICardContractError, AssetContractError, UICardSkillError) as exc:
        raise UICardSkillError(f"L0 standalone contract failed: {exc}") from exc

    root = Path(project_root)
    passed = ["L0"]
    try:
        for path in _l1_paths(spec):
            file_path = assert_within_output_dir(
                root, resolve_res_path(root, path, label="declared standalone source"),
                production_family=request["asset_type"], asset_id=request["asset_id"],
                label="declared standalone source",
            )
            if not file_path.is_file() or file_path.stat().st_size <= 0:
                raise ValidationError(f"declared standalone source is not a non-empty file: {path}")
    except (OSError, StableEntryError, ValidationError) as exc:
        return _failure(result, passed, "L1", exc)

    passed.append("L1")
    runtime = {output["name"]: output for output in result["outputs"] if output["role"] == "runtime"}
    declarations: list[tuple[str, Mapping[str, Any], Mapping[str, Any]]] = [
        ("theme", spec["theme"], runtime[spec["theme"]["output_name"]])
    ]
    declarations.extend(("stylebox", box, runtime[box["output_name"]]) for box in spec["styleboxes"])
    declarations.extend(("atlas", region, runtime[region["output_name"]]) for region in spec["atlas_regions"])
    compiled_requests: dict[str, CompileRequest] = {}
    try:
        registry = build_default_registry()
        theme.register_into(registry)
        for kind, declaration, output in declarations:
            compile_request = _artifact_request(
                request=request, output=output, kind=kind, declaration=declaration, root=root
            )
            compiled = registry.compile(compile_request)
            if compiled.godot_artifact.to_dict() != {"type": output["godot_type"], "path": output["path"]}:
                raise ValidationError(f"compiler output does not match declared runtime output {output['name']!r}")
            compiled_requests[output["path"]] = compile_request
    except (CompilerError, OSError, ValidationError) as exc:
        return _failure(result, passed, "L2", exc)

    passed.append("L2")
    structures = build_default_structures()
    theme.register_structure_into(structures)
    try:
        probe_requests = [
            ProbeRequest(res_path=output["path"], expected_type=output["godot_type"], checks=structures.checks_for(output["godot_type"]))
            for output in runtime.values()
        ]
        report = GodotProbe(godot_path).probe(root, probe_requests)
        loaded_by_path = {item.res_path: item for item in report.resources}
        for output in runtime.values():
            loaded = loaded_by_path.get(output["path"])
            if loaded is None or not loaded.loaded or not loaded.type_matches:
                raise ValidationError(
                    (loaded.error if loaded is not None else None)
                    or f"Godot did not load {output['path']} as {output['godot_type']}"
                )
    except ValidationError as exc:
        return _failure(result, passed, "L3", exc)

    passed.append("L3")
    try:
        for output in runtime.values():
            compiled = compiled_requests[output["path"]]
            structures.validate(
                StructureRequest(
                    production_family=compiled.production_family, asset_id=compiled.asset_id,
                    source_layout_type=compiled.source_layout_type, source_path=compiled.source_path,
                    artifact_type=compiled.artifact_type, artifact_path=compiled.artifact_path,
                    project_root=root, probe=loaded_by_path[output["path"]], spec=compiled.spec,
                )
            )
    except ValidationError as exc:
        return _failure(result, passed, "L4", exc)
    return _mapped_result(result, {level: True for level in _LEVELS})
