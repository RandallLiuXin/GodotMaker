#!/usr/bin/env python3
"""Update ASSETS.md rows from asset-generation manifest entries."""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


class AssetsMdUpdateError(Exception):
    """Raised when ASSETS.md cannot be updated from manifest entries."""


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AssetsMdUpdateError(f"Invalid JSON: {path}") from exc


def _entry_from_data(data: Any, path: Path) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise AssetsMdUpdateError(f"{path} entry must be an object")
    if isinstance(data.get("assets"), list):
        raise AssetsMdUpdateError(f"{path} must contain one asset entry, not a manifest")
    return data


def _string_field(entry: dict[str, Any], field: str, entry_path: Path) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise AssetsMdUpdateError(f"{entry_path} entry missing {field}")
    return value.strip()


def _optional_string(entry: dict[str, Any], field: str) -> str | None:
    value = entry.get(field)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _resolve_project_path(project_root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return project_root / path


def _load_entries(entry_paths: list[Path], *, project_root: Path) -> list[tuple[Path, dict[str, Any]]]:
    entries: list[tuple[Path, dict[str, Any]]] = []
    seen: set[tuple[str, str]] = set()
    for entry_path in entry_paths:
        entry_path = Path(entry_path)
        entry = _entry_from_data(_load_json(entry_path), entry_path)
        tag = _string_field(entry, "tag", entry_path)
        asset_id = _string_field(entry, "asset_id", entry_path)
        key = (tag, asset_id)
        if key in seen:
            raise AssetsMdUpdateError(f"Duplicate entry for {tag}/{asset_id}")
        seen.add(key)
        final_path = _optional_string(entry, "final_path")
        if final_path is None:
            raise AssetsMdUpdateError(f"{entry_path} entry missing final_path")
        resolved_final_path = _resolve_project_path(project_root, final_path)
        if not resolved_final_path.exists():
            raise AssetsMdUpdateError(f"{entry_path} final_path does not exist: {final_path}")
        entries.append((entry_path, entry))
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


def _entry_params(entry_path: Path, entry: dict[str, Any]) -> dict[str, str]:
    return {"manifest_entry": str(entry_path).replace("\\", "/")}


def update_assets_md(
    assets_md: Path,
    entry_paths: list[Path],
    *,
    status: str = "generated",
) -> dict[str, object]:
    """Update ASSETS.md rows that match the provided manifest entries."""
    assets_md = Path(assets_md)
    if not assets_md.exists():
        raise AssetsMdUpdateError(f"ASSETS.md not found: {assets_md}")
    project_root = assets_md.parent
    entries = _load_entries(entry_paths, project_root=project_root)
    entries_by_key = {
        (_string_field(entry, "tag", entry_path), _string_field(entry, "asset_id", entry_path)): (entry_path, entry)
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

        entry_path, entry = entries_by_key[key]
        cells[5] = _merge_generation_params(cells[5], _entry_params(entry_path, entry))
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
    parser = argparse.ArgumentParser(description="Update ASSETS.md rows from manifest entries")
    parser.add_argument("--assets-md", default="ASSETS.md", help="ASSETS.md path")
    parser.add_argument(
        "--entry-file",
        action="append",
        required=True,
        help="JSON asset entry used to update one ASSETS.md row",
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
