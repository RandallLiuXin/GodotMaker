#!/usr/bin/env python3
"""Upsert entries into the asset-generation handoff manifest."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from asset_generation_manifest_check import ManifestCheckError, check_manifest


class ManifestUpdateError(Exception):
    """Raised when asset-generation manifest entries cannot be updated."""


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ManifestUpdateError(f"Invalid JSON: {path}") from exc


def _entry_from_data(data: Any, path: Path) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ManifestUpdateError(f"{path} entry must be an object")
    if isinstance(data.get("assets"), list):
        raise ManifestUpdateError(f"{path} must contain one asset entry, not a manifest")
    return data


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "assets": []}
    data = _load_json(path)
    if not isinstance(data, dict):
        raise ManifestUpdateError(f"Manifest must be an object: {path}")
    if data.get("version") != 1:
        raise ManifestUpdateError(f"Manifest version must be 1: {path}")
    if "assets" not in data:
        raise ManifestUpdateError(f"Manifest missing assets: {path}")
    if not isinstance(data["assets"], list):
        raise ManifestUpdateError(f"Manifest assets must be a list: {path}")
    return data


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


def update_manifest(
    manifest_path: Path,
    entry_paths: list[Path],
    *,
    project_root: Path | None = None,
    check_files: bool = False,
) -> dict[str, object]:
    """Upsert entries into a manifest and validate the result before replacing."""
    manifest_path = Path(manifest_path)
    data = _load_manifest(manifest_path)
    existing_assets = data["assets"]
    assets_by_key: dict[tuple[str, str], dict[str, Any]] = {}

    for item in existing_assets:
        if not isinstance(item, dict):
            raise ManifestUpdateError("Existing manifest asset entries must be objects")
        asset_id = item.get("asset_id")
        if not isinstance(asset_id, str) or not asset_id.strip():
            raise ManifestUpdateError("Existing manifest asset entry missing asset_id")
        tag = item.get("tag")
        if not isinstance(tag, str) or not tag.strip():
            raise ManifestUpdateError("Existing manifest asset entry missing tag")
        key = (tag, asset_id)
        if key in assets_by_key:
            raise ManifestUpdateError(f"Existing manifest has duplicate asset_id for tag {tag}: {asset_id}")
        assets_by_key[key] = item

    upserted: list[str] = []
    for entry_path in entry_paths:
        entry = _entry_from_data(_load_json(Path(entry_path)), Path(entry_path))
        asset_id = entry.get("asset_id")
        if not isinstance(asset_id, str) or not asset_id.strip():
            raise ManifestUpdateError(f"{entry_path} entry missing asset_id")
        tag = entry.get("tag")
        if not isinstance(tag, str) or not tag.strip():
            raise ManifestUpdateError(f"{entry_path} entry missing tag")
        key = (tag, asset_id)
        assets_by_key[key] = entry
        upserted.append(asset_id)

    next_data = dict(data)
    next_data["version"] = 1
    next_data["assets"] = list(assets_by_key.values())

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        delete=False,
        dir=str(manifest_path.parent),
        suffix=".json",
        mode="w",
        encoding="utf-8",
    ) as handle:
        tmp_path = Path(handle.name)
        json.dump(next_data, handle, indent=2)
        handle.write("\n")

    try:
        check_manifest(tmp_path, project_root=project_root, check_files=check_files)
        _write_atomic(manifest_path, next_data)
    except ManifestCheckError as exc:
        raise ManifestUpdateError(str(exc)) from exc
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    return {
        "ok": True,
        "path": str(manifest_path),
        "asset_count": len(next_data["assets"]),
        "upserted": upserted,
    }


def _main() -> int:
    parser = argparse.ArgumentParser(description="Upsert asset-generation manifest entries")
    parser.add_argument(
        "--manifest",
        default=".godotmaker/asset-generation/manifest.json",
        help="Manifest path",
    )
    parser.add_argument(
        "--entry-file",
        action="append",
        required=True,
        help="JSON asset entry to upsert",
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="Project root for relative file checks",
    )
    parser.add_argument(
        "--check-files",
        action="store_true",
        help="Check referenced source, prompt, and final files before writing",
    )
    args = parser.parse_args()

    try:
        result = update_manifest(
            Path(args.manifest),
            [Path(path) for path in args.entry_file],
            project_root=Path(args.project_root),
            check_files=args.check_files,
        )
    except ManifestUpdateError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
