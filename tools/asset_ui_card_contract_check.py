#!/usr/bin/env python3
"""Closed request/result contracts for the standalone UI and card Asset Skills."""
from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from asset_skill_contract_check import (
    AssetContractError,
    RES_PATH_PATTERN,
    check_request,
    check_result,
)


class UICardContractError(Exception):
    """Raised when a UI or card request cannot be bound to its runtime result."""


_FAMILIES = {
    "ui-kit": {"states": {"normal", "hover", "pressed", "disabled", "focus"}},
    "card-kit": {
        "states": {"normal", "hover", "pressed", "disabled", "selected", "locked"}
    },
}

_PIXEL_ART_REQUEST = re.compile(r"\bpixel(?:[-\s]?art)\b", re.IGNORECASE)

def _text(value: Any, label: str, issues: list[str]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        issues.append(f"{label} must be a non-empty string")
        return None
    return value


def _res_path(value: Any, label: str, issues: list[str]) -> str | None:
    path = _text(value, label, issues)
    if path is not None and not RES_PATH_PATTERN.match(path):
        issues.append(f"{label} must be a loadable res:// resource path")
    return path


def _exact_keys(value: Any, keys: set[str], label: str, issues: list[str]) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        issues.append(f"{label} must be an object")
        return None
    actual = set(value)
    if actual != keys:
        missing = sorted(keys - actual)
        extra = sorted(actual - keys)
        message = f"{label} must contain exactly {', '.join(sorted(keys))}"
        if missing:
            message += "; missing " + ", ".join(missing)
        if extra:
            message += "; unexpected " + ", ".join(extra)
        issues.append(message)
    return value


def _names(value: Any, label: str, issues: list[str]) -> list[str]:
    if not isinstance(value, list) or not value:
        issues.append(f"{label} must be a non-empty list")
        return []
    names = [_text(item, f"{label}[{index}]", issues) for index, item in enumerate(value)]
    clean = [item for item in names if item is not None]
    if len(clean) != len(set(clean)):
        issues.append(f"{label} must not contain duplicates")
    return clean


def _theme(value: Any, issues: list[str]) -> dict[str, str] | None:
    item = _exact_keys(value, {"output_name", "recipe_path", "variation"}, "request.spec.theme", issues)
    if item is None:
        return None
    output_name = _text(item.get("output_name"), "request.spec.theme.output_name", issues)
    recipe_path = _res_path(item.get("recipe_path"), "request.spec.theme.recipe_path", issues)
    variation = _text(item.get("variation"), "request.spec.theme.variation", issues)
    if output_name is None or recipe_path is None or variation is None:
        return None
    if not recipe_path.endswith(".json"):
        issues.append("request.spec.theme.recipe_path must end in .json")
    return {"output_name": output_name, "recipe_path": recipe_path, "variation": variation}


def _stylebox(value: Any, family: str, index: int, issues: list[str]) -> dict[str, Any] | None:
    label = f"request.spec.styleboxes[{index}]"
    keys = {
        "output_name", "state", "source_path", "layout", "texture_region", "border",
        "expand_margin", "axis_stretch",
    }
    if family == "card-kit":
        keys.add("frame")
    item = _exact_keys(value, keys, label, issues)
    if item is None:
        return None
    output_name = _text(item.get("output_name"), f"{label}.output_name", issues)
    state = _text(item.get("state"), f"{label}.state", issues)
    source_path = _res_path(item.get("source_path"), f"{label}.source_path", issues)
    layout = item.get("layout")
    if layout not in {"single", "region_atlas"}:
        issues.append(f"{label}.layout must be single or region_atlas")
    frame = None
    if family == "card-kit":
        frame = _text(item.get("frame"), f"{label}.frame", issues)
    if output_name is None or state is None or source_path is None or layout not in {"single", "region_atlas"}:
        return None
    result = {
        "output_name": output_name,
        "state": state,
        "source_path": source_path,
        "layout": layout,
        "compiler_spec": {
            "texture_region": item.get("texture_region"),
            "border": item.get("border"),
            "expand_margin": item.get("expand_margin"),
            "axis_stretch": item.get("axis_stretch"),
        },
    }
    if frame is not None:
        result["frame"] = frame
    return result


def _atlas_region(value: Any, index: int, issues: list[str]) -> dict[str, str] | None:
    label = f"request.spec.atlas_regions[{index}]"
    item = _exact_keys(
        value, {"output_name", "source_path", "metadata_path", "logical_asset_id"}, label, issues
    )
    if item is None:
        return None
    output_name = _text(item.get("output_name"), f"{label}.output_name", issues)
    source_path = _res_path(item.get("source_path"), f"{label}.source_path", issues)
    metadata_path = _res_path(item.get("metadata_path"), f"{label}.metadata_path", issues)
    logical_asset_id = _text(item.get("logical_asset_id"), f"{label}.logical_asset_id", issues)
    if output_name is None or source_path is None or metadata_path is None or logical_asset_id is None:
        return None
    if not metadata_path.endswith(".json"):
        issues.append(f"{label}.metadata_path must end in .json")
    if output_name != logical_asset_id:
        issues.append(f"{label}.output_name must match logical_asset_id")
    return {
        "output_name": output_name,
        "source_path": source_path,
        "metadata_path": metadata_path,
        "logical_asset_id": logical_asset_id,
    }


def _spec(request: Mapping[str, Any], issues: list[str]) -> dict[str, Any] | None:
    family = request["asset_type"]
    keys = {"theme", "required_states", "styleboxes", "required_regions", "atlas_regions"}
    if family == "card-kit":
        keys.add("required_frames")
    spec = _exact_keys(request.get("spec"), keys, "request.spec", issues)
    if spec is None:
        return None
    theme = _theme(spec.get("theme"), issues)
    states = _names(spec.get("required_states"), "request.spec.required_states", issues)
    allowed_states = _FAMILIES[family]["states"]
    unknown_states = sorted(set(states) - allowed_states)
    if unknown_states:
        issues.append(f"request.spec.required_states has unsupported {family} states: " + ", ".join(unknown_states))
    raw_boxes = spec.get("styleboxes")
    if not isinstance(raw_boxes, list) or not raw_boxes:
        issues.append("request.spec.styleboxes must be a non-empty list")
        boxes: list[dict[str, Any]] = []
    else:
        boxes = [item for index, raw in enumerate(raw_boxes) if (item := _stylebox(raw, family, index, issues)) is not None]
    regions = _names(spec.get("required_regions"), "request.spec.required_regions", issues)
    raw_regions = spec.get("atlas_regions")
    if not isinstance(raw_regions, list) or not raw_regions:
        issues.append("request.spec.atlas_regions must be a non-empty list")
        atlas_regions: list[dict[str, str]] = []
    else:
        atlas_regions = [item for index, raw in enumerate(raw_regions) if (item := _atlas_region(raw, index, issues)) is not None]
    frames: list[str] = []
    if family == "card-kit":
        frames = _names(spec.get("required_frames"), "request.spec.required_frames", issues)

    output_names = [item["output_name"] for item in boxes] + [item["output_name"] for item in atlas_regions]
    if theme is not None:
        output_names.append(theme["output_name"])
    if len(output_names) != len(set(output_names)):
        issues.append("request.spec output_name values must be unique")

    actual_states = [item["state"] for item in boxes]
    if family == "ui-kit":
        if set(actual_states) != set(states) or len(actual_states) != len(states):
            issues.append("ui-kit styleboxes must declare exactly one entry for every required_state")
    else:
        actual_frames = [item.get("frame") for item in boxes]
        pairs = [(item.get("frame"), item["state"]) for item in boxes]
        expected_pairs = {(frame, state) for frame in frames for state in states}
        if set(pairs) != expected_pairs or len(pairs) != len(expected_pairs):
            issues.append("card-kit styleboxes must declare every required_frame and required_state pair exactly once")
        if set(actual_frames) != set(frames):
            issues.append("card-kit styleboxes must match required_frames")
    actual_regions = [item["output_name"] for item in atlas_regions]
    if set(actual_regions) != set(regions) or len(actual_regions) != len(regions):
        issues.append("atlas_regions must declare exactly one entry for every required_region")
    return {"theme": theme, "styleboxes": boxes, "atlas_regions": atlas_regions}


def check_ui_card_request(data: Any) -> dict[str, Any]:
    """Validate the closed, family-owned request spec."""
    try:
        shared = check_request(data)
    except AssetContractError as exc:
        raise UICardContractError(str(exc)) from exc
    if data["asset_type"] not in _FAMILIES:
        raise UICardContractError("asset_type is not ui-kit or card-kit")
    if data["asset_type"] == "card-kit" and _PIXEL_ART_REQUEST.search(data["brief"]):
        raise UICardContractError("card-kit does not support pixel-art requests")
    issues: list[str] = []
    normalized = _spec(data, issues)
    if issues:
        raise UICardContractError("; ".join(issues))
    return {"ok": True, "kind": "request", "asset_type": data["asset_type"], "spec": normalized, "shared": shared}


def check_ui_card_result(data: Any) -> dict[str, Any]:
    try:
        shared = check_result(data)
    except AssetContractError as exc:
        raise UICardContractError(str(exc)) from exc
    if data["asset_type"] not in _FAMILIES:
        raise UICardContractError("asset_type is not ui-kit or card-kit")
    return {"ok": True, "kind": "result", "asset_type": data["asset_type"], "shared": shared}


def _source_paths(result: Mapping[str, Any]) -> set[tuple[str, str | None]]:
    return {(source["path"], source.get("layout")) for source in result["sources"]}


def _runtime_by_name(result: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    runtime = [output for output in result["outputs"] if output["role"] == "runtime"]
    names = [output.get("name") for output in runtime]
    if any(not isinstance(name, str) or not name for name in names) or len(names) != len(set(names)):
        raise UICardContractError("every runtime output must have a unique non-empty name")
    return {output["name"]: output for output in runtime}


def check_ui_card_handoff(request: Any, result: Any) -> dict[str, Any]:
    """Bind every declared family item to a source and one native output."""
    request_check = check_ui_card_request(request)
    result_check = check_ui_card_result(result)
    if request["asset_type"] != result["asset_type"]:
        raise UICardContractError("request.asset_type must match result.asset_type")
    spec = request_check["spec"]
    assert spec is not None
    runtime = _runtime_by_name(result)
    sources = _source_paths(result)
    expected_names = {spec["theme"]["output_name"]}

    theme = spec["theme"]
    theme_output = runtime.get(theme["output_name"])
    expected_theme_path = (
        f"res://assets/generated/{request['asset_type']}/{request['asset_id']}/"
        f"{request['asset_id']}_theme.tres"
    )
    if (
        theme_output is None
        or theme_output.get("godot_type") != "Theme"
        or theme_output.get("path") != expected_theme_path
    ):
        raise UICardContractError("theme.output_name must bind to one Theme runtime output")
    if (theme["recipe_path"], "theme_recipe") not in sources:
        raise UICardContractError("theme.recipe_path must be a theme_recipe result source")

    for box in spec["styleboxes"]:
        expected_names.add(box["output_name"])
        output = runtime.get(box["output_name"])
        if output is None or output.get("godot_type") != "StyleBoxTexture":
            raise UICardContractError(f"stylebox {box['output_name']!r} must bind to StyleBoxTexture")
        if (box["source_path"], box["layout"]) not in sources:
            raise UICardContractError(f"stylebox {box['output_name']!r} source is missing from result")

    for region in spec["atlas_regions"]:
        expected_names.add(region["output_name"])
        output = runtime.get(region["output_name"])
        if output is None or output.get("godot_type") != "AtlasTexture":
            raise UICardContractError(f"atlas region {region['output_name']!r} must bind to AtlasTexture")
        if (region["source_path"], "region_atlas") not in sources:
            raise UICardContractError(f"atlas region {region['output_name']!r} source is missing from result")
    if set(runtime) != expected_names:
        raise UICardContractError("result must contain no undeclared or unvalidated runtime outputs")
    return {"ok": True, "kind": "handoff", "asset_type": request["asset_type"], "request": request_check, "result": result_check}


def _main() -> int:
    parser = argparse.ArgumentParser(description="Validate UI/card Asset Skill family contracts")
    parser.add_argument("document", nargs="?", type=Path)
    parser.add_argument("--kind", choices=["request", "result"])
    parser.add_argument("--request", type=Path)
    parser.add_argument("--result", type=Path)
    args = parser.parse_args()
    try:
        if args.request or args.result:
            if args.document or not args.request or not args.result:
                raise UICardContractError("handoff validation needs --request and --result with no document")
            checked = check_ui_card_handoff(
                json.loads(args.request.read_text(encoding="utf-8")),
                json.loads(args.result.read_text(encoding="utf-8")),
            )
        elif args.document and args.kind:
            document = json.loads(args.document.read_text(encoding="utf-8"))
            checked = check_ui_card_request(document) if args.kind == "request" else check_ui_card_result(document)
        else:
            raise UICardContractError("document with --kind is required without --request and --result")
    except (UICardContractError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(checked))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
