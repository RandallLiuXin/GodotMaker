"""Executable standalone validation for the remaining first-class Asset Skills.

The public asset result is only a declaration.  This module intentionally
rebuilds its validation from the request, files, compiler, and Godot probe;
the caller's ``validation`` object is overwritten rather than trusted.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from typing import Any

from asset_compiler import CompileRequest, CompilerError, build_default_registry
from asset_compiler._stable_entry import (
    StableEntryError,
    assert_within_output_dir,
    resolve_res_path,
)
from asset_validation import (
    GodotProbe,
    ProbeRequest,
    ValidationError,
    build_default_structures,
)
from asset_validation.structure import StructureRequest
from asset_skill_contract_check import AssetContractError, check_request, check_result
from asset_animated_bundle_contract_check import (
    AnimatedBundleContractError,
    build_spriteframes_spec,
    check_bundle_request,
    check_bundle_result,
)
from asset_atlas_assemble import AtlasAssemblyError, assemble_atlas


class MissingFamilySkillError(Exception):
    """Raised when a public request/result pair cannot enter standalone L0."""


_LEVELS = ("L0", "L1", "L2", "L3", "L4")
_FAMILIES = {
    "background-map",
    "platform-strip",
    "screen-reference",
    "character-bundle",
    "fx-bundle",
    "compact-prop-pack",
    "scene-prop-set",
}


def _mapped(
    result: Mapping[str, Any],
    levels: Mapping[str, bool],
    error: Exception | None = None,
) -> dict[str, Any]:
    mapped = deepcopy(dict(result))
    mapped["validation"] = {"passed": all(levels.values()), "levels": dict(levels)}
    if error is not None:
        mapped["validation"]["notes"] = str(error)
    try:
        check_result(mapped)
    except AssetContractError as exc:  # protected by L0
        raise MissingFamilySkillError(f"cannot map validation result: {exc}") from exc
    return mapped


def _failure(
    result: Mapping[str, Any], passed: list[str], level: str, error: Exception
) -> dict[str, Any]:
    levels = {name: name in passed for name in _LEVELS}
    levels[level] = False
    return _mapped(result, levels, error)


def _runtime(result: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [item for item in result["outputs"] if item["role"] == "runtime"]


def _stable_path(family: str, asset_id: str, name: str, suffix: str) -> str:
    return f"res://assets/generated/{family}/{asset_id}/{name}{suffix}"


def _exact_keys(value: Any, keys: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise MissingFamilySkillError(
            f"{label} must contain exactly {', '.join(sorted(keys))}"
        )
    return value


def _check_background(
    request: Mapping[str, Any], result: Mapping[str, Any]
) -> list[tuple[Mapping[str, Any], CompileRequest]]:
    asset_id = request["asset_id"]
    outputs = _runtime(result)
    path = _stable_path("background-map", asset_id, asset_id, ".png")
    if (
        len(outputs) != 1
        or outputs[0].get("name") != asset_id
        or outputs[0].get("path") != path
        or outputs[0].get("godot_type") != "Texture2D"
    ):
        raise MissingFamilySkillError(
            "background-map needs exactly its stable Texture2D runtime output"
        )
    if result["sources"] != [{"path": path, "layout": "single"}]:
        raise MissingFamilySkillError(
            "background-map result needs exactly its stable single source"
        )
    output = outputs[0]
    return [
        (
            output,
            CompileRequest(
                "background-map", asset_id, "single", path, "Texture2D", path, Path(".")
            ),
        )
    ]


def _check_screen_reference(
    request: Mapping[str, Any], result: Mapping[str, Any]
) -> str:
    asset_id = request["asset_id"]
    expected = f"references/{asset_id}.png"
    if _runtime(result) or result["sources"] or len(result["outputs"]) != 1:
        raise MissingFamilySkillError(
            "screen-reference must have one reference output and no runtime source"
        )
    output = result["outputs"][0]
    if (
        output.get("role") != "reference"
        or output.get("name") != asset_id
        or output.get("path") != expected
        or "godot_type" in output
    ):
        raise MissingFamilySkillError(
            "screen-reference output must use its stable reference path"
        )
    return expected


def _check_platform(
    request: Mapping[str, Any], result: Mapping[str, Any]
) -> list[tuple[Mapping[str, Any], CompileRequest]]:
    spec = _exact_keys(request.get("spec"), {"kind", "segments"}, "platform-strip spec")
    kind = spec.get("kind")
    segments = spec.get("segments")
    if (
        kind not in {"single", "atlas"}
        or not isinstance(segments, list)
        or not segments
    ):
        raise MissingFamilySkillError(
            "platform-strip spec needs kind single/atlas and non-empty segments"
        )
    asset_id = request["asset_id"]
    expected: list[tuple[Mapping[str, Any], CompileRequest]] = []
    sources: list[dict[str, str]] = []
    names: set[str] = set()
    for item in segments:
        entry = _exact_keys(item, {"name"}, "platform-strip segment")
        name = entry.get("name")
        if not isinstance(name, str) or not name or name in names:
            raise MissingFamilySkillError(
                "platform-strip segment names must be unique non-empty strings"
            )
        names.add(name)
        if kind == "single":
            path = _stable_path("platform-strip", asset_id, name, ".png")
            sources.append({"path": path, "layout": "single"})
            expected.append(
                (
                    {"name": name, "path": path, "godot_type": "Texture2D"},
                    CompileRequest(
                        "platform-strip",
                        asset_id,
                        "single",
                        path,
                        "Texture2D",
                        path,
                        Path("."),
                    ),
                )
            )
        else:
            source = _stable_path("platform-strip", asset_id, asset_id, ".png")
            sources = [{"path": source, "layout": "region_atlas"}]
            expected.append(
                (
                    {
                        "name": name,
                        "path": _stable_path("platform-strip", asset_id, name, ".tres"),
                        "godot_type": "AtlasTexture",
                    },
                    CompileRequest(
                        "platform-strip",
                        asset_id,
                        "region_atlas",
                        source,
                        "AtlasTexture",
                        _stable_path("platform-strip", asset_id, name, ".tres"),
                        Path("."),
                        {
                            "metadata_path": _stable_path(
                                "platform-strip", asset_id, asset_id, ".json"
                            ),
                            "logical_asset_id": name,
                        },
                    ),
                )
            )
    actual = {
        (item.get("name"), item.get("path"), item.get("godot_type"))
        for item in _runtime(result)
    }
    wanted = {
        (item[0]["name"], item[0]["path"], item[0]["godot_type"]) for item in expected
    }
    if (
        len(_runtime(result)) != len(wanted)
        or actual != wanted
        or result["sources"] != sources
    ):
        raise MissingFamilySkillError(
            "platform-strip result must bind every declared segment to its stable native output"
        )
    return expected


def _check_bundle(
    request: Mapping[str, Any], result: Mapping[str, Any]
) -> list[tuple[Mapping[str, Any], CompileRequest]]:
    try:
        check_bundle_request(request)
        check_bundle_result(result)
    except AnimatedBundleContractError as exc:
        raise MissingFamilySkillError(str(exc)) from exc
    if request["asset_type"] != result["asset_type"]:
        raise MissingFamilySkillError("request.asset_type must match result.asset_type")
    family, asset_id = request["asset_type"], request["asset_id"]
    outputs = _runtime(result)
    if len(outputs) != 1 or outputs[0].get("name") != asset_id:
        raise MissingFamilySkillError(
            "bundle result must have exactly one stable runtime output"
        )
    output = outputs[0]
    if family == "fx-bundle" and request["spec"]["mode"] == "static":
        path = _stable_path(family, asset_id, asset_id, ".png")
        if (
            output.get("godot_type") != "Texture2D"
            or output.get("path") != path
            or result["sources"] != [{"path": path, "layout": "single"}]
        ):
            raise MissingFamilySkillError(
                "static FX must bind its stable PNG Texture2D"
            )
        return [
            (
                output,
                CompileRequest(
                    family, asset_id, "single", path, "Texture2D", path, Path(".")
                ),
            )
        ]
    path = _stable_path(family, asset_id, asset_id, ".tres")
    if output.get("godot_type") != "SpriteFrames" or output.get("path") != path:
        raise MissingFamilySkillError(
            "animated bundle must bind its stable SpriteFrames output"
        )
    sheets = [
        source["path"]
        for source in result["sources"]
        if source.get("layout") == "grid_sheet"
    ]
    if not sheets:
        raise MissingFamilySkillError("animated bundle needs a grid_sheet source")
    frame_paths: dict[str, list[str]] = {}
    for action in request["spec"]["actions"]:
        action_name = action["name"]
        frame_paths[action_name] = [
            _stable_path(family, asset_id, f"{asset_id}_{action_name}_{frame}", ".png")
            for frame in action["frame_names"]
        ]
    try:
        compiler_spec = build_spriteframes_spec(request, frame_paths)
    except AnimatedBundleContractError as exc:
        raise MissingFamilySkillError(str(exc)) from exc
    return [
        (
            output,
            CompileRequest(
                family,
                asset_id,
                "grid_sheet",
                sheets[0],
                "SpriteFrames",
                path,
                Path("."),
                compiler_spec,
            ),
        )
    ]


def _check_props(
    request: Mapping[str, Any], result: Mapping[str, Any]
) -> list[tuple[Mapping[str, Any], CompileRequest]]:
    family, asset_id = request["asset_type"], request["asset_id"]
    spec = _exact_keys(
        request.get("spec"), {"version", "atlas", "slots"}, f"{family} spec"
    )
    if (
        spec.get("version") != 1
        or not isinstance(spec.get("slots"), list)
        or not spec["slots"]
    ):
        raise MissingFamilySkillError(
            f"{family} spec must be a v1 non-empty fixed-slot declaration"
        )
    slots = spec["slots"]
    names = [item.get("name") for item in slots if isinstance(item, Mapping)]
    if (
        len(names) != len(slots)
        or any(not isinstance(name, str) or not name for name in names)
        or len(set(names)) != len(names)
    ):
        raise MissingFamilySkillError(
            f"{family} slots must have unique non-empty names"
        )
    source = _stable_path(family, asset_id, asset_id, ".png")
    metadata = _stable_path(family, asset_id, asset_id, ".json")
    if result["sources"] != [{"path": source, "layout": "region_atlas"}]:
        raise MissingFamilySkillError(
            f"{family} result must declare its one stable region_atlas source"
        )
    expected = [
        (
            {
                "name": name,
                "path": _stable_path(family, asset_id, name, ".tres"),
                "godot_type": "AtlasTexture",
            },
            CompileRequest(
                family,
                asset_id,
                "region_atlas",
                source,
                "AtlasTexture",
                _stable_path(family, asset_id, name, ".tres"),
                Path("."),
                {"metadata_path": metadata, "logical_asset_id": name},
            ),
        )
        for name in names
    ]
    actual = {
        (item.get("name"), item.get("path"), item.get("godot_type"))
        for item in _runtime(result)
    }
    wanted = {
        (item[0]["name"], item[0]["path"], item[0]["godot_type"]) for item in expected
    }
    if len(_runtime(result)) != len(wanted) or actual != wanted:
        raise MissingFamilySkillError(
            f"{family} result must expose every declared slot exactly once"
        )
    return expected


def _declarations(
    request: Mapping[str, Any], result: Mapping[str, Any]
) -> tuple[str | None, list[tuple[Mapping[str, Any], CompileRequest]]]:
    family = request["asset_type"]
    if family == "background-map":
        return None, _check_background(request, result)
    if family == "screen-reference":
        return _check_screen_reference(request, result), []
    if family == "platform-strip":
        return None, _check_platform(request, result)
    if family in {"character-bundle", "fx-bundle"}:
        return None, _check_bundle(request, result)
    return None, _check_props(request, result)


def _l1_file(root: Path, path: str, *, family: str, asset_id: str) -> Path:
    return assert_within_output_dir(
        root,
        resolve_res_path(root, path, label="standalone source"),
        production_family=family,
        asset_id=asset_id,
        label="standalone source",
    )


def compile_and_validate(
    request: Mapping[str, Any],
    result: Mapping[str, Any],
    *,
    project_root: Path,
    godot_path: str,
) -> dict[str, Any]:
    """Execute the real applicable ladder for one of the seven missing families."""
    try:
        check_request(request)
        check_result(result)
        if (
            request["asset_type"] not in _FAMILIES
            or result["asset_type"] != request["asset_type"]
        ):
            raise MissingFamilySkillError(
                "standalone validation needs one supported matching asset_type"
            )
        reference_path, declarations = _declarations(request, result)
    except (AssetContractError, MissingFamilySkillError) as exc:
        raise MissingFamilySkillError(f"L0 standalone contract failed: {exc}") from exc
    root, family, asset_id = (
        Path(project_root),
        request["asset_type"],
        request["asset_id"],
    )
    passed = ["L0"]
    try:
        if reference_path is not None:
            file = (root / reference_path).resolve()
            if (
                not file.is_relative_to(root.resolve())
                or not file.is_file()
                or file.stat().st_size <= 0
            ):
                raise ValidationError(
                    f"reference image is not a non-empty project file: {reference_path}"
                )
            return _mapped(result, {"L0": True, "L1": True})
        for _, declaration in declarations:
            if family in {"compact-prop-pack", "scene-prop-set"}:
                continue
            declaration = CompileRequest(
                **{**declaration.__dict__, "project_root": root}
            )
            source = _l1_file(
                root, declaration.source_path, family=family, asset_id=asset_id
            )
            if not source.is_file() or source.stat().st_size <= 0:
                raise ValidationError(
                    f"standalone source is not a non-empty file: {declaration.source_path}"
                )
            if declaration.source_layout_type == "region_atlas":
                metadata = declaration.spec["metadata_path"]
                metadata_file = _l1_file(
                    root, metadata, family=family, asset_id=asset_id
                )
                if not metadata_file.is_file() or metadata_file.stat().st_size <= 0:
                    raise ValidationError(
                        f"atlas metadata is not a non-empty file: {metadata}"
                    )
            if declaration.source_layout_type == "grid_sheet":
                for action in declaration.spec["actions"]:
                    for frame in action["frame_paths"]:
                        frame_file = _l1_file(
                            root, frame, family=family, asset_id=asset_id
                        )
                        if not frame_file.is_file() or frame_file.stat().st_size <= 0:
                            raise ValidationError(
                                f"processed action frame is not a non-empty file: {frame}"
                            )
        if family in {"compact-prop-pack", "scene-prop-set"}:
            for slot in request["spec"]["slots"]:
                slot_file = (root / slot["source"]).resolve()
                if (
                    not slot_file.is_relative_to(root.resolve())
                    or not slot_file.is_file()
                    or slot_file.stat().st_size <= 0
                ):
                    raise ValidationError(
                        f"atlas slot source is not a non-empty project file: {slot['source']}"
                    )
    except (OSError, StableEntryError, ValidationError) as exc:
        return _failure(result, passed, "L1", exc)
    passed.append("L1")
    try:
        registry = build_default_registry()
        compiled: dict[str, CompileRequest] = {}
        if family in {"compact-prop-pack", "scene-prop-set"}:
            atlas_path = (
                Path("assets/generated") / family / asset_id / f"{asset_id}.png"
            )
            metadata_path = atlas_path.with_suffix(".json")
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", suffix=".json", dir=root, delete=False
            ) as handle:
                declaration_path = Path(handle.name)
                json.dump(request["spec"], handle)
            try:
                assemble_atlas(
                    declaration_path,
                    atlas_path,
                    metadata_path,
                    production_family=family,
                    asset_id=asset_id,
                    project_root=root,
                )
            finally:
                declaration_path.unlink(missing_ok=True)
        for output, declaration in declarations:
            actual = CompileRequest(**{**declaration.__dict__, "project_root": root})
            compiled_result = registry.compile(actual)
            if compiled_result.godot_artifact.to_dict() != {
                "type": output["godot_type"],
                "path": output["path"],
            }:
                raise ValidationError(
                    f"compiler output does not match runtime output {output['name']!r}"
                )
            compiled[output["path"]] = actual
    except (AtlasAssemblyError, CompilerError, OSError, ValidationError) as exc:
        return _failure(result, passed, "L2", exc)
    passed.append("L2")
    structures = build_default_structures()
    try:
        probe_requests = [
            ProbeRequest(
                output["path"],
                output["godot_type"],
                structures.checks_for(output["godot_type"]),
            )
            for output, _ in declarations
        ]
        report = GodotProbe(godot_path).probe(root, probe_requests)
        loaded = {item.res_path: item for item in report.resources}
        for output, _ in declarations:
            item = loaded.get(output["path"])
            if item is None or not item.loaded or not item.type_matches:
                raise ValidationError(
                    (item.error if item else None)
                    or f"Godot did not load {output['path']} as {output['godot_type']}"
                )
    except ValidationError as exc:
        return _failure(result, passed, "L3", exc)
    passed.append("L3")
    try:
        for output, _ in declarations:
            actual = compiled[output["path"]]
            structures.validate(
                StructureRequest(
                    actual.production_family,
                    actual.asset_id,
                    actual.source_layout_type,
                    actual.source_path,
                    actual.artifact_type,
                    actual.artifact_path,
                    root,
                    loaded[output["path"]],
                    actual.spec,
                )
            )
    except ValidationError as exc:
        return _failure(result, passed, "L4", exc)
    return _mapped(result, {level: True for level in _LEVELS})
