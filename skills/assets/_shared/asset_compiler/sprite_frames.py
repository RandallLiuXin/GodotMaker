"""Deterministically serialize independent action PNGs as ``SpriteFrames``."""
from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from typing import Any

from ._runtime_contract import assert_within_output_dir, check_output_path, resolve_res_path
from .contract import CompileRequest, CompilerError
from .registry import CompilerRegistry, CompilerRoute

COMPILER_ID = "spriteframes_actions"
COMPILER_VERSION = 1


def _number(value: Any, label: str) -> float:
    if type(value) not in (int, float) or isinstance(value, bool) or not isfinite(value) or value <= 0:
        raise CompilerError(f"{label} must be a finite positive number")
    return float(value)


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CompilerError(f"{label} must be a non-empty string")
    return value


def action_spec(request: CompileRequest) -> list[dict[str, Any]]:
    """Validate the explicit action contract and resolve every required PNG."""
    required = request.spec.get("required_actions")
    actions = request.spec.get("actions")
    if not isinstance(required, list) or not required:
        raise CompilerError("spec.required_actions must be a non-empty list")
    names = [_text(name, f"spec.required_actions[{index}]") for index, name in enumerate(required)]
    if len(set(names)) != len(names):
        raise CompilerError("spec.required_actions must not contain duplicates")
    if not isinstance(actions, list) or not actions:
        raise CompilerError("spec.actions must be a non-empty list")

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(actions):
        if not isinstance(raw, Mapping):
            raise CompilerError(f"spec.actions[{index}] must be an object")
        name = _text(raw.get("name"), f"spec.actions[{index}].name")
        if name in seen:
            raise CompilerError(f"spec.actions contains duplicate action {name!r}")
        seen.add(name)
        loop = raw.get("loop")
        if type(loop) is not bool:
            raise CompilerError(f"spec.actions[{index}].loop must be boolean")
        fps = _number(raw.get("fps"), f"spec.actions[{index}].fps")
        frames = raw.get("frame_paths")
        durations = raw.get("frame_durations")
        if not isinstance(frames, list) or not frames:
            raise CompilerError(f"spec.actions[{index}].frame_paths must be a non-empty list")
        if not isinstance(durations, list) or len(durations) != len(frames):
            raise CompilerError(f"spec.actions[{index}].frame_durations must have one value per frame")
        resolved_frames: list[str] = []
        for frame_index, frame in enumerate(frames):
            path = _text(frame, f"spec.actions[{index}].frame_paths[{frame_index}]")
            try:
                checked = check_output_path(path, production_family=request.production_family,
                                              asset_id=request.asset_id,
                                              label=f"spec.actions[{index}].frame_paths[{frame_index}]")
                file = assert_within_output_dir(request.project_root,
                    resolve_res_path(request.project_root, checked, label="frame path"),
                    production_family=request.production_family, asset_id=request.asset_id,
                    label="frame path")
            except Exception as exc:  # runtime record errors remain compiler errors
                raise CompilerError(str(exc)) from exc
            if file.suffix.lower() != ".png" or not file.is_file():
                raise CompilerError(f"action frame is not an existing PNG: {path}")
            resolved_frames.append(checked)
        normalized.append({"name": name, "loop": loop, "fps": fps,
                           "frame_paths": resolved_frames,
                           "frame_durations": [_number(value, f"spec.actions[{index}].frame_durations[{duration_index}]")
                                               for duration_index, value in enumerate(durations)]})
    if set(names) != seen:
        missing = sorted(set(names) - seen)
        extra = sorted(seen - set(names))
        detail = f"missing required actions: {', '.join(missing)}" if missing else f"unexpected actions: {', '.join(extra)}"
        raise CompilerError(detail)
    return normalized


def _escape(path: str) -> str:
    return path.replace("\\", "\\\\").replace('"', '\\"')


def compile_spriteframes(request: CompileRequest) -> dict[str, Any]:
    """Write a Godot 4 text resource from the caller's explicit action facts."""
    actions = action_spec(request)
    texture_ids: dict[str, str] = {}
    for action in actions:
        for path in action["frame_paths"]:
            if path not in texture_ids:
                texture_ids[path] = f"{len(texture_ids) + 1}_texture"
    lines = [f'[gd_resource type="SpriteFrames" load_steps={len(texture_ids) + 1} format=3]', ""]
    for path, resource_id in texture_ids.items():
        lines.append(f'[ext_resource type="Texture2D" path="{_escape(path)}" id="{resource_id}"]')
    lines.extend(["", "[resource]", "animations = ["])
    for action_index, action in enumerate(actions):
        lines.extend(["{", "\"frames\": ["])
        for frame_index, (path, duration) in enumerate(zip(action["frame_paths"], action["frame_durations"])):
            separator = "," if frame_index + 1 < len(action["frame_paths"]) else ""
            lines.append(f'{{"duration": {duration!r}, "texture": ExtResource("{texture_ids[path]}")}}{separator}')
        lines.extend(["],", f'"loop": {str(action["loop"]).lower()},',
                      f'"name": &"{_escape(action["name"])}",', f'"speed": {action["fps"]!r}',
                      "}" + ("," if action_index + 1 < len(actions) else "")])
    lines.extend(["]", ""])
    artifact = request.artifact_file()
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return {"actions": [{key: action[key] for key in ("name", "fps", "loop", "frame_paths", "frame_durations")} for action in actions]}


def register_into(registry: CompilerRegistry) -> CompilerRoute:
    return registry.register(source_layout_type="grid_sheet", artifact_type="SpriteFrames",
                             compiler_id=COMPILER_ID, compiler_version=COMPILER_VERSION,
                             compiler=compile_spriteframes)
