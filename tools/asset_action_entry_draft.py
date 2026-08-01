#!/usr/bin/env python3
"""Build a v1 stable-entry draft and action support metadata from action output.

``asset_action_process.py`` writes ``pipeline-meta.json`` plus runtime frames and
a delivery sheet. This tool turns that mechanical output into:

1. the action support metadata beside the delivery sheet, at the fixed
   ``assets/generated/<production_family>/<asset_id>/<asset_id>.json`` path;
2. a v1 stable-entry draft ready for ``asset_stable_entry.py --write``.

Every check the pipeline relies on stays mechanical here rather than being
restated in prose for a producer to honour by hand: frame count against the
listed frames, an empty ``edge_touch_frames`` set, a recorded scale reference,
and containment of every runtime path inside the asset's stable output
directory.

Single-action drafts stop at ``processing_status: source_ready`` and carry no
``godot_artifact``. Character-bundle mode receives every required action, while
animated FX mode receives its one explicit action. The latter constructs one
shared ``SpriteFrames`` resource with the native compiler and writes a compiled
entry; the FX Skill promotes it to ready only after L0-L4 pass.
"""
from __future__ import annotations

import argparse
import json
from math import isfinite
import sys
from pathlib import Path
from typing import Any

from asset_stable_entry import (
    PRODUCTION_FAMILIES,
    REFERENCE_FAMILIES,
    SCHEMA_VERSION,
    StableEntryError,
    check_output_path,
    stable_output_dir,
    validate_entry,
)
from asset_animated_bundle_contract_check import (
    AnimatedBundleContractError,
    build_spriteframes_spec,
    check_bundle_request,
)

SHARED_ROOT = Path(__file__).resolve().parents[1] / "skills" / "assets" / "_shared"
if str(SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_ROOT))
from asset_compiler import CompileRequest, CompilerError, build_default_registry  # noqa: E402

SOURCE_LAYOUT_TYPE = "grid_sheet"
DRAFT_STATUS = "source_ready"


class ActionEntryDraftError(Exception):
    """Raised when an action stable-entry draft cannot be built."""


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - surfaced as a tool error
        raise ActionEntryDraftError(f"{label} is not readable JSON: {path}") from exc
    if not isinstance(data, dict):
        raise ActionEntryDraftError(f"{label} must be a JSON object: {path}")
    return data


