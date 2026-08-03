#!/usr/bin/env python3
"""Build the ready v1 entry for one compiled tileset atlas.

The `tileset` Skill compiles a fixed-profile terrain atlas into a native
`TileSet` and runs its own L0-L4 loop. This adapter is what turns that finished
result into the registration the manager writes: it re-binds the result to the
request it came from, pins both files to the asset's stable directory, and
refuses anything that has not actually passed L0-L4.

A `TileSet` is a tile library — art plus the tile semantics the resource
declares. Where a tile goes is not in it, and this builder never invents that:
map layout stays a worker decision.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from asset_skill_contract_check import AssetContractError, check_request, check_result
from asset_stable_entry import (
    SCHEMA_VERSION,
    StableEntryError,
    stable_output_dir,
    validate_entry,
)

from asset_tileset_contract_check import (
    TileSetRequestError,
    check_tileset_request,
)

FAMILY = "tileset"
SOURCE_LAYOUT = "tile_atlas"
ARTIFACT_TYPE = "TileSet"
LEVELS = ("L0", "L1", "L2", "L3", "L4")


class TileSetEntryDraftError(Exception):
    """Raised when a tileset result cannot become a ready entry."""


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TileSetEntryDraftError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise TileSetEntryDraftError(f"{label} must be a JSON object: {path}")
    return value


def _stable_paths(asset_id: str) -> tuple[str, str]:
    directory = stable_output_dir(FAMILY, asset_id)
    return f"res://{directory}/{asset_id}_atlas.png", f"res://{directory}/{asset_id}.tres"


def _assert_file(project_root: Path, res_path: str, label: str) -> None:
    target = Path(project_root) / res_path[len("res://"):]
    if not target.is_file() or target.stat().st_size <= 0:
        raise TileSetEntryDraftError(f"{label} is missing or empty: {res_path}")


def build_tileset_entry_draft(
    request_path: Path,
    result_path: Path,
    *,
    tag: str,
    project_root: Path,
    check_files: bool = True,
) -> dict[str, Any]:
    """Validate a complete tileset delivery and build its ready entry."""
    request = _load_object(request_path, "request")
    result = _load_object(result_path, "asset Skill result")
    try:
        check_request(request)
        check_result(result)
    except AssetContractError as exc:
        raise TileSetEntryDraftError(str(exc)) from exc
    if request.get("asset_type") != FAMILY or result.get("asset_type") != FAMILY:
        raise TileSetEntryDraftError("request and result must both be tileset")
    try:
        check_tileset_request(request)
    except TileSetRequestError as exc:
        raise TileSetEntryDraftError(str(exc)) from exc
    if not isinstance(tag, str) or not tag.strip():
        raise TileSetEntryDraftError("--tag must be a non-empty string")

    asset_id = request["asset_id"]
    atlas_path, artifact_path = _stable_paths(asset_id)

    if result["sources"] != [{"path": atlas_path, "layout": SOURCE_LAYOUT}]:
        raise TileSetEntryDraftError(
            "result must expose exactly the one stable tile_atlas source"
        )
    # A tile library is one resource. A second output would reach a worker as a
    # rival tile source for the same map, so the family publishes exactly one.
    runtime = [item for item in result["outputs"] if item.get("role") == "runtime"]
    if len(runtime) != 1 or len(result["outputs"]) != 1:
        raise TileSetEntryDraftError(
            "result must expose exactly one stable TileSet runtime output"
        )
    # `name` is an optional field of the shared result contract, so compare the
    # fields this family actually pins rather than the whole object.
    if (
        runtime[0].get("path") != artifact_path
        or runtime[0].get("godot_type") != ARTIFACT_TYPE
    ):
        raise TileSetEntryDraftError(
            "result runtime output must be the stable TileSet artifact"
        )

    # L5 is a legal level of the shared contract; require L0-L4 to have passed
    # rather than demanding the level map contain nothing else.
    validation = result["validation"]
    levels = validation.get("levels")
    if validation.get("passed") is not True or not isinstance(levels, dict):
        raise TileSetEntryDraftError(
            "result must have passed L0-L4 before a ready entry is drafted; "
            "no explicit validation levels were reported"
        )
    unpassed = [level for level in LEVELS if levels.get(level) is not True]
    if unpassed:
        raise TileSetEntryDraftError(
            "result must have passed L0-L4 before a ready entry is drafted; "
            f"not passing: {', '.join(unpassed)}"
        )

    if check_files:
        _assert_file(project_root, atlas_path, "stable tile atlas")
        _assert_file(project_root, artifact_path, "compiled TileSet")

    entry = {
        "version": SCHEMA_VERSION,
        "asset_id": asset_id,
        "tag": tag,
        "production_family": FAMILY,
        "source_layout": {"type": SOURCE_LAYOUT, "path": atlas_path},
        "godot_artifact": {"type": ARTIFACT_TYPE, "path": artifact_path},
        "processing_status": "ready",
    }
    try:
        validate_entry(entry, project_root=Path(project_root), check_files=check_files)
    except StableEntryError as exc:
        raise TileSetEntryDraftError(str(exc)) from exc
    return entry


def write_tileset_entry_draft(
    request_path: Path,
    result_path: Path,
    *,
    tag: str,
    project_root: Path,
    out: Path,
    check_files: bool = True,
) -> dict[str, Any]:
    entry = build_tileset_entry_draft(
        request_path,
        result_path,
        tag=tag,
        project_root=project_root,
        check_files=check_files,
    )
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "draft": str(out), "entry": entry}


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a ready v1 stable-entry draft for a compiled tileset"
    )
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--project-root", default=".", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--no-check-files",
        action="store_true",
        help="Only validate declared paths; do not require the atlas and .tres on disk",
    )
    args = parser.parse_args()
    try:
        payload = write_tileset_entry_draft(
            args.request,
            args.result,
            tag=args.tag,
            project_root=args.project_root,
            out=args.out,
            check_files=not args.no_check_files,
        )
    except TileSetEntryDraftError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
