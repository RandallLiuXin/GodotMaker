#!/usr/bin/env python3
"""Declare the ASSETS.md rows a bundle production will fill.

Most families deliver one runtime asset per planned ASSETS.md row, so the row
the planner wrote is the row registration updates. A bundle family does not:
one `ui-kit`, `card-kit`, or `compact-prop-pack` production delivers many
separately bindable resources, and every one of them needs its own row before
`asset_assets_md_update.py` — which matches an entry to an existing
`(Tag, Name)` row and fails closed when there is none — can promote it.

The names are derived from the request, so the rows can be declared during
planning, before the Skill runs, and every declared output is traceable back to
the bundle that will produce it. Nothing here invents a status: rows land as
`MISSING` and only registration promotes them.

The planned request row that asked for the work (`ui_component_sheet`,
`card_component_sheet`, `compact_prop_pack`, ...) is not itself one of the
delivered resources. Pass it to `--supersede` so it closes as `N/A` against the
bundle that serves it instead of blocking the asset stage forever.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from asset_assets_md_update import (
    ASSET_TABLE_HEADING,
    ASSETS_MD_ASSET_ID_COLUMN,
    ASSETS_MD_PARAMS_COLUMN,
    ASSETS_MD_STATUS_COLUMN,
    ASSETS_MD_TAG_COLUMN,
    asset_table_bounds,
    format_assets_md_row,
    merge_generation_params,
    split_assets_md_row,
)
from asset_stable_entry import BUNDLE_FAMILIES, StableEntryError, safe_identifier

ASSETS_MD_NUMBER_COLUMN = 0

DECLARED_STATUS = "MISSING"
SUPERSEDED_STATUS = "N/A"
EMPTY_CELL = "—"

# Only a row still waiting on production may be superseded. ASSETS.md statuses
# are forward-only, so rewriting a delivered or deferred row would walk one
# backwards and silently retire an asset the project already has.
SUPERSEDABLE_STATUS = "MISSING"

# Which planner request families each bundle production unit may close out.
# This mirrors the ASSETS Family Routing table in
# `skills/core/gm-asset/references/asset-planner.md`, which is the authority for
# what a family routes to; `tests/test_asset_bundle_row_routing.py` fails if the
# two ever disagree. Without this, `--supersede` would accept any row name and
# retire an unrelated asset that merely happened to be spelled correctly.
SERVED_REQUEST_FAMILIES = {
    "ui-kit": {"ui_component_sheet", "icon_pack", "panel_source"},
    "card-kit": {
        "card_component_sheet",
        "card_frame_source",
        "portrait_frame_source",
    },
    "compact-prop-pack": {"compact_prop_pack", "runtime_sprite"},
}


class BundleRowError(Exception):
    """Raised when bundle rows cannot be declared."""


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BundleRowError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise BundleRowError(f"{label} must be a JSON object: {path}")
    return value


def declared_outputs(request: dict[str, Any]) -> list[tuple[str, str]]:
    """Return ``(output_name, godot_type)`` for every output a bundle declares."""
    family = request.get("asset_type")
    if family not in BUNDLE_FAMILIES:
        raise BundleRowError(
            f"{family!r} is not a bundle family; its planned ASSETS.md row is "
            "already the row registration updates"
        )
    if family == "compact-prop-pack":
        from asset_compact_prop_pack_entry_draft import (  # noqa: PLC0415
            CompactPropPackEntryDraftError,
            logical_outputs,
        )

        errors: tuple[type[Exception], ...] = (CompactPropPackEntryDraftError,)
    else:
        from asset_ui_card_entry_draft import (  # noqa: PLC0415
            UICardEntryDraftError,
            logical_outputs,
        )

        errors = (UICardEntryDraftError,)
    try:
        return logical_outputs(request)
    except errors as exc:
        raise BundleRowError(str(exc)) from exc


def _asset_ids(request: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Return ``(asset_id, output_name, godot_type)`` for each declared output."""
    bundle_id = request.get("asset_id")
    if not isinstance(bundle_id, str) or not bundle_id.strip():
        raise BundleRowError("request.asset_id must be a non-empty string")
    try:
        safe_identifier(bundle_id, "request.asset_id")
    except StableEntryError as exc:
        raise BundleRowError(str(exc)) from exc
    rows: list[tuple[str, str, str]] = []
    for name, godot_type in declared_outputs(request):
        try:
            safe_identifier(name, f"declared output {name!r}")
        except StableEntryError as exc:
            raise BundleRowError(str(exc)) from exc
        rows.append((f"{bundle_id}--{name}", name, godot_type))
    return rows


def _row_family(params: str) -> str | None:
    for part in params.split(";"):
        key, _, value = part.partition("=")
        if key.strip() == "family":
            return value.strip()
    return None


def _superseded_by(params: str) -> str | None:
    for part in params.split(";"):
        key, _, value = part.partition("=")
        if key.strip() == "superseded_by":
            return value.strip()
    return None


