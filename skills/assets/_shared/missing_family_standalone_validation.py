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
from typing import Any
import warnings

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
from asset_atlas_assemble import validate_fixed_slot_rectangles


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


def _reference_failure(result: Mapping[str, Any], error: Exception) -> dict[str, Any]:
    """Map reference-only failures without inventing runtime ladder levels."""
    return _mapped(result, {"L0": True, "L1": False}, error)


def _terminal_generation_stop(result: Mapping[str, Any]) -> dict[str, Any] | None:
    """Accept a declared no-output provider stop without inventing an artifact.

    A provider or required-reference failure happens before L1 can observe a
    source file.  It is still a valid L0 request/result pair, but treating it as
    a malformed successful background would make a fail-closed STOP impossible.
    """
    validation = result["validation"]
    if validation.get("passed") is not False:
        return None
    if result["outputs"] or result["sources"] or result["previews"]:
        return None
    note = validation.get("notes")
    if not isinstance(note, str) or not note.strip():
        raise MissingFamilySkillError(
            "a no-output generation STOP must include a validation note"
        )
    return _mapped(result, {"L0": True, "L1": False}, ValidationError(note))


def _runtime(result: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [item for item in result["outputs"] if item["role"] == "runtime"]


def _stable_path(family: str, asset_id: str, name: str, suffix: str) -> str:
    return f"res://assets/generated/{family}/{asset_id}/{name}{suffix}"


def _project_file(root: Path, path: Any, label: str) -> Path:
    if not isinstance(path, str) or not path.strip():
        raise ValidationError(f"{label} must be a non-empty project-relative path")
    candidate = (
        resolve_res_path(root, path, label=label)
        if path.startswith("res://")
        else (root / path).resolve()
    )
    if not candidate.is_relative_to(root.resolve()):
        raise ValidationError(f"{label} resolves outside the project root")
    return candidate


def _auxiliary_paths(result: Mapping[str, Any]) -> list[str]:
    """Return non-runtime output and preview paths for L1 containment checks."""
    paths: list[str] = []
    for output in result["outputs"]:
        if output["role"] == "reference":
            paths.append(output["path"])
    paths.extend(item["path"] for item in result["previews"])
    return paths


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
    if (
        _runtime(result)
        or result["sources"]
        or result["previews"]
        or len(result["outputs"]) != 1
    ):
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
    sources: set[tuple[str, str]] = set()
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
            sources.add((path, "single"))
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
            sources.add((source, "region_atlas"))
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
        or len(result["sources"]) != len(sources)
        or {(source["path"], source.get("layout")) for source in result["sources"]}
        != sources
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
    if not sheets or len(sheets) != len(result["sources"]):
        raise MissingFamilySkillError(
            "animated bundle sources must be non-empty grid_sheet files"
        )
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
    atlas = _exact_keys(spec.get("atlas"), {"width", "height"}, f"{family} atlas")
    if any(
        type(atlas.get(axis)) is not int or atlas[axis] <= 0
        for axis in ("width", "height")
    ):
        raise MissingFamilySkillError(
            f"{family} atlas width and height must be positive integers"
        )
    slots = spec["slots"]
    names: list[str] = []
    rectangles: list[tuple[int, int, int, int]] = []
    for index, raw_slot in enumerate(slots):
        if not isinstance(raw_slot, Mapping):
            raise MissingFamilySkillError(f"{family} slots[{index}] must be an object")
        keys = (
            {"name", "rect", "source", "pivot"}
            if "pivot" in raw_slot
            else {"name", "rect", "source"}
        )
        slot = _exact_keys(raw_slot, keys, f"{family} slots[{index}]")
        name = slot.get("name")
        rect = slot.get("rect")
        if (
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(slot.get("source"), str)
            or not slot["source"].strip()
            or not isinstance(rect, list)
            or len(rect) != 4
            or any(type(value) is not int for value in rect)
            or rect[0] < 0
            or rect[1] < 0
            or rect[2] <= 0
            or rect[3] <= 0
        ):
            raise MissingFamilySkillError(
                f"{family} slots[{index}] must be a valid fixed-slot declaration"
            )
        rectangles.append(tuple(rect))
        try:
            validate_fixed_slot_rectangles(rectangles, atlas["width"], atlas["height"])
        except ValueError as exc:
            raise MissingFamilySkillError(f"{family} {exc}") from exc
        names.append(name)
    if len(set(names)) != len(names):
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


def _png_dimensions(path: Path) -> tuple[int, int]:
    """Fully verify and decode a PNG before returning its dimensions."""
    try:
        from PIL import Image
    except ImportError as exc:
        raise ValidationError("Pillow is required to validate delivered PNG images") from exc
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                if image.format != "PNG":
                    raise ValidationError("delivered image is not a PNG")
                image.verify()
            with Image.open(path) as image:
                if image.format != "PNG":
                    raise ValidationError("delivered image is not a PNG")
                image.load()
                return image.size
    except (
        OSError,
        SyntaxError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValidationError("delivered image is not a decodable PNG") from exc


def _verify_prop_delivery(
    request: Mapping[str, Any], declaration: CompileRequest, root: Path
) -> None:
    """Bind delivered atlas dimensions and metadata regions to request.spec."""
    family, asset_id = request["asset_type"], request["asset_id"]
    atlas = _l1_file(root, declaration.source_path, family=family, asset_id=asset_id)
    metadata = _l1_file(
        root, declaration.spec["metadata_path"], family=family, asset_id=asset_id
    )
    if not atlas.is_file() or atlas.stat().st_size <= 0:
        raise ValidationError(
            f"standalone source is not a non-empty file: {declaration.source_path}"
        )
    if not metadata.is_file() or metadata.stat().st_size <= 0:
        raise ValidationError(
            f"atlas metadata is not a non-empty file: {declaration.spec['metadata_path']}"
        )
    try:
        delivered = json.loads(metadata.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValidationError(f"atlas metadata is not valid JSON: {metadata}") from exc
    if not isinstance(delivered, Mapping) or set(delivered) != {
        "version",
        "atlas_path",
        "regions",
    }:
        raise ValidationError(
            "atlas metadata must contain exactly version, atlas_path, and regions"
        )
    if (
        delivered.get("version") != 1
        or delivered.get("atlas_path") != declaration.source_path
    ):
        raise ValidationError(
            "atlas metadata does not bind the delivered stable atlas path"
        )
    regions = delivered.get("regions")
    if not isinstance(regions, list):
        raise ValidationError("atlas metadata regions must be a list")
    actual: dict[str, list[int]] = {}
    for region in regions:
        if (
            not isinstance(region, Mapping)
            or not isinstance(region.get("name"), str)
            or not isinstance(region.get("rect"), list)
            or len(region["rect"]) != 4
            or any(type(value) is not int for value in region["rect"])
            or region["name"] in actual
        ):
            raise ValidationError(
                "atlas metadata regions must have unique named integer rectangles"
            )
        actual[region["name"]] = region["rect"]
    expected = {slot["name"]: slot["rect"] for slot in request["spec"]["slots"]}
    if actual != expected:
        raise ValidationError(
            "atlas metadata regions must exactly match declared slot names and rectangles"
        )
    try:
        dimensions = _png_dimensions(atlas)
    except ValidationError as exc:
        raise ValidationError(
            f"delivered atlas is not a decodable PNG: {declaration.source_path}"
        ) from exc
    if dimensions != (
        request["spec"]["atlas"]["width"],
        request["spec"]["atlas"]["height"],
    ):
        raise ValidationError(
            "delivered atlas dimensions do not match the declared atlas"
        )


def compile_and_validate(
    request: Mapping[str, Any],
    result: Mapping[str, Any],
    *,
    project_root: Path,
    godot_path: str,
    expected_family: str | None = None,
) -> dict[str, Any]:
    """Execute the real applicable ladder for one of the seven missing families."""
    try:
        check_request(request)
        check_result(result)
        if expected_family is not None and (
            request["asset_type"] != expected_family
            or result["asset_type"] != expected_family
        ):
            raise MissingFamilySkillError(
                f"standalone adapter requires asset_type {expected_family!r}"
            )
        if (
            request["asset_type"] not in _FAMILIES
            or result["asset_type"] != request["asset_type"]
        ):
            raise MissingFamilySkillError(
                "standalone validation needs one supported matching asset_type"
            )
        stopped = _terminal_generation_stop(result)
        if stopped is not None:
            return stopped
        reference_path, declarations = _declarations(request, result)
        auxiliary_paths = _auxiliary_paths(result)
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
            file = _project_file(root, reference_path, "reference image")
            try:
                is_non_empty = file.is_file() and file.stat().st_size > 0
            except OSError as exc:
                raise ValidationError(
                    f"reference image cannot be read: {reference_path}"
                ) from exc
            if not is_non_empty:
                raise ValidationError(
                    f"reference image is not a non-empty file: {reference_path}"
                )
            try:
                _png_dimensions(file)
            except ValidationError as exc:
                raise ValidationError(
                    f"reference image is not a decodable PNG: {reference_path}"
                ) from exc
            return _mapped(result, {"L0": True, "L1": True})
        if family in {"compact-prop-pack", "scene-prop-set"}:
            _verify_prop_delivery(request, declarations[0][1], root)
        for _, declaration in declarations:
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
                for source_path in result["sources"]:
                    sheet_file = _l1_file(
                        root, source_path["path"], family=family, asset_id=asset_id
                    )
                    if not sheet_file.is_file() or sheet_file.stat().st_size <= 0:
                        raise ValidationError(
                            f"grid sheet is not a non-empty file: {source_path['path']}"
                        )
                for action in declaration.spec["actions"]:
                    for frame in action["frame_paths"]:
                        frame_file = _l1_file(
                            root, frame, family=family, asset_id=asset_id
                        )
                        if not frame_file.is_file() or frame_file.stat().st_size <= 0:
                            raise ValidationError(
                                f"processed action frame is not a non-empty file: {frame}"
                            )
        for path in auxiliary_paths:
            file = _project_file(root, path, "reference output or preview")
            if not file.is_file() or file.stat().st_size <= 0:
                raise ValidationError(
                    f"reference output or preview is not a non-empty file: {path}"
                )
    except (OSError, StableEntryError, ValidationError) as exc:
        return (
            _reference_failure(result, exc)
            if reference_path is not None
            else _failure(result, passed, "L1", exc)
        )
    passed.append("L1")
    try:
        registry = build_default_registry()
        compiled: dict[str, CompileRequest] = {}
        for output, declaration in declarations:
            actual = CompileRequest(**{**declaration.__dict__, "project_root": root})
            registry.compile(actual)
            compiled[output["path"]] = actual
    except (CompilerError, OSError, ValidationError) as exc:
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
