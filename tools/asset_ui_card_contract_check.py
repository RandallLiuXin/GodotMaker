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
from asset_output_paths import AssetOutputPathError, generated_output_dir, safe_identifier
from asset_ui_theme_recipe import UI_ICONS, UI_STYLEBOXES


class UICardContractError(Exception):
    """Raised when a UI or card request cannot be bound to its runtime result."""


_FAMILIES = {
    "ui-kit": {"states": {"normal", "hover", "pressed", "disabled", "focus"}},
    "card-kit": {
        "states": {"normal", "hover", "pressed", "disabled", "selected", "locked"}
    },
}
_UI_PROVIDERS = {"native", "codex", "gemini", "openai", "wan"}
_UI_REQUIRED_STATES = {"normal", "hover", "pressed", "disabled", "focus"}

_PIXEL_ART_REQUEST = re.compile(r"\bpixel(?:[-\s]?art)\b", re.IGNORECASE)
_PIXEL_ART_NEGATION = re.compile(r"\b(?:not|non)(?:[-\s]+[a-z]+){0,2}[-\s]*$", re.IGNORECASE)
_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?$")

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
    _safe_output_name(output_name, "request.spec.theme.output_name", issues)
    if not recipe_path.endswith(".json"):
        issues.append("request.spec.theme.recipe_path must end in .json")
    return {"output_name": output_name, "recipe_path": recipe_path, "variation": variation}


def _requests_pixel_art(brief: str) -> bool:
    """Recognize a pixel-art request without rejecting an explicit negation."""
    for match in _PIXEL_ART_REQUEST.finditer(brief):
        context = brief[max(0, match.start() - 32):match.start()]
        if not _PIXEL_ART_NEGATION.search(context):
            return True
    return False


def _stylebox(value: Any, family: str, index: int, issues: list[str]) -> dict[str, Any] | None:
    label = f"request.spec.styleboxes[{index}]"
    keys = {
        "output_name", "state", "source_path", "layout", "texture_region", "border",
        "content_margin", "expand_margin", "axis_stretch",
    }
    if family == "card-kit":
        keys.add("frame")
    else:
        keys.update({"source_component", "geometry_profile", "safe_center", "modulate_color", "preview_sizes"})
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
    preview_sizes: list[list[int]] = []
    source_component = None
    geometry_profile = None
    safe_center: list[int] = []
    modulate_color = None
    if family == "ui-kit":
        source_component = _text(item.get("source_component"), f"{label}.source_component", issues)
        geometry_profile = _text(item.get("geometry_profile"), f"{label}.geometry_profile", issues)
        raw_safe_center = item.get("safe_center")
        if (
            not isinstance(raw_safe_center, list)
            or len(raw_safe_center) != 4
            or any(type(part) is not int or part < 0 for part in raw_safe_center)
        ):
            issues.append(f"{label}.safe_center must be four non-negative integers")
        else:
            safe_center = list(raw_safe_center)
        modulate_color = _text(item.get("modulate_color"), f"{label}.modulate_color", issues)
        if modulate_color is not None and not _COLOR.fullmatch(modulate_color):
            issues.append(f"{label}.modulate_color must be #RRGGBB or #RRGGBBAA")
        raw_sizes = item.get("preview_sizes")
        if not isinstance(raw_sizes, list) or len(raw_sizes) < 2:
            issues.append(f"{label}.preview_sizes must contain at least two [width, height] entries")
        else:
            for size_index, raw_size in enumerate(raw_sizes):
                if (
                    not isinstance(raw_size, list)
                    or len(raw_size) != 2
                    or any(type(part) is not int or part <= 0 for part in raw_size)
                ):
                    issues.append(f"{label}.preview_sizes[{size_index}] must be positive [width, height]")
                else:
                    preview_sizes.append(list(raw_size))
    if output_name is None or state is None or source_path is None or layout not in {"single", "region_atlas"}:
        return None
    _safe_output_name(output_name, f"{label}.output_name", issues)
    result = {
        "output_name": output_name,
        "state": state,
        "source_path": source_path,
        "layout": layout,
        "compiler_spec": {
            "texture_region": item.get("texture_region"),
            "border": item.get("border"),
            "content_margin": item.get("content_margin"),
            "expand_margin": item.get("expand_margin"),
            "axis_stretch": item.get("axis_stretch"),
        },
    }
    if family == "ui-kit":
        result.update({
            "source_component": source_component,
            "geometry_profile": geometry_profile,
            "safe_center": safe_center,
            "modulate_color": modulate_color,
            "preview_sizes": preview_sizes,
        })
        result["compiler_spec"]["modulate_color"] = modulate_color
    if frame is not None:
        result["frame"] = frame
    return result


