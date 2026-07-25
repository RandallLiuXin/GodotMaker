#!/usr/bin/env python3
"""Update ASSETS.md rows from v1 generated-asset stable entries.

Each input is one stable entry at its canonical
``.godotmaker/asset-generation/entries/<tag>/<asset_id>.json`` path. The entry is
validated against the v1 schema before any row is touched, and the row records
the entry pointer — never a duplicated path snapshot — so the entry stays the
single source of truth for the asset.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from asset_stable_entry import (
    StableEntryError,
    entry_relative_path,
    validate_entry,
)


class AssetsMdUpdateError(Exception):
    """Raised when ASSETS.md cannot be updated from stable entries."""


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AssetsMdUpdateError(f"Invalid JSON: {path}") from exc


def _load_entries(
    entry_paths: list[Path], *, project_root: Path
) -> list[tuple[str, dict[str, Any]]]:
    """Validate each stable entry and pair it with its canonical pointer.

    ``validate_entry(check_files=True)`` proves identity, schema, and that every
    referenced file exists, so a row can only ever be promoted from an entry
    whose asset is really on disk.
    """
    entries: list[tuple[str, dict[str, Any]]] = []
    seen: set[tuple[str, str]] = set()
    for raw_path in entry_paths:
        entry_path = Path(raw_path)
        data = _load_json(entry_path)
        try:
            entry = validate_entry(data, project_root=project_root, check_files=True)
        except StableEntryError as exc:
            raise AssetsMdUpdateError(f"{entry_path}: {exc}") from exc
        tag = entry["tag"]
        asset_id = entry["asset_id"]
        key = (tag, asset_id)
        if key in seen:
            raise AssetsMdUpdateError(f"Duplicate entry for {tag}/{asset_id}")
        seen.add(key)
        canonical = entry_relative_path(tag, asset_id)
        if entry_path.resolve() != (project_root / canonical).resolve():
            raise AssetsMdUpdateError(
                f"{entry_path} must be the canonical entry path {canonical}"
            )
        entries.append((canonical, entry))
    return entries


def _split_markdown_row(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    if len(cells) < 8:
        return None
    return cells


def _format_markdown_row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |\n"


def _merge_generation_params(current: str, additions: dict[str, str]) -> str:
    current = current.strip()
    if current in {"", "-", "—"}:
        parts: list[str] = []
    else:
        parts = [part.strip() for part in current.split(";") if part.strip()]

    existing_keys: set[str] = set()
    for part in parts:
        if "=" in part:
            existing_keys.add(part.split("=", 1)[0].strip())

    for key, value in additions.items():
        if key not in existing_keys:
            parts.append(f"{key}={value}")

    return "; ".join(parts) if parts else "—"


def _entry_params(entry_path: str) -> dict[str, str]:
    return {"manifest_entry": entry_path}


def update_assets_md(
    assets_md: Path,
    entry_paths: list[Path],
    *,
    status: str = "generated",
) -> dict[str, object]:
    """Update ASSETS.md rows that match the provided stable entries."""
    assets_md = Path(assets_md)
    if not assets_md.exists():
        raise AssetsMdUpdateError(f"ASSETS.md not found: {assets_md}")
    project_root = assets_md.parent
    entries = _load_entries(entry_paths, project_root=project_root)
    entries_by_key = {
        (entry["tag"], entry["asset_id"]): entry_path
        for entry_path, entry in entries
    }
    remaining = set(entries_by_key.keys())

    lines = assets_md.read_text(encoding="utf-8").splitlines(keepends=True)
    output: list[str] = []
    updated: list[str] = []
    row_re = re.compile(r"^\s*\|")

    for line in lines:
        cells = _split_markdown_row(line) if row_re.match(line) else None
        if cells is None or len(cells) < 8:
            output.append(line)
            continue
        tag = cells[1]
        asset_id = cells[2]
        key = (tag, asset_id)
        if key not in entries_by_key:
            output.append(line)
            continue

        cells[5] = _merge_generation_params(
            cells[5], _entry_params(entries_by_key[key])
        )
        cells[7] = status
        output.append(_format_markdown_row(cells))
        updated.append(asset_id)
        remaining.discard(key)

    if remaining:
        missing = ", ".join(f"{tag}/{asset_id}" for tag, asset_id in sorted(remaining))
        raise AssetsMdUpdateError(f"ASSETS.md missing rows for entries: {missing}")

    with tempfile.NamedTemporaryFile(
        delete=False,
        dir=str(assets_md.parent),
        suffix=".md",
        mode="w",
        encoding="utf-8",
    ) as handle:
        tmp_path = Path(handle.name)
        handle.writelines(output)
    try:
        tmp_path.replace(assets_md)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    return {
        "ok": True,
        "path": str(assets_md),
        "updated": updated,
        "status": status,
    }


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Update ASSETS.md rows from v1 generated-asset stable entries"
    )
    parser.add_argument("--assets-md", default="ASSETS.md", help="ASSETS.md path")
    parser.add_argument(
        "--entry-file",
        action="append",
        required=True,
        help="Canonical stable entry JSON used to update one ASSETS.md row",
    )
    parser.add_argument("--status", default="generated", help="Status to write")
    args = parser.parse_args()

    try:
        result = update_assets_md(
            Path(args.assets_md),
            [Path(path) for path in args.entry_file],
            status=args.status,
        )
    except AssetsMdUpdateError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
