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

The draft stops at ``processing_status: source_ready`` and carries no
``godot_artifact``. A ``grid_sheet`` asset becomes worker-consumable only once a
native compiler produces its ``SpriteFrames`` and the L0-L4 runner verifies it;
neither exists yet, so declaring anything further here would be a false
readiness claim.
"""
from __future__ import annotations

import argparse
import json
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

    support_relative = (
        f"{stable_output_dir(production_family, asset_id)}/{asset_id}.json"
    )
    support = {
        "version": SCHEMA_VERSION,
        "sheet_path": sheet_res,
        "frame_count": frame_count,
        "frame_paths": frame_res,
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


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a v1 stable-entry draft and support metadata from action output"
    )
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--production-family", required=True)
    parser.add_argument("--project-root", default=".", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    try:
        result = write_action_entry_draft(
            args.metadata,
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
