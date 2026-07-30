#!/usr/bin/env python3
"""Create auditable, color-keyed ui-kit image-provider source-sheet prompts."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


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


def _sheet_layout(sheet: dict[str, Any]) -> tuple[list[dict[str, str]], dict[str, Any], list[dict[str, Any]]]:
    sheet_id = sheet.get("id")
    source_name = sheet.get("source_name")
    components = sheet.get("components")
    atlas = sheet.get("atlas")
    if not isinstance(sheet_id, str) or not SAFE_NAME.fullmatch(sheet_id):
        raise UISourcePlanError("source-sheet scheme contains an invalid sheet id")
    if not isinstance(source_name, str) or not source_name.endswith(".png"):
        raise UISourcePlanError(f"source-sheet scheme {sheet_id} has an invalid source_name")
    if not isinstance(components, list) or not components:
        raise UISourcePlanError(f"source-sheet scheme {sheet_id} has no components")
    if not isinstance(atlas, dict):
        raise UISourcePlanError(f"source-sheet scheme {sheet_id} has no atlas layout")

    columns = _positive_int(atlas.get("columns"), f"{sheet_id}.atlas.columns")
    rows = _positive_int(atlas.get("rows"), f"{sheet_id}.atlas.rows")
    gutter = _positive_int(atlas.get("gutter"), f"{sheet_id}.atlas.gutter")
    cell_size = atlas.get("cell_size")
    if not isinstance(cell_size, list) or len(cell_size) != 2:
        raise UISourcePlanError(f"{sheet_id}.atlas.cell_size must be [width, height]")
    cell_width = _positive_int(cell_size[0], f"{sheet_id}.atlas.cell_size[0]")
    cell_height = _positive_int(cell_size[1], f"{sheet_id}.atlas.cell_size[1]")
    if len(components) > columns * rows:
        raise UISourcePlanError(f"{sheet_id} components exceed atlas grid capacity")

    parsed_components: list[dict[str, str]] = []
    slots: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for index, component in enumerate(components):
        if not isinstance(component, dict):
            raise UISourcePlanError(f"{sheet_id}.components[{index}] must be an object")
        name = component.get("name")
        label = component.get("label")
        if not isinstance(name, str) or not SAFE_NAME.fullmatch(name):
            raise UISourcePlanError(f"{sheet_id}.components[{index}].name is invalid")
        if name in seen_names:
            raise UISourcePlanError(f"{sheet_id} component name is duplicated: {name}")
        if not isinstance(label, str) or not label.strip():
            raise UISourcePlanError(f"{sheet_id}.components[{index}].label is invalid")
        seen_names.add(name)
        parsed_components.append({"name": name, "label": label.strip()})
        row, column = divmod(index, columns)
        slots.append({
            "index": index,
            "name": name,
            "label": label.strip(),
            "target_size": [cell_width, cell_height],
            "rect": [
                gutter + column * (cell_width + gutter),
                gutter + row * (cell_height + gutter),
                cell_width,
                cell_height,
            ],
        })

    atlas_plan = {
        "source_name": f"{sheet_id}_atlas.png",
        "metadata_name": f"{sheet_id}_atlas.json",
        "columns": columns,
        "rows": rows,
        "cell_size": [cell_width, cell_height],
        "gutter": gutter,
        "width": columns * cell_width + (columns + 1) * gutter,
        "height": rows * cell_height + (rows + 1) * gutter,
    }
    return parsed_components, atlas_plan, slots


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
    if (
        not isinstance(background, dict)
        or background.get("color") != "#FF00FF"
        or not isinstance(composition, dict)
        or composition.get("reading_order") != "row_major"
        or not isinstance(sheets, list)
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
    for sheet in sheets:
        if not isinstance(sheet, dict):
            raise UISourcePlanError("source-sheet scheme contains a malformed sheet")
        components, atlas, slots = _sheet_layout(sheet)
        labels = [component["label"] for component in components]
        prompt = (
            common
            + f"Arrange exactly {len(components)} visual components in a {atlas['columns']}-column by {atlas['rows']}-row layout, "
            "ordered left to right and then top to bottom; leave unused trailing cells empty. "
            "Render each listed component as one isolated reusable element. Do not render component labels. Components in order: "
            + "; ".join(labels)
            + "."
        )
        planned_sheets.append({
            "id": sheet["id"],
            "source_name": sheet["source_name"],
            "components": [component["name"] for component in components],
            "component_labels": labels,
            "atlas": atlas,
            "slots": slots,
            "prompt": prompt,
        })
    return {
        "version": 1,
        "asset_type": "ui-kit",
        "asset_id": asset_id,
        "provider": provider,
        "rendering_medium": rendering_medium.strip(),
        "references": references,
        "scheme": {
            "version": scheme.get("version"),
            "background": background,
            "composition": composition,
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
