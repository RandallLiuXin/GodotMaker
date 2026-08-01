#!/usr/bin/env python3
"""Create auditable, color-keyed ui-kit image-provider source-sheet prompts."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from asset_ui_theme_recipe import UI_ICONS, UI_TEXTURE_STYLEBOXES


class UISourcePlanError(Exception):
    """Raised when a provider source-sheet plan cannot be produced."""


PIXEL_LANGUAGE = re.compile(r"\b(?:non[- ]?pixel(?:[- ]?art)?|not\s+pixel(?:[- ]?art)?)\b", re.IGNORECASE)
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UISourcePlanError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise UISourcePlanError(f"JSON object required: {path}")
    return value


def _clean_visual_direction(brief: str) -> str:
    return " ".join(PIXEL_LANGUAGE.sub("", brief).split())


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise UISourcePlanError(f"{label} must be a positive integer")
    return value


def _runtime_names(value: Any, label: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(name, str) or not SAFE_NAME.fullmatch(name) for name in value)
        or len(value) != len(set(value))
    ):
        raise UISourcePlanError(f"{label} must be a duplicate-free list of safe names")
    return list(value)


def _runtime_styleboxes(value: Any, label: str) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise UISourcePlanError(f"{label} must contain runtime StyleBox mappings")
    result: list[dict[str, str]] = []
    for index, raw in enumerate(value):
        item_label = f"{label}[{index}]"
        if not isinstance(raw, dict) or set(raw) != {"output_name", "state", "tint"}:
            raise UISourcePlanError(f"{item_label} must contain output_name, state, and tint")
        if any(not isinstance(raw[key], str) or not SAFE_NAME.fullmatch(raw[key]) for key in raw):
            raise UISourcePlanError(f"{item_label} values must be safe names")
        result.append(dict(raw))
    if len({item["output_name"] for item in result}) != len(result):
        raise UISourcePlanError(f"{label} contains duplicate output names")
    return result


def _sheet_layout(
    sheet: dict[str, Any], geometry_profiles: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], dict[str, int]]:
    sheet_id = sheet.get("id")
    source_name = sheet.get("source_name")
    components = sheet.get("components")
    atlas = sheet.get("atlas")
    provider_grid = sheet.get("provider_grid")
    if not isinstance(sheet_id, str) or not SAFE_NAME.fullmatch(sheet_id):
        raise UISourcePlanError("source-sheet scheme contains an invalid sheet id")
    if not isinstance(source_name, str) or not source_name.endswith(".png"):
        raise UISourcePlanError(f"source-sheet scheme {sheet_id} has an invalid source_name")
    if not isinstance(components, list) or not components:
        raise UISourcePlanError(f"source-sheet scheme {sheet_id} has no components")
    if not isinstance(atlas, dict):
        raise UISourcePlanError(f"source-sheet scheme {sheet_id} has no atlas layout")
    if not isinstance(provider_grid, dict):
        raise UISourcePlanError(f"source-sheet scheme {sheet_id} has no provider grid")

    columns = _positive_int(provider_grid.get("columns"), f"{sheet_id}.provider_grid.columns")
    rows = _positive_int(provider_grid.get("rows"), f"{sheet_id}.provider_grid.rows")
    gutter = _positive_int(atlas.get("gutter"), f"{sheet_id}.atlas.gutter")
    max_width = _positive_int(atlas.get("max_width"), f"{sheet_id}.atlas.max_width")
    if len(components) > columns * rows:
        raise UISourcePlanError(f"{sheet_id} components exceed provider grid capacity")

    parsed_components: list[dict[str, Any]] = []
    slots: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    x = gutter
    y = gutter
    row_height = 0
    for index, component in enumerate(components):
        if not isinstance(component, dict):
            raise UISourcePlanError(f"{sheet_id}.components[{index}] must be an object")
        name = component.get("name")
        label = component.get("label")
        target_size = component.get("target_size")
        kind = component.get("kind")
        geometry_profile = component.get("geometry_profile")
        if not isinstance(name, str) or not SAFE_NAME.fullmatch(name):
            raise UISourcePlanError(f"{sheet_id}.components[{index}].name is invalid")
        if name in seen_names:
            raise UISourcePlanError(f"{sheet_id} component name is duplicated: {name}")
        if not isinstance(label, str) or not label.strip():
            raise UISourcePlanError(f"{sheet_id}.components[{index}].label is invalid")
        if not isinstance(target_size, list) or len(target_size) != 2:
            raise UISourcePlanError(f"{sheet_id}.components[{index}].target_size must be [width, height]")
        target_width = _positive_int(target_size[0], f"{sheet_id}.components[{index}].target_size[0]")
        target_height = _positive_int(target_size[1], f"{sheet_id}.components[{index}].target_size[1]")
        if target_width + gutter * 2 > max_width:
            raise UISourcePlanError(f"{sheet_id}.components[{index}] exceeds atlas.max_width")
        if kind not in {"surface", "icon"}:
            raise UISourcePlanError(f"{sheet_id}.components[{index}].kind is invalid")
        runtime_styleboxes: list[dict[str, str]] = []
        runtime_names: list[str] = []
        if kind == "surface":
            if not isinstance(geometry_profile, str) or geometry_profile not in geometry_profiles:
                raise UISourcePlanError(
                    f"{sheet_id}.components[{index}].geometry_profile is invalid"
                )
            profile = geometry_profiles[geometry_profile]
            if not isinstance(profile, dict) or profile.get("patch_size") != [target_width, target_height]:
                raise UISourcePlanError(
                    f"{sheet_id}.components[{index}] must match its geometry profile patch_size"
                )
            runtime_styleboxes = _runtime_styleboxes(
                component.get("runtime_styleboxes"),
                f"{sheet_id}.components[{index}].runtime_styleboxes",
            )
            if "runtime_names" in component:
                raise UISourcePlanError(f"{sheet_id}.components[{index}] may not declare runtime_names")
        else:
            if "geometry_profile" in component or "runtime_styleboxes" in component:
                raise UISourcePlanError(
                    f"{sheet_id}.components[{index}] icon may not declare surface fields"
                )
            runtime_names = _runtime_names(
                component.get("runtime_names"), f"{sheet_id}.components[{index}].runtime_names"
            )
        seen_names.add(name)
        parsed = {
            "name": name, "label": label.strip(), "target_size": [target_width, target_height],
            "kind": kind,
        }
        if kind == "surface":
            parsed.update({
                "geometry_profile": geometry_profile,
                "runtime_styleboxes": runtime_styleboxes,
            })
        else:
            parsed["runtime_names"] = runtime_names
        parsed_components.append(parsed)
        if x + target_width + gutter > max_width:
            x = gutter
            y += row_height + gutter
            row_height = 0
        slot = {
            "index": index,
            "name": name,
            "label": label.strip(),
            "kind": kind,
            "target_size": [target_width, target_height],
            "rect": [x, y, target_width, target_height],
        }
        if kind == "surface":
            slot.update({
                "geometry_profile": geometry_profile,
                "runtime_styleboxes": runtime_styleboxes,
            })
        else:
            slot["runtime_names"] = runtime_names
        slots.append(slot)
        x += target_width + gutter
        row_height = max(row_height, target_height)

    atlas_plan = {
        "source_name": f"{sheet_id}_atlas.png",
        "metadata_name": f"{sheet_id}_atlas.json",
        "max_width": max_width,
        "gutter": gutter,
        "width": max_width,
        "height": y + row_height + gutter,
    }
    return parsed_components, atlas_plan, slots, {"columns": columns, "rows": rows}


def build_source_sheet_plan(request: dict[str, Any], scheme: dict[str, Any], *, rendering_medium: str) -> dict[str, Any]:
    if request.get("asset_type") != "ui-kit":
        raise UISourcePlanError("ui-kit request required")
    asset_id = request.get("asset_id")
    provider = request.get("provider")
    references = request.get("references")
    brief = request.get("brief")
    if not isinstance(asset_id, str) or not asset_id:
        raise UISourcePlanError("request.asset_id must be a non-empty string")
    if provider not in {"native", "codex", "gemini", "openai"}:
        raise UISourcePlanError("request.provider must be pinned")
    if not isinstance(references, list) or not references:
        raise UISourcePlanError("ui-kit requires a binding reference")
    if not isinstance(brief, str) or not brief.strip():
        raise UISourcePlanError("request.brief must be a non-empty string")
    if not isinstance(rendering_medium, str) or not rendering_medium.strip():
        raise UISourcePlanError("rendering_medium must describe the visual medium")
    background = scheme.get("background")
    composition = scheme.get("composition")
    sheets = scheme.get("sheets")
    geometry_profiles = scheme.get("geometry_profiles")
    if (
        not isinstance(background, dict)
        or background.get("color") != "#FF00FF"
        or not isinstance(composition, dict)
        or composition.get("reading_order") != "row_major"
        or not isinstance(sheets, list)
        or not isinstance(geometry_profiles, dict)
        or not geometry_profiles
    ):
        raise UISourcePlanError("source-sheet scheme is malformed")
    direction = _clean_visual_direction(brief)
    common = (
        f"Create reusable {rendering_medium.strip()} game UI source art. "
        f"Match the supplied style reference's palette, shape language, outlines, shadows, and material treatment. "
        f"Visual direction: {direction} "
        "Use a perfectly flat, solid #FF00FF canvas background only. Reserve exact #FF00FF exclusively for the color-key background; do not use it in the artwork. "
        f"Keep every component fully separated by at least {composition['minimum_gap_px']} pixels of visible #FF00FF and away from every canvas edge. "
        "Create isolated reusable UI elements only: no characters, scenes, full screen mockups, readable text, numbers, logos, or branding. "
    )
    planned_sheets = []
    runtime_stylebox_names: list[str] = []
    runtime_icon_names: list[str] = []
    for sheet in sheets:
        if not isinstance(sheet, dict):
            raise UISourcePlanError("source-sheet scheme contains a malformed sheet")
        components, atlas, slots, provider_grid = _sheet_layout(sheet, geometry_profiles)
        for component in components:
            runtime_stylebox_names.extend(
                mapping["output_name"] for mapping in component.get("runtime_styleboxes", [])
            )
            runtime_icon_names.extend(component.get("runtime_names", []))
        labels = [component["label"] for component in components]
        surface_instruction = ""
        if any(component["kind"] == "surface" for component in components):
            used_profiles = []
            for component in components:
                profile_name = component.get("geometry_profile")
                if profile_name and profile_name not in used_profiles:
                    used_profiles.append(profile_name)
            profile_text = "; ".join(
                f"{name}: {geometry_profiles[name]['patch_size'][0]} by {geometry_profiles[name]['patch_size'][1]} square patch, "
                f"border {geometry_profiles[name]['border']}, safe center {geometry_profiles[name]['safe_center']}"
                for name in used_profiles
            )
            surface_instruction = (
                "Render every component as the same-size square surface patch. "
                "Use light neutral tintable fills while preserving the reference material, contour, outline, highlight, and shadow language. "
                "Carry all corners, outlines, highlights, shadows, and ornament inside the declared outer border band. "
                "Keep the declared safe center continuous and free of text, icons, emblems, focal decoration, seams, or directional lighting. "
                f"Geometry profiles: {profile_text}. "
            )
        prompt = (
            common
            + surface_instruction
            + f"Arrange exactly {len(components)} visual components in a {provider_grid['columns']}-column by {provider_grid['rows']}-row layout, "
            "ordered left to right and then top to bottom; leave unused trailing cells empty. "
            "Render each listed component as one isolated reusable element. Do not render component labels. Components in order: "
            + "; ".join(labels)
            + "."
        )
        planned_sheets.append({
            "id": sheet["id"],
            "source_name": sheet["source_name"],
            "components": [component["name"] for component in components],
            "component_specs": components,
            "component_labels": labels,
            "provider_grid": provider_grid,
            "atlas": atlas,
            "slots": slots,
            "prompt": prompt,
        })
    if (
        len(runtime_stylebox_names) != len(set(runtime_stylebox_names))
        or set(runtime_stylebox_names) != set(UI_TEXTURE_STYLEBOXES)
    ):
        raise UISourcePlanError(
            "surface source mappings must cover the complete runtime StyleBox baseline exactly once"
        )
    if len(runtime_icon_names) != len(set(runtime_icon_names)) or set(runtime_icon_names) != set(UI_ICONS):
        raise UISourcePlanError(
            "icon source mappings must cover the complete runtime icon baseline exactly once"
        )
    return {
        "version": 3,
        "asset_type": "ui-kit",
        "asset_id": asset_id,
        "provider": provider,
        "rendering_medium": rendering_medium.strip(),
        "references": references,
        "scheme": {
            "version": scheme.get("version"),
            "background": background,
            "composition": composition,
            "geometry_profiles": geometry_profiles,
        },
        "sheets": planned_sheets,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--scheme", required=True)
    parser.add_argument("--rendering-medium", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        plan = build_source_sheet_plan(_read_json(Path(args.request)), _read_json(Path(args.scheme)), rendering_medium=args.rendering_medium)
    except UISourcePlanError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "path": args.out, "sheet_count": len(plan["sheets"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
