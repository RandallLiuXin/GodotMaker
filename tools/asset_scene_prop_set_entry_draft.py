#!/usr/bin/env python3
"""Build the ready v1 entry for one compiled scene-prop-set atlas."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from asset_atlas_assemble import validate_fixed_slot_rectangles
from asset_skill_contract_check import AssetContractError, check_request, check_result
from asset_stable_entry import SCHEMA_VERSION, StableEntryError, safe_identifier, stable_output_dir, validate_entry


FAMILY = "scene-prop-set"
LEVELS = ("L0", "L1", "L2", "L3", "L4")


class ScenePropSetEntryDraftError(Exception):
    """Raised when a scene-prop-set result cannot become a ready entry."""


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ScenePropSetEntryDraftError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ScenePropSetEntryDraftError(f"{label} must be a JSON object: {path}")
    return value


def _stable_paths(asset_id: str) -> tuple[str, str, str]:
    directory = stable_output_dir(FAMILY, asset_id)
    return (
        f"res://{directory}/{asset_id}.png",
        f"res://{directory}/{asset_id}.json",
        directory,
    )


def _slots(request: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the validated request declaration that the runtime result must match."""
    spec = request.get("spec")
    if not isinstance(spec, dict) or set(spec) != {"version", "atlas", "slots"}:
        raise ScenePropSetEntryDraftError(
            "scene-prop-set request.spec must be the exact fixed-slot declaration"
        )
    atlas = spec.get("atlas")
    if (
        spec.get("version") != 1
        or not isinstance(atlas, dict)
        or set(atlas) != {"width", "height"}
        or type(atlas.get("width")) is not int
        or type(atlas.get("height")) is not int
        or atlas["width"] <= 0
        or atlas["height"] <= 0
        or not isinstance(spec.get("slots"), list)
        or not spec["slots"]
    ):
        raise ScenePropSetEntryDraftError(
            "scene-prop-set request.spec must declare a non-empty v1 atlas"
        )

    slots: list[dict[str, Any]] = []
    rectangles: list[tuple[int, int, int, int]] = []
    names: set[str] = set()
    for index, raw_slot in enumerate(spec["slots"]):
        if not isinstance(raw_slot, dict):
            raise ScenePropSetEntryDraftError(f"request.spec.slots[{index}] must be an object")
        allowed = {"name", "rect", "source"}
        if "pivot" in raw_slot:
            allowed.add("pivot")
        if set(raw_slot) != allowed:
            raise ScenePropSetEntryDraftError(
                f"request.spec.slots[{index}] must contain only name, rect, source, and optional pivot"
            )
        name = raw_slot.get("name")
        rect = raw_slot.get("rect")
        source = raw_slot.get("source")
        if (
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(source, str)
            or not source.strip()
            or not isinstance(rect, list)
            or len(rect) != 4
            or any(type(value) is not int for value in rect)
            or rect[0] < 0
            or rect[1] < 0
            or rect[2] <= 0
            or rect[3] <= 0
        ):
            raise ScenePropSetEntryDraftError(
                f"request.spec.slots[{index}] is not a valid fixed slot"
            )
        try:
            safe_identifier(name, f"request.spec.slots[{index}].name")
        except StableEntryError as exc:
            raise ScenePropSetEntryDraftError(str(exc)) from exc
        if name in names:
            raise ScenePropSetEntryDraftError("request.spec.slots names must be unique")
        names.add(name)
        rectangles.append(tuple(rect))
        try:
            validate_fixed_slot_rectangles(rectangles, atlas["width"], atlas["height"])
        except ValueError as exc:
            raise ScenePropSetEntryDraftError(f"request.spec.{exc}") from exc
        slots.append(raw_slot)
    return slots


def _assert_file(project_root: Path, res_path: str, label: str) -> None:
    if not res_path.startswith("res://"):
        raise ScenePropSetEntryDraftError(f"{label} must be a res:// path")
    target = project_root / res_path[len("res://"):]
    if not target.is_file() or target.stat().st_size <= 0:
        raise ScenePropSetEntryDraftError(f"{label} is missing or empty: {res_path}")


