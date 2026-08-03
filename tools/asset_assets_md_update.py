#!/usr/bin/env python3
"""Update ASSETS.md rows from v1 generated-asset stable entries.

Each input is one stable entry at its canonical
``.godotmaker/asset-generation/entries/<tag>/<asset_id>.json`` path. The entry is
validated against the v1 schema before any row is touched, and the row records
the entry pointer — never a duplicated path snapshot — so the entry stays the
single source of truth for the asset.

Runtime entries may promote a row only when they are genuinely
worker-consumable. A registered reference-only entry has a separate completion
path: it proves an accepted scene/style reference exists without claiming that
a worker can consume it as a runtime artifact.
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
    REFERENCE_LAYOUTS,
    StableEntryError,
    entry_relative_path,
    validate_entry,
)
from asset_generation_index import GenerationIndexError, check_index

# The only readiness state that means "a worker can load this asset now".
PROMOTABLE_STATUS = "ready"
REFERENCE_PROMOTABLE_STATUSES = {"source_ready"}
ROOT_INDEX_RELATIVE = ".godotmaker/asset-generation/manifest.json"
GENERATED_ROW_STATUS = "generated"
ASSETS_MD_MIN_CELLS = 8
ASSET_TABLE_TITLE = "Asset Table"
ASSET_TABLE_LEVEL = 2
ASSET_TABLE_HEADING = f"{'#' * ASSET_TABLE_LEVEL} {ASSET_TABLE_TITLE}"
_SEPARATOR_CELL = re.compile(r"^:?-{3,}:?$")
ASSETS_MD_TAG_COLUMN = 1
ASSETS_MD_ASSET_ID_COLUMN = 2
ASSETS_MD_PARAMS_COLUMN = 5
ASSETS_MD_STATUS_COLUMN = 7


def is_separator_row(line: str) -> bool:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return False
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    return bool(cells) and all(_SEPARATOR_CELL.match(cell) for cell in cells)


class AssetsMdUpdateError(Exception):
    """Raised when ASSETS.md cannot be updated from stable entries."""


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AssetsMdUpdateError(f"Invalid JSON: {path}") from exc


def _assert_promotable(entry: dict[str, Any], entry_path: Path) -> bool:
    """Validate an entry's completion path and return whether it is a reference.

    ``validate_entry`` proves the entry is well-formed and its files exist, but a
    well-formed runtime entry can still be mid-flight (``pending``,
    ``source_ready``, ``compiled``) or failed outright. A screen reference is
    intentionally different: it completes at ``source_ready``. That status does
    not make a reference worker-consumable.
    """
    is_reference = entry["source_layout"]["type"] in REFERENCE_LAYOUTS
    status = entry["processing_status"]
    if is_reference and status in REFERENCE_PROMOTABLE_STATUSES:
        return True
    expected_status = "source_ready" if is_reference else PROMOTABLE_STATUS
    if status != expected_status:
        raise AssetsMdUpdateError(
            f"{entry_path} processing_status is {status}; only a {expected_status} "
            f"{'reference' if is_reference else 'runtime'} entry may update an "
            "ASSETS.md row"
        )
    return False


def _assert_registered_reference(
    entry: dict[str, Any], entry_path: Path, *, project_root: Path
) -> None:
    """Require a reference to pass the root-index gate before completion.

    A reference has no runtime artifact, so its ``source_ready`` status is
    enough only after the canonical entry is registered and the root index
    schema-validates every pointer. The caller separately validates this entry's
    source file, avoiding unrelated pending entries from other tags blocking a
    reference-only completion. The membership check prevents a valid but
    unregistered entry from changing ASSETS.md directly.
    """
    index_path = project_root / ROOT_INDEX_RELATIVE
    try:
        check_index(index_path, project_root=project_root, check_entries=True)
    except GenerationIndexError as exc:
        raise AssetsMdUpdateError(
            f"Reference entry cannot pass the root-index gate: {exc}"
        ) from exc

    index_data = _load_json(index_path)
    expected = {
        "asset_id": entry["asset_id"],
        "tag": entry["tag"],
        "entry_path": entry_relative_path(entry["tag"], entry["asset_id"]),
    }
    if expected not in index_data["entries"]:
        raise AssetsMdUpdateError(
            f"{entry_path} is not registered in the root index as "
            f"{expected['entry_path']}"
        )


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
        is_reference = _assert_promotable(entry, entry_path)
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
        if is_reference:
            _assert_registered_reference(
                entry, entry_path, project_root=project_root
            )
        entries.append((canonical, entry))
    return entries


def split_assets_md_row(line: str) -> list[str] | None:
    """Return one contract-shaped ASSETS.md row, or ``None`` otherwise."""
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    if len(cells) < ASSETS_MD_MIN_CELLS:
        return None
    if is_separator_row(line):
        return None
    return cells


def _heading_level(line: str) -> int | None:
    """Return the ATX heading level of a line, or ``None`` if it is not one."""
    stripped = line.strip()
    hashes = len(stripped) - len(stripped.lstrip("#"))
    if not hashes or not stripped[hashes:].startswith(" "):
        return None
    return hashes


def _outside_code_fences(lines: list[str]):
    """Yield ``(index, line)`` for lines that are not inside a fenced block.

    A document may quote its own structure in an example block. Those lines are
    prose, not the manifest, and must not be able to anchor or terminate a
    section.
    """
    fence: str | None = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if fence is not None:
            if stripped.startswith(fence):
                fence = None
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fence = stripped[:3]
            continue
        yield index, line


def asset_table_bounds(lines: list[str]) -> tuple[int, int] | None:
    """Return the ``[start, end)`` line span of the ``## Asset Table`` section.

    ASSETS.md holds several Markdown tables and the Asset Table is not the only
    one wide enough to look like an asset row — the Visual Asset Contract and
    Budget Tracking tables also parse as eight-plus cells. Selecting rows by
    column count therefore reads and writes whichever table happens to sit last
    in the file.

    The heading must be exactly ``## Asset Table``, at the template's own level,
    and must be unique: accepting any depth let a nested ``### Asset Table``
    example earlier in the document hijack the whole manifest, which is the very
    failure this anchor exists to prevent. Fenced blocks are skipped so a quoted
    example cannot anchor it either. Returns ``None`` when the heading is absent.
    """
    starts = [
        index
        for index, line in _outside_code_fences(lines)
        if _heading_level(line) == ASSET_TABLE_LEVEL
        and line.strip()[ASSET_TABLE_LEVEL:].strip().lower()
        == ASSET_TABLE_TITLE.lower()
    ]
    if not starts:
        return None
    if len(starts) > 1:
        raise AssetsMdUpdateError(
            f"ASSETS.md has {len(starts)} '{ASSET_TABLE_HEADING}' sections; the "
            "asset manifest must be unambiguous"
        )
    start = starts[0] + 1
    for index, line in _outside_code_fences(lines):
        if index >= start and _heading_level(line) is not None:
            return start, index
    return start, len(lines)


def iter_asset_rows(lines: list[str]):
    """Yield ``(index, cells)`` for every Asset Table *data* row.

    The header row is as wide as the data it labels, so a table that has not
    been filled in yet — the state of a project's first tag — would otherwise
    report its own header as an asset and let a writer insert between the header
    and its ``|---|`` separator, destroying the table. A row immediately
    followed by a separator is the header, which is exactly the Markdown rule.
    """
    bounds = asset_table_bounds(lines)
    if bounds is None:
        # Only the Asset Table is the asset manifest. Guessing a table by column
        # count is what let rows be read from, and written into, the Visual Asset
        # Contract; the readers that promote and resolve must not keep that
        # branch open just because a document is malformed.
        raise AssetsMdUpdateError(
            f"ASSETS.md has no '{ASSET_TABLE_HEADING}' section; the asset "
            "manifest cannot be located"
        )
    table = [
        index for index in range(*bounds) if split_assets_md_row(lines[index]) is not None
    ]
    if table and not any(is_separator_row(lines[index]) for index in range(*bounds)):
        # Header detection is "the row followed by the |---| separator". Without
        # a separator there is no header to recognise, and the column labels
        # would be returned as an asset row.
        raise AssetsMdUpdateError(
            f"ASSETS.md '{ASSET_TABLE_HEADING}' has rows but no |---| separator; "
            "its header cannot be told from its data"
        )
    for index in table:
        following = lines[index + 1] if index + 1 < bounds[1] else ""
        if is_separator_row(following):
            continue
        yield index, split_assets_md_row(lines[index])


def format_assets_md_row(cells: list[str], newline: str = "\n") -> str:
    """Render one row, ending it the way the document it joins already ends."""
    return "| " + " | ".join(cells) + " |" + newline


def document_newline(lines: list[str], default: str = "\n") -> str:
    """Return the line ending the document already uses.

    Rows are rendered, not copied, so a hard-coded ``\\n`` would leave bare LF
    lines inside a CRLF document — a partial rewrite that shows up as noise in
    every later diff.
    """
    for line in lines:
        if line.endswith("\r\n"):
            return "\r\n"
        if line.endswith("\n"):
            return "\n"
    return default


def merge_generation_params(current: str, additions: dict[str, str]) -> str:
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

    # newline="" on both ends: read_text() would translate CRLF to LF and the
    # write would then rewrite every line in the file, burying a three-line
    # change in a whole-file diff and flipping back on the next checkout.
    with assets_md.open(encoding="utf-8", newline="") as handle:
        output = handle.readlines()
    newline = document_newline(output)
    updated: list[str] = []

    # Only the Asset Table is the asset manifest. The Visual Asset Contract and
    # Budget Tracking tables are just as wide, so matching by column count alone
    # would let an entry rewrite a row in a table that never described it.
    for index, cells in iter_asset_rows(output):
        tag = cells[ASSETS_MD_TAG_COLUMN]
        asset_id = cells[ASSETS_MD_ASSET_ID_COLUMN]
        key = (tag, asset_id)
        if key not in entries_by_key:
            continue

        cells[ASSETS_MD_PARAMS_COLUMN] = merge_generation_params(
            cells[ASSETS_MD_PARAMS_COLUMN], _entry_params(entries_by_key[key])
        )
        cells[ASSETS_MD_STATUS_COLUMN] = status
        output[index] = format_assets_md_row(cells, newline)
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
        newline="",
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