def _string(data: dict[str, Any], field: str, label: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ActionEntryDraftError(f"{label}.{field} must be a non-empty string")
    return value


def _project_relative(raw_path: str, project_root: Path) -> str:
    """Return a project-relative POSIX path for a tool-emitted path.

    ``asset_action_process.py`` may report absolute paths; anything that cannot
    be expressed relative to the project is rejected rather than silently kept,
    because a registered path must live inside the project tree.
    """
    path = Path(raw_path)
    if path.is_absolute():
        try:
            return path.resolve().relative_to(Path(project_root).resolve()).as_posix()
        except ValueError as exc:
            raise ActionEntryDraftError(
                f"path resolves outside the project root: {raw_path}"
            ) from exc
    return path.as_posix()


def _res(project_relative: str) -> str:
    return f"res://{project_relative}"


def _power_of_two(value: Any) -> bool:
    return type(value) is int and value > 0 and value & (value - 1) == 0


def _checked_output(
    raw_path: str,
    *,
    project_root: Path,
    production_family: str,
    asset_id: str,
    label: str,
) -> str:
    relative = _project_relative(raw_path, project_root)
    try:
        return check_output_path(
            _res(relative),
            production_family=production_family,
            asset_id=asset_id,
            label=label,
        )
    except StableEntryError as exc:
        raise ActionEntryDraftError(str(exc)) from exc


def _frame_paths(metadata: dict[str, Any]) -> list[str]:
    value = metadata.get("final_frame_paths")
    if not isinstance(value, list) or not value:
        raise ActionEntryDraftError("metadata.final_frame_paths must be a non-empty list")
    frames: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ActionEntryDraftError(
                f"metadata.final_frame_paths[{index}] must be a non-empty string"
            )
        frames.append(item)
    return frames


def build_action_entry_draft(
    metadata_path: Path,
    *,
    asset_id: str,
    tag: str,
    production_family: str,
    project_root: Path,
) -> dict[str, Any]:
    """Validate action output and return the draft entry plus support metadata."""
    if not asset_id.strip():
        raise ActionEntryDraftError("--asset-id must be a non-empty string")
    if not tag.strip():
        raise ActionEntryDraftError("--tag must be a non-empty string")
    if production_family not in PRODUCTION_FAMILIES:
        raise ActionEntryDraftError(
            f"production_family is not allowed: {production_family}"
        )
    if production_family in REFERENCE_FAMILIES:
        raise ActionEntryDraftError(
            f"production_family {production_family} is reference-only and has no action output"
        )

    metadata = _load_object(metadata_path, "metadata")

    frame_count = metadata.get("frame_count")
    if not isinstance(frame_count, int) or isinstance(frame_count, bool) or frame_count <= 0:
        raise ActionEntryDraftError("metadata.frame_count must be a positive integer")

    frames = _frame_paths(metadata)
    if len(frames) != frame_count:
        raise ActionEntryDraftError(
            "metadata.final_frame_paths length must match frame_count"
        )

    align = _string(metadata, "align", "metadata")
    shared_scale = metadata.get("shared_scale")
    if not isinstance(shared_scale, bool):
        raise ActionEntryDraftError("metadata.shared_scale must be boolean")

    # An edge-touching frame means the source cell clipped the character, which
    # is a regeneration signal, not something a downstream stage can recover.
    edge_touch_frames = metadata.get("edge_touch_frames")
    if not isinstance(edge_touch_frames, list):
        raise ActionEntryDraftError("metadata.edge_touch_frames must be a list")
    if edge_touch_frames:
        raise ActionEntryDraftError(
            "metadata.edge_touch_frames must be empty; regenerate the action source"
        )

    scale_reference = metadata.get("scale_reference")
    if not isinstance(scale_reference, dict) or not isinstance(
        scale_reference.get("checked"), bool
    ):
        raise ActionEntryDraftError("metadata.scale_reference.checked must be boolean")

    sheet_res = _checked_output(
        _string(metadata, "final_sheet_path", "metadata"),
        project_root=project_root,
        production_family=production_family,
        asset_id=asset_id,
        label="final_sheet_path",
    )
    frame_res = [
        _checked_output(
            frame,
            project_root=project_root,
            production_family=production_family,
            asset_id=asset_id,
            label=f"final_frame_paths[{index}]",
        )
        for index, frame in enumerate(frames)
    ]
    action_name = _string(metadata, "action_name", "metadata")
    fps = metadata.get("fps")
    if (type(fps) not in (int, float) or isinstance(fps, bool)
            or not isfinite(fps) or fps <= 0):
        raise ActionEntryDraftError("metadata.fps must be a positive number")
    loop = metadata.get("loop")
    if type(loop) is not bool:
        raise ActionEntryDraftError("metadata.loop must be boolean")
    durations = metadata.get("frame_durations")
    if not isinstance(durations, list) or len(durations) != frame_count:
        raise ActionEntryDraftError(
            "metadata.frame_durations must have one value per frame"
        )
    if any(type(value) not in (int, float) or isinstance(value, bool)
           or not isfinite(value) or value <= 0
           for value in durations):
        raise ActionEntryDraftError("metadata.frame_durations values must be positive numbers")

    support_relative = (
        f"{stable_output_dir(production_family, asset_id)}/{asset_id}.json"
    )
    support = {
        "version": SCHEMA_VERSION,
        "sheet_path": sheet_res,
        "frame_count": frame_count,
        "frame_paths": frame_res,
        "action_name": action_name,
        "fps": float(fps),
        "loop": loop,
        "frame_durations": [float(value) for value in durations],
        "align": align,
        "shared_scale": shared_scale,
        "edge_touch_frames": [],
        "scale_reference": scale_reference,
        "source_metadata_path": _project_relative(str(metadata_path), project_root),
    }

    entry = {
        "version": SCHEMA_VERSION,
        "asset_id": asset_id,
        "tag": tag,
        "production_family": production_family,
        "source_layout": {"type": SOURCE_LAYOUT_TYPE, "path": sheet_res},
        "processing_status": DRAFT_STATUS,
    }
    try:
        validate_entry(entry, project_root=Path(project_root))
    except StableEntryError as exc:
        raise ActionEntryDraftError(str(exc)) from exc

    return {"entry": entry, "support": support, "support_path": support_relative}


def write_action_entry_draft(
    metadata_path: Path,
    *,
    asset_id: str,
    tag: str,
    production_family: str,
    project_root: Path,
    out: Path,
) -> dict[str, Any]:
    """Build the draft, then write the support metadata and the draft file."""
    built = build_action_entry_draft(
        metadata_path,
        asset_id=asset_id,
        tag=tag,
        production_family=production_family,
        project_root=project_root,
    )
    support_path = Path(project_root) / built["support_path"]
    support_path.parent.mkdir(parents=True, exist_ok=True)
    support_path.write_text(
        json.dumps(built["support"], indent=2) + "\n", encoding="utf-8"
    )

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(built["entry"], indent=2) + "\n", encoding="utf-8")

    return {
        "ok": True,
        "draft": str(out),
        "support": built["support_path"],
        "asset_id": asset_id,
        "tag": tag,
        "frame_count": built["support"]["frame_count"],
    }


