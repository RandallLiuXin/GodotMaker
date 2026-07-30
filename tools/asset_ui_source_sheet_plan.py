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
    if not isinstance(background, dict) or background.get("color") != "#FF00FF" or not isinstance(composition, dict) or not isinstance(sheets, list):
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
        if not isinstance(sheet, dict) or not isinstance(sheet.get("components"), list):
            raise UISourcePlanError("source-sheet scheme contains a malformed sheet")
        components = [str(item) for item in sheet["components"]]
        prompt = common + "Arrange exactly these visual components in the stated reading order, with no rendered labels: " + "; ".join(components) + "."
        planned_sheets.append({
            "id": sheet["id"], "source_name": sheet["source_name"], "components": components,
            "prompt": prompt,
        })
    return {
        "version": 1,
        "asset_type": "ui-kit",
        "asset_id": asset_id,
        "provider": provider,
        "rendering_medium": rendering_medium.strip(),
        "references": references,
        "scheme": {"version": scheme.get("version"), "background": background, "composition": composition},
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
