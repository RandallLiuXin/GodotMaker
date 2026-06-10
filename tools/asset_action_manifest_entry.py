#!/usr/bin/env python3
"""Build a character_frame_output manifest entry from action processing metadata."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


class ActionManifestEntryError(Exception):
    """Raised when an action manifest entry cannot be built."""


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ActionManifestEntryError(f"{label} is not readable JSON: {path}") from exc
    if not isinstance(data, dict):
        raise ActionManifestEntryError(f"{label} must be a JSON object: {path}")
    return data


def _string(data: dict[str, Any], field: str, label: str, *, required: bool = True) -> str | None:
    value = data.get(field)
    if value is None:
        if required:
            raise ActionManifestEntryError(f"{label}.{field} is required")
        return None
    if not isinstance(value, str) or not value.strip():
        raise ActionManifestEntryError(f"{label}.{field} must be a non-empty string")
    return value


def _as_project_path(raw_path: str, project_root: Path) -> str:
    path = Path(raw_path)
    if path.is_absolute():
        try:
            return path.relative_to(project_root).as_posix()
        except ValueError:
            return path.as_posix()
    return path.as_posix()


def _string_list(data: dict[str, Any], field: str, project_root: Path) -> list[str]:
    value = data.get(field)
    if not isinstance(value, list) or not value:
        raise ActionManifestEntryError(f"metadata.{field} must be a non-empty list")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ActionManifestEntryError(f"metadata.{field}[{index}] must be a non-empty string")
        result.append(_as_project_path(item, project_root))
    return result


def _write_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        delete=False,
        dir=str(path.parent),
        suffix=".json",
        mode="w",
        encoding="utf-8",
    ) as handle:
        tmp_path = Path(handle.name)
        json.dump(data, handle, indent=2)
        handle.write("\n")
    try:
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def build_action_manifest_entry(
    metadata_path: Path,
    source_entry_path: Path,
    *,
    asset_id: str,
    project_root: Path,
    final_path: str | None = None,
    runtime_metadata_path: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Build one character_frame_output entry from processed action metadata."""
    if not asset_id.strip():
        raise ActionManifestEntryError("--asset-id must be a non-empty string")

    metadata = _load_object(metadata_path, "metadata")
    source_entry = _load_object(source_entry_path, "source_entry")

    source_asset_id = _string(source_entry, "asset_id", "source_entry")
    tag = _string(source_entry, "tag", "source_entry")
    runtime_role = _string(source_entry, "runtime_role", "source_entry")
    source_path = _string(source_entry, "source_path", "source_entry")
    prompt_path = _string(source_entry, "prompt_path", "source_entry")
    canonical_reference = _string(source_entry, "canonical_reference", "source_entry")

    frame_count = metadata.get("frame_count")
    if not isinstance(frame_count, int) or frame_count <= 0:
        raise ActionManifestEntryError("metadata.frame_count must be positive")

    frame_paths = _string_list(metadata, "final_frame_paths", project_root)
    if len(frame_paths) != frame_count:
        raise ActionManifestEntryError("metadata.final_frame_paths length must match frame_count")

    align = _string(metadata, "align", "metadata")
    shared_scale = metadata.get("shared_scale")
    if not isinstance(shared_scale, bool):
        raise ActionManifestEntryError("metadata.shared_scale must be boolean")

    sheet_path = final_path or _string(metadata, "final_sheet_path", "metadata")
    if sheet_path is None:
        raise ActionManifestEntryError("metadata.final_sheet_path is required")
    clean_sheet_path = _as_project_path(sheet_path, project_root)
    clean_runtime_metadata_path = _as_project_path(
        runtime_metadata_path or str((project_root / clean_sheet_path).with_suffix(".json")),
        project_root,
    )

    gif_path = _as_project_path(_string(metadata, "gif_path", "metadata") or "", project_root)
    clean_metadata_path = _as_project_path(str(metadata_path), project_root)
    edge_touch_frames = metadata.get("edge_touch_frames")
    if not isinstance(edge_touch_frames, list):
        raise ActionManifestEntryError("metadata.edge_touch_frames must be a list")
    if edge_touch_frames:
        raise ActionManifestEntryError("metadata.edge_touch_frames must be empty")

    scale_reference = metadata.get("scale_reference")
    if not isinstance(scale_reference, dict) or not isinstance(scale_reference.get("checked"), bool):
        raise ActionManifestEntryError("metadata.scale_reference.checked must be boolean")

    runtime_metadata = {
        "version": 1,
        "runtime_artifact": "grid_sheet",
        "asset_id": asset_id,
        "tag": tag,
        "sheet_path": clean_sheet_path,
        "frame_count": frame_count,
        "frame_paths": frame_paths,
        "frame_labels": metadata.get("frame_labels", []),
        "grid": metadata.get("grid"),
        "align": align,
        "shared_scale": shared_scale,
        "duration": metadata.get("duration"),
        "loop": True,
        "edge_touch_frames": edge_touch_frames,
        "scale_reference": scale_reference,
        "source_metadata_path": clean_metadata_path,
    }
    _write_atomic(project_root / clean_runtime_metadata_path, runtime_metadata)

    return {
        "asset_id": asset_id,
        "tag": tag,
        "family": "character_frame_output",
        "production_shape": "delivery_sheet",
        "runtime_role": runtime_role,
        "source_path": source_path,
        "final_path": clean_sheet_path,
        "derived_from": source_asset_id,
        "canonical_reference": canonical_reference,
        "prompt_path": prompt_path,
        "runtime_artifact": "grid_sheet",
        "processing_status": "ready",
        "extraction_status": "processed",
        "curation": {
            "status": "selected",
            "strategy": "solid_background_grid",
            "report_path": _as_project_path(_string(metadata, "curation_report_path", "metadata") or "", project_root),
            "selected_count": frame_count,
            "rejected_count": 0,
        },
        "qc": {
            "action_processing": {
                "frame_count": frame_count,
                "metadata_path": clean_runtime_metadata_path,
            }
        },
        "preview_path": gif_path,
        "notes": notes,
    }


def _main() -> int:
    parser = argparse.ArgumentParser(description="Build a character_frame_output manifest entry")
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--source-entry", required=True, type=Path)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--project-root", default=".", type=Path)
    parser.add_argument("--final-path")
    parser.add_argument("--runtime-metadata-path")
    parser.add_argument("--notes", default="")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    try:
        entry = build_action_manifest_entry(
            args.metadata,
            args.source_entry,
            asset_id=args.asset_id,
            project_root=args.project_root,
            final_path=args.final_path,
            runtime_metadata_path=args.runtime_metadata_path,
            notes=args.notes,
        )
        if args.out is not None:
            _write_atomic(args.out, entry)
    except ActionManifestEntryError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(json.dumps({"ok": True, "entry": entry, "path": str(args.out) if args.out else None}))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