def _load_bundle_request(path: Path, asset_type: str) -> dict[str, Any]:
    request = _load_object(path, "request")
    try:
        check_bundle_request(request)
    except AnimatedBundleContractError as exc:
        raise ActionEntryDraftError(str(exc)) from exc
    if request["asset_type"] != asset_type:
        raise ActionEntryDraftError(f"--request must describe a {asset_type}")
    return request


def build_character_bundle_entry_draft(
    metadata_paths: list[Path],
    *,
    request_path: Path,
    asset_id: str,
    tag: str,
    project_root: Path,
) -> dict[str, Any]:
    """Build one ready SpriteFrames stable entry from every required action."""
    request = _load_bundle_request(request_path, "character-bundle")
    if request["asset_id"] != asset_id:
        raise ActionEntryDraftError("--asset-id must match request.asset_id")
    if not tag.strip():
        raise ActionEntryDraftError("--tag must be a non-empty string")

    required_actions = request["spec"]["required_actions"]
    resolved_actions = request["spec"]["actions"]
    if [action["name"] for action in resolved_actions] != required_actions:
        raise ActionEntryDraftError(
            "request.spec.actions must match request.spec.required_actions in order"
        )
    expected_by_action = {action["name"]: action for action in resolved_actions}
    frame_canvas_px = request["spec"].get("frame_canvas_px", 256)
    if not _power_of_two(frame_canvas_px):
        raise ActionEntryDraftError("request.spec.frame_canvas_px must be a positive power-of-two integer")
    if len(metadata_paths) != len(required_actions):
        raise ActionEntryDraftError("--metadata must contain one report per required action")

    by_action: dict[str, dict[str, Any]] = {}
    built_by_action: dict[str, dict[str, Any]] = {}
    metadata_path_by_action: dict[str, Path] = {}
    for metadata_path in metadata_paths:
        metadata = _load_object(metadata_path, "metadata")
        action_name = _string(metadata, "action_name", "metadata")
        if action_name in by_action:
            raise ActionEntryDraftError(f"duplicate action metadata: {action_name}")
        if metadata.get("align") != "feet":
            raise ActionEntryDraftError("character action metadata.align must be feet")
        if metadata.get("shared_scale") is not True:
            raise ActionEntryDraftError("character action metadata.shared_scale must be true")
        if metadata.get("cell_size") != frame_canvas_px:
            raise ActionEntryDraftError(
                "character action metadata.cell_size must match request.spec.frame_canvas_px"
            )
        expected = expected_by_action.get(action_name)
        if expected is None:
            raise ActionEntryDraftError(
                f"unexpected character action metadata: {action_name}"
            )
        frame_labels = metadata.get("frame_labels")
        if frame_labels != expected["frame_names"]:
            raise ActionEntryDraftError(
                f"character action {action_name} frame_labels must match the resolved request"
            )
        expected_grid = {
            "cols": expected["grid"]["columns"],
            "rows": expected["grid"]["rows"],
        }
        if metadata.get("grid") != expected_grid:
            raise ActionEntryDraftError(
                f"character action {action_name} grid must match the resolved request"
            )
        by_action[action_name] = metadata
        metadata_path_by_action[action_name] = Path(metadata_path)
        built = build_action_entry_draft(
            metadata_path,
            asset_id=asset_id,
            tag=tag,
            production_family="character-bundle",
            project_root=project_root,
        )
        support = built["support"]
        if support["fps"] != float(expected["fps"]):
            raise ActionEntryDraftError(
                f"character action {action_name} fps must match the resolved request"
            )
        if support["loop"] is not expected["loop"]:
            raise ActionEntryDraftError(
                f"character action {action_name} loop must match the resolved request"
            )
        if support["frame_durations"] != [
            float(value) for value in expected["frame_durations"]
        ]:
            raise ActionEntryDraftError(
                f"character action {action_name} frame_durations must match the resolved request"
            )
        expected_sheet_path = _res(
            f"{stable_output_dir('character-bundle', asset_id)}/"
            f"{asset_id}_{action_name}_sheet.png"
        )
        if support["sheet_path"] != expected_sheet_path:
            raise ActionEntryDraftError(
                f"character action {action_name} sheet path must match the stable action path"
            )
        expected_frame_paths = [
            _res(
                f"{stable_output_dir('character-bundle', asset_id)}/"
                f"{asset_id}_{action_name}_{label}.png"
            )
            for label in frame_labels
        ]
        if support["frame_paths"] != expected_frame_paths:
            raise ActionEntryDraftError(
                f"character action {action_name} frame paths must match the stable action paths in order"
            )
        support["frame_labels"] = list(frame_labels)
        support["grid"] = expected_grid
        built_by_action[action_name] = built

    if set(by_action) != set(required_actions):
        raise ActionEntryDraftError("action metadata names must match request.spec.required_actions")

    baseline_action = required_actions[0]
    baseline_metadata_path = metadata_path_by_action[baseline_action].resolve()
    baseline_reference = by_action[baseline_action].get("scale_reference")
    if (
        not isinstance(baseline_reference, dict)
        or baseline_reference.get("checked") is not False
    ):
        raise ActionEntryDraftError(
            "canonical action must be the unchecked scale reference root"
        )
    for action_name in required_actions[1:]:
        reference = by_action[action_name].get("scale_reference")
        if not isinstance(reference, dict) or reference.get("checked") is not True:
            raise ActionEntryDraftError(
                f"character action {action_name} must record a checked scale reference"
            )
        reference_path = reference.get("reference_metadata_path")
        if (
            not isinstance(reference_path, str)
            or not reference_path
            or Path(reference_path).resolve() != baseline_metadata_path
        ):
            raise ActionEntryDraftError(
                f"character action {action_name} must use the canonical action scale reference"
            )

    frame_paths_by_action = {
        action_name: built_by_action[action_name]["support"]["frame_paths"]
        for action_name in required_actions
    }
    try:
        compiler_spec = build_spriteframes_spec(request, frame_paths_by_action)
    except AnimatedBundleContractError as exc:
        raise ActionEntryDraftError(str(exc)) from exc

    artifact_path = _res(
        f"{stable_output_dir('character-bundle', asset_id)}/{asset_id}.tres"
    )
    source_path = built_by_action[baseline_action]["support"]["sheet_path"]
    entry = {
        "version": SCHEMA_VERSION,
        "asset_id": asset_id,
        "tag": tag,
        "production_family": "character-bundle",
        "source_layout": {"type": SOURCE_LAYOUT_TYPE, "path": source_path},
        "godot_artifact": {"type": "SpriteFrames", "path": artifact_path},
        "processing_status": "ready",
    }
    try:
        validate_entry(entry, project_root=Path(project_root))
        build_default_registry().compile(
            CompileRequest(
                "character-bundle",
                asset_id,
                "grid_sheet",
                source_path,
                "SpriteFrames",
                artifact_path,
                Path(project_root),
                compiler_spec,
            )
        )
    except (CompilerError, StableEntryError) as exc:
        raise ActionEntryDraftError(str(exc)) from exc

    support = {
        "version": SCHEMA_VERSION,
        "canonical_action": baseline_action,
        "frame_canvas_px": frame_canvas_px,
        "actions": [built_by_action[action_name]["support"] for action_name in required_actions],
    }
    return {"entry": entry, "support": support, "support_path": (
        f"{stable_output_dir('character-bundle', asset_id)}/{asset_id}.json"
    )}