def _needs_supersede(
    cells: list[str], *, name: str, production_family: str, bundle_id: str
) -> bool:
    """Return whether this row still has to be retired, or fail closed.

    ``--supersede`` rewrites a status, so a name that is real but wrong would
    quietly retire a delivered or unrelated asset. Two things must hold: the row
    is still waiting on production, and it is a request this production family
    actually serves. A row this same bundle already retired is a no-op, because
    `/gm-asset` is re-runnable per tag.
    """
    status = cells[ASSETS_MD_STATUS_COLUMN]
    params = cells[ASSETS_MD_PARAMS_COLUMN]
    if status == SUPERSEDED_STATUS and _superseded_by(params) == bundle_id:
        return False
    if status != SUPERSEDABLE_STATUS:
        raise BundleRowError(
            f"ASSETS.md row {name!r} is {status!r}; only a "
            f"{SUPERSEDABLE_STATUS} row may be superseded, and ASSETS.md "
            "statuses are forward-only"
        )
    served = SERVED_REQUEST_FAMILIES[production_family]
    family = _row_family(params)
    if family is None:
        raise BundleRowError(
            f"ASSETS.md row {name!r} declares no family=, so it cannot be shown "
            f"to be a request {production_family} serves"
        )
    if family not in served:
        raise BundleRowError(
            f"ASSETS.md row {name!r} has family={family}, which {production_family} "
            f"does not serve; expected one of: {', '.join(sorted(served))}"
        )
    return True


def _write_atomic(path: Path, lines: list[str]) -> None:
    with tempfile.NamedTemporaryFile(
        delete=False, dir=str(path.parent), suffix=".md", mode="w", encoding="utf-8"
    ) as handle:
        handle.writelines(lines)
        temporary = Path(handle.name)
    try:
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def declare_bundle_rows(
    assets_md: Path,
    request_path: Path,
    *,
    tag: str,
    supersede: list[str] | None = None,
) -> dict[str, Any]:
    """Append one MISSING row per declared bundle output, idempotently."""
    assets_md = Path(assets_md)
    if not assets_md.exists():
        raise BundleRowError(f"ASSETS.md not found: {assets_md}")
    if not isinstance(tag, str) or not tag.strip():
        raise BundleRowError("--tag must be a non-empty string")
    request = _load_object(request_path, "request")
    bundle_id = request["asset_id"]
    family = request["asset_type"]
    declared = _asset_ids(request)

    lines = assets_md.read_text(encoding="utf-8").splitlines(keepends=True)
    # ASSETS.md holds several equally wide Markdown tables. Writing by column
    # count alone appends into whichever one sits last in the file, so the
    # section heading is the only safe anchor and its absence is fatal here.
    bounds = asset_table_bounds(lines)
    if bounds is None:
        raise BundleRowError(
            f"{assets_md} has no '{ASSET_TABLE_HEADING}' section to extend"
        )
    existing: set[tuple[str, str]] = set()
    highest = 0
    last_row_index = -1
    rows: list[tuple[int, list[str]]] = []
    for index in range(*bounds):
        cells = split_assets_md_row(lines[index])
        if cells is None:
            continue
        rows.append((index, cells))
        last_row_index = index
        existing.add((cells[ASSETS_MD_TAG_COLUMN], cells[ASSETS_MD_ASSET_ID_COLUMN]))
        number = cells[ASSETS_MD_NUMBER_COLUMN]
        if number.isdigit():
            highest = max(highest, int(number))
    if last_row_index < 0:
        raise BundleRowError(f"{assets_md} has no Asset Table rows to extend")

    pending = [item for item in declared if (tag, item[0]) not in existing]
    remaining = list(supersede or [])
    superseded: list[str] = []
    for index, cells in rows:
        name = cells[ASSETS_MD_ASSET_ID_COLUMN]
        if cells[ASSETS_MD_TAG_COLUMN] != tag or name not in remaining:
            continue
        remaining.remove(name)
        if not _needs_supersede(
            cells, name=name, production_family=family, bundle_id=bundle_id
        ):
            continue
        cells[ASSETS_MD_PARAMS_COLUMN] = merge_generation_params(
            cells[ASSETS_MD_PARAMS_COLUMN], {"superseded_by": bundle_id}
        )
        cells[ASSETS_MD_STATUS_COLUMN] = SUPERSEDED_STATUS
        lines[index] = format_assets_md_row(cells)
        superseded.append(name)
    if remaining:
        raise BundleRowError(
            "ASSETS.md has no current-tag rows to supersede: " + ", ".join(remaining)
        )

    created: list[str] = []
    new_lines: list[str] = []
    for asset_id, output_name, godot_type in pending:
        highest += 1
        new_lines.append(
            format_assets_md_row(
                [
                    str(highest),
                    tag,
                    asset_id,
                    godot_type,
                    EMPTY_CELL,
                    merge_generation_params(
                        "",
                        {
                            "family": family,
                            "bundle": bundle_id,
                            "logical_output": output_name,
                        },
                    ),
                    EMPTY_CELL,
                    DECLARED_STATUS,
                ]
            )
        )
        created.append(asset_id)

    if new_lines or superseded:
        lines[last_row_index + 1 : last_row_index + 1] = new_lines
        _write_atomic(assets_md, lines)

    return {
        "ok": True,
        "path": str(assets_md),
        "bundle_id": bundle_id,
        "production_family": family,
        "declared": [item[0] for item in declared],
        "created": created,
        "superseded": superseded,
    }


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Declare the ASSETS.md rows one bundle production will fill"
    )
    parser.add_argument("--assets-md", default="ASSETS.md", type=Path)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--tag", required=True)
    parser.add_argument(
        "--supersede",
        action="append",
        default=[],
        help=(
            "Current-tag request row this bundle serves; it closes as N/A with a "
            "superseded_by pointer instead of blocking the asset stage"
        ),
    )
    args = parser.parse_args()
    try:
        result = declare_bundle_rows(
            args.assets_md,
            args.request,
            tag=args.tag,
            supersede=args.supersede,
        )
    except BundleRowError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