def _validate_metadata(
    request: dict[str, Any], *, project_root: Path, atlas_path: str, metadata_path: str
) -> None:
    """Reject a ready handoff whose persisted regions drift from its request."""
    metadata = _load_object(project_root / metadata_path[len("res://"):], "atlas metadata")
    if metadata.get("version") != 1 or metadata.get("atlas_path") != atlas_path:
        raise ScenePropSetEntryDraftError("atlas metadata does not bind the stable atlas path")
    regions = metadata.get("regions")
    if not isinstance(regions, list):
        raise ScenePropSetEntryDraftError("atlas metadata regions must be a list")
    actual: dict[str, tuple[list[int], list[float | int]]] = {}
    for region in regions:
        if (
            not isinstance(region, dict)
            or not isinstance(region.get("name"), str)
            or not isinstance(region.get("rect"), list)
            or len(region["rect"]) != 4
            or any(type(value) is not int for value in region["rect"])
            or not isinstance(region.get("pivot"), list)
            or len(region["pivot"]) != 2
            or any(type(value) not in {int, float} for value in region["pivot"])
            or region["name"] in actual
        ):
            raise ScenePropSetEntryDraftError(
                "atlas metadata regions must have unique named integer rectangles and pivots"
            )
        actual[region["name"]] = (region["rect"], region["pivot"])
    expected = {
        slot["name"]: (slot["rect"], slot.get("pivot", [0.5, 0.5]))
        for slot in _slots(request)
    }
    if actual != expected:
        raise ScenePropSetEntryDraftError(
            "atlas metadata regions must exactly match declared slot rectangles and pivots"
        )


def build_scene_prop_set_entry_draft(
    request_path: Path,
    result_path: Path,
    *,
    tag: str,
    primary_output: str,
    project_root: Path,
) -> dict[str, Any]:
    """Validate a complete scene-prop-set delivery and build its ready entry."""
    request = _load_object(request_path, "request")
    result = _load_object(result_path, "asset Skill result")
    try:
        check_request(request)
        check_result(result)
    except AssetContractError as exc:
        raise ScenePropSetEntryDraftError(str(exc)) from exc
    if request.get("asset_type") != FAMILY or result.get("asset_type") != FAMILY:
        raise ScenePropSetEntryDraftError(
            "request and result must both be scene-prop-set"
        )
    if not isinstance(tag, str) or not tag.strip() or not isinstance(primary_output, str) or not primary_output.strip():
        raise ScenePropSetEntryDraftError("--tag and --primary-output must be non-empty strings")

    asset_id = request["asset_id"]
    slots = _slots(request)
    names = {slot["name"] for slot in slots}
    if primary_output not in names:
        raise ScenePropSetEntryDraftError("primary output must be a declared slot name")
    atlas_path, metadata_path, directory = _stable_paths(asset_id)
    if result["sources"] != [{"path": atlas_path, "layout": "region_atlas"}]:
        raise ScenePropSetEntryDraftError(
            "result must expose the one stable region_atlas source"
        )
    expected_outputs = {
        (name, f"res://{directory}/{name}.tres", "AtlasTexture") for name in names
    }
    actual_outputs = {
        (output.get("name"), output.get("path"), output.get("godot_type"))
        for output in result["outputs"]
        if output.get("role") == "runtime"
    }
    if actual_outputs != expected_outputs or len(result["outputs"]) != len(actual_outputs):
        raise ScenePropSetEntryDraftError(
            "result runtime outputs must exactly match declared scene prop slots"
        )
    validation = result["validation"]
    if validation.get("passed") is not True or validation.get("levels") != {
        level: True for level in LEVELS
    }:
        raise ScenePropSetEntryDraftError("result must have passed L0-L4 before ready entry is drafted")

    _assert_file(project_root, atlas_path, "stable atlas")
    _assert_file(project_root, metadata_path, "atlas metadata")
    _validate_metadata(
        request,
        project_root=project_root,
        atlas_path=atlas_path,
        metadata_path=metadata_path,
    )
    for _, path, _ in actual_outputs:
        _assert_file(project_root, path, "runtime output")

    entry = {
        "version": SCHEMA_VERSION,
        "asset_id": asset_id,
        "tag": tag,
        "production_family": FAMILY,
        "source_layout": {"type": "region_atlas", "path": atlas_path},
        "godot_artifact": {
            "type": "AtlasTexture",
            "path": f"res://{directory}/{primary_output}.tres",
        },
        "processing_status": "ready",
    }
    try:
        validate_entry(entry, project_root=project_root, check_files=True)
    except StableEntryError as exc:
        raise ScenePropSetEntryDraftError(str(exc)) from exc
    return entry


def write_scene_prop_set_entry_draft(
    request_path: Path,
    result_path: Path,
    *,
    tag: str,
    primary_output: str,
    project_root: Path,
    out: Path,
) -> dict[str, Any]:
    entry = build_scene_prop_set_entry_draft(
        request_path,
        result_path,
        tag=tag,
        primary_output=primary_output,
        project_root=project_root,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "draft": str(out), "entry": entry}


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a ready v1 stable-entry draft for a scene-prop-set atlas"
    )
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--primary-output", required=True)
    parser.add_argument("--project-root", default=".", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        payload = write_scene_prop_set_entry_draft(
            args.request,
            args.result,
            tag=args.tag,
            primary_output=args.primary_output,
            project_root=args.project_root,
            out=args.out,
        )
    except ScenePropSetEntryDraftError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
