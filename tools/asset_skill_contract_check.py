#!/usr/bin/env python3
"""Validate the standalone asset-skill request and result contract.

This is a dependency-free implementation of the rules declared in
`skills/assets/_shared/schema/asset-skill-request.schema.json` and
`skills/assets/_shared/schema/asset-skill-result.schema.json`, so schema/L0
validation can run at runtime inside a game project without a `jsonschema`
dependency. A parity test keeps this checker in sync with those schemas.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from asset_family_registry import FAMILY_NAMES
from asset_stable_entry import StableEntryError, safe_identifier

# The public families a request or result may name are exactly the first-class
# Asset Skills the family registry declares.
ASSET_TYPES = set(FAMILY_NAMES)

REFERENCE_ROLES = {"canonical", "style", "screen"}
PROVIDERS = {"native", "codex", "gemini", "openai"}
OUTPUT_ROLES = {"runtime", "reference"}
SOURCE_LAYOUTS = {
    "single",
    "grid_sheet",
    "region_atlas",
    "action_frames",
    "theme_recipe",
    "tile_atlas",
}
VALIDATION_LEVELS = {"L0", "L1", "L2", "L3", "L4", "L5"}

ASSET_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
GODOT_TYPE_PATTERN = re.compile(r"^[A-Z][A-Za-z0-9]+$")
# A loadable res:// resource path: the scheme, then one or more "/"-separated
# path segments of non-whitespace, non-slash characters. No segment may be "."
# or ".." (a lone dot resolves to a directory, and ".." escapes the project
# root), and there are no empty segments. Rejects bare "res://", "res:///",
# "res://.", "res://..", and "res://../outside.tres".
_RES_SEGMENT = r"(?!\.\.?(?:/|$))[^/\s]+"
RES_PATH_PATTERN = re.compile(rf"^res://{_RES_SEGMENT}(?:/{_RES_SEGMENT})*$")

# Pipeline / registration concepts that must never leak into a skill-neutral
# request or result. Reported with a targeted message; any other unknown key is
# still rejected by the generic additional-key check.
FORBIDDEN_REQUEST_KEYS = {
    "tag",
    "stage",
    "stage_state",
    "gm_mode",
    "manifest_entry",
    "asset_generation",
}
FORBIDDEN_RESULT_KEYS = {
    "tag",
    "stage",
    "stage_state",
    "gm_mode",
    "manifest_entry",
    "runtime_artifact",
    "source_layout",
    "godot_artifact",
    "processing_status",
    "extraction_status",
}


class AssetContractError(Exception):
    """Raised when an asset-skill request or result is invalid."""


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _check_extra_keys(
    obj: dict[str, Any],
    allowed: set[str],
    *,
    location: str,
    forbidden: set[str],
    issues: list[str],
) -> None:
    for key in obj:
        if key in allowed:
            continue
        if key in forbidden:
            issues.append(
                f"{location}.{key} is a pipeline/registration field and is not "
                "allowed in the skill-neutral contract"
            )
        else:
            issues.append(f"{location} has unknown field: {key}")


def _check_asset_type(value: Any, *, location: str, issues: list[str]) -> None:
    if not _non_empty_string(value):
        issues.append(f"{location} must be a non-empty string")
    elif value not in ASSET_TYPES:
        issues.append(f"{location} is not an allowed production family: {value}")


def _check_scene_prop_set_spec(value: Any, *, issues: list[str]) -> None:
    """Mirror the declared scene-prop-set request schema at generic L0."""
    if not isinstance(value, dict):
        issues.append("request.spec must be a scene-prop-set fixed-slot object")
        return
    _check_extra_keys(
        value,
        {"version", "atlas", "slots"},
        location="request.spec",
        forbidden=set(),
        issues=issues,
    )
    if type(value.get("version")) is not int or value.get("version") != 1:
        issues.append("request.spec.version must be integer 1")

    atlas = value.get("atlas")
    if not isinstance(atlas, dict):
        issues.append("request.spec.atlas must be an object")
    else:
        _check_extra_keys(
            atlas,
            {"width", "height"},
            location="request.spec.atlas",
            forbidden=set(),
            issues=issues,
        )
        for axis in ("width", "height"):
            if type(atlas.get(axis)) is not int or atlas.get(axis) <= 0:
                issues.append(f"request.spec.atlas.{axis} must be a positive integer")

    slots = value.get("slots")
    if not isinstance(slots, list) or not slots:
        issues.append("request.spec.slots must be a non-empty list")
        return
    for index, slot in enumerate(slots):
        location = f"request.spec.slots[{index}]"
        if not isinstance(slot, dict):
            issues.append(f"{location} must be an object")
            continue
        _check_extra_keys(
            slot,
            {"name", "rect", "source", "pivot"},
            location=location,
            forbidden=set(),
            issues=issues,
        )
        name = slot.get("name")
        if not _non_empty_string(name):
            issues.append(f"{location}.name must be a non-empty string")
        else:
            try:
                safe_identifier(name, f"{location}.name")
            except StableEntryError as exc:
                issues.append(str(exc))
        if not _non_empty_string(slot.get("source")):
            issues.append(f"{location}.source must be a non-empty string")
        rect = slot.get("rect")
        if (
            not isinstance(rect, list)
            or len(rect) != 4
            or any(type(component) is not int for component in rect)
            or (isinstance(rect, list) and len(rect) == 4 and (rect[0] < 0 or rect[1] < 0 or rect[2] <= 0 or rect[3] <= 0))
        ):
            issues.append(f"{location}.rect must be [x, y, width, height] with non-negative origin and positive size")
        if "pivot" in slot:
            pivot = slot["pivot"]
            if (
                not isinstance(pivot, list)
                or len(pivot) != 2
                or any(type(component) not in {int, float} or not 0 <= component <= 1 for component in pivot)
            ):
                issues.append(f"{location}.pivot must contain two numbers from 0 to 1")


def check_request(data: Any) -> dict[str, Any]:
    """Validate an asset-skill request. Raise AssetContractError if invalid."""
    issues: list[str] = []
    if not isinstance(data, dict):
        raise AssetContractError("request must be a JSON object")

    allowed = {"asset_type", "asset_id", "brief", "references", "provider", "spec"}
    _check_extra_keys(
        data, allowed, location="request", forbidden=FORBIDDEN_REQUEST_KEYS, issues=issues
    )

    _check_asset_type(data.get("asset_type"), location="request.asset_type", issues=issues)

    asset_id = data.get("asset_id")
    if not _non_empty_string(asset_id):
        issues.append("request.asset_id must be a non-empty string")
    elif not ASSET_ID_PATTERN.match(asset_id):
        issues.append(f"request.asset_id must match {ASSET_ID_PATTERN.pattern}: {asset_id}")

    if not _non_empty_string(data.get("brief")):
        issues.append("request.brief must be a non-empty string")

    # Optional fields are keyed on presence, not on a non-None value: an explicit
    # null is a wrong-typed value the schema rejects, not an omission.
    if "references" in data:
        references = data["references"]
        if not isinstance(references, list):
            issues.append("request.references must be a list")
        else:
            for index, ref in enumerate(references):
                loc = f"request.references[{index}]"
                if not isinstance(ref, dict):
                    issues.append(f"{loc} must be an object")
                    continue
                _check_extra_keys(
                    ref, {"role", "path"}, location=loc, forbidden=set(), issues=issues
                )
                role = ref.get("role")
                if not isinstance(role, str) or role not in REFERENCE_ROLES:
                    issues.append(f"{loc}.role is not allowed: {role!r}")
                if not _non_empty_string(ref.get("path")):
                    issues.append(f"{loc}.path must be a non-empty string")

    if "provider" in data and (
        not isinstance(data["provider"], str) or data["provider"] not in PROVIDERS
    ):
        issues.append(f"request.provider is not allowed: {data['provider']!r}")

    if "spec" in data and not isinstance(data["spec"], dict):
        issues.append("request.spec must be an object")
    if data.get("asset_type") == "scene-prop-set":
        if "spec" not in data:
            issues.append("request.spec is required for scene-prop-set")
        else:
            _check_scene_prop_set_spec(data["spec"], issues=issues)

    if issues:
        raise AssetContractError("; ".join(issues))

    return {"ok": True, "kind": "request", "asset_type": data.get("asset_type")}


def _check_output(output: Any, *, index: int, issues: list[str]) -> bool:
    loc = f"result.outputs[{index}]"
    if not isinstance(output, dict):
        issues.append(f"{loc} must be an object")
        return False

    _check_extra_keys(
        output,
        {"role", "path", "godot_type", "name"},
        location=loc,
        forbidden=FORBIDDEN_RESULT_KEYS,
        issues=issues,
    )

    role = output.get("role")
    if not isinstance(role, str) or role not in OUTPUT_ROLES:
        issues.append(f"{loc}.role is not allowed: {role!r}")

    path = output.get("path")
    if not _non_empty_string(path):
        issues.append(f"{loc}.path must be a non-empty string")
    elif role == "runtime" and not RES_PATH_PATTERN.match(path):
        issues.append(
            f"{loc}.path must be a loadable res:// resource path "
            "(res:// followed by a relative resource path) for a runtime output"
        )

    if role == "runtime" or "godot_type" in output:
        godot_type = output.get("godot_type")
        if role == "runtime" and "godot_type" not in output:
            issues.append(f"{loc}.godot_type is required for a runtime output")
        elif not _non_empty_string(godot_type) or not GODOT_TYPE_PATTERN.match(godot_type):
            issues.append(
                f"{loc}.godot_type must be a Godot ClassDB type name "
                f"({GODOT_TYPE_PATTERN.pattern}): {godot_type}"
            )

    if "name" in output and not _non_empty_string(output["name"]):
        issues.append(f"{loc}.name must be a non-empty string")

    return role == "runtime"


def _check_file_list(
    items: Any,
    *,
    field: str,
    allowed: set[str],
    issues: list[str],
) -> None:
    if not isinstance(items, list):
        issues.append(f"result.{field} must be a list")
        return
    for index, item in enumerate(items):
        loc = f"result.{field}[{index}]"
        if not isinstance(item, dict):
            issues.append(f"{loc} must be an object")
            continue
        _check_extra_keys(
            item, allowed, location=loc, forbidden=FORBIDDEN_RESULT_KEYS, issues=issues
        )
        if not _non_empty_string(item.get("path")):
            issues.append(f"{loc}.path must be a non-empty string")


def _check_validation(validation: Any, *, issues: list[str]) -> None:
    if not isinstance(validation, dict):
        issues.append("result.validation must be an object")
        return

    _check_extra_keys(
        validation,
        {"passed", "levels", "notes"},
        location="result.validation",
        forbidden=FORBIDDEN_RESULT_KEYS,
        issues=issues,
    )

    passed = validation.get("passed")
    if not isinstance(passed, bool):
        issues.append("result.validation.passed must be a boolean")

    if "levels" in validation:
        levels = validation["levels"]
        if not isinstance(levels, dict):
            issues.append("result.validation.levels must be an object")
        else:
            for level, value in levels.items():
                if level not in VALIDATION_LEVELS:
                    issues.append(f"result.validation.levels has unknown level: {level}")
                elif not isinstance(value, bool):
                    issues.append(f"result.validation.levels.{level} must be a boolean")
            if passed is True:
                failed = sorted(
                    level
                    for level, value in levels.items()
                    if level in VALIDATION_LEVELS and value is False
                )
                if failed:
                    issues.append(
                        "result.validation.passed is true but these levels failed: "
                        + ", ".join(failed)
                    )

    if "notes" in validation and not isinstance(validation["notes"], str):
        issues.append("result.validation.notes must be a string")


def check_result(data: Any) -> dict[str, Any]:
    """Validate an asset-skill result. Raise AssetContractError if invalid."""
    issues: list[str] = []
    if not isinstance(data, dict):
        raise AssetContractError("result must be a JSON object")

    allowed = {"asset_type", "outputs", "sources", "previews", "validation"}
    _check_extra_keys(
        data, allowed, location="result", forbidden=FORBIDDEN_RESULT_KEYS, issues=issues
    )

    for required in ("asset_type", "outputs", "sources", "previews", "validation"):
        if required not in data:
            issues.append(f"result is missing required field: {required}")

    _check_asset_type(data.get("asset_type"), location="result.asset_type", issues=issues)

    validation = data.get("validation")
    validation_passed = validation.get("passed") if isinstance(validation, dict) else None
    runtime_output_count = 0
    outputs = data.get("outputs")
    if not isinstance(outputs, list):
        issues.append("result.outputs must be a list")
    elif not outputs and validation_passed is not False:
        issues.append("result.outputs must contain at least one output")
    else:
        for index, output in enumerate(outputs):
            if _check_output(output, index=index, issues=issues):
                runtime_output_count += 1

    _check_file_list(
        data.get("sources"), field="sources", allowed={"path", "layout"}, issues=issues
    )
    if isinstance(data.get("sources"), list):
        for index, source in enumerate(data["sources"]):
            if isinstance(source, dict) and "layout" in source:
                if not isinstance(source["layout"], str) or source["layout"] not in SOURCE_LAYOUTS:
                    issues.append(
                        f"result.sources[{index}].layout is not allowed: {source['layout']!r}"
                    )

    _check_file_list(
        data.get("previews"), field="previews", allowed={"path", "label"}, issues=issues
    )
    if isinstance(data.get("previews"), list):
        for index, preview in enumerate(data["previews"]):
            if isinstance(preview, dict) and "label" in preview:
                if not _non_empty_string(preview["label"]):
                    issues.append(f"result.previews[{index}].label must be a non-empty string")

    _check_validation(data.get("validation"), issues=issues)

    if issues:
        raise AssetContractError("; ".join(issues))

    output_count = len(outputs) if isinstance(outputs, list) else 0
    return {
        "ok": True,
        "kind": "result",
        "asset_type": data.get("asset_type"),
        "output_count": output_count,
        "runtime_output_count": runtime_output_count,
    }


def check_document(data: Any, *, kind: str | None = None) -> dict[str, Any]:
    """Validate a request or result. Infer the kind when not given."""
    if kind is None:
        if isinstance(data, dict) and "outputs" in data:
            kind = "result"
        else:
            kind = "request"
    if kind == "request":
        return check_request(data)
    if kind == "result":
        return check_result(data)
    raise AssetContractError(f"unknown document kind: {kind}")


def _main() -> int:
    parser = argparse.ArgumentParser(description="Validate an asset-skill request or result")
    parser.add_argument("document", help="Path to the request or result JSON")
    parser.add_argument(
        "--kind",
        choices=["request", "result"],
        default=None,
        help="Document kind; inferred from shape when omitted",
    )
    args = parser.parse_args()

    try:
        data = json.loads(Path(args.document).read_text(encoding="utf-8"))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"invalid JSON: {exc}"}))
        return 1

    try:
        result = check_document(data, kind=args.kind)
    except AssetContractError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
