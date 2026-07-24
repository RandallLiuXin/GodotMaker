#!/usr/bin/env python3
"""Validate and serialize the v1 generated-asset root index.

The root index is the single index of generated stable entries. It stores only
stable identity and a pointer to each entry file; it never duplicates a full
entry body. It lives at::

    .godotmaker/asset-generation/manifest.json

Each item points at one stable entry::

    {
      "asset_id": "player",
      "tag": "v0.1.0",
      "entry_path": ".godotmaker/asset-generation/entries/v0.1.0/player.json"
    }

This is the v1.0.0 contract. An old ``runtime_artifact`` manifest (one that
stores full entry bodies under ``assets``) is not migrated or dual-read; it
fails with a clear message and must be regenerated through ``/gm-asset``.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from asset_stable_entry import (
    LEGACY_FIELDS,
    SCHEMA_VERSION,
    StableEntryError,
    _load_json,
    _safe_identifier,
    entry_relative_path,
    validate_entry,
)

INDEX_ITEM_KEYS = {"asset_id", "tag", "entry_path"}


class GenerationIndexError(Exception):
    """Raised when the generated-asset root index is invalid."""


def _regenerate_error(reason: str) -> GenerationIndexError:
    return GenerationIndexError(
        f"{reason}; v1.0.0 provides no migration or compatibility read. "
        "Regenerate generated assets through /gm-asset."
    )


def _reject_legacy_container(data: dict[str, Any]) -> None:
    if "assets" in data:
        raise _regenerate_error("Legacy runtime_artifact manifest detected (assets key)")
    present = LEGACY_FIELDS.intersection(data.keys())
    if present:
        listed = ", ".join(sorted(present))
        raise _regenerate_error(f"Legacy runtime_artifact fields detected ({listed})")


def _validate_item(item: Any, *, index: int) -> tuple[str, str, str]:
    if not isinstance(item, dict):
        raise GenerationIndexError(f"entries[{index}] must be an object")
    _reject_legacy_container(item)
    extra = set(item.keys()) - INDEX_ITEM_KEYS
    if extra:
        listed = ", ".join(sorted(extra))
        raise GenerationIndexError(
            f"entries[{index}] must only hold identity and a pointer; "
            f"unexpected fields: {listed}"
        )

    def _string(field: str) -> str:
        value = item.get(field)
        if not isinstance(value, str) or not value.strip():
            raise GenerationIndexError(f"entries[{index}].{field} must be a non-empty string")
        return value

    asset_id = _string("asset_id")
    tag = _string("tag")
    entry_path = _string("entry_path")
    try:
        _safe_identifier(asset_id, "asset_id")
        _safe_identifier(tag, "tag")
        expected = entry_relative_path(tag, asset_id)
    except StableEntryError as exc:
        raise GenerationIndexError(f"entries[{index}]: {exc}") from exc
    if Path(entry_path).as_posix() != expected:
        raise GenerationIndexError(
            f"entries[{index}].entry_path must be {expected}"
        )
    return tag, asset_id, entry_path


def check_index(
    index_path: Path,
    *,
    project_root: Path | None = None,
    check_entries: bool = False,
) -> dict[str, Any]:
    """Validate one root index and return a summary."""
    index_path = Path(index_path)
    root = Path(project_root) if project_root is not None else index_path.parent.parent.parent

    data = _load_json_index(index_path)
    if not isinstance(data, dict):
        raise GenerationIndexError("Root index must be a JSON object")
    _reject_legacy_container(data)

    if data.get("version") != SCHEMA_VERSION:
        raise GenerationIndexError(f"Root index version must be {SCHEMA_VERSION}")
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise GenerationIndexError("Root index entries must be a list")

    seen: set[tuple[str, str]] = set()
    entry_checks = 0
    for index, item in enumerate(entries):
        tag, asset_id, entry_path = _validate_item(item, index=index)
        key = (tag, asset_id)
        if key in seen:
            raise GenerationIndexError(f"Duplicate asset_id for tag {tag}: {asset_id}")
        seen.add(key)

        if check_entries:
            resolved = root / entry_path
            if not resolved.exists():
                raise GenerationIndexError(f"Entry file not found: {entry_path}")
            try:
                entry = validate_entry(_load_json_index(resolved), project_root=root)
            except StableEntryError as exc:
                raise GenerationIndexError(f"{entry_path}: {exc}") from exc
            if entry.get("asset_id") != asset_id or entry.get("tag") != tag:
                raise GenerationIndexError(
                    f"{entry_path} identity does not match index item {key}"
                )
            entry_checks += 1

    return {
        "ok": True,
        "path": str(index_path),
        "entry_count": len(entries),
        "check_entries": check_entries,
        "entry_checks": entry_checks,
    }


def _load_json_index(path: Path) -> Any:
    try:
        return _load_json(path)
    except StableEntryError as exc:
        raise GenerationIndexError(str(exc)) from exc


def _load_index(index_path: Path) -> dict[str, Any]:
    if not index_path.exists():
        return {"version": SCHEMA_VERSION, "entries": []}
    data = _load_json_index(index_path)
    if not isinstance(data, dict):
        raise GenerationIndexError(f"Root index must be an object: {index_path}")
    _reject_legacy_container(data)
    if data.get("version") != SCHEMA_VERSION:
        raise GenerationIndexError(f"Root index version must be {SCHEMA_VERSION}: {index_path}")
    if not isinstance(data.get("entries"), list):
        raise GenerationIndexError(f"Root index missing entries list: {index_path}")
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


def update_index(
    index_path: Path,
    entry_paths: list[Path],
    *,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Upsert stable-entry pointers into the root index."""
    index_path = Path(index_path)
    data = _load_index(index_path)

    items_by_key: dict[tuple[str, str], dict[str, str]] = {}
    for index, item in enumerate(data["entries"]):
        tag, asset_id, entry_path = _validate_item(item, index=index)
        items_by_key[(tag, asset_id)] = {
            "asset_id": asset_id,
            "tag": tag,
            "entry_path": entry_path,
        }

    upserted: list[str] = []
    for entry_path in entry_paths:
        try:
            entry = validate_entry(_load_json_index(Path(entry_path)))
        except StableEntryError as exc:
            raise GenerationIndexError(f"{entry_path}: {exc}") from exc
        tag = entry["tag"]
        asset_id = entry["asset_id"]
        items_by_key[(tag, asset_id)] = {
            "asset_id": asset_id,
            "tag": tag,
            "entry_path": entry_relative_path(tag, asset_id),
        }
        upserted.append(asset_id)

    next_data = {
        "version": SCHEMA_VERSION,
        "entries": list(items_by_key.values()),
    }

    index_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        delete=False,
        dir=str(index_path.parent),
        suffix=".json",
        mode="w",
        encoding="utf-8",
    ) as handle:
        tmp_path = Path(handle.name)
        json.dump(next_data, handle, indent=2)
        handle.write("\n")
    try:
        check_index(tmp_path, project_root=project_root)
        _write_atomic(index_path, next_data)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    return {
        "ok": True,
        "path": str(index_path),
        "entry_count": len(next_data["entries"]),
        "upserted": upserted,
    }


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and serialize the v1 generated-asset root index"
    )
    parser.add_argument(
        "index",
        nargs="?",
        default=".godotmaker/asset-generation/manifest.json",
        help="Root index path",
    )
    parser.add_argument("--project-root", default=".", type=Path)
    parser.add_argument(
        "--entry-file",
        action="append",
        help="Stable entry JSON file to upsert as a pointer",
    )
    parser.add_argument(
        "--check-entries",
        action="store_true",
        help="Load and validate each referenced stable entry file",
    )
    args = parser.parse_args()

    try:
        if args.entry_file:
            result = update_index(
                Path(args.index),
                [Path(path) for path in args.entry_file],
                project_root=args.project_root,
            )
        else:
            result = check_index(
                Path(args.index),
                project_root=args.project_root,
                check_entries=args.check_entries,
            )
    except (GenerationIndexError, StableEntryError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