def build_fx_bundle_entry_draft(
    metadata_path: Path,
    *,
    request_path: Path,
    asset_id: str,
    tag: str,
    project_root: Path,
) -> dict[str, Any]:
    """Build the compiled SpriteFrames entry for an animated FX request."""
    request = _load_bundle_request(request_path, "fx-bundle")
    if request["spec"]["mode"] != "animated":
        raise ActionEntryDraftError("--request must describe an animated fx-bundle")
    if request["asset_id"] != asset_id:
        raise ActionEntryDraftError("--asset-id must match request.asset_id")
    if not tag.strip():
        raise ActionEntryDraftError("--tag must be a non-empty string")

    action = request["spec"]["actions"][0]
    action_name = action["name"]
    metadata = _load_object(metadata_path, "metadata")
    if metadata.get("action_name") != action_name:
        raise ActionEntryDraftError("FX action metadata must match the request action name")
    if metadata.get("align") != "center":
        raise ActionEntryDraftError("animated FX metadata.align must be center")
    if metadata.get("frame_labels") != action["frame_names"]:
        raise ActionEntryDraftError(
            "FX action frame_labels must match the request frame_names in order"
        )
    expected_grid = {"cols": action["grid"]["columns"], "rows": action["grid"]["rows"]}
    if metadata.get("grid") != expected_grid:
        raise ActionEntryDraftError("FX action grid must match the request grid")

    built = build_action_entry_draft(
        metadata_path,
        asset_id=asset_id,
        tag=tag,
        production_family="fx-bundle",
        project_root=project_root,
    )
    support = built["support"]
    if support["fps"] != float(action["fps"]):
        raise ActionEntryDraftError("FX action fps must match the request")
    if support["loop"] is not action["loop"]:
        raise ActionEntryDraftError("FX action loop must match the request")
    if support["frame_durations"] != [float(value) for value in action["frame_durations"]]:
        raise ActionEntryDraftError("FX action frame_durations must match the request")
    expected_sheet_path = _res(
        f"{stable_output_dir('fx-bundle', asset_id)}/{asset_id}_sheet.png"
    )
    if support["sheet_path"] != expected_sheet_path:
        raise ActionEntryDraftError("FX action sheet path must match the stable action path")
    expected_frame_paths = [
        _res(
            f"{stable_output_dir('fx-bundle', asset_id)}/{asset_id}_{action_name}_{label}.png"
        )
        for label in action["frame_names"]
    ]
    if support["frame_paths"] != expected_frame_paths:
        raise ActionEntryDraftError("FX action frame paths must match the stable action paths in order")

    try:
        compiler_spec = build_spriteframes_spec(request, {action_name: support["frame_paths"]})
    except AnimatedBundleContractError as exc:
        raise ActionEntryDraftError(str(exc)) from exc
    artifact_path = _res(f"{stable_output_dir('fx-bundle', asset_id)}/{asset_id}.tres")
    entry = {
        "version": SCHEMA_VERSION,
        "asset_id": asset_id,
        "tag": tag,
        "production_family": "fx-bundle",
        "source_layout": {"type": SOURCE_LAYOUT_TYPE, "path": support["sheet_path"]},
        "godot_artifact": {"type": "SpriteFrames", "path": artifact_path},
        "processing_status": "compiled",
    }
    try:
        validate_entry(entry, project_root=Path(project_root))
        build_default_registry().compile(
            CompileRequest(
                "fx-bundle",
                asset_id,
                "grid_sheet",
                support["sheet_path"],
                "SpriteFrames",
                artifact_path,
                Path(project_root),
                compiler_spec,
            )
        )
    except (CompilerError, StableEntryError) as exc:
        raise ActionEntryDraftError(str(exc)) from exc

    support["frame_labels"] = list(action["frame_names"])
    support["grid"] = expected_grid
    return {
        "entry": entry,
        "support": {"version": SCHEMA_VERSION, "action": support},
        "support_path": f"{stable_output_dir('fx-bundle', asset_id)}/{asset_id}.json",
    }


