#!/usr/bin/env python3
"""Resolve one registered v1 stable entry into a worker runtime snapshot.

ASSETS.md keeps an asset's ``manifest_entry`` pointer while the generated root
index records which canonical entries are registered. This tool requires both
records to agree, validates the ready entry and its files, then emits only the
worker-facing runtime contract.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from asset_assets_md_update import (
    ASSETS_MD_ASSET_ID_COLUMN,
    ASSETS_MD_PARAMS_COLUMN,
    ASSETS_MD_STATUS_COLUMN,
    ASSETS_MD_TAG_COLUMN,
    GENERATED_ROW_STATUS,
    split_assets_md_row,
)
from asset_bundle_manifest import (
    BUNDLES_ROOT,
    AssetBundleManifestError,
    bundle_manifest_relative_path,
    validate_bundle_manifest,
)
from asset_generation_index import GenerationIndexError, check_index
from asset_stable_entry import (
    ENTRIES_ROOT,
    REFERENCE_LAYOUTS,
    WORK_ROOT,
    StableEntryError,
    _load_json,
    entry_relative_path,
    validate_entry,
)

ROOT_INDEX_PATH = ".godotmaker/asset-generation/manifest.json"


class AssetRuntimeResolverError(Exception):
    """Raised when a stable entry cannot safely become a runtime snapshot."""


def _read_assets_md(assets_md: Path) -> str:
    try:
        return assets_md.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise AssetRuntimeResolverError(f"Cannot read ASSETS.md: {assets_md}") from exc


def _manifest_entry_from_params(value: str) -> str:
    """Read exactly one ``manifest_entry`` value from ASSETS generation params."""
    matches: list[str] = []
    for item in value.split(";"):
        key, separator, candidate = item.strip().partition("=")
        if key == "manifest_entry" and separator:
            candidate = candidate.strip()
            if not candidate:
                raise AssetRuntimeResolverError("ASSETS.md manifest_entry must not be empty")
            matches.append(candidate)
    if not matches:
        raise AssetRuntimeResolverError("ASSETS.md row is missing manifest_entry")
    if len(matches) != 1:
        raise AssetRuntimeResolverError("ASSETS.md row must contain exactly one manifest_entry")
    return matches[0]


def manifest_entry_from_assets_row(
    assets_md: Path,
    *,
    tag: str,
    asset_id: str,
) -> str:
    """Return the registered pointer from one generated ASSETS.md row."""
    assets_md = Path(assets_md)
    matches: list[list[str]] = []
    for line in _read_assets_md(assets_md).splitlines():
        cells = split_assets_md_row(line)
        if cells is None:
            continue
        if (
            cells[ASSETS_MD_TAG_COLUMN] == tag
            and cells[ASSETS_MD_ASSET_ID_COLUMN] == asset_id
        ):
            matches.append(cells)

    if not matches:
        raise AssetRuntimeResolverError(f"ASSETS.md row not found for {tag}/{asset_id}")
    if len(matches) != 1:
        raise AssetRuntimeResolverError(f"ASSETS.md has multiple rows for {tag}/{asset_id}")

    row = matches[0]
    if row[ASSETS_MD_STATUS_COLUMN] != GENERATED_ROW_STATUS:
        raise AssetRuntimeResolverError(
            f"ASSETS.md row for {tag}/{asset_id} has status "
            f"{row[ASSETS_MD_STATUS_COLUMN]!r}; expected {GENERATED_ROW_STATUS!r}"
        )
    return _manifest_entry_from_params(row[ASSETS_MD_PARAMS_COLUMN])


def _canonical_entry_path(project_root: Path, pointer: str) -> Path:
    """Resolve only the exact v1 entry-path shape, before reading JSON."""
    if not isinstance(pointer, str) or not pointer.strip():
        raise AssetRuntimeResolverError("manifest_entry must be a non-empty path")
    if "\\" in pointer:
        raise AssetRuntimeResolverError("manifest_entry must use forward slashes")
    parts = pointer.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise AssetRuntimeResolverError(
            "manifest_entry must not contain empty, '.' or '..' segments"
        )
    expected_prefix = ENTRIES_ROOT.split("/")
    if (
        len(parts) != len(expected_prefix) + 2
        or parts[: len(expected_prefix)] != expected_prefix
        or not parts[-1].endswith(".json")
        or parts[-1] == ".json"
    ):
        raise AssetRuntimeResolverError(
            "manifest_entry must be a canonical entries/<tag>/<asset_id>.json path"
        )
    relative = Path(pointer)
    if relative.is_absolute() or relative.drive:
        raise AssetRuntimeResolverError("manifest_entry must be project-relative")

    root = Path(project_root).resolve()
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root):
        raise AssetRuntimeResolverError("manifest_entry resolves outside the project root")
    if resolved.is_relative_to((root / WORK_ROOT).resolve()):
        raise AssetRuntimeResolverError("manifest_entry must not resolve into the generation work/ workspace")
    if not resolved.is_file():
        raise AssetRuntimeResolverError(f"Entry file not found: {pointer}")
    return resolved


def _canonical_bundle_path(project_root: Path, pointer: str) -> Path:
    """Resolve only the exact v1 bundle-manifest path shape."""
    if not isinstance(pointer, str) or not pointer.strip():
        raise AssetRuntimeResolverError("manifest_entry must be a non-empty path")
    if "\\" in pointer:
        raise AssetRuntimeResolverError("manifest_entry must use forward slashes")
    parts = pointer.split("/")
    expected_prefix = BUNDLES_ROOT.split("/")
    if (
        any(part in {"", ".", ".."} for part in parts)
        or len(parts) != len(expected_prefix) + 2
        or parts[: len(expected_prefix)] != expected_prefix
        or not parts[-1].endswith(".json")
        or parts[-1] == ".json"
    ):
        raise AssetRuntimeResolverError(
            "manifest_entry must be a canonical bundles/<tag>/<bundle_id>.json path"
        )
    root = Path(project_root).resolve()
    resolved = (root / Path(pointer)).resolve()
    if not resolved.is_relative_to(root):
        raise AssetRuntimeResolverError("manifest_entry resolves outside the project root")
    if not resolved.is_file():
        raise AssetRuntimeResolverError(f"Bundle manifest not found: {pointer}")
    return resolved


def _assert_registered(
    *, project_root: Path, manifest_entry: str, tag: str, asset_id: str
) -> None:
    """Require a structurally valid root index that points at this entry.

    The resolver proves the requested entry's files below. Other entries may
    legitimately still be ``pending`` or ``source_ready`` without files, so the
    root index's all-entry file gate remains an explicit batch validation.
    """
    index_path = project_root / ROOT_INDEX_PATH
    try:
        check_index(index_path, project_root=project_root, check_entries=True)
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (GenerationIndexError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AssetRuntimeResolverError(f"Generated root index is invalid: {exc}") from exc

    registered = any(
        item.get("tag") == tag
        and item.get("asset_id") == asset_id
        and item.get("entry_path") == manifest_entry
        for item in index["entries"]
    )
    if not registered:
        raise AssetRuntimeResolverError(
            f"manifest_entry is not registered in {ROOT_INDEX_PATH}: {manifest_entry}"
        )


def _assert_assets_root(assets_md: Path, project_root: Path) -> Path:
    assets_path = Path(assets_md).resolve()
    if assets_path.parent != project_root:
        raise AssetRuntimeResolverError("ASSETS.md must be located at the project root")
    return assets_path


def _resolve_stable_entry(
    manifest_entry: str,
    *,
    project_root: Path,
    expected_tag: str | None = None,
    expected_asset_id: str | None = None,
) -> dict[str, Any]:
    """Return a registered runtime snapshot without consulting ASSETS.md."""
    root = Path(project_root).resolve()
    entry_path = _canonical_entry_path(root, manifest_entry)
    try:
        entry = validate_entry(_load_json(entry_path), project_root=root, check_files=True)
    except StableEntryError as exc:
        raise AssetRuntimeResolverError(f"{manifest_entry}: {exc}") from exc

    tag = entry["tag"]
    asset_id = entry["asset_id"]
    canonical = entry_relative_path(tag, asset_id)
    if manifest_entry != canonical:
        raise AssetRuntimeResolverError(
            f"manifest_entry must be the canonical entry path {canonical}"
        )
    if expected_tag is not None and tag != expected_tag:
        raise AssetRuntimeResolverError(
            f"manifest_entry tag {tag!r} does not match ASSETS.md tag {expected_tag!r}"
        )
    if expected_asset_id is not None and asset_id != expected_asset_id:
        raise AssetRuntimeResolverError(
            "manifest_entry asset_id "
            f"{asset_id!r} does not match ASSETS.md asset_id {expected_asset_id!r}"
        )
    _assert_registered(
        project_root=root,
        manifest_entry=manifest_entry,
        tag=tag,
        asset_id=asset_id,
    )
    if entry["processing_status"] != "ready":
        raise AssetRuntimeResolverError(
            f"{manifest_entry} processing_status is {entry['processing_status']}; expected ready"
        )
    if entry["source_layout"]["type"] in REFERENCE_LAYOUTS:
        raise AssetRuntimeResolverError(
            f"{manifest_entry} is reference-only and cannot produce a worker runtime snapshot"
        )

    artifact = entry["godot_artifact"]
    return {
        "asset_id": asset_id,
        "production_family": entry["production_family"],
        "source_layout": {
            "type": entry["source_layout"]["type"],
            "path": entry["source_layout"]["path"],
        },
        "godot_artifact": {
            "type": artifact["type"],
            "path": artifact["path"],
        },
    }


def _assert_bundle_assets_rows(
    manifest: dict[str, Any],
    *,
    pointer: str,
    assets_md: Path,
) -> None:
    for asset_id in manifest["asset_ids"]:
        row_pointer = manifest_entry_from_assets_row(
            assets_md, tag=manifest["tag"], asset_id=asset_id
        )
        if row_pointer != pointer:
            raise AssetRuntimeResolverError(
                f"ASSETS.md row for {manifest['tag']}/{asset_id} does not point at "
                "the requested bundle manifest"
            )


def _resolve_bundle_manifest(
    manifest_entry: str,
    *,
    project_root: Path,
    assets_md: Path,
    expected_tag: str | None = None,
    expected_asset_id: str | None = None,
) -> list[dict[str, Any]]:
    root = Path(project_root).resolve()
    path = _canonical_bundle_path(root, manifest_entry)
    try:
        manifest = validate_bundle_manifest(
            _load_json(path), project_root=root, check_files=True, check_registered=True
        )
    except (AssetBundleManifestError, StableEntryError) as exc:
        raise AssetRuntimeResolverError(f"{manifest_entry}: {exc}") from exc
    canonical = bundle_manifest_relative_path(
        manifest["tag"], manifest["bundle_id"]
    )
    if manifest_entry != canonical:
        raise AssetRuntimeResolverError(
            f"manifest_entry must be the canonical bundle path {canonical}"
        )
    if expected_tag is not None and manifest["tag"] != expected_tag:
        raise AssetRuntimeResolverError(
            f"bundle tag {manifest['tag']!r} does not match ASSETS.md tag "
            f"{expected_tag!r}"
        )
    if expected_asset_id is not None and expected_asset_id not in manifest["asset_ids"]:
        raise AssetRuntimeResolverError(
            f"bundle does not satisfy ASSETS.md asset_id {expected_asset_id!r}"
        )
    assets_path = _assert_assets_root(assets_md, root)
    _assert_bundle_assets_rows(
        manifest, pointer=manifest_entry, assets_md=assets_path
    )
    return [
        _resolve_stable_entry(
            pointer,
            project_root=root,
            expected_tag=manifest["tag"],
        )
        for pointer in manifest["entries"]
    ]


def resolve_manifest_entry(
    manifest_entry: str,
    *,
    project_root: Path,
    assets_md: Path,
    expected_tag: str | None = None,
    expected_asset_id: str | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    """Resolve one stable-entry or bundle pointer through every handoff gate."""
    root = Path(project_root).resolve()
    assets_path = _assert_assets_root(assets_md, root)
    if manifest_entry.startswith(f"{BUNDLES_ROOT}/"):
        return _resolve_bundle_manifest(
            manifest_entry,
            project_root=root,
            assets_md=assets_path,
            expected_tag=expected_tag,
            expected_asset_id=expected_asset_id,
        )
    snapshot = _resolve_stable_entry(
        manifest_entry,
        project_root=root,
        expected_tag=expected_tag,
        expected_asset_id=expected_asset_id,
    )
    entry_tag = expected_tag or manifest_entry.split("/")[-2]
    row_pointer = manifest_entry_from_assets_row(
        assets_path, tag=entry_tag, asset_id=snapshot["asset_id"]
    )
    if row_pointer != manifest_entry:
        raise AssetRuntimeResolverError(
            "ASSETS.md manifest_entry does not match the requested pointer"
        )
    return snapshot


def resolve_assets_row(
    assets_md: Path,
    *,
    tag: str,
    asset_id: str,
    project_root: Path,
) -> dict[str, Any] | list[dict[str, Any]]:
    """Resolve one current-tag ASSETS.md row through all handoff gates."""
    root = Path(project_root).resolve()
    assets_path = _assert_assets_root(assets_md, root)
    pointer = manifest_entry_from_assets_row(assets_path, tag=tag, asset_id=asset_id)
    return resolve_manifest_entry(
        pointer,
        project_root=root,
        assets_md=assets_path,
        expected_tag=tag,
        expected_asset_id=asset_id,
    )


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve one registered v1 entry or bundle into worker runtime snapshots"
    )
    parser.add_argument("--project-root", default=".", type=Path)
    parser.add_argument(
        "--assets-md",
        default=Path("ASSETS.md"),
        type=Path,
        help="Project-root ASSETS.md used by both input modes",
    )
    parser.add_argument("--manifest-entry", help="Canonical stable entry pointer")
    parser.add_argument("--tag", help="ASSETS.md tag (used with --asset-id)")
    parser.add_argument("--asset-id", help="ASSETS.md asset ID (used with --tag)")
    args = parser.parse_args()

    try:
        root = args.project_root.resolve()
        assets_md = args.assets_md if args.assets_md.is_absolute() else root / args.assets_md
        if args.manifest_entry is not None:
            if args.tag is not None or args.asset_id is not None:
                parser.error("--tag and --asset-id are not valid with --manifest-entry")
            snapshot = resolve_manifest_entry(
                args.manifest_entry, project_root=root, assets_md=assets_md
            )
        else:
            if not args.tag or not args.asset_id:
                parser.error("provide --manifest-entry or both --tag and --asset-id")
            snapshot = resolve_assets_row(
                assets_md,
                tag=args.tag,
                asset_id=args.asset_id,
                project_root=root,
            )
    except AssetRuntimeResolverError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(json.dumps(snapshot, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
