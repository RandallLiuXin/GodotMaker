#!/usr/bin/env python3
"""Expand fixed ui-kit surface profiles into reusable StyleBoxTexture declarations."""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

from asset_ui_theme_recipe import (
    UI_TEXTURE_STYLEBOXES,
    UIThemeRecipeError,
    state_color,
    theme_tokens,
)


class UIStyleBoxPlanError(Exception):
    """Raised when fixed surface patches cannot form a closed StyleBox plan."""


_ASSET_ID = re.compile(r"^[A-Za-z0-9_-]+$")
_AXIS_STRETCH = {"stretch", "tile", "tile_fit"}
_PROFILE_KEYS = {
    "patch_size", "border", "content_margin", "expand_margin", "axis_stretch",
    "safe_center", "preview_sizes",
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UIStyleBoxPlanError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise UIStyleBoxPlanError(f"JSON object required: {path}")
    return value


def _numbers(value: Any, label: str, length: int, *, integers: bool = False) -> list[int | float]:
    if not isinstance(value, list) or len(value) != length:
        raise UIStyleBoxPlanError(f"{label} must contain exactly {length} values")
    result: list[int | float] = []
    for component in value:
        valid_type = type(component) is int if integers else type(component) in (int, float)
        if not valid_type or component < 0 or not math.isfinite(float(component)):
            raise UIStyleBoxPlanError(f"{label} must contain finite non-negative numbers")
        result.append(component)
    return result


def _profile(name: str, value: Any) -> dict[str, Any]:
    label = f"geometry_profiles.{name}"
    if not isinstance(value, dict) or set(value) != _PROFILE_KEYS:
        raise UIStyleBoxPlanError(f"{label} must contain the fixed geometry profile fields")
    patch_size = _numbers(value["patch_size"], f"{label}.patch_size", 2, integers=True)
    border = _numbers(value["border"], f"{label}.border", 4, integers=True)
    content_margin = _numbers(value["content_margin"], f"{label}.content_margin", 4)
    expand_margin = _numbers(value["expand_margin"], f"{label}.expand_margin", 4)
    safe_center = _numbers(value["safe_center"], f"{label}.safe_center", 4, integers=True)
    axis = value["axis_stretch"]
    if (
        not isinstance(axis, dict)
        or set(axis) != {"horizontal", "vertical"}
        or any(axis[key] not in _AXIS_STRETCH for key in axis)
    ):
        raise UIStyleBoxPlanError(f"{label}.axis_stretch is invalid")
    preview_sizes = value["preview_sizes"]
    if not isinstance(preview_sizes, list) or len(preview_sizes) < 2:
        raise UIStyleBoxPlanError(f"{label}.preview_sizes must contain at least two sizes")
    parsed_previews = [
        _numbers(size, f"{label}.preview_sizes[{index}]", 2, integers=True)
        for index, size in enumerate(preview_sizes)
    ]
    width, height = patch_size
    left, top, right, bottom = border
    if left + right >= width or top + bottom >= height:
        raise UIStyleBoxPlanError(f"{label}.border leaves no stretchable center")
    expected_center = [left, top, width - left - right, height - top - bottom]
    if safe_center != expected_center:
        raise UIStyleBoxPlanError(f"{label}.safe_center must match the nine-slice center")
    if any(content < edge for content, edge in zip(content_margin, border)):
        raise UIStyleBoxPlanError(f"{label}.content_margin must cover every border")
    for preview_width, preview_height in parsed_previews:
        if content_margin[0] + content_margin[2] > preview_width or content_margin[1] + content_margin[3] > preview_height:
            raise UIStyleBoxPlanError(f"{label}.content_margin exceeds a preview size")
    return {
        "patch_size": patch_size,
        "border": border,
        "content_margin": content_margin,
        "expand_margin": expand_margin,
        "axis_stretch": dict(axis),
        "safe_center": safe_center,
        "preview_sizes": parsed_previews,
    }


def build_stylebox_plan(
    source_sheet_plan: dict[str, Any], theme_plan: dict[str, Any], *, asset_id: str
) -> dict[str, Any]:
    if not _ASSET_ID.fullmatch(asset_id):
        raise UIStyleBoxPlanError("asset_id must use only letters, digits, underscores, and hyphens")
    if source_sheet_plan.get("version") != 3 or source_sheet_plan.get("asset_id") != asset_id:
        raise UIStyleBoxPlanError("version 3 source sheet plan for the same asset_id is required")
    try:
        tokens = theme_tokens(theme_plan)
    except UIThemeRecipeError as exc:
        raise UIStyleBoxPlanError(str(exc)) from exc
    scheme = source_sheet_plan.get("scheme")
    raw_profiles = scheme.get("geometry_profiles") if isinstance(scheme, dict) else None
    if not isinstance(raw_profiles, dict) or not raw_profiles:
        raise UIStyleBoxPlanError("source sheet plan has no geometry profiles")
    profiles = {name: _profile(name, value) for name, value in raw_profiles.items()}
    sheets = source_sheet_plan.get("sheets")
    if not isinstance(sheets, list) or not sheets:
        raise UIStyleBoxPlanError("source sheet plan has no sheets")

    asset_root = f"res://assets/generated/ui-kit/{asset_id}"
    declarations: list[dict[str, Any]] = []
    inspected_atlases: list[dict[str, str]] = []
    seen_outputs: set[str] = set()
    for sheet in sheets:
        if not isinstance(sheet, dict) or not isinstance(sheet.get("id"), str):
            raise UIStyleBoxPlanError("source sheet plan contains a malformed sheet")
        atlas = sheet.get("atlas")
        if not isinstance(atlas, dict) or not isinstance(atlas.get("source_name"), str):
            raise UIStyleBoxPlanError(f"source sheet plan {sheet['id']} has no atlas source")
        surface_slots = [slot for slot in sheet.get("slots", []) if isinstance(slot, dict) and slot.get("kind") == "surface"]
        if not surface_slots:
            continue
        atlas_path = f"{asset_root}/{atlas['source_name']}"
        inspected_atlases.append({"sheet_id": sheet["id"], "path": atlas_path})
        for slot in surface_slots:
            name = slot.get("name")
            profile_name = slot.get("geometry_profile")
            region = slot.get("rect")
            mappings = slot.get("runtime_styleboxes")
            if not isinstance(name, str) or profile_name not in profiles:
                raise UIStyleBoxPlanError("source sheet plan contains an invalid surface slot")
            if not isinstance(region, list) or len(region) != 4 or any(type(part) is not int for part in region):
                raise UIStyleBoxPlanError(f"surface slot {name} has an invalid rect")
            profile = profiles[profile_name]
            if region[2:] != profile["patch_size"]:
                raise UIStyleBoxPlanError(f"surface slot {name} does not match its fixed patch size")
            if not isinstance(mappings, list) or not mappings:
                raise UIStyleBoxPlanError(f"surface slot {name} has no runtime mappings")
            for mapping in mappings:
                if not isinstance(mapping, dict) or set(mapping) != {"output_name", "state", "tint"}:
                    raise UIStyleBoxPlanError(f"surface slot {name} has an invalid runtime mapping")
                output_name = mapping["output_name"]
                tint_name = mapping["tint"]
                state = mapping["state"]
                if output_name in seen_outputs or output_name not in UI_TEXTURE_STYLEBOXES:
                    raise UIStyleBoxPlanError(f"surface slot {name} has an invalid or duplicate output")
                if tint_name not in tokens or state not in {"normal", "hover", "pressed", "disabled"}:
                    raise UIStyleBoxPlanError(f"surface slot {name} has an invalid tint or state")
                seen_outputs.add(output_name)
                declarations.append({
                    "output_name": output_name,
                    "source_component": name,
                    "state": state,
                    "source_path": atlas_path,
                    "layout": "region_atlas",
                    "texture_region": list(region),
                    "border": list(profile["border"]),
                    "content_margin": list(profile["content_margin"]),
                    "expand_margin": list(profile["expand_margin"]),
                    "axis_stretch": dict(profile["axis_stretch"]),
                    "modulate_color": state_color(tokens[tint_name], state),
                    "geometry_profile": profile_name,
                    "safe_center": list(profile["safe_center"]),
                    "preview_sizes": [list(size) for size in profile["preview_sizes"]],
                })
    if seen_outputs != set(UI_TEXTURE_STYLEBOXES):
        missing = sorted(set(UI_TEXTURE_STYLEBOXES) - seen_outputs)
        extra = sorted(seen_outputs - set(UI_TEXTURE_STYLEBOXES))
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("unexpected " + ", ".join(extra))
        raise UIStyleBoxPlanError("surface runtime mappings are incomplete: " + "; ".join(details))
    return {
        "version": 2,
        "asset_id": asset_id,
        "inspected_atlases": inspected_atlases,
        "styleboxes": sorted(declarations, key=lambda item: item["output_name"]),
    }


def validate_stylebox_plan(plan: Any, request_styleboxes: Any, *, asset_id: str) -> dict[str, Any]:
    if not isinstance(plan, dict) or plan.get("version") != 2 or plan.get("asset_id") != asset_id:
        raise UIStyleBoxPlanError("stylebox plan must be version 2 for the same asset_id")
    atlases = plan.get("inspected_atlases")
    if not isinstance(atlases, list) or len(atlases) != 1:
        raise UIStyleBoxPlanError("stylebox plan must identify the surface atlas")
    if plan.get("styleboxes") != request_styleboxes:
        raise UIStyleBoxPlanError("request.spec.styleboxes must exactly match stylebox_plan.styleboxes")
    return {"styleboxes": len(request_styleboxes), "inspected_atlases": atlases}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sheet-plan", required=True)
    parser.add_argument("--theme-plan", required=True)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        plan = build_stylebox_plan(
            _read_json(Path(args.source_sheet_plan)),
            _read_json(Path(args.theme_plan)),
            asset_id=args.asset_id,
        )
    except UIStyleBoxPlanError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "path": args.out, "styleboxes": len(plan["styleboxes"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
