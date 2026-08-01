"""Executable standalone validation for the remaining first-class Asset Skills.

The public asset result is only a declaration.  This module intentionally
rebuilds its validation from the request, files, compiler, and Godot probe;
the caller's ``validation`` object is overwritten rather than trusted.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import json
import os
from pathlib import Path
from typing import Any
import warnings

from asset_compiler import CompileRequest, CompilerError, build_default_registry
from asset_compiler._stable_entry import (
    StableEntryError,
    assert_within_output_dir,
    resolve_res_path,
    safe_identifier,
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
    expected_source = f".godotmaker/asset-generation/sources/{asset_id}_source.png"
    if (
        _runtime(result)
        or result["previews"]
        or len(result["outputs"]) != 1
    ):
        raise MissingFamilySkillError(
            "screen-reference must have one reference output and no runtime source"
        )
    if result["sources"] != [{"path": expected_source, "layout": "single"}]:
        raise MissingFamilySkillError(
            "screen-reference must declare its deterministic raw single source"
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
    spec = _exact_keys(
        request.get("spec"), {"kind", "grid", "segments"}, "platform-strip spec"
    )
    kind = spec.get("kind")
    grid = _exact_keys(
        spec.get("grid"), {"columns", "rows", "cell_width", "cell_height"},
        "platform-strip grid",
    )
    segments = spec.get("segments")
    if (
        kind not in {"single", "atlas"}
        or not isinstance(segments, list)
        or len(segments) < 3
        or any(type(grid.get(key)) is not int or grid[key] <= 0 for key in grid)
    ):
        raise MissingFamilySkillError(
            "platform-strip spec needs kind, a positive fixed grid, and at least three segments"
        )
    asset_id = request["asset_id"]
    expected: list[tuple[Mapping[str, Any], CompileRequest]] = []
    sources: set[tuple[str, str]] = set()
    names: set[str] = set()
    slots: set[tuple[int, int]] = set()
    slots_in_order: list[tuple[int, int]] = []
    roles: list[str] = []
    for item in segments:
        entry = _exact_keys(item, {"name", "role", "slot"}, "platform-strip segment")
        name = entry.get("name")
        role = entry.get("role")
        slot = entry.get("slot")
        if (
            not isinstance(name, str)
            or not name
            or name in names
            or role not in {"left_cap", "repeat_middle", "right_cap"}
            or not isinstance(slot, list)
            or len(slot) != 2
            or any(type(value) is not int for value in slot)
            or not (0 <= slot[0] < grid["columns"] and 0 <= slot[1] < grid["rows"])
            or tuple(slot) in slots
        ):
            raise MissingFamilySkillError(
                "platform-strip segments need unique names, valid roles, and unique grid slots"
            )
        names.add(name)
        slots.add(tuple(slot))
        slots_in_order.append(tuple(slot))
        roles.append(role)
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
    expected_slots = [(index, 0) for index in range(len(segments))]
    expected_roles = [
        "left_cap",
        *("repeat_middle" for _ in segments[1:-1]),
        "right_cap",
    ]
    if (
        grid["rows"] != 1
        or grid["columns"] != len(segments)
        or slots_in_order != expected_slots
        or roles != expected_roles
    ):
        raise MissingFamilySkillError(
            "platform-strip needs one continuous left_cap/repeat_middle/right_cap row in slot order"
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
    if family == "character-bundle":
        has_user_identity = any(
            item.get("role") == "canonical"
            for item in request.get("references", [])
            if isinstance(item, Mapping)
        )
        reference_outputs = [item for item in result["outputs"] if item.get("role") == "reference"]
        canonical_path = _stable_path(family, asset_id, f"{asset_id}_canonical", ".png")
        if not has_user_identity and (
            len(reference_outputs) != 1
            or reference_outputs[0].get("name") != "canonical"
            or reference_outputs[0].get("path") != canonical_path
        ):
            raise MissingFamilySkillError(
                "a character-bundle without a user canonical reference must deliver its generated canonical image"
            )
        if has_user_identity and reference_outputs:
            raise MissingFamilySkillError(
                "a character-bundle with a user canonical reference must not replace it with an extra generated canonical output"
            )
    if family == "character-bundle":
        expected_sheets = [
            _stable_path(family, asset_id, f"{asset_id}_{action['name']}_sheet", ".png")
            for action in request["spec"]["actions"]
        ]
    else:
        expected_sheets = [_stable_path(family, asset_id, asset_id, "_sheet.png")]
    sheets = [source.get("path") for source in result["sources"]]
    if (
        len(sheets) != len(expected_sheets)
        or any(source.get("layout") != "grid_sheet" for source in result["sources"])
        or sheets != expected_sheets
    ):
        raise MissingFamilySkillError(
            "animated bundle sources must contain one stable grid_sheet per action"
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
        try:
            safe_identifier(name, f"{family} slots[{index}].name")
        except StableEntryError as exc:
            raise MissingFamilySkillError(str(exc)) from exc
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
    if family != "compact-prop-pack":
        return

    try:
        from PIL import Image

        with Image.open(atlas) as image:
            if image.format != "PNG" or image.mode != "RGBA":
                raise ValidationError("compact-prop-pack atlas must be an RGBA PNG")
            image.load()
            for slot in request["spec"]["slots"]:
                x, y, width, height = slot["rect"]
                crop = image.crop((x, y, x + width, y + height))
                try:
                    alpha = crop.getchannel("A").getextrema()
                    if alpha[0] != 0 or alpha[1] == 0:
                        raise ValidationError(
                            "compact-prop-pack slot must contain transparent padding "
                            f"and visible pixels: {slot['name']}"
                        )
                    if any(
                        pixel[:3] == (255, 0, 255) and pixel[3] > 0
                            for pixel in crop.get_flattened_data()
                    ):
                        raise ValidationError(
                            "compact-prop-pack atlas retains opaque magenta: "
                            f"{slot['name']}"
                        )
                finally:
                    crop.close()
    except ImportError as exc:
        raise ValidationError(
            "Pillow is required to validate compact-prop-pack transparency"
        ) from exc


def _verify_platform_png(
    path: Path, expected_dimensions: tuple[int, int]
) -> None:
    """Verify a processed platform cell or atlas is RGBA, sized, and chroma-clean."""
    try:
        from PIL import Image
    except ImportError as exc:
        raise ValidationError("Pillow is required to validate platform-strip PNG images") from exc
    try:
        with Image.open(path) as image:
            if image.format != "PNG" or image.mode != "RGBA":
                raise ValidationError("platform-strip output must be an RGBA PNG")
            image.load()
            if image.size != expected_dimensions:
                raise ValidationError("platform-strip output dimensions do not match its fixed grid")
            pixels = list(image.get_flattened_data())
    except (OSError, SyntaxError, ValueError) as exc:
        raise ValidationError(f"platform-strip output is not a decodable PNG: {path}") from exc
    if any(pixel[:3] == (255, 0, 255) and pixel[3] > 0 for pixel in pixels):
        raise ValidationError("platform-strip output contains opaque magenta background pixels")


def _verify_platform_source_and_references(
    request: Mapping[str, Any], root: Path
) -> None:
    """Verify the real source and any optional image inputs are readable project files."""
    try:
        from PIL import Image
    except ImportError as exc:
        raise ValidationError("Pillow is required to validate platform-strip image inputs") from exc

    paths = [
        (f".godotmaker/asset-generation/sources/{request['asset_id']}_source.png", "raw provider source")
    ]
    paths.extend((item["path"], f"platform-strip reference {item['role']}") for item in request.get("references", []))
    for path, label in paths:
        file = _project_file(root, path, label)
        if not file.is_file() or file.stat().st_size <= 0:
            raise ValidationError(f"{label} is not a non-empty readable file: {path}")
        try:
            with Image.open(file) as image:
                image.verify()
            with Image.open(file) as image:
                image.load()
        except (OSError, SyntaxError, ValueError) as exc:
            raise ValidationError(f"{label} is not a decodable image: {path}") from exc


def _verify_platform_delivery(
    request: Mapping[str, Any], declarations: list[tuple[Mapping[str, Any], CompileRequest]], root: Path
) -> None:
    """Bind platform-strip cells, atlas regions, and transparency to its fixed slot contract."""
    family, asset_id, spec = request["asset_type"], request["asset_id"], request["spec"]
    grid = spec["grid"]
    cell_size = (grid["cell_width"], grid["cell_height"])
    _verify_platform_source_and_references(request, root)
    if spec["kind"] == "single":
        for _, declaration in declarations:
            source = _l1_file(root, declaration.source_path, family=family, asset_id=asset_id)
            _verify_platform_png(source, cell_size)
        return

    declaration = declarations[0][1]
    atlas = _l1_file(root, declaration.source_path, family=family, asset_id=asset_id)
    metadata = _l1_file(root, declaration.spec["metadata_path"], family=family, asset_id=asset_id)
    if not atlas.is_file() or atlas.stat().st_size <= 0:
        raise ValidationError(f"standalone source is not a non-empty file: {declaration.source_path}")
    if not metadata.is_file() or metadata.stat().st_size <= 0:
        raise ValidationError(f"atlas metadata is not a non-empty file: {declaration.spec['metadata_path']}")
    try:
        delivered = json.loads(metadata.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValidationError(f"atlas metadata is not valid JSON: {metadata}") from exc
    if not isinstance(delivered, Mapping) or set(delivered) != {"version", "atlas_path", "regions"}:
        raise ValidationError("platform-strip atlas metadata must contain exactly version, atlas_path, and regions")
    if delivered.get("version") != 1 or delivered.get("atlas_path") != declaration.source_path:
        raise ValidationError("platform-strip atlas metadata does not bind the delivered stable atlas path")
    regions = delivered.get("regions")
    if not isinstance(regions, list):
        raise ValidationError("platform-strip atlas metadata regions must be a list")
    expected = {
        item["name"]: [
            item["slot"][0] * cell_size[0], item["slot"][1] * cell_size[1], *cell_size
        ]
        for item in spec["segments"]
    }
    actual: dict[str, list[int]] = {}
    for region in regions:
        if (
            not isinstance(region, Mapping)
            or set(region) != {"name", "rect", "pivot", "nine_slice"}
            or not isinstance(region.get("name"), str)
            or not isinstance(region.get("rect"), list)
            or len(region["rect"]) != 4
            or any(type(value) is not int for value in region["rect"])
            or region["name"] in actual
            or region.get("pivot") != [0.5, 1.0]
            or region.get("nine_slice") is not None
        ):
            raise ValidationError("platform-strip atlas metadata regions must use declared rects and bottom-center pivots")
        actual[region["name"]] = region["rect"]
    if actual != expected:
        raise ValidationError("platform-strip atlas metadata regions must exactly match declared slots")
    _verify_platform_png(
        atlas,
        (grid["columns"] * cell_size[0], grid["rows"] * cell_size[1]),
    )


def _resolved_character_request(
    request: Mapping[str, Any], project_root: Path
) -> Mapping[str, Any]:
    """Load the Skill-resolved request required for character runtime validation."""
    if request.get("asset_type") != "character-bundle":
        return request
    spec = request.get("spec")
    if isinstance(spec, Mapping) and "required_actions" in spec:
        return request
    try:
        check_bundle_request(request)
    except AnimatedBundleContractError as exc:
        raise MissingFamilySkillError(str(exc)) from exc
    asset_id = request.get("asset_id")
    if not isinstance(asset_id, str) or not asset_id:
        raise MissingFamilySkillError("character-bundle request.asset_id must be a non-empty string")
    resolved_path = (
        Path(project_root) / ".godotmaker" / "asset-generation" / "plans"
        / f"{asset_id}_resolved_request.json"
    )
    try:
        resolved = json.loads(resolved_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MissingFamilySkillError(
            "character-bundle runtime validation requires the archived resolved request: "
            f"{resolved_path}"
        ) from exc
    if not isinstance(resolved, Mapping):
        raise MissingFamilySkillError("character-bundle resolved request must be a JSON object")
    if (
        resolved.get("asset_type") != "character-bundle"
        or resolved.get("asset_id") != asset_id
        or resolved.get("provider") != request.get("provider")
        or resolved.get("references", []) != request.get("references", [])
    ):
        raise MissingFamilySkillError(
            "character-bundle resolved request must bind the public asset, provider, and references"
        )
    public_actions = spec.get("actions") if isinstance(spec, Mapping) else None
    resolved_spec = resolved.get("spec")
    if not isinstance(public_actions, list) or not isinstance(resolved_spec, Mapping):
        raise MissingFamilySkillError("character-bundle action plan cannot be resolved")
    public_names = [item.get("name") for item in public_actions if isinstance(item, Mapping)]
    if public_names != resolved_spec.get("required_actions"):
        raise MissingFamilySkillError(
            "character-bundle resolved request must retain public action names in order"
        )
    public_canvas = spec.get("frame_canvas_px", 256)
    if resolved_spec.get("frame_canvas_px", 256) != public_canvas:
        raise MissingFamilySkillError(
            "character-bundle resolved request must retain public frame_canvas_px"
        )
    resolved_actions = resolved_spec.get("actions")
    if not isinstance(resolved_actions, list) or len(resolved_actions) != len(public_actions):
        raise MissingFamilySkillError(
            "character-bundle resolved request must retain every public action"
        )
    for index, (public_action, resolved_action) in enumerate(
        zip(public_actions, resolved_actions)
    ):
        if not isinstance(public_action, Mapping) or not isinstance(
            resolved_action, Mapping
        ):
            raise MissingFamilySkillError(
                "character-bundle resolved request actions must be objects"
            )
        if (
            resolved_action.get("name") != public_action.get("name")
            or resolved_action.get("intent") != public_action.get("intent")
        ):
            raise MissingFamilySkillError(
                "character-bundle resolved request must retain public action "
                f"name and intent at index {index}"
            )
        if (
            "loop" in public_action
            and resolved_action.get("loop") is not public_action.get("loop")
        ):
            raise MissingFamilySkillError(
                "character-bundle resolved request must retain explicit public action "
                f"loop at index {index}"
            )
    return resolved


def compile_and_validate(
    request: Mapping[str, Any],
    result: Mapping[str, Any],
    *,
    project_root: Path,
    godot_path: str,
    expected_family: str | None = None,
) -> dict[str, Any]:
    """Execute the real applicable ladder for one of the seven missing families."""
    root = Path(project_root)
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
        request = _resolved_character_request(request, root)
        reference_path, declarations = _declarations(request, result)
        auxiliary_paths = _auxiliary_paths(result)
    except (AssetContractError, MissingFamilySkillError) as exc:
        raise MissingFamilySkillError(f"L0 standalone contract failed: {exc}") from exc
    family, asset_id = request["asset_type"], request["asset_id"]
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
            raw_source = _project_file(
                root,
                f".godotmaker/asset-generation/sources/{asset_id}_source.png",
                "raw screen-reference source",
            )
            if not raw_source.is_file() or raw_source.stat().st_size <= 0:
                raise ValidationError(
                    "raw screen-reference source is not a non-empty file: "
                    f".godotmaker/asset-generation/sources/{asset_id}_source.png"
                )
            try:
                _png_dimensions(raw_source)
            except ValidationError as exc:
                raise ValidationError(
                    "raw screen-reference source is not a decodable PNG: "
                    f".godotmaker/asset-generation/sources/{asset_id}_source.png"
                ) from exc
            return _mapped(result, {"L0": True, "L1": True})
        if family == "platform-strip":
            _verify_platform_delivery(request, declarations, root)
        elif family in {"compact-prop-pack", "scene-prop-set"}:
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
        # Eval runners inject a pinned executable through this variable.  Callers
        # that retained the historical generic ``godot`` placeholder must not
        # silently bypass that pin and fall back to PATH.
        resolved_godot_path = (
            os.environ.get("GM_EVAL_GODOT_PATH")
            if godot_path == "godot" and os.environ.get("GM_EVAL_GODOT_PATH")
            else godot_path
        )
        report = GodotProbe(resolved_godot_path).probe(root, probe_requests)
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
