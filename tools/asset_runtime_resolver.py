#!/usr/bin/env python3
"""Resolve one v1 stable entry into a worker runtime snapshot.

The generated-asset root index and ASSETS.md deliberately retain only stable
identity and a ``manifest_entry`` pointer.  This tool is the single,
fail-closed reader for that pointer: it validates the entry, proves its files
still exist, and emits the small runtime contract a worker may consume.

Reference-only entries remain valid stable entries, but they are never worker
runtime assets and therefore cannot produce a runtime snapshot.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from asset_stable_entry import (
    REFERENCE_LAYOUTS,
    StableEntryError,
    _load_json,
    entry_relative_path,
    validate_entry,
)


class AssetRuntimeResolverError(Exception):
    """Raised when a stable entry cannot safely become a runtime snapshot."""


def _split_markdown_row(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    return [cell.strip() for cell in stripped.strip("|").split("|")]


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
    """Return the manifest pointer from one unambiguous ASSETS.md row."""
    assets_md = Path(assets_md)
    if not assets_md.exists():
        raise AssetRuntimeResolverError(f"ASSETS.md not found: {assets_md}")

    matches: list[list[str]] = []
    for line in assets_md.read_text(encoding="utf-8").splitlines():
        cells = _split_markdown_row(line)
        if cells is None or len(cells) < 8:
            continue
        if cells[1] == tag and cells[2] == asset_id:
            matches.append(cells)

    if not matches:
        raise AssetRuntimeResolverError(f"ASSETS.md row not found for {tag}/{asset_id}")
    if len(matches) != 1:
        raise AssetRuntimeResolverError(f"ASSETS.md has multiple rows for {tag}/{asset_id}")

    row = matches[0]
    if row[7] != "generated":
        raise AssetRuntimeResolverError(
            f"ASSETS.md row for {tag}/{asset_id} has status {row[7]!r}; expected 'generated'"
        )
    return _manifest_entry_from_params(row[5])


def _canonical_entry_path(project_root: Path, pointer: str) -> Path:
    """Resolve a project-relative pointer without permitting path traversal."""
    if not isinstance(pointer, str) or not pointer.strip():
        raise AssetRuntimeResolverError("manifest_entry must be a non-empty path")
    if "\\" in pointer:
        raise AssetRuntimeResolverError("manifest_entry must use forward slashes")
    raw_parts = pointer.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise AssetRuntimeResolverError(
            "manifest_entry must not contain empty, '.' or '..' segments"
        )
    relative = Path(pointer)
    if relative.is_absolute() or relative.drive:
        raise AssetRuntimeResolverError("manifest_entry must be project-relative")

    root = Path(project_root).resolve()
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root):
        raise AssetRuntimeResolverError("manifest_entry resolves outside the project root")
    if not resolved.exists():
        raise AssetRuntimeResolverError(f"Entry file not found: {pointer}")
    return resolved


def resolve_manifest_entry(
    manifest_entry: str,
    *,
    project_root: Path,
    expected_tag: str | None = None,
    expected_asset_id: str | None = None,
) -> dict[str, Any]:
    """Return a stable, minimal runtime snapshot from one canonical pointer."""
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
    if entry_path != (root / canonical).resolve():
        raise AssetRuntimeResolverError("manifest_entry resolves outside the canonical entry location")
    if expected_tag is not None and tag != expected_tag:
        raise AssetRuntimeResolverError(
            f"manifest_entry tag {tag!r} does not match ASSETS.md tag {expected_tag!r}"
        )
    if expected_asset_id is not None and asset_id != expected_asset_id:
        raise AssetRuntimeResolverError(
            "manifest_entry asset_id "
            f"{asset_id!r} does not match ASSETS.md asset_id {expected_asset_id!r}"
        )
    if entry["processing_status"] != "ready":
        raise AssetRuntimeResolverError(
            f"{manifest_entry} processing_status is {entry['processing_status']}; expected ready"
        )
    if entry["source_layout"]["type"] in REFERENCE_LAYOUTS:
        raise AssetRuntimeResolverError(
            f"{manifest_entry} is reference-only and cannot produce a worker runtime snapshot"
        )

    artifact = entry.get("godot_artifact")
    if not isinstance(artifact, dict):
        raise AssetRuntimeResolverError(
            f"{manifest_entry} has no godot_artifact for a runtime asset"
        )

    # Construct fresh dictionaries rather than returning the entry body so the
    # output has no internal fields and keeps a deterministic field order.
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


def resolve_assets_row(
    assets_md: Path,
    *,
    tag: str,
    asset_id: str,
    project_root: Path,
) -> dict[str, Any]:
    """Resolve the pointer in one current-tag ASSETS.md row."""
    pointer = manifest_entry_from_assets_row(assets_md, tag=tag, asset_id=asset_id)
    return resolve_manifest_entry(
        pointer,
        project_root=project_root,
        expected_tag=tag,
        expected_asset_id=asset_id,
    )


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve a v1 manifest_entry into a worker runtime snapshot"
    )
    parser.add_argument("--project-root", default=".", type=Path)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--manifest-entry", help="Canonical stable entry pointer")
    source.add_argument(
        "--assets-md",
        type=Path,
        help="ASSETS.md from which to read a manifest_entry pointer",
    )
    parser.add_argument("--tag", help="ASSETS.md tag (required with --assets-md)")
    parser.add_argument("--asset-id", help="ASSETS.md asset ID (required with --assets-md)")
    args = parser.parse_args()

    try:
        if args.manifest_entry:
            if args.tag is not None or args.asset_id is not None:
                parser.error("--tag and --asset-id are only valid with --assets-md")
            snapshot = resolve_manifest_entry(
                args.manifest_entry, project_root=args.project_root
            )
        else:
            if not args.tag or not args.asset_id:
                parser.error("--assets-md requires --tag and --asset-id")
            snapshot = resolve_assets_row(
                args.assets_md,
                tag=args.tag,
                asset_id=args.asset_id,
                project_root=args.project_root,
            )
    except AssetRuntimeResolverError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(json.dumps(snapshot, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
