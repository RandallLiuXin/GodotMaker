#!/usr/bin/env python3
"""Validate the public contracts for standalone animated-bundle skills.

The shared asset-skill checker owns the shape common to every production
family. This module owns the declared ``spec`` and runtime-result rules for
``character-bundle`` and ``fx-bundle``. It also turns a validated action request
and the processed action-frame paths into the exact SpriteFrames compiler spec.
"""
from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from math import isfinite
from pathlib import Path
from typing import Any

from asset_skill_contract_check import AssetContractError, check_request, check_result


class AnimatedBundleContractError(Exception):
    """Raised when a character-bundle or fx-bundle contract is invalid."""


def _text(value: Any, label: str, issues: list[str]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        issues.append(f"{label} must be a non-empty string")
        return None
    return value


def _positive_number(value: Any, label: str, issues: list[str]) -> None:
    if type(value) not in (int, float) or isinstance(value, bool) or not isfinite(value) or value <= 0:
        issues.append(f"{label} must be a finite positive number")


def _action(raw: Any, *, label: str, issues: list[str]) -> str | None:
    if not isinstance(raw, dict):
        issues.append(f"{label} must be an object")
        return None
    allowed = {"name", "frame_names", "fps", "loop", "frame_durations"}
    for key in raw:
        if key not in allowed:
            issues.append(f"{label} has unknown field: {key}")

    name = _text(raw.get("name"), f"{label}.name", issues)
    frames = raw.get("frame_names")
    if not isinstance(frames, list) or not frames:
        issues.append(f"{label}.frame_names must be a non-empty list")
        frames = []
    else:
        checked_frames = [_text(value, f"{label}.frame_names[{index}]", issues)
                          for index, value in enumerate(frames)]
        if len(set(value for value in checked_frames if value is not None)) != len(frames):
            issues.append(f"{label}.frame_names must not contain duplicates")

    _positive_number(raw.get("fps"), f"{label}.fps", issues)
    if type(raw.get("loop")) is not bool:
        issues.append(f"{label}.loop must be boolean")

    durations = raw.get("frame_durations")
    if not isinstance(durations, list) or len(durations) != len(frames):
        issues.append(f"{label}.frame_durations must have one value per frame")
    elif not isinstance(raw.get("frame_names"), list) or not raw["frame_names"]:
        # The frame-list error above is the useful primary diagnostic.
        pass
    else:
        for index, duration in enumerate(durations):
            _positive_number(duration, f"{label}.frame_durations[{index}]", issues)
    return name


def _required_actions(value: Any, *, label: str, issues: list[str]) -> list[str]:
    if not isinstance(value, list) or not value:
        issues.append(f"{label} must be a non-empty list")
        return []
    names = [_text(name, f"{label}[{index}]", issues) for index, name in enumerate(value)]
    clean = [name for name in names if name is not None]
    if len(set(clean)) != len(value):
        issues.append(f"{label} must not contain duplicates")
    return clean


def _actions(value: Any, *, label: str, issues: list[str]) -> list[str]:
    if not isinstance(value, list) or not value:
        issues.append(f"{label} must be a non-empty list")
        return []
    names = [_action(action, label=f"{label}[{index}]", issues=issues)
             for index, action in enumerate(value)]
    clean = [name for name in names if name is not None]
    if len(set(clean)) != len(value):
        issues.append(f"{label} must not contain duplicate action names")
    return clean


def _character_spec(spec: Any, issues: list[str]) -> None:
    if not isinstance(spec, dict):
        issues.append("request.spec must be an object")
        return
    allowed = {"required_actions", "actions"}
    for key in spec:
        if key not in allowed:
            issues.append(f"request.spec has unknown field: {key}")
    required = _required_actions(spec.get("required_actions"), label="request.spec.required_actions", issues=issues)
    actions = _actions(spec.get("actions"), label="request.spec.actions", issues=issues)
    if required and actions and set(required) != set(actions):
        missing = sorted(set(required) - set(actions))
        extra = sorted(set(actions) - set(required))
        if missing:
            issues.append("request.spec.actions is missing required actions: " + ", ".join(missing))
        if extra:
            issues.append("request.spec.actions has unexpected actions: " + ", ".join(extra))


def _fx_spec(spec: Any, issues: list[str]) -> None:
    if not isinstance(spec, dict):
        issues.append("request.spec must be an object")
        return
    allowed = {"mode", "required_actions", "actions"}
    for key in spec:
        if key not in allowed:
            issues.append(f"request.spec has unknown field: {key}")
    mode = spec.get("mode")
    if not isinstance(mode, str) or mode not in {"static", "animated"}:
        issues.append("request.spec.mode must be static or animated")
        return
    if mode == "static":
        for key in ("required_actions", "actions"):
            if key in spec:
                issues.append(f"request.spec.{key} is not allowed for a static FX request")
        return

    required = _required_actions(spec.get("required_actions"), label="request.spec.required_actions", issues=issues)
    actions = _actions(spec.get("actions"), label="request.spec.actions", issues=issues)
    if len(required) != 1:
        issues.append("request.spec.required_actions must contain exactly one animated FX action")
    if len(actions) != 1:
        issues.append("request.spec.actions must contain exactly one animated FX action")
    if len(required) == 1 and len(actions) == 1 and required[0] != actions[0]:
        issues.append("request.spec.actions must match request.spec.required_actions")


def check_bundle_request(data: Any) -> dict[str, Any]:
    """Validate a standalone character-bundle or fx-bundle request."""
    try:
        shared = check_request(data)
    except AssetContractError as exc:
        raise AnimatedBundleContractError(str(exc)) from exc

    issues: list[str] = []
    asset_type = data["asset_type"]
    if asset_type == "character-bundle":
        _character_spec(data.get("spec"), issues)
    elif asset_type == "fx-bundle":
        _fx_spec(data.get("spec"), issues)
    else:
        issues.append(f"asset_type is not an animated bundle family: {asset_type}")
    if issues:
        raise AnimatedBundleContractError("; ".join(issues))
    return {"ok": True, "kind": "request", "asset_type": asset_type, "shared": shared}


def _runtime_outputs(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [output for output in data["outputs"]
            if isinstance(output, dict) and output.get("role") == "runtime"]


def _source_layouts(data: dict[str, Any]) -> set[str]:
    return {source.get("layout") for source in data["sources"] if isinstance(source, dict)}


def check_bundle_result(data: Any) -> dict[str, Any]:
    """Validate a bundle result's intrinsic runtime-output boundary.

    This function checks constraints visible in the result alone. Use
    :func:`check_bundle_handoff` for final validation, because only that path can
    bind an FX result to the request's ``static`` or ``animated`` mode.
    """
    try:
        shared = check_result(data)
    except AssetContractError as exc:
        raise AnimatedBundleContractError(str(exc)) from exc

    issues: list[str] = []
    asset_type = data["asset_type"]
    runtime = _runtime_outputs(data)
    if asset_type == "character-bundle":
        if sum(output.get("godot_type") == "SpriteFrames" for output in runtime) != 1:
            issues.append("character-bundle result must contain exactly one SpriteFrames runtime output")
        elif "grid_sheet" not in _source_layouts(data):
            issues.append("character-bundle SpriteFrames result needs a grid_sheet source")
    elif asset_type == "fx-bundle":
        if len(runtime) != 1:
            issues.append("fx-bundle result must contain exactly one runtime output")
        elif runtime[0].get("godot_type") not in {"Texture2D", "SpriteFrames"}:
            issues.append("fx-bundle runtime output must be Texture2D or SpriteFrames")
        else:
            expected_layout = "single" if runtime[0]["godot_type"] == "Texture2D" else "grid_sheet"
            if expected_layout not in _source_layouts(data):
                issues.append(f"fx-bundle {runtime[0]['godot_type']} result needs a {expected_layout} source")
    else:
        issues.append(f"asset_type is not an animated bundle family: {asset_type}")
    if issues:
        raise AnimatedBundleContractError("; ".join(issues))
    return {"ok": True, "kind": "result", "asset_type": asset_type, "shared": shared}


def check_bundle_handoff(request: Any, result: Any) -> dict[str, Any]:
    """Validate the final request-to-result runtime handoff for one bundle.

    FX output type cannot be inferred from a result alone: both Texture2D and
    SpriteFrames are legitimate FX artifacts. This boundary therefore validates
    the request and result together and makes the request's explicit mode the
    authority for the final artifact type and source layout.
    """
    request_check = check_bundle_request(request)
    result_check = check_bundle_result(result)
    if request["asset_type"] != result["asset_type"]:
        raise AnimatedBundleContractError("request.asset_type must match result.asset_type")

    if request["asset_type"] == "fx-bundle":
        runtime = _runtime_outputs(result)
        mode = request["spec"]["mode"]
        expected_type = "Texture2D" if mode == "static" else "SpriteFrames"
        expected_layout = "single" if mode == "static" else "grid_sheet"
        if len(runtime) != 1 or runtime[0].get("godot_type") != expected_type:
            raise AnimatedBundleContractError(
                f"{mode} FX request must hand off exactly one {expected_type} runtime output"
            )
        if expected_layout not in _source_layouts(result):
            raise AnimatedBundleContractError(
                f"{mode} FX request must hand off a {expected_layout} source"
            )
    return {
        "ok": True,
        "kind": "handoff",
        "asset_type": request["asset_type"],
        "request": request_check,
        "result": result_check,
    }


def build_spriteframes_spec(data: Any, frame_paths_by_action: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    """Build the exact shared SpriteFrames spec from a validated public request.

    ``frame_paths_by_action`` is supplied only after action-frame processing. It
    must have exactly the declared action names and one non-empty path per public
    frame name, so an action cannot quietly lose a processed frame before it
    reaches the real compiler.
    """
    check_bundle_request(data)
    spec = data["spec"]
    if data["asset_type"] == "fx-bundle" and spec["mode"] != "animated":
        raise AnimatedBundleContractError("static FX requests do not compile SpriteFrames")
    actions = spec["actions"]
    required = spec["required_actions"]
    if set(frame_paths_by_action) != set(required):
        raise AnimatedBundleContractError("processed action-frame paths must match required_actions exactly")

    compiled_actions: list[dict[str, Any]] = []
    for action in actions:
        name = action["name"]
        paths = frame_paths_by_action[name]
        if isinstance(paths, (str, bytes)) or not isinstance(paths, Sequence):
            raise AnimatedBundleContractError(f"processed frame paths for {name!r} must be a list")
        if len(paths) != len(action["frame_names"]):
            raise AnimatedBundleContractError(
                f"processed frame paths for {name!r} must match frame_names"
            )
        checked_paths: list[str] = []
        for index, path in enumerate(paths):
            if not isinstance(path, str) or not path.strip():
                raise AnimatedBundleContractError(
                    f"processed frame paths for {name!r}[{index}] must be a non-empty string"
                )
            checked_paths.append(path)
        compiled_actions.append({
            "name": name,
            "fps": action["fps"],
            "loop": action["loop"],
            "frame_paths": checked_paths,
            "frame_durations": list(action["frame_durations"]),
        })
    return {"required_actions": list(required), "actions": compiled_actions}


def _main() -> int:
    parser = argparse.ArgumentParser(description="Validate animated bundle asset-skill contracts")
    parser.add_argument("document", nargs="?", type=Path, help="Request or result JSON path")
    parser.add_argument("--kind", choices=["request", "result"])
    parser.add_argument("--request", type=Path, help="Validated request JSON for final handoff")
    parser.add_argument("--result", type=Path, help="Result JSON for final handoff")
    args = parser.parse_args()
    try:
        if args.request or args.result:
            if args.document or not args.request or not args.result:
                raise AnimatedBundleContractError(
                    "handoff validation needs --request and --result with no document"
                )
            request = json.loads(args.request.read_text(encoding="utf-8"))
            result_document = json.loads(args.result.read_text(encoding="utf-8"))
            result = check_bundle_handoff(request, result_document)
        elif args.document and args.kind:
            data = json.loads(args.document.read_text(encoding="utf-8"))
            result = check_bundle_request(data) if args.kind == "request" else check_bundle_result(data)
        else:
            raise AnimatedBundleContractError(
                "document with --kind is required without --request and --result"
            )
    except (AnimatedBundleContractError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