def _atlas_region(value: Any, family: str, index: int, issues: list[str]) -> dict[str, str] | None:
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
    _safe_output_name(output_name, f"{label}.output_name", issues)
    if not metadata_path.endswith(".json"):
        issues.append(f"{label}.metadata_path must end in .json")
    if family == "card-kit" and output_name != logical_asset_id:
        issues.append(f"{label}.output_name must match logical_asset_id")
    return {
        "output_name": output_name,
        "source_path": source_path,
        "metadata_path": metadata_path,
        "logical_asset_id": logical_asset_id,
    }


def _safe_output_name(value: str, label: str, issues: list[str]) -> None:
    try:
        safe_identifier(value, label)
    except AssetOutputPathError as exc:
        issues.append(str(exc))


def _spec(request: Mapping[str, Any], issues: list[str]) -> dict[str, Any] | None:
    family = request["asset_type"]
    keys = {"required_states", "styleboxes", "required_regions", "atlas_regions"}
    if family == "card-kit":
        keys.add("required_frames")
    else:
        keys.update({"theme", "stylebox_plan_path"})
    spec = request.get("spec")
    if not isinstance(spec, Mapping):
        issues.append("request.spec must be an object")
        return None
    actual = set(spec)
    allowed_shapes = (keys, keys | {"theme"}) if family == "card-kit" else (keys,)
    allowed_keys = keys | ({"theme"} if family == "card-kit" else set())
    if actual not in allowed_shapes:
        missing = sorted(keys - actual)
        extra = sorted(actual - allowed_keys)
        message = "request.spec must contain the required family fields"
        if family == "card-kit":
            message += " and may contain theme"
        if missing:
            message += "; missing " + ", ".join(missing)
        if extra:
            message += "; unexpected " + ", ".join(extra)
        issues.append(message)
    theme = _theme(spec["theme"], issues) if "theme" in spec else None
    stylebox_plan_path = None
    if family == "ui-kit":
        stylebox_plan_path = _res_path(
            spec.get("stylebox_plan_path"), "request.spec.stylebox_plan_path", issues
        )
        if stylebox_plan_path is not None and not stylebox_plan_path.endswith(".json"):
            issues.append("request.spec.stylebox_plan_path must end in .json")
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
        atlas_regions = [
            item
            for index, raw in enumerate(raw_regions)
            if (item := _atlas_region(raw, family, index, issues)) is not None
        ]
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
        image_states = set(states) - {"focus"}
        if not image_states.issubset(actual_states):
            issues.append("ui-kit texture styleboxes must declare every non-focus required_state")
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
    if family == "ui-kit":
        if set(states) != _UI_REQUIRED_STATES or len(states) != len(_UI_REQUIRED_STATES):
            issues.append("ui-kit required_states must declare normal, hover, pressed, disabled, and focus")
        actual_styleboxes = [item["output_name"] for item in boxes]
        if set(actual_styleboxes) != set(UI_STYLEBOXES) or len(actual_styleboxes) != len(UI_STYLEBOXES):
            issues.append("ui-kit styleboxes must declare the complete named Theme baseline exactly once")
        if set(actual_regions) != set(UI_ICONS) or len(actual_regions) != len(UI_ICONS):
            issues.append("ui-kit atlas_regions must declare the complete named icon baseline exactly once")
        if not {item["source_path"] for item in boxes} or not {item["source_path"] for item in atlas_regions}:
            issues.append("ui-kit must retain separate component and icon source sheets")
    return {
        "theme": theme,
        "stylebox_plan_path": stylebox_plan_path,
        "styleboxes": boxes,
        "atlas_regions": atlas_regions,
    }


def _ui_input_gate(request: Mapping[str, Any], issues: list[str]) -> None:
    """Require the binding inputs that make a UI Theme visually coherent."""
    references = request.get("references")
    if not isinstance(references, list) or not references:
        issues.append("ui-kit requires at least one binding image reference")
    provider = request.get("provider")
    if provider not in _UI_PROVIDERS:
        issues.append("ui-kit provider must be one of native, codex, gemini, openai, wan")


