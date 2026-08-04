#!/usr/bin/env python3
"""Build ready stable-entry drafts for a validated platform-strip delivery."""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from asset_skill_contract_check import AssetContractError, check_request, check_result
from asset_stable_entry import SCHEMA_VERSION, StableEntryError, safe_identifier, validate_entry


FAMILY = "platform-strip"
LEVELS = ("L0", "L1", "L2", "L3", "L4")


class PlatformStripEntryDraftError(Exception):
    """Raised when a platform-strip result cannot become ready stable entries."""


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PlatformStripEntryDraftError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise PlatformStripEntryDraftError(f"{label} must be a JSON object: {path}")
    return value


def _segments(request: dict[str, Any]) -> tuple[str, list[str]]:
    spec = request.get("spec")
    if not isinstance(spec, dict) or set(spec) != {"kind", "grid", "segments"}:
        raise PlatformStripEntryDraftError(
            "platform-strip request.spec must contain exactly kind, grid, and segments"
        )
    kind = spec.get("kind")
    grid = spec.get("grid")
    segments = spec.get("segments")
    if kind not in {"single", "atlas"}:
        raise PlatformStripEntryDraftError("platform-strip spec.kind must be single or atlas")
    if (
        not isinstance(grid, dict)
        or set(grid) != {"columns", "rows", "cell_width", "cell_height"}
        or any(type(grid.get(key)) is not int or grid[key] <= 0 for key in grid)
        or grid["rows"] != 1
        or not isinstance(segments, list)
        or len(segments) < 3
        or grid["columns"] != len(segments)
    ):
        raise PlatformStripEntryDraftError(
            "platform-strip needs one positive fixed row with one declared segment per column"
        )

    names: list[str] = []
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict) or set(segment) != {"name", "role", "slot"}:
            raise PlatformStripEntryDraftError(
                f"platform-strip segment {index} must contain exactly name, role, and slot"
            )
        name = segment.get("name")
        expected_role = (
            "left_cap" if index == 0 else "right_cap" if index == len(segments) - 1 else "repeat_middle"
        )
        if (
            not isinstance(name, str)
            or not name.strip()
            or segment.get("role") != expected_role
            or segment.get("slot") != [index, 0]
        ):
            raise PlatformStripEntryDraftError(
                "platform-strip segments must be ordered left_cap/repeat_middle/right_cap slots"
            )
        try:
            safe_identifier(name, f"platform-strip segment {index} name")
        except StableEntryError as exc:
            raise PlatformStripEntryDraftError(str(exc)) from exc
        names.append(name)
    if len(set(names)) != len(names):
        raise PlatformStripEntryDraftError("platform-strip segment names must be unique")
    return kind, names


def _assert_passing_ladder(result: dict[str, Any]) -> None:
    validation = result.get("validation")
    if not isinstance(validation, dict) or validation.get("passed") is not True:
        raise PlatformStripEntryDraftError("result must report a passing validation")
    levels = validation.get("levels")
    if not isinstance(levels, dict) or any(levels.get(level) is not True for level in LEVELS):
        raise PlatformStripEntryDraftError("result must have passed L0-L4 before entries are drafted")


def build_platform_strip_entry_drafts(
    request_path: Path,
    result_path: Path,
    *,
    tag: str,
    project_root: Path,
    check_files: bool = True,
) -> list[dict[str, Any]]:
    """Return one ready bundle entry for every declared platform segment."""
    request = _load_object(request_path, "request")
    result = _load_object(result_path, "asset Skill result")
    try:
        check_request(request)
        check_result(result)
    except AssetContractError as exc:
        raise PlatformStripEntryDraftError(str(exc)) from exc
    if request.get("asset_type") != FAMILY or result.get("asset_type") != FAMILY:
        raise PlatformStripEntryDraftError("request and result must both be platform-strip")
    if not isinstance(tag, str) or not tag.strip():
        raise PlatformStripEntryDraftError("tag must be a non-empty string")

    kind, names = _segments(request)
    _assert_passing_ladder(result)
    bundle_id = request["asset_id"]
    root = f"res://assets/generated/{FAMILY}/{bundle_id}"
    extension = ".png" if kind == "single" else ".tres"
    artifact_type = "Texture2D" if kind == "single" else "AtlasTexture"
    expected_outputs = [
        {"role": "runtime", "name": name, "path": f"{root}/{name}{extension}", "godot_type": artifact_type}
        for name in names
    ]
    if result["outputs"] != expected_outputs:
        raise PlatformStripEntryDraftError(
            "result must expose every declared segment at its stable runtime path"
        )
    expected_sources = (
        [{"path": f"{root}/{name}.png", "layout": "single"} for name in names]
        if kind == "single"
        else [{"path": f"{root}/{bundle_id}.png", "layout": "region_atlas"}]
    )
    if result["sources"] != expected_sources:
        raise PlatformStripEntryDraftError(
            "result sources must exactly match the platform-strip request kind"
        )

    entries: list[dict[str, Any]] = []
    for name in names:
        source_path = f"{root}/{name}.png" if kind == "single" else f"{root}/{bundle_id}.png"
        entry = {
            "version": SCHEMA_VERSION,
            "asset_id": f"{bundle_id}--{name}",
            "tag": tag,
            "production_family": FAMILY,
            "bundle_id": bundle_id,
            "source_layout": {
                "type": "single" if kind == "single" else "region_atlas",
                "path": source_path,
            },
            "godot_artifact": {"type": artifact_type, "path": f"{root}/{name}{extension}"},
            "processing_status": "ready",
        }
        try:
            validate_entry(entry, project_root=Path(project_root), check_files=check_files)
        except StableEntryError as exc:
            raise PlatformStripEntryDraftError(str(exc)) from exc
        entries.append(entry)
    return entries


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", delete=False, dir=path.parent, suffix=".json"
    ) as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def write_platform_strip_entry_drafts(
    request_path: Path,
    result_path: Path,
    *,
    tag: str,
    project_root: Path,
    out_dir: Path,
    check_files: bool = True,
) -> dict[str, Any]:
    entries = build_platform_strip_entry_drafts(
        request_path, result_path, tag=tag, project_root=project_root, check_files=check_files
    )
    outputs: list[str] = []
    for entry in entries:
        target = Path(out_dir) / f"{entry['asset_id']}.json"
        _write_json(target, entry)
        outputs.append(str(target))
    return {"ok": True, "count": len(entries), "drafts": outputs}


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Build ready stable-entry drafts for a platform-strip delivery"
    )
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--project-root", default=".", type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--no-check-files", action="store_true")
    args = parser.parse_args()
    try:
        result = write_platform_strip_entry_drafts(
            args.request,
            args.result,
            tag=args.tag,
            project_root=args.project_root,
            out_dir=args.out_dir,
            check_files=not args.no_check_files,
        )
    except PlatformStripEntryDraftError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