def write_character_bundle_entry_draft(
    metadata_paths: list[Path],
    *,
    request_path: Path,
    asset_id: str,
    tag: str,
    project_root: Path,
    out: Path,
) -> dict[str, Any]:
    built = build_character_bundle_entry_draft(
        metadata_paths,
        request_path=request_path,
        asset_id=asset_id,
        tag=tag,
        project_root=project_root,
    )
    support_path = Path(project_root) / built["support_path"]
    support_path.parent.mkdir(parents=True, exist_ok=True)
    support_path.write_text(json.dumps(built["support"], indent=2) + "\n", encoding="utf-8")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(built["entry"], indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "draft": str(out), "support": built["support_path"], "asset_id": asset_id, "tag": tag}


def write_fx_bundle_entry_draft(
    metadata_path: Path,
    *,
    request_path: Path,
    asset_id: str,
    tag: str,
    project_root: Path,
    out: Path,
) -> dict[str, Any]:
    """Write the compiled animated FX entry and its action support metadata."""
    built = build_fx_bundle_entry_draft(
        metadata_path,
        request_path=request_path,
        asset_id=asset_id,
        tag=tag,
        project_root=project_root,
    )
    support_path = Path(project_root) / built["support_path"]
    support_path.parent.mkdir(parents=True, exist_ok=True)
    support_path.write_text(json.dumps(built["support"], indent=2) + "\n", encoding="utf-8")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(built["entry"], indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "draft": str(out), "support": built["support_path"], "asset_id": asset_id, "tag": tag}


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a v1 stable-entry draft and support metadata from action output"
    )
    parser.add_argument("--metadata", required=True, type=Path, action="append")
    parser.add_argument("--request", type=Path)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--production-family", required=True)
    parser.add_argument("--project-root", default=".", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    try:
        if args.request:
            if args.production_family == "character-bundle":
                result = write_character_bundle_entry_draft(
                    args.metadata,
                    request_path=args.request,
                    asset_id=args.asset_id,
                    tag=args.tag,
                    project_root=args.project_root,
                    out=args.out,
                )
            elif args.production_family == "fx-bundle":
                if len(args.metadata) != 1:
                    raise ActionEntryDraftError(
                        "animated fx-bundle mode accepts exactly one --metadata"
                    )
                result = write_fx_bundle_entry_draft(
                    args.metadata[0],
                    request_path=args.request,
                    asset_id=args.asset_id,
                    tag=args.tag,
                    project_root=args.project_root,
                    out=args.out,
                )
            else:
                raise ActionEntryDraftError(
                    "--request bundle mode supports character-bundle or fx-bundle only"
                )
        else:
            if len(args.metadata) != 1:
                raise ActionEntryDraftError("single-action mode accepts exactly one --metadata")
            result = write_action_entry_draft(
                args.metadata[0],
                asset_id=args.asset_id,
                tag=args.tag,
                production_family=args.production_family,
                project_root=args.project_root,
                out=args.out,
            )
    except ActionEntryDraftError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