def validate_ui_reference_inputs(request: Mapping[str, Any], project_root: Path) -> None:
    """Fail closed before generation when a required UI reference is unreadable."""
    if request.get("asset_type") != "ui-kit":
        return
    references = request.get("references")
    if not isinstance(references, list) or not references:
        raise UICardContractError("ui-kit requires at least one binding image reference")
    for index, reference in enumerate(references):
        if not isinstance(reference, Mapping) or reference.get("role") not in {"canonical", "style", "screen"}:
            raise UICardContractError(f"ui-kit reference[{index}] must preserve a supported role")
        raw_path = reference.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise UICardContractError(f"ui-kit reference[{index}].path must be a non-empty image path")
        target = Path(raw_path)
        if not target.is_absolute():
            target = Path(project_root) / target
        try:
            from PIL import Image
            with Image.open(target) as image:
                image.verify()
        except (ImportError, OSError, ValueError) as exc:
            raise UICardContractError(f"ui-kit reference[{index}] is not a readable image: {raw_path}: {exc}") from exc


def check_ui_card_request(data: Any) -> dict[str, Any]:
    """Validate the closed, family-owned request spec."""
    try:
        shared = check_request(data)
    except AssetContractError as exc:
        raise UICardContractError(str(exc)) from exc
    if data["asset_type"] not in _FAMILIES:
        raise UICardContractError("asset_type is not ui-kit or card-kit")
    if data["asset_type"] == "card-kit" and _requests_pixel_art(data["brief"]):
        raise UICardContractError("card-kit does not support pixel-art requests")
    issues: list[str] = []
    if data["asset_type"] == "ui-kit":
        _ui_input_gate(data, issues)
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


def expected_runtime_path(
    asset_type: str, asset_id: str, output_name: str, godot_type: str
) -> str:
    """Return the one stable path a declared kit output may be published at.

    One production delivers many separately bindable resources into one
    directory, so "somewhere under the kit directory" is not a binding: two
    outputs could land on the same file and a worker would load a
    StyleBoxTexture as an AtlasTexture. Deriving the filename from the output
    name removes that freedom. The Theme keeps its kit-derived name, which this
    family has always pinned.

    The derivation is not injective on its own: a stylebox literally named
    ``<asset_id>_theme`` derives the Theme's path. Each output still matches
    its expected value here; direct registration rejects duplicate output paths.
    """
    stem = f"{asset_id}_theme" if godot_type == "Theme" else output_name
    return f"res://{generated_output_dir(asset_type, asset_id)}/{stem}.tres"


def _assert_runtime_path(
    output: Mapping[str, Any], request: Mapping[str, Any], *, label: str
) -> None:
    expected = expected_runtime_path(
        request["asset_type"],
        request["asset_id"],
        output["name"],
        output["godot_type"],
    )
    if output.get("path") != expected:
        raise UICardContractError(
            f"{label} must be published at {expected}, not {output.get('path')!r}"
        )


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
    theme = spec["theme"]
    expected_names: set[str] = set()
    if theme is not None:
        expected_names.add(theme["output_name"])
        theme_output = runtime.get(theme["output_name"])
        expected_theme_path = expected_runtime_path(
            request["asset_type"], request["asset_id"], theme["output_name"], "Theme"
        )
        if (
            theme_output is None
            or theme_output.get("godot_type") != "Theme"
            or theme_output.get("path") != expected_theme_path
        ):
            raise UICardContractError("theme.output_name must bind to one Theme runtime output")
        if (theme["recipe_path"], "theme_recipe") not in sources:
            raise UICardContractError("theme.recipe_path must be a theme_recipe result source")
    if request["asset_type"] == "ui-kit" and (spec["stylebox_plan_path"], None) not in sources:
        raise UICardContractError("stylebox_plan_path must be a result source")

    for box in spec["styleboxes"]:
        expected_names.add(box["output_name"])
        output = runtime.get(box["output_name"])
        if output is None or output.get("godot_type") != "StyleBoxTexture":
            raise UICardContractError(f"stylebox {box['output_name']!r} must bind to StyleBoxTexture")
        _assert_runtime_path(
            output, request, label=f"stylebox {box['output_name']!r}"
        )
        if (box["source_path"], box["layout"]) not in sources:
            raise UICardContractError(f"stylebox {box['output_name']!r} source is missing from result")

    for region in spec["atlas_regions"]:
        expected_names.add(region["output_name"])
        output = runtime.get(region["output_name"])
        if output is None or output.get("godot_type") != "AtlasTexture":
            raise UICardContractError(f"atlas region {region['output_name']!r} must bind to AtlasTexture")
        _assert_runtime_path(
            output, request, label=f"atlas region {region['output_name']!r}"
        )
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
