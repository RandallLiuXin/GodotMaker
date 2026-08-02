#!/usr/bin/env python3
"""Build logical stable-entry drafts for one ready compact prop atlas bundle."""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from asset_atlas_assemble import validate_fixed_slot_rectangles
from asset_skill_contract_check import AssetContractError, check_request, check_result
from asset_stable_entry import StableEntryError, safe_identifier, validate_entry


FAMILY = "compact-prop-pack"
LEVELS = ("L0", "L1", "L2", "L3", "L4")


class CompactPropPackEntryDraftError(Exception):
    """Raised when a compact prop result cannot become ready stable entries."""


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CompactPropPackEntryDraftError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise CompactPropPackEntryDraftError(f"{label} must be a JSON object")
    return value


def _require_slot_names(request: dict[str, Any]) -> list[str]:
    spec = request.get("spec")
    if not isinstance(spec, dict) or set(spec) != {"version", "atlas", "slots"}:
        raise CompactPropPackEntryDraftError(
            "compact-prop-pack request.spec must be the exact fixed-slot declaration"
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
        raise CompactPropPackEntryDraftError(
            "compact-prop-pack request.spec must declare a non-empty v1 atlas"
        )

    names: list[str] = []
    rectangles: list[tuple[int, int, int, int]] = []
    for index, raw_slot in enumerate(spec["slots"]):
        if not isinstance(raw_slot, dict):
            raise CompactPropPackEntryDraftError(f"spec.slots[{index}] must be an object")
        allowed = {"name", "rect", "source"}
        if "pivot" in raw_slot:
            allowed.add("pivot")
        if set(raw_slot) != allowed:
            raise CompactPropPackEntryDraftError(
                f"spec.slots[{index}] must contain only name, rect, source, and optional pivot"
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
            raise CompactPropPackEntryDraftError(
                f"spec.slots[{index}] is not a valid fixed slot"
            )
        try:
            safe_identifier(name, f"spec.slots[{index}].name")
        except StableEntryError as exc:
            raise CompactPropPackEntryDraftError(str(exc)) from exc
        rectangles.append(tuple(rect))
        try:
            validate_fixed_slot_rectangles(rectangles, atlas["width"], atlas["height"])
        except ValueError as exc:
            raise CompactPropPackEntryDraftError(f"spec.{exc}") from exc
        names.append(name)
    if len(set(names)) != len(names):
        raise CompactPropPackEntryDraftError("spec.slots names must be unique")
    return names


def logical_outputs(request: dict[str, Any]) -> list[tuple[str, str]]:
    """Return every declared prop as ``(output_name, godot_type)``.

    The slot names come from the request, so the manager can declare the
    ASSETS.md rows this bundle will fill before its Skill runs.
    """
    try:
        check_request(request)
    except AssetContractError as exc:
        raise CompactPropPackEntryDraftError(str(exc)) from exc
    if request.get("asset_type") != FAMILY:
        raise CompactPropPackEntryDraftError("request must be compact-prop-pack")
    return [(name, "AtlasTexture") for name in _require_slot_names(request)]


def _validate_bundle_metadata(
    request: dict[str, Any], *, project_root: Path, bundle_id: str
) -> None:
    """Reject a ready handoff whose persisted atlas regions drift from its request."""
    root = f"res://assets/generated/{FAMILY}/{bundle_id}"
    metadata = Path(project_root) / root[len("res://"):] / f"{bundle_id}.json"
    try:
        value = json.loads(metadata.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CompactPropPackEntryDraftError(
            f"compact-prop-pack atlas metadata is not valid JSON: {metadata}"
        ) from exc
    if not isinstance(value, dict) or set(value) != {"version", "atlas_path", "regions"}:
        raise CompactPropPackEntryDraftError(
            "compact-prop-pack atlas metadata must contain exactly version, atlas_path, and regions"
        )
    if value.get("version") != 1 or value.get("atlas_path") != f"{root}/{bundle_id}.png":
        raise CompactPropPackEntryDraftError(
            "compact-prop-pack atlas metadata must bind the stable bundle atlas"
        )
    regions = value.get("regions")
    if not isinstance(regions, list):
        raise CompactPropPackEntryDraftError("compact-prop-pack atlas metadata regions must be a list")
    actual: dict[str, list[int]] = {}
    for region in regions:
        if (
            not isinstance(region, dict)
            or not isinstance(region.get("name"), str)
            or not isinstance(region.get("rect"), list)
            or len(region["rect"]) != 4
            or any(type(component) is not int for component in region["rect"])
            or region["name"] in actual
        ):
            raise CompactPropPackEntryDraftError(
                "compact-prop-pack atlas metadata regions must have unique named integer rectangles"
            )
        actual[region["name"]] = region["rect"]
    expected = {slot["name"]: slot["rect"] for slot in request["spec"]["slots"]}
    if actual != expected:
        raise CompactPropPackEntryDraftError(
            "compact-prop-pack atlas metadata regions must exactly match declared slots"
        )


def build_compact_prop_pack_entry_drafts(
    request_path: Path,
    result_path: Path,
    *,
    tag: str,
    project_root: Path,
    check_files: bool = True,
) -> list[dict[str, Any]]:
    """Return one ready entry per logical prop in a validated atlas bundle."""
    request = _load_json(request_path, "request")
    result = _load_json(result_path, "result")
    try:
        check_request(request)
        check_result(result)
    except AssetContractError as exc:
        raise CompactPropPackEntryDraftError(str(exc)) from exc
    if request["asset_type"] != FAMILY or result["asset_type"] != FAMILY:
        raise CompactPropPackEntryDraftError(
            "request and result must both be compact-prop-pack"
        )

    bundle_id = request["asset_id"]
    names = _require_slot_names(request)
    root = f"res://assets/generated/{FAMILY}/{bundle_id}"
    expected_source = {"path": f"{root}/{bundle_id}.png", "layout": "region_atlas"}
    if result["sources"] != [expected_source]:
        raise CompactPropPackEntryDraftError(
            "result must expose exactly the bundle's stable region_atlas source"
        )
    expected_outputs = {
        (name, f"{root}/{name}.tres", "AtlasTexture") for name in names
    }
    actual_outputs = {
        (item.get("name"), item.get("path"), item.get("godot_type"))
        for item in result["outputs"]
        if item.get("role") == "runtime"
    }
    if actual_outputs != expected_outputs or len(actual_outputs) != len(result["outputs"]):
        raise CompactPropPackEntryDraftError(
            "result must expose every declared compact prop as one AtlasTexture"
        )
    validation = result["validation"]
    if validation.get("passed") is not True or validation.get("levels") != {
        level: True for level in LEVELS
    }:
        raise CompactPropPackEntryDraftError(
            "result must have passed L0-L4 before ready entries are drafted"
        )
    if check_files:
        _validate_bundle_metadata(request, project_root=Path(project_root), bundle_id=bundle_id)

    entries: list[dict[str, Any]] = []
    for name in names:
        entry = {
            "version": 1,
            "asset_id": f"{bundle_id}--{name}",
            "tag": tag,
            "production_family": FAMILY,
            "bundle_id": bundle_id,
            "source_layout": {"type": "region_atlas", "path": expected_source["path"]},
            "godot_artifact": {
                "type": "AtlasTexture",
                "path": f"{root}/{name}.tres",
            },
            "processing_status": "ready",
        }
        try:
            validate_entry(entry, project_root=Path(project_root), check_files=check_files)
        except StableEntryError as exc:
            raise CompactPropPackEntryDraftError(str(exc)) from exc
        entries.append(entry)
    return entries


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", delete=False, dir=str(path.parent), suffix=".json"
    ) as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def write_compact_prop_pack_entry_drafts(
    request_path: Path,
    result_path: Path,
    *,
    tag: str,
    project_root: Path,
    out_dir: Path,
    check_files: bool = True,
) -> dict[str, Any]:
    entries = build_compact_prop_pack_entry_drafts(
        request_path,
        result_path,
        tag=tag,
        project_root=project_root,
        check_files=check_files,
    )
    outputs: list[str] = []
    for entry in entries:
        path = Path(out_dir) / f"{entry['asset_id']}.json"
        _atomic_write_json(path, entry)
        outputs.append(str(path))
    return {"ok": True, "count": len(entries), "drafts": outputs}


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Build ready stable-entry drafts for a compact prop atlas bundle"
    )
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--project-root", default=".", type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument(
        "--no-check-files",
        action="store_true",
        help="Only validate declaration paths; do not require source and .tres files",
    )
    args = parser.parse_args()
    try:
        result = write_compact_prop_pack_entry_drafts(
            args.request,
            args.result,
            tag=args.tag,
            project_root=args.project_root,
            out_dir=args.out_dir,
            check_files=not args.no_check_files,
        )
    except CompactPropPackEntryDraftError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
