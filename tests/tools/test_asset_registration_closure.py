"""End-to-end registration closure for every v1 runtime artifact type.

Scope note: `scene-prop-set` has the same many-outputs-from-one-production shape
as the bundle families but is deliberately not one of them here — it still
registers a single entry whose artifact is the first declared prop, exactly as it
did before this work. Widening it is a separate change with its own contract.


Each test drives the real chain a `/gm-asset` run walks — deterministic entry
draft, `asset_stable_entry.py --write`, root-index upsert and gate,
`asset_assets_md_update.py`, then `asset_runtime_resolver.py` — and asserts the
worker snapshot that comes out the far end.

The gap these pin closed: a family could produce and fully validate a runtime
resource and still have no way to register it, so the asset reached `ready`
inside its Skill and never reached a worker at all.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from asset_action_entry_draft import (  # noqa: E402
    ActionEntryDraftError,
    build_fx_bundle_entry_draft,
    write_fx_bundle_entry_draft,
)
from asset_assets_md_update import (  # noqa: E402
    AssetsMdUpdateError,
    split_assets_md_row,
    update_assets_md,
)
from asset_assets_md_update import (  # noqa: E402
    ASSETS_MD_ASSET_ID_COLUMN,
    asset_table_bounds,
    is_separator_row,
    iter_asset_rows,
)
from asset_bundle_rows import BundleRowError, declare_bundle_rows  # noqa: E402
from asset_curation_entry_draft import (  # noqa: E402
    CurationEntryDraftError,
    write_fx_static_entry_draft,
)
from asset_generation_index import check_index, update_index  # noqa: E402
from asset_runtime_resolver import (  # noqa: E402
    AssetRuntimeResolverError,
    resolve_assets_row,
)
from asset_stable_entry import entry_relative_path, write_entry  # noqa: E402
from asset_tileset_entry_draft import (  # noqa: E402
    TileSetEntryDraftError,
    build_tileset_entry_draft,
)
from asset_ui_card_contract_check import (  # noqa: E402
    UICardContractError,
    check_ui_card_handoff,
    expected_runtime_path,
)
from asset_ui_card_entry_draft import (  # noqa: E402
    UICardEntryDraftError,
    build_ui_card_entry_drafts,
    write_ui_card_entry_drafts,
)

TAG = "v0.1.0"
ASSETS_DIR = ROOT / "skills" / "assets"
LEVELS_PASSED = ("L0", "L1", "L2", "L3", "L4")


def _write_json(path: Path, value) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")
    return path


def _touch(project_root: Path, res_path: str) -> None:
    path = project_root / res_path[len("res://"):]
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".png":
        Image.new("RGBA", (8, 8), (255, 255, 255, 255)).save(path)
    else:
        path.write_text("stub", encoding="utf-8")


def _assets_md(project_root: Path, rows: list[str]) -> Path:
    lines = [
        "# Assets: Closure",
        "",
        "## Asset Table",
        "",
        "| # | Tag | Name | Type | Size | Generation Params | File Path | Status |",
        "|---|-----|------|------|------|-------------------|-----------|--------|",
    ]
    for number, name in enumerate(rows, start=1):
        lines.append(f"| {number} | {TAG} | {name} | runtime | - | - | - | MISSING |")
    path = project_root / "ASSETS.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _register(project_root: Path, entries: list[dict]) -> list[Path]:
    """Write every entry, upsert its pointer, and run the full root-index gate."""
    written: list[Path] = []
    for entry in entries:
        write_entry(entry, project_root=project_root, check_files=True)
        path = project_root / entry_relative_path(entry["tag"], entry["asset_id"])
        written.append(path)
        update_index(
            project_root / ".godotmaker/asset-generation/manifest.json",
            [path],
            project_root=project_root,
        )
    check_index(
        project_root / ".godotmaker/asset-generation/manifest.json",
        project_root=project_root,
        check_entries=True,
        check_files=True,
    )
    return written


def _snapshot(project_root: Path, asset_id: str) -> dict:
    return resolve_assets_row(
        project_root / "ASSETS.md",
        tag=TAG,
        asset_id=asset_id,
        project_root=project_root,
    )


# --------------------------------------------------------------------------
# tileset -> TileSet
# --------------------------------------------------------------------------


def _tileset_delivery(project_root: Path, asset_id: str = "grassland"):
    root = f"res://assets/generated/tileset/{asset_id}"
    request = {
        "asset_type": "tileset",
        "asset_id": asset_id,
        "brief": "A grassland tile atlas.",
        "provider": "codex",
        "spec": {
            "autotile_profile": "marching_squares_15",
            "tile_size": {"width": 16, "height": 16},
            "terrain": {
                "name": "grassland",
                "foreground_material": "dirt",
                "background_material": "grass",
            },
        },
    }
    result = {
        "asset_type": "tileset",
        "outputs": [
            {
                "role": "runtime",
                "path": f"{root}/{asset_id}.tres",
                "godot_type": "TileSet",
            }
        ],
        "sources": [{"path": f"{root}/{asset_id}_atlas.png", "layout": "tile_atlas"}],
        "previews": [],
        "validation": {
            "passed": True,
            "levels": {level: True for level in ("L0", "L1", "L2", "L3", "L4")},
        },
    }
    _touch(project_root, f"{root}/{asset_id}_atlas.png")
    _touch(project_root, f"{root}/{asset_id}.tres")
    return (
        _write_json(project_root / "ASSET_REQUEST.json", request),
        _write_json(project_root / "tileset-result.json", result),
    )


def test_tileset_reaches_a_worker_snapshot_from_a_validated_delivery(tmp_path):
    request_path, result_path = _tileset_delivery(tmp_path)
    assets_md = _assets_md(tmp_path, ["grassland"])

    entry = build_tileset_entry_draft(
        request_path, result_path, tag=TAG, project_root=tmp_path
    )
    _register(tmp_path, [entry])
    update_assets_md(assets_md, [tmp_path / entry_relative_path(TAG, "grassland")])

    snapshot = _snapshot(tmp_path, "grassland")

    assert snapshot == {
        "asset_id": "grassland",
        "production_family": "tileset",
        "source_layout": {
            "type": "tile_atlas",
            "path": "res://assets/generated/tileset/grassland/grassland_atlas.png",
        },
        "godot_artifact": {
            "type": "TileSet",
            "path": "res://assets/generated/tileset/grassland/grassland.tres",
        },
    }


def test_tileset_without_a_passing_ladder_never_registers(tmp_path):
    request_path, result_path = _tileset_delivery(tmp_path)
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["validation"]["levels"]["L4"] = False
    result["validation"]["passed"] = False
    _write_json(result_path, result)

    with pytest.raises(TileSetEntryDraftError, match="passed L0-L4"):
        build_tileset_entry_draft(
            request_path, result_path, tag=TAG, project_root=tmp_path
        )


def test_tileset_rejects_a_second_runtime_output(tmp_path):
    # A map has one tile library. A second one would reach the worker as a rival
    # tile source for the same TileMapLayer.
    request_path, result_path = _tileset_delivery(tmp_path)
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["outputs"].append(
        {
            "role": "runtime",
            "path": "res://assets/generated/tileset/grassland/extra.tres",
            "godot_type": "TileSet",
        }
    )
    _write_json(result_path, result)

    with pytest.raises(TileSetEntryDraftError, match="exactly one stable TileSet"):
        build_tileset_entry_draft(
            request_path, result_path, tag=TAG, project_root=tmp_path
        )


# --------------------------------------------------------------------------
# ui-kit / card-kit -> Theme, StyleBoxTexture, AtlasTexture
# --------------------------------------------------------------------------


def _kit_delivery(project_root: Path, family: str):
    """Materialize the family's committed representative request/result pair."""
    fixtures = ASSETS_DIR / family / "fixtures"
    request = json.loads(
        (fixtures / "representative-request.json").read_text(encoding="utf-8")
    )
    result = json.loads(
        (fixtures / "representative-result.json").read_text(encoding="utf-8")
    )
    for source in result["sources"]:
        _touch(project_root, source["path"])
    for output in result["outputs"]:
        _touch(project_root, output["path"])
    return (
        _write_json(project_root / f"{family}-request.json", request),
        _write_json(project_root / f"{family}-result.json", result),
    )


@pytest.mark.parametrize("family", ["ui-kit", "card-kit"])
def test_every_kit_runtime_output_becomes_its_own_ready_entry(tmp_path, family):
    request_path, result_path = _kit_delivery(tmp_path, family)
    result = json.loads(result_path.read_text(encoding="utf-8"))

    entries = build_ui_card_entry_drafts(
        request_path, result_path, tag=TAG, project_root=tmp_path
    )

    runtime = [item for item in result["outputs"] if item["role"] == "runtime"]
    assert len(entries) == len(runtime)
    assert {entry["godot_artifact"]["type"] for entry in entries} == {
        "Theme",
        "StyleBoxTexture",
        "AtlasTexture",
    }
    assert all(entry["processing_status"] == "ready" for entry in entries)
    assert all(entry["bundle_id"] == json.loads(
        request_path.read_text(encoding="utf-8")
    )["asset_id"] for entry in entries)
    # The Theme binds its recipe, never the atlas its styleboxes are cut from.
    theme = next(
        entry for entry in entries if entry["godot_artifact"]["type"] == "Theme"
    )
    assert theme["source_layout"]["type"] == "theme_recipe"


def _planned_assets_md(project_root: Path, extra_rows: list[str] | None = None) -> Path:
    """Start from the shipped ASSETS.md template, as /gm-gdd would leave it.

    Only planner-shaped *request* rows exist here. The logical rows a bundle
    delivers must be produced by `asset_bundle_rows.py`, never by this helper —
    fabricating them is exactly what hid the missing-row failure.
    """
    template = (ROOT / "templates" / "ASSETS.md").read_text(encoding="utf-8")
    lines = template.splitlines(keepends=True)
    if extra_rows:
        # Into the Asset Table, not "the last wide table in the file" — the
        # Visual Asset Contract and Budget Tracking tables are just as wide.
        bounds = asset_table_bounds(lines)
        last = max(
            index
            for index in range(*bounds)
            if split_assets_md_row(lines[index]) is not None
        )
        lines[last + 1 : last + 1] = [row + "\n" for row in extra_rows]
    path = project_root / "ASSETS.md"
    path.write_text("".join(lines), encoding="utf-8")
    return path


def _sections(text: str) -> dict[str, str]:
    """Split an ASSETS.md document into `## heading -> body` for byte compare."""
    sections: dict[str, str] = {}
    heading = ""
    body: list[str] = []
    for line in text.splitlines(keepends=True):
        if line.startswith("## "):
            sections[heading] = "".join(body)
            heading = line.strip()
            body = []
        else:
            body.append(line)
    sections[heading] = "".join(body)
    return sections


CARD_REQUEST_ROW = (
    "| 7 | v0.1.0 | card_frame | ui | 128x192 px | family=card_component_sheet; "
    "component=rare_card | assets/generated/card-kit/card_frame/card_frame.png | MISSING |"
)

KIT_REQUEST_ROW = {"ui-kit": "action_button", "card-kit": "card_frame"}


def _row(assets_md: Path, name: str) -> list[str] | None:
    for line in assets_md.read_text(encoding="utf-8").splitlines():
        cells = split_assets_md_row(line)
        if cells is not None and cells[2] == name and cells[1] == TAG:
            return cells
    return None


@pytest.mark.parametrize("family", ["ui-kit", "card-kit"])
def test_a_planned_kit_row_declares_and_fills_every_delivered_row(tmp_path, family):
    # The chain the manager really walks: a planner-shaped request row, the
    # bundle's declared rows, registration, then the ASSETS.md update that used
    # to fail closed with "missing rows for entries".
    request_path, result_path = _kit_delivery(tmp_path, family)
    assets_md = _planned_assets_md(
        tmp_path, [CARD_REQUEST_ROW] if family == "card-kit" else None
    )
    request = json.loads(request_path.read_text(encoding="utf-8"))
    bundle_id = request["asset_id"]
    entries = build_ui_card_entry_drafts(
        request_path, result_path, tag=TAG, project_root=tmp_path
    )
    assert _row(assets_md, entries[0]["asset_id"]) is None

    declared = declare_bundle_rows(
        assets_md,
        request_path,
        tag=TAG,
        supersede=[KIT_REQUEST_ROW[family]],
    )

    assert declared["created"] == [entry["asset_id"] for entry in entries]
    served = _row(assets_md, KIT_REQUEST_ROW[family])
    assert served[7] == "N/A"
    assert f"superseded_by={bundle_id}" in served[5]

    _register(tmp_path, entries)
    update_assets_md(
        assets_md,
        [tmp_path / entry_relative_path(TAG, entry["asset_id"]) for entry in entries],
    )

    for entry in entries:
        snapshot = _snapshot(tmp_path, entry["asset_id"])
        assert snapshot["godot_artifact"] == entry["godot_artifact"]


def test_undeclared_kit_rows_still_fail_the_assets_update(tmp_path):
    # The regression the declaration step exists for: registering ready entries
    # against a planner-shaped ASSETS.md that never declared them.
    request_path, result_path = _kit_delivery(tmp_path, "card-kit")
    assets_md = _planned_assets_md(tmp_path, [CARD_REQUEST_ROW])
    entries = build_ui_card_entry_drafts(
        request_path, result_path, tag=TAG, project_root=tmp_path
    )
    _register(tmp_path, entries)

    with pytest.raises(AssetsMdUpdateError, match="missing rows for entries"):
        update_assets_md(
            assets_md,
            [
                tmp_path / entry_relative_path(TAG, entry["asset_id"])
                for entry in entries
            ],
        )


def test_declaring_bundle_rows_twice_changes_nothing(tmp_path):
    request_path, _ = _kit_delivery(tmp_path, "card-kit")
    assets_md = _planned_assets_md(tmp_path, [CARD_REQUEST_ROW])
    declare_bundle_rows(assets_md, request_path, tag=TAG, supersede=["card_frame"])
    once = assets_md.read_text(encoding="utf-8")

    again = declare_bundle_rows(
        assets_md, request_path, tag=TAG, supersede=["card_frame"]
    )

    assert again["created"] == []
    assert assets_md.read_text(encoding="utf-8") == once


def test_superseding_an_absent_request_row_fails_closed(tmp_path):
    request_path, _ = _kit_delivery(tmp_path, "card-kit")
    assets_md = _planned_assets_md(tmp_path)

    with pytest.raises(BundleRowError, match="no row to supersede"):
        declare_bundle_rows(
            assets_md, request_path, tag=TAG, supersede=["card_frame"]
        )


PROP_REQUEST_ROW = (
    "| 7 | v0.1.0 | market_props | ui | 64x64 px | family=compact_prop_pack; "
    "component=props | assets/generated/compact-prop-pack/market/market.png | MISSING |"
)


def test_a_compact_prop_bundle_declares_and_fills_its_logical_rows(tmp_path):
    # compact-prop-pack has produced <bundle>--<prop> entries since before this
    # change and was never driven through the ASSETS.md update, so it carried
    # the same missing-row failure.
    request = {
        "asset_type": "compact-prop-pack",
        "asset_id": "market",
        "brief": "A market prop pack.",
        "spec": {
            "version": 1,
            "atlas": {"width": 64, "height": 32},
            "slots": [
                {"name": "lantern", "rect": [0, 0, 32, 32], "source": "lantern.png"},
                {"name": "crate", "rect": [32, 0, 32, 32], "source": "crate.png"},
            ],
        },
    }
    request_path = _write_json(tmp_path / "props-request.json", request)
    assets_md = _planned_assets_md(tmp_path, [PROP_REQUEST_ROW])

    declared = declare_bundle_rows(
        assets_md, request_path, tag=TAG, supersede=["market_props"]
    )

    assert declared["created"] == ["market--lantern", "market--crate"]
    assert _row(assets_md, "market--lantern")[3] == "AtlasTexture"
    assert "bundle=market" in _row(assets_md, "market--crate")[5]
    assert _row(assets_md, "market_props")[7] == "N/A"


def test_declared_rows_land_in_the_asset_table_and_touch_nothing_else(tmp_path):
    # ASSETS.md holds several equally wide tables. Appending by column count
    # alone put logical rows in Budget Tracking, which still parsed and still
    # resolved — the manifest was simply not the manifest any more.
    request_path, _ = _kit_delivery(tmp_path, "card-kit")
    assets_md = _planned_assets_md(tmp_path, [CARD_REQUEST_ROW])
    before = _sections(assets_md.read_text(encoding="utf-8"))

    declare_bundle_rows(assets_md, request_path, tag=TAG, supersede=["card_frame"])

    text = assets_md.read_text(encoding="utf-8")
    after = _sections(text)
    assert set(after) == set(before)
    for heading, body in after.items():
        if heading != "## Asset Table":
            assert body == before[heading], f"{heading} was rewritten"

    table = text.index("## Asset Table")
    contract = text.index("## Visual Asset Contract")
    for asset_id in ("arcane_deck--card_theme", "arcane_deck--mana_badge"):
        assert table < text.index(asset_id) < contract


def test_declared_rows_never_reach_the_visual_asset_contract_columns(tmp_path):
    request_path, _ = _kit_delivery(tmp_path, "card-kit")
    assets_md = _planned_assets_md(tmp_path, [CARD_REQUEST_ROW])
    declare_bundle_rows(assets_md, request_path, tag=TAG, supersede=["card_frame"])

    lines = assets_md.read_text(encoding="utf-8").splitlines(keepends=True)
    bounds = asset_table_bounds(lines)
    inside = {
        cells[ASSETS_MD_ASSET_ID_COLUMN]
        for index in range(*bounds)
        if (cells := split_assets_md_row(lines[index])) is not None
    }
    assert "arcane_deck--card_theme" in inside
    outside = "".join(lines[bounds[1] :])
    assert "arcane_deck--" not in outside


def test_declaring_into_a_document_without_an_asset_table_fails_closed(tmp_path):
    request_path, _ = _kit_delivery(tmp_path, "card-kit")
    assets_md = tmp_path / "ASSETS.md"
    assets_md.write_text(
        "# Assets\n\n## Budget Tracking\n\n"
        "| Asset | Tag | Tool | Cost | Notes | A | B | C |\n"
        "|---|---|---|---|---|---|---|---|\n"
        "| x | v0.1.0 | y | 0 | - | - | - | - |\n",
        encoding="utf-8",
    )

    with pytest.raises(BundleRowError, match="Asset Table"):
        declare_bundle_rows(assets_md, request_path, tag=TAG)


@pytest.mark.parametrize("status", ["generated", "provided", "N/A", "deferred"])
def test_supersede_refuses_a_row_that_is_no_longer_missing(tmp_path, status):
    # ASSETS.md statuses are forward-only. A real but wrong row name must not
    # retire an asset the project already has.
    request_path, _ = _kit_delivery(tmp_path, "card-kit")
    delivered = CARD_REQUEST_ROW.replace("| MISSING |", f"| {status} |")
    assets_md = _planned_assets_md(tmp_path, [delivered])
    before = assets_md.read_text(encoding="utf-8")

    with pytest.raises(BundleRowError, match="only a MISSING row may be superseded"):
        declare_bundle_rows(
            assets_md, request_path, tag=TAG, supersede=["card_frame"]
        )
    assert assets_md.read_text(encoding="utf-8") == before


def test_supersede_refuses_a_request_family_the_bundle_does_not_serve(tmp_path):
    # `background_sky` is a real current-tag MISSING row in the template, but a
    # card kit has no standing to close a background out.
    request_path, _ = _kit_delivery(tmp_path, "card-kit")
    assets_md = _planned_assets_md(tmp_path, [CARD_REQUEST_ROW])
    before = assets_md.read_text(encoding="utf-8")

    with pytest.raises(BundleRowError, match="does not serve"):
        declare_bundle_rows(
            assets_md, request_path, tag=TAG, supersede=["background_sky"]
        )
    assert assets_md.read_text(encoding="utf-8") == before


def test_a_second_bundle_cannot_steal_an_already_superseded_row(tmp_path):
    request_path, _ = _kit_delivery(tmp_path, "card-kit")
    assets_md = _planned_assets_md(tmp_path, [CARD_REQUEST_ROW])
    declare_bundle_rows(assets_md, request_path, tag=TAG, supersede=["card_frame"])
    other = json.loads(request_path.read_text(encoding="utf-8"))
    other["asset_id"] = "other_deck"
    other_path = _write_json(tmp_path / "other-request.json", other)

    with pytest.raises(BundleRowError, match="only a MISSING row may be superseded"):
        declare_bundle_rows(assets_md, other_path, tag=TAG, supersede=["card_frame"])


def test_supersede_refuses_a_row_with_no_declared_family(tmp_path):
    request_path, _ = _kit_delivery(tmp_path, "card-kit")
    anonymous = CARD_REQUEST_ROW.replace(
        "family=card_component_sheet; component=rare_card", "—"
    )
    assets_md = _planned_assets_md(tmp_path, [anonymous])

    with pytest.raises(BundleRowError, match="declares no family="):
        declare_bundle_rows(
            assets_md, request_path, tag=TAG, supersede=["card_frame"]
        )


def test_declaring_into_an_empty_asset_table_keeps_the_table_valid(tmp_path):
    # A project's first tag has a header and separator and no rows yet. The
    # header is exactly as wide as the data it labels, so treating it as a row
    # put new rows above the |---| separator and destroyed the table.
    request_path, _ = _kit_delivery(tmp_path, "card-kit")
    assets_md = tmp_path / "ASSETS.md"
    assets_md.write_text(
        "# Assets\n\n## Asset Table\n\n"
        "| # | Tag | Name | Type | Size | Generation Params | File Path | Status |\n"
        "|---|-----|------|------|------|-------------------|-----------|--------|\n"
        "\n## Visual Asset Contract\n\nnothing here\n",
        encoding="utf-8",
    )

    declare_bundle_rows(assets_md, request_path, tag=TAG)

    lines = assets_md.read_text(encoding="utf-8").splitlines()
    header = next(i for i, line in enumerate(lines) if line.startswith("| # | Tag |"))
    separator = next(i for i, line in enumerate(lines) if is_separator_row(line))
    first_row = next(
        i for i, line in enumerate(lines) if "arcane_deck--card_theme" in line
    )
    assert header < separator < first_row
    assert _row(assets_md, "arcane_deck--card_theme") is not None


def _rewrite_endings(path: Path, newline: bytes) -> None:
    body = path.read_bytes().replace(b"\r\n", b"\n")
    path.write_bytes(body.replace(b"\n", newline))


def _assert_uniform_endings(raw: bytes, newline: bytes) -> None:
    assert raw.count(newline) > 0
    if newline == b"\n":
        assert raw.count(b"\r") == 0
    else:
        assert raw.count(b"\n") == raw.count(b"\r\n")


def _untouched_lines(before: bytes, after: bytes) -> int:
    """Count lines present in `before` that survived byte-identical in `after`."""
    kept = set(after.splitlines(keepends=True))
    return sum(1 for line in before.splitlines(keepends=True) if line in kept)


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
def test_declaring_rows_preserves_the_document_line_endings(tmp_path, newline):
    # A tool that appends three lines must not rewrite every line in the file:
    # a whole-file diff buries the real change and flips back on the next
    # normalizing checkout.
    request_path, _ = _kit_delivery(tmp_path, "card-kit")
    assets_md = _planned_assets_md(tmp_path, [CARD_REQUEST_ROW])
    _rewrite_endings(assets_md, newline)
    before = assets_md.read_bytes()

    declare_bundle_rows(assets_md, request_path, tag=TAG, supersede=["card_frame"])

    after = assets_md.read_bytes()
    _assert_uniform_endings(after, newline)
    # Only the superseded row changed; every other original line is untouched.
    assert _untouched_lines(before, after) == len(before.splitlines()) - 1


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
def test_updating_rows_preserves_the_document_line_endings(tmp_path, newline):
    request_path, result_path = _kit_delivery(tmp_path, "card-kit")
    assets_md = _planned_assets_md(tmp_path, [CARD_REQUEST_ROW])
    declare_bundle_rows(assets_md, request_path, tag=TAG, supersede=["card_frame"])
    _rewrite_endings(assets_md, newline)
    before = assets_md.read_bytes()
    entries = build_ui_card_entry_drafts(
        request_path, result_path, tag=TAG, project_root=tmp_path
    )
    _register(tmp_path, entries)

    update_assets_md(
        assets_md,
        [tmp_path / entry_relative_path(TAG, entry["asset_id"]) for entry in entries],
    )

    after = assets_md.read_bytes()
    _assert_uniform_endings(after, newline)
    # Exactly the three promoted rows changed; nothing else was rewritten.
    assert _untouched_lines(before, after) == len(before.splitlines()) - len(entries)


def test_declared_rows_do_not_reuse_the_request_family_key(tmp_path):
    # `family=` means "request family" in the planner routing table and in this
    # tool's own supersede guard. A production unit is never one of those values,
    # so a declared row must not claim that key.
    request_path, _ = _kit_delivery(tmp_path, "card-kit")
    assets_md = _planned_assets_md(tmp_path, [CARD_REQUEST_ROW])

    declare_bundle_rows(assets_md, request_path, tag=TAG, supersede=["card_frame"])

    params = _row(assets_md, "arcane_deck--card_theme")[5]
    assert "produced_by=card-kit" in params
    assert "family=" not in params


TAG_TWO = "v0.2.0"


def _named_row(assets_md: Path, name: str, tag: str) -> list[str] | None:
    for line in assets_md.read_text(encoding="utf-8").splitlines():
        cells = split_assets_md_row(line)
        if cells is not None and cells[2] == name and cells[1] == tag:
            return cells
    return None


def test_supersede_prefers_the_current_tag_row_over_a_same_named_older_one(tmp_path):
    # ASSETS.md accumulates across tags, so the same request name legitimately
    # appears twice. Taking the first match retired the previous tag's row and
    # left the one this production actually serves blocking the stage.
    request_path, _ = _kit_delivery(tmp_path, "card-kit")
    older = CARD_REQUEST_ROW
    newer = CARD_REQUEST_ROW.replace(f"| {TAG} |", f"| {TAG_TWO} |").replace(
        "| 7 |", "| 8 |"
    )
    assets_md = _planned_assets_md(tmp_path, [older, newer])

    declare_bundle_rows(
        assets_md, request_path, tag=TAG_TWO, supersede=["card_frame"]
    )

    assert _named_row(assets_md, "card_frame", TAG)[7] == "MISSING"
    assert _named_row(assets_md, "card_frame", TAG_TWO)[7] == "N/A"


def test_supersede_refuses_an_ambiguous_cross_tag_name(tmp_path):
    request_path, _ = _kit_delivery(tmp_path, "card-kit")
    older = CARD_REQUEST_ROW
    other = CARD_REQUEST_ROW.replace(f"| {TAG} |", "| v0.0.9 |").replace(
        "| 7 |", "| 8 |"
    )
    assets_md = _planned_assets_md(tmp_path, [older, other])
    before = assets_md.read_bytes()

    with pytest.raises(BundleRowError, match="ambiguous"):
        declare_bundle_rows(
            assets_md, request_path, tag=TAG_TWO, supersede=["card_frame"]
        )
    assert assets_md.read_bytes() == before


def test_supersede_refuses_two_rows_with_the_same_name_in_one_tag(tmp_path):
    request_path, _ = _kit_delivery(tmp_path, "card-kit")
    duplicate = CARD_REQUEST_ROW.replace("| 7 |", "| 8 |")
    assets_md = _planned_assets_md(tmp_path, [CARD_REQUEST_ROW, duplicate])

    with pytest.raises(BundleRowError, match="ambiguous"):
        declare_bundle_rows(
            assets_md, request_path, tag=TAG, supersede=["card_frame"]
        )


def test_an_older_delivered_row_does_not_abort_the_whole_declaration(tmp_path):
    # A previous tag's row that already shipped must not make the current tag's
    # supersede raise and take every logical row down with it.
    request_path, _ = _kit_delivery(tmp_path, "card-kit")
    shipped = CARD_REQUEST_ROW.replace("| MISSING |", "| generated |")
    newer = CARD_REQUEST_ROW.replace(f"| {TAG} |", f"| {TAG_TWO} |").replace(
        "| 7 |", "| 8 |"
    )
    assets_md = _planned_assets_md(tmp_path, [shipped, newer])

    payload = declare_bundle_rows(
        assets_md, request_path, tag=TAG_TWO, supersede=["card_frame"]
    )

    assert payload["created"] == [
        "arcane_deck--card_theme",
        "arcane_deck--rare_card_normal",
        "arcane_deck--mana_badge",
    ]
    assert _named_row(assets_md, "card_frame", TAG)[7] == "generated"
    assert _named_row(assets_md, "card_frame", TAG_TWO)[7] == "N/A"


def test_a_request_row_from_an_earlier_tag_can_still_be_superseded(tmp_path):
    # ASSETS.md accumulates across tags, so a row planned in v0.1.0 and produced
    # in v0.2.0 is still the request this bundle serves.
    request_path, _ = _kit_delivery(tmp_path, "card-kit")
    assets_md = _planned_assets_md(tmp_path, [CARD_REQUEST_ROW])

    declare_bundle_rows(
        assets_md, request_path, tag="v0.2.0", supersede=["card_frame"]
    )

    row = next(
        cells
        for line in assets_md.read_text(encoding="utf-8").splitlines()
        if (cells := split_assets_md_row(line)) is not None
        and cells[ASSETS_MD_ASSET_ID_COLUMN] == "card_frame"
    )
    assert row[1] == TAG and row[7] == "N/A"


def test_a_nested_asset_table_example_cannot_hijack_the_manifest(tmp_path):
    # Accepting the heading at any depth let an earlier `### Asset Table`
    # example shadow the real section — exactly what this anchor exists to stop.
    assets_md = tmp_path / "ASSETS.md"
    assets_md.write_text(
        "# Assets\n\n## Notes\n\n### Asset Table\n\n"
        "| # | Tag | Name | T | S | P | F | Status |\n"
        "|---|---|---|---|---|---|---|---|\n"
        f"| 1 | {TAG} | DECOY | - | - | - | - | generated |\n"
        "\n## Asset Table\n\n"
        "| # | Tag | Name | T | S | P | F | Status |\n"
        "|---|---|---|---|---|---|---|---|\n"
        f"| 1 | {TAG} | real_asset | - | - | - | - | MISSING |\n",
        encoding="utf-8",
    )

    lines = assets_md.read_text(encoding="utf-8").splitlines(keepends=True)
    names = [cells[ASSETS_MD_ASSET_ID_COLUMN] for _, cells in iter_asset_rows(lines)]

    assert names == ["real_asset"]


def test_an_asset_table_quoted_inside_a_code_fence_is_not_the_manifest(tmp_path):
    assets_md = tmp_path / "ASSETS.md"
    assets_md.write_text(
        "# Assets\n\n## How to read this\n\n"
        "```markdown\n## Asset Table\n\n"
        "| # | Tag | Name | T | S | P | F | Status |\n"
        "|---|---|---|---|---|---|---|---|\n"
        f"| 1 | {TAG} | EXAMPLE | - | - | - | - | generated |\n"
        "```\n\n## Asset Table\n\n"
        "| # | Tag | Name | T | S | P | F | Status |\n"
        "|---|---|---|---|---|---|---|---|\n"
        f"| 1 | {TAG} | real_asset | - | - | - | - | MISSING |\n",
        encoding="utf-8",
    )

    lines = assets_md.read_text(encoding="utf-8").splitlines(keepends=True)
    names = [cells[ASSETS_MD_ASSET_ID_COLUMN] for _, cells in iter_asset_rows(lines)]

    assert names == ["real_asset"]


def _table_document(body: str) -> str:
    return (
        "# Assets\n\n## Asset Table\n\n"
        + body
        + "\n## Visual Asset Contract\n\nnothing\n"
    )


TABLE_ROWS = (
    "| # | Tag | Name | T | S | P | F | Status |\n"
    "|---|---|---|---|---|---|---|---|\n"
    f"| 1 | {TAG} | real | - | - | - | - | MISSING |\n"
)


def test_a_subheading_inside_the_section_does_not_cut_the_table_off(tmp_path):
    # The section ends at the next same-or-shallower heading. Ending at *any*
    # heading let a `### Legend` written above the table truncate the manifest
    # to zero rows, and the downstream errors then pointed at the wrong cause.
    assets_md = tmp_path / "ASSETS.md"
    assets_md.write_text(
        _table_document("### Legend\n\nsome prose\n\n" + TABLE_ROWS), encoding="utf-8"
    )

    lines = assets_md.read_text(encoding="utf-8").splitlines(keepends=True)
    names = [cells[ASSETS_MD_ASSET_ID_COLUMN] for _, cells in iter_asset_rows(lines)]

    assert names == ["real"]


def test_a_sibling_or_shallower_heading_still_ends_the_section(tmp_path):
    assets_md = tmp_path / "ASSETS.md"
    assets_md.write_text(
        "# Assets\n\n## Asset Table\n\n"
        + TABLE_ROWS
        + "\n# Appendix\n\n"
        "| # | Tag | Name | T | S | P | F | Status |\n"
        "|---|---|---|---|---|---|---|---|\n"
        f"| 9 | {TAG} | after | - | - | - | - | MISSING |\n",
        encoding="utf-8",
    )

    lines = assets_md.read_text(encoding="utf-8").splitlines(keepends=True)
    names = [cells[ASSETS_MD_ASSET_ID_COLUMN] for _, cells in iter_asset_rows(lines)]

    assert names == ["real"]


def test_a_fenced_example_inside_the_section_is_not_an_asset_row(tmp_path):
    # Skipping fences when locating the heading but not when scanning rows left
    # the example readable as an asset — and as the section's last "row" it
    # became the insertion anchor, so new rows were written into the block.
    assets_md = tmp_path / "ASSETS.md"
    assets_md.write_text(
        _table_document(
            TABLE_ROWS
            + "\n```markdown\n"
            "| # | Tag | Name | T | S | P | F | Status |\n"
            "|---|---|---|---|---|---|---|---|\n"
            f"| 9 | {TAG} | EXAMPLE | - | - | - | - | generated |\n"
            "```\n"
        ),
        encoding="utf-8",
    )

    lines = assets_md.read_text(encoding="utf-8").splitlines(keepends=True)
    names = [cells[ASSETS_MD_ASSET_ID_COLUMN] for _, cells in iter_asset_rows(lines)]

    assert names == ["real"]


def test_declared_rows_are_not_written_into_a_fenced_example(tmp_path):
    request_path, _ = _kit_delivery(tmp_path, "card-kit")
    assets_md = tmp_path / "ASSETS.md"
    assets_md.write_text(
        _table_document(
            TABLE_ROWS
            + "\n```markdown\n"
            f"| 9 | {TAG} | EXAMPLE | - | - | - | - | generated |\n"
            "```\n"
        ),
        encoding="utf-8",
    )

    declare_bundle_rows(assets_md, request_path, tag=TAG)

    text = assets_md.read_text(encoding="utf-8")
    fence_start = text.index("```markdown")
    assert text.index("arcane_deck--card_theme") < fence_start


def test_a_long_fence_is_not_closed_by_a_shorter_inner_one(tmp_path):
    assets_md = tmp_path / "ASSETS.md"
    assets_md.write_text(
        _table_document(
            TABLE_ROWS
            + "\n````markdown\n"
            "```\n"
            f"| 9 | {TAG} | EXAMPLE | - | - | - | - | generated |\n"
            "````\n"
        ),
        encoding="utf-8",
    )

    lines = assets_md.read_text(encoding="utf-8").splitlines(keepends=True)
    names = [cells[ASSETS_MD_ASSET_ID_COLUMN] for _, cells in iter_asset_rows(lines)]

    assert names == ["real"]


def test_an_unclosed_fence_is_reported_as_itself(tmp_path):
    # An unclosed fence swallows the rest of the document; saying so beats
    # reporting a missing Asset Table, which is only the symptom.
    assets_md = tmp_path / "ASSETS.md"
    assets_md.write_text(
        "# Assets\n\n```markdown\nstill open\n\n## Asset Table\n\n" + TABLE_ROWS,
        encoding="utf-8",
    )

    with pytest.raises(AssetsMdUpdateError, match="unclosed"):
        list(iter_asset_rows(assets_md.read_text(encoding="utf-8").splitlines(True)))


def test_bundle_rows_cli_reports_a_malformed_document_as_json(tmp_path):
    # The shared parser raises its own error type; this tool still owes the
    # caller machine-readable JSON rather than a traceback.
    request_path, _ = _kit_delivery(tmp_path, "card-kit")
    assets_md = tmp_path / "ASSETS.md"
    body = "## Asset Table\n\n" + TABLE_ROWS + "\n"
    assets_md.write_text("# Assets\n\n" + body + body, encoding="utf-8")

    completed = _run(
        "asset_bundle_rows.py",
        "--assets-md", str(assets_md),
        "--request", str(request_path),
        "--tag", TAG,
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout)["ok"] is False
    assert "sections" in json.loads(completed.stdout)["error"]


def test_two_asset_table_sections_are_an_error(tmp_path):
    assets_md = tmp_path / "ASSETS.md"
    body = (
        "## Asset Table\n\n"
        "| # | Tag | Name | T | S | P | F | Status |\n"
        "|---|---|---|---|---|---|---|---|\n"
        f"| 1 | {TAG} | a | - | - | - | - | MISSING |\n\n"
    )
    assets_md.write_text("# Assets\n\n" + body + body, encoding="utf-8")

    with pytest.raises(AssetsMdUpdateError, match="sections"):
        list(iter_asset_rows(assets_md.read_text(encoding="utf-8").splitlines(True)))


def test_a_table_without_a_separator_cannot_be_read_as_data(tmp_path):
    # Header detection is "the row followed by the separator". With no separator
    # the column labels were returned as an asset row.
    assets_md = tmp_path / "ASSETS.md"
    assets_md.write_text(
        "# Assets\n\n## Asset Table\n\n"
        "| # | Tag | Name | T | S | P | F | Status |\n"
        f"| 1 | {TAG} | player | - | - | - | - | MISSING |\n",
        encoding="utf-8",
    )

    with pytest.raises(AssetsMdUpdateError, match="no .* separator"):
        list(iter_asset_rows(assets_md.read_text(encoding="utf-8").splitlines(True)))


def test_declaring_after_an_unterminated_final_row_does_not_weld_lines(tmp_path):
    request_path, _ = _kit_delivery(tmp_path, "card-kit")
    assets_md = _planned_assets_md(tmp_path, [CARD_REQUEST_ROW])
    assets_md.write_bytes(assets_md.read_bytes().rstrip(b"\r\n"))

    declare_bundle_rows(assets_md, request_path, tag=TAG, supersede=["card_frame"])

    lines = assets_md.read_text(encoding="utf-8").splitlines()
    for line in lines:
        cells = split_assets_md_row(line)
        assert cells is None or len(cells) == 8, f"welded row: {line!r}"
    assert _row(assets_md, "arcane_deck--card_theme") is not None


def test_readers_fail_closed_without_an_asset_table(tmp_path):
    # The PR makes "only the Asset Table is the asset manifest" an invariant, so
    # the two readers that rewrite delivered state must not keep guessing.
    assets_md = tmp_path / "ASSETS.md"
    assets_md.write_text(
        "# Assets\n\n## Visual Asset Contract\n\n"
        "| Scene | Object | A | B | C | D | E | F |\n"
        "|---|---|---|---|---|---|---|---|\n"
        f"| menu | logo | - | - | - | - | - | {TAG} |\n",
        encoding="utf-8",
    )

    with pytest.raises(AssetsMdUpdateError, match="no '## Asset Table' section"):
        update_assets_md(assets_md, [])
    with pytest.raises(AssetRuntimeResolverError, match="no '## Asset Table' section"):
        resolve_assets_row(
            assets_md, tag=TAG, asset_id="logo", project_root=tmp_path
        )


def test_a_non_bundle_family_has_no_rows_to_declare(tmp_path):
    # A family that delivers one asset per planned row must keep failing loudly
    # when that row is missing; auto-appending would hide a planning mistake.
    request_path, _ = _tileset_delivery(tmp_path)
    assets_md = _planned_assets_md(tmp_path)

    with pytest.raises(BundleRowError, match="not a bundle family"):
        declare_bundle_rows(assets_md, request_path, tag=TAG)


@pytest.mark.parametrize(
    "artifact_type", ["Theme", "StyleBoxTexture", "AtlasTexture"]
)
def test_each_kit_artifact_type_resolves_to_a_worker_snapshot(tmp_path, artifact_type):
    request_path, result_path = _kit_delivery(tmp_path, "card-kit")
    assets_md = _planned_assets_md(tmp_path, [CARD_REQUEST_ROW])
    declare_bundle_rows(assets_md, request_path, tag=TAG, supersede=["card_frame"])
    entries = build_ui_card_entry_drafts(
        request_path, result_path, tag=TAG, project_root=tmp_path
    )
    _register(tmp_path, entries)
    update_assets_md(
        assets_md,
        [tmp_path / entry_relative_path(TAG, entry["asset_id"]) for entry in entries],
    )

    entry = next(
        item for item in entries if item["godot_artifact"]["type"] == artifact_type
    )
    snapshot = _snapshot(tmp_path, entry["asset_id"])

    assert snapshot["godot_artifact"] == entry["godot_artifact"]
    assert snapshot["source_layout"] == entry["source_layout"]
    assert list(snapshot) == [
        "asset_id",
        "production_family",
        "source_layout",
        "godot_artifact",
    ]


def test_kit_entries_are_refused_before_the_ladder_passes(tmp_path):
    request_path, result_path = _kit_delivery(tmp_path, "card-kit")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["validation"] = {"passed": True, "levels": {"L0": True, "L1": True}}
    _write_json(result_path, result)

    with pytest.raises(UICardEntryDraftError, match="passed L0-L4"):
        build_ui_card_entry_drafts(
            request_path, result_path, tag=TAG, project_root=tmp_path
        )


def test_two_kit_outputs_may_not_claim_the_same_artifact(tmp_path):
    # Only the Theme has an upstream path contract, so a compiler that derived a
    # stylebox filename from its state rather than its output name would bind
    # several entries to one .tres. The worker then loads a StyleBoxTexture as an
    # AtlasTexture and fails at runtime, with nothing else in the chain to catch
    # it.
    request_path, result_path = _kit_delivery(tmp_path, "card-kit")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    stylebox = next(
        item for item in result["outputs"] if item["godot_type"] == "StyleBoxTexture"
    )
    atlas = next(
        item for item in result["outputs"] if item["godot_type"] == "AtlasTexture"
    )
    atlas["path"] = stylebox["path"]
    _write_json(result_path, result)

    with pytest.raises(UICardEntryDraftError, match="must be published at"):
        build_ui_card_entry_drafts(
            request_path, result_path, tag=TAG, project_root=tmp_path
        )


@pytest.mark.parametrize("family", ["ui-kit", "card-kit"])
def test_a_kit_naming_outputs_by_the_contract_registers(tmp_path, family):
    # The other half of the path rule: a Skill that follows the documented
    # naming must succeed. Without this, the rule is only ever proven by what it
    # rejects, and a producer that never heard of it looks correct until the
    # last step.
    request_path, result_path = _kit_delivery(tmp_path, family)
    request = json.loads(request_path.read_text(encoding="utf-8"))
    result = json.loads(result_path.read_text(encoding="utf-8"))

    for output in result["outputs"]:
        assert output["path"] == expected_runtime_path(
            family, request["asset_id"], output["name"], output["godot_type"]
        )

    entries = build_ui_card_entry_drafts(
        request_path, result_path, tag=TAG, project_root=tmp_path
    )
    assert len(entries) == len(result["outputs"])


def test_the_naming_rule_is_enforced_where_a_skill_can_still_repair_it(tmp_path):
    # The rule lives in check_ui_card_handoff, which standalone L0 calls, so a
    # drifting filename fails during production instead of at registration.
    request_path, result_path = _kit_delivery(tmp_path, "card-kit")
    request = json.loads(request_path.read_text(encoding="utf-8"))
    result = json.loads(result_path.read_text(encoding="utf-8"))
    atlas = next(
        item for item in result["outputs"] if item["godot_type"] == "AtlasTexture"
    )
    atlas["path"] = "res://assets/generated/card-kit/arcane_deck/icons/mana_badge.tres"

    with pytest.raises(UICardContractError, match="must be published at"):
        check_ui_card_handoff(request, result)


def test_a_kit_output_published_off_its_derived_path_is_refused(tmp_path):
    request_path, result_path = _kit_delivery(tmp_path, "card-kit")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    atlas = next(
        item for item in result["outputs"] if item["godot_type"] == "AtlasTexture"
    )
    atlas["path"] = "res://assets/generated/card-kit/arcane_deck/renamed.tres"
    _touch(tmp_path, atlas["path"])
    _write_json(result_path, result)

    with pytest.raises(UICardEntryDraftError, match="must be published at"):
        build_ui_card_entry_drafts(
            request_path, result_path, tag=TAG, project_root=tmp_path
        )


def test_a_rejected_kit_delivery_writes_no_drafts_at_all(tmp_path):
    # Every entry is built before anything is written, so a kit whose third
    # output is bad must not leave the first two on disk for Step 5 to register.
    request_path, result_path = _kit_delivery(tmp_path, "card-kit")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["outputs"][-1]["path"] = (
        "res://assets/generated/card-kit/arcane_deck/wrong.tres"
    )
    _write_json(result_path, result)
    out_dir = tmp_path / "work"

    with pytest.raises(UICardEntryDraftError):
        write_ui_card_entry_drafts(
            request_path, result_path, tag=TAG, project_root=tmp_path, out_dir=out_dir
        )

    assert not out_dir.exists() or list(out_dir.glob("*.json")) == []


def test_a_dropped_kit_output_does_not_leave_a_stale_ready_draft(tmp_path):
    request_path, result_path = _kit_delivery(tmp_path, "card-kit")
    out_dir = tmp_path / "work"
    write_ui_card_entry_drafts(
        request_path, result_path, tag=TAG, project_root=tmp_path, out_dir=out_dir
    )
    assert (out_dir / "arcane_deck--mana_badge.json").exists()

    # Re-plan the kit with the region renamed: the old logical output is gone.
    request = json.loads(request_path.read_text(encoding="utf-8"))
    result = json.loads(result_path.read_text(encoding="utf-8"))
    request["spec"]["required_regions"] = ["mana_pip"]
    request["spec"]["atlas_regions"][0]["output_name"] = "mana_pip"
    request["spec"]["atlas_regions"][0]["logical_asset_id"] = "mana_pip"
    atlas = next(
        item for item in result["outputs"] if item["godot_type"] == "AtlasTexture"
    )
    atlas["name"] = "mana_pip"
    atlas["path"] = "res://assets/generated/card-kit/arcane_deck/mana_pip.tres"
    _touch(tmp_path, atlas["path"])
    _write_json(request_path, request)
    _write_json(result_path, result)

    payload = write_ui_card_entry_drafts(
        request_path, result_path, tag=TAG, project_root=tmp_path, out_dir=out_dir
    )

    assert payload["removed"] == ["arcane_deck--mana_badge.json"]
    assert not (out_dir / "arcane_deck--mana_badge.json").exists()
    assert (out_dir / "arcane_deck--mana_pip.json").exists()


def test_kit_entry_fails_closed_on_a_missing_compiled_resource(tmp_path):
    request_path, result_path = _kit_delivery(tmp_path, "card-kit")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    theme = next(
        item for item in result["outputs"] if item["godot_type"] == "Theme"
    )
    (tmp_path / theme["path"][len("res://"):]).unlink()

    with pytest.raises(UICardEntryDraftError, match="missing or empty"):
        build_ui_card_entry_drafts(
            request_path, result_path, tag=TAG, project_root=tmp_path
        )


def test_a_kit_row_below_ready_stays_missing_for_the_worker(tmp_path):
    request_path, result_path = _kit_delivery(tmp_path, "card-kit")
    entries = build_ui_card_entry_drafts(
        request_path, result_path, tag=TAG, project_root=tmp_path
    )
    entry = entries[0]
    entry["processing_status"] = "compiled"
    assets_md = _planned_assets_md(tmp_path, [CARD_REQUEST_ROW])
    declare_bundle_rows(assets_md, request_path, tag=TAG, supersede=["card_frame"])
    _register(tmp_path, [entry])

    with pytest.raises(AssetsMdUpdateError, match="only a ready runtime entry"):
        update_assets_md(
            assets_md, [tmp_path / entry_relative_path(TAG, entry["asset_id"])]
        )
    with pytest.raises(AssetRuntimeResolverError):
        _snapshot(tmp_path, entry["asset_id"])


# --------------------------------------------------------------------------
# fx-bundle -> SpriteFrames and Texture2D, compiled -> ready
# --------------------------------------------------------------------------

FX_ANIMATED_ID = "arc_blast"
FX_STATIC_ID = "lantern_spark"


def _fx_animated_inputs(project_root: Path):
    root = f"assets/generated/fx-bundle/{FX_ANIMATED_ID}"
    frames = ["blast_01", "blast_02", "blast_03"]
    request = {
        "asset_type": "fx-bundle",
        "asset_id": FX_ANIMATED_ID,
        "brief": "A centered three-frame arc blast.",
        "provider": "codex",
        "spec": {
            "mode": "animated",
            "required_actions": ["blast"],
            "actions": [
                {
                    "name": "blast",
                    "grid": {"columns": 3, "rows": 1},
                    "frame_names": frames,
                    "fps": 12,
                    "loop": False,
                    "frame_durations": [1, 2, 1],
                }
            ],
        },
    }
    metadata = {
        "frame_count": 3,
        "final_sheet_path": f"{root}/{FX_ANIMATED_ID}_sheet.png",
        "final_frame_paths": [
            f"{root}/{FX_ANIMATED_ID}_blast_{frame}.png" for frame in frames
        ],
        "align": "center",
        "shared_scale": True,
        "action_name": "blast",
        "fps": 12,
        "loop": False,
        "frame_durations": [1, 2, 1],
        "edge_touch_frames": [],
        "scale_reference": {"checked": False},
        "cell_size": 256,
        "grid": {"cols": 3, "rows": 1},
        "frame_labels": frames,
    }
    for relative in [metadata["final_sheet_path"], *metadata["final_frame_paths"]]:
        _touch(project_root, f"res://{relative}")
    return (
        _write_json(project_root / "ASSET_REQUEST.json", request),
        _write_json(
            project_root / ".godotmaker/asset-generation/work/blast/pipeline-meta.json",
            metadata,
        ),
        root,
    )


def _fx_animated_result(root: str) -> dict:
    return {
        "asset_type": "fx-bundle",
        "outputs": [
            {
                "role": "runtime",
                "path": f"res://{root}/{FX_ANIMATED_ID}.tres",
                "godot_type": "SpriteFrames",
            }
        ],
        "sources": [
            {"path": f"res://{root}/{FX_ANIMATED_ID}_sheet.png", "layout": "grid_sheet"}
        ],
        "previews": [],
        "validation": {
            "passed": True,
            "levels": {level: True for level in LEVELS_PASSED},
        },
    }


def _compile_fx_animated(project_root: Path, request_path: Path, metadata_path: Path):
    return write_fx_bundle_entry_draft(
        metadata_path,
        request_path=request_path,
        asset_id=FX_ANIMATED_ID,
        tag=TAG,
        project_root=project_root,
        out=project_root / ".godotmaker/asset-generation/work/entries/fx.json",
    )


def test_animated_fx_promotes_to_ready_and_reaches_a_worker_snapshot(tmp_path):
    request_path, metadata_path, root = _fx_animated_inputs(tmp_path)
    compiled = _compile_fx_animated(tmp_path, request_path, metadata_path)
    assert compiled["processing_status"] == "compiled"
    result_path = _write_json(tmp_path / "fx-result.json", _fx_animated_result(root))
    assets_md = _assets_md(tmp_path, [FX_ANIMATED_ID])

    promoted = build_fx_bundle_entry_draft(
        metadata_path,
        request_path=request_path,
        asset_id=FX_ANIMATED_ID,
        tag=TAG,
        project_root=tmp_path,
        result_path=result_path,
    )
    assert promoted["entry"]["processing_status"] == "ready"

    _register(tmp_path, [promoted["entry"]])
    update_assets_md(assets_md, [tmp_path / entry_relative_path(TAG, FX_ANIMATED_ID)])

    assert _snapshot(tmp_path, FX_ANIMATED_ID)["godot_artifact"] == {
        "type": "SpriteFrames",
        "path": f"res://{root}/{FX_ANIMATED_ID}.tres",
    }


def test_animated_fx_promotion_registers_the_validated_bytes(tmp_path):
    request_path, metadata_path, root = _fx_animated_inputs(tmp_path)
    _compile_fx_animated(tmp_path, request_path, metadata_path)
    artifact = tmp_path / root / f"{FX_ANIMATED_ID}.tres"
    validated = artifact.read_bytes()
    result_path = _write_json(tmp_path / "fx-result.json", _fx_animated_result(root))

    build_fx_bundle_entry_draft(
        metadata_path,
        request_path=request_path,
        asset_id=FX_ANIMATED_ID,
        tag=TAG,
        project_root=tmp_path,
        result_path=result_path,
    )

    assert artifact.read_bytes() == validated


def test_a_stale_result_cannot_promote_a_regenerated_animated_fx(tmp_path):
    # Stable paths are identity-derived, so a regeneration lands on the exact
    # paths the old result names. Only the fingerprint tells them apart.
    request_path, metadata_path, root = _fx_animated_inputs(tmp_path)
    _compile_fx_animated(tmp_path, request_path, metadata_path)
    result_path = _write_json(tmp_path / "fx-result.json", _fx_animated_result(root))
    Image.new("RGBA", (8, 8), (7, 7, 7, 255)).save(
        tmp_path / root / f"{FX_ANIMATED_ID}_blast_blast_02.png"
    )

    with pytest.raises(ActionEntryDraftError, match="changed since the compiled build"):
        build_fx_bundle_entry_draft(
            metadata_path,
            request_path=request_path,
            asset_id=FX_ANIMATED_ID,
            tag=TAG,
            project_root=tmp_path,
            result_path=result_path,
        )


def test_animated_fx_promotion_needs_a_compiled_build_to_stand_on(tmp_path):
    request_path, metadata_path, root = _fx_animated_inputs(tmp_path)
    result_path = _write_json(tmp_path / "fx-result.json", _fx_animated_result(root))

    with pytest.raises(ActionEntryDraftError, match="no compiled build to promote"):
        build_fx_bundle_entry_draft(
            metadata_path,
            request_path=request_path,
            asset_id=FX_ANIMATED_ID,
            tag=TAG,
            project_root=tmp_path,
            result_path=result_path,
        )


def test_animated_fx_promotion_rejects_a_failed_ladder(tmp_path):
    request_path, metadata_path, root = _fx_animated_inputs(tmp_path)
    _compile_fx_animated(tmp_path, request_path, metadata_path)
    result = _fx_animated_result(root)
    result["validation"] = {"passed": False, "levels": {"L0": True, "L1": False}}
    result_path = _write_json(tmp_path / "fx-result.json", result)

    with pytest.raises(ActionEntryDraftError):
        build_fx_bundle_entry_draft(
            metadata_path,
            request_path=request_path,
            asset_id=FX_ANIMATED_ID,
            tag=TAG,
            project_root=tmp_path,
            result_path=result_path,
        )


def _fx_static_inputs(project_root: Path):
    relative = f"assets/generated/fx-bundle/{FX_STATIC_ID}/{FX_STATIC_ID}.png"
    _touch(project_root, f"res://{relative}")
    report = {
        "version": 1,
        "asset_id": "fx_source",
        "tag": TAG,
        "strategy": "transparent_autoslice",
        "status": "selected",
        "selected_count": 1,
        "rejected_count": 0,
        "candidates": [
            {
                "candidate_id": f"fx.{FX_STATIC_ID}",
                "name": FX_STATIC_ID,
                "state": "selected",
                "final_path": relative,
            }
        ],
    }
    request = {
        "asset_type": "fx-bundle",
        "asset_id": FX_STATIC_ID,
        "brief": "A static lantern spark.",
        "provider": "codex",
        "spec": {"mode": "static"},
    }
    return (
        _write_json(
            project_root / ".godotmaker/asset-generation/curation/fx_source.json",
            report,
        ),
        _write_json(project_root / "ASSET_REQUEST.json", request),
        relative,
    )


def _fx_static_result(relative: str) -> dict:
    return {
        "asset_type": "fx-bundle",
        "outputs": [
            {"role": "runtime", "path": f"res://{relative}", "godot_type": "Texture2D"}
        ],
        "sources": [{"path": f"res://{relative}", "layout": "single"}],
        "previews": [],
        "validation": {
            "passed": True,
            "levels": {level: True for level in LEVELS_PASSED},
        },
    }


def _publish_fx_static(project_root: Path, report_path, request_path, result_path=None):
    return write_fx_static_entry_draft(
        report_path,
        candidate=FX_STATIC_ID,
        request_path=request_path,
        asset_id=FX_STATIC_ID,
        tag=TAG,
        project_root=project_root,
        out=project_root / ".godotmaker/asset-generation/work/entries/spark.json",
        result_path=result_path,
    )


def test_static_fx_promotes_to_ready_and_reaches_a_worker_snapshot(tmp_path):
    report_path, request_path, relative = _fx_static_inputs(tmp_path)
    compiled = _publish_fx_static(tmp_path, report_path, request_path)
    assert compiled["processing_status"] == "compiled"
    result_path = _write_json(tmp_path / "fx-result.json", _fx_static_result(relative))
    assets_md = _assets_md(tmp_path, [FX_STATIC_ID])

    promoted = _publish_fx_static(tmp_path, report_path, request_path, result_path)
    assert promoted["processing_status"] == "ready"

    entry = json.loads(
        (tmp_path / ".godotmaker/asset-generation/work/entries/spark.json").read_text(
            encoding="utf-8"
        )
    )
    _register(tmp_path, [entry])
    update_assets_md(assets_md, [tmp_path / entry_relative_path(TAG, FX_STATIC_ID)])

    assert _snapshot(tmp_path, FX_STATIC_ID)["godot_artifact"] == {
        "type": "Texture2D",
        "path": f"res://{relative}",
    }


def test_a_stale_result_cannot_promote_a_regenerated_static_fx(tmp_path):
    report_path, request_path, relative = _fx_static_inputs(tmp_path)
    _publish_fx_static(tmp_path, report_path, request_path)
    result_path = _write_json(tmp_path / "fx-result.json", _fx_static_result(relative))
    Image.new("RGBA", (8, 8), (3, 3, 3, 255)).save(tmp_path / relative)

    with pytest.raises(
        CurationEntryDraftError, match="changed since the compiled build"
    ):
        _publish_fx_static(tmp_path, report_path, request_path, result_path)


def test_static_fx_promotion_needs_a_compiled_build_to_stand_on(tmp_path):
    report_path, request_path, relative = _fx_static_inputs(tmp_path)
    result_path = _write_json(tmp_path / "fx-result.json", _fx_static_result(relative))

    with pytest.raises(CurationEntryDraftError, match="no compiled build to promote"):
        _publish_fx_static(tmp_path, report_path, request_path, result_path)


def test_static_fx_promotion_rejects_a_result_sourced_from_another_asset(tmp_path):
    # check_bundle_handoff only proves *some* source carries the `single` layout,
    # never which file, so the static path needs the same source binding the
    # animated path has always had.
    report_path, request_path, relative = _fx_static_inputs(tmp_path)
    _publish_fx_static(tmp_path, report_path, request_path)
    result = _fx_static_result(relative)
    result["sources"] = [
        {"path": "res://assets/generated/fx-bundle/other/other.png", "layout": "single"}
    ]
    result_path = _write_json(tmp_path / "fx-result.json", result)

    with pytest.raises(CurationEntryDraftError, match="single source must be"):
        _publish_fx_static(tmp_path, report_path, request_path, result_path)


def test_static_fx_promotion_rejects_a_reference_output_posing_as_runtime(tmp_path):
    # A canonical PNG announced with a godot_type reaches the game as a rival
    # sprite for the same asset. The animated path rejected this; static did not.
    report_path, request_path, relative = _fx_static_inputs(tmp_path)
    _publish_fx_static(tmp_path, report_path, request_path)
    result = _fx_static_result(relative)
    result["outputs"].append(
        {
            "role": "reference",
            "path": f"res://assets/generated/fx-bundle/{FX_STATIC_ID}/canonical.png",
            "godot_type": "Texture2D",
        }
    )
    result_path = _write_json(tmp_path / "fx-result.json", result)

    with pytest.raises(CurationEntryDraftError, match="must not declare a godot_type"):
        _publish_fx_static(tmp_path, report_path, request_path, result_path)


def test_static_fx_promotion_pins_reference_outputs_to_this_asset(tmp_path):
    report_path, request_path, relative = _fx_static_inputs(tmp_path)
    _publish_fx_static(tmp_path, report_path, request_path)
    result = _fx_static_result(relative)
    result["outputs"].append(
        {
            "role": "reference",
            "path": "res://assets/generated/fx-bundle/other_asset/canonical.png",
        }
    )
    result_path = _write_json(tmp_path / "fx-result.json", result)

    with pytest.raises(CurationEntryDraftError, match="must be a file under"):
        _publish_fx_static(tmp_path, report_path, request_path, result_path)


def test_static_fx_promotion_accepts_a_well_formed_reference_output(tmp_path):
    report_path, request_path, relative = _fx_static_inputs(tmp_path)
    _publish_fx_static(tmp_path, report_path, request_path)
    result = _fx_static_result(relative)
    result["outputs"].append(
        {
            "role": "reference",
            "path": f"res://assets/generated/fx-bundle/{FX_STATIC_ID}/canonical.png",
        }
    )
    result_path = _write_json(tmp_path / "fx-result.json", result)

    promoted = _publish_fx_static(tmp_path, report_path, request_path, result_path)

    assert promoted["processing_status"] == "ready"


def test_static_fx_promotion_rejects_a_result_about_another_image(tmp_path):
    report_path, request_path, relative = _fx_static_inputs(tmp_path)
    _publish_fx_static(tmp_path, report_path, request_path)
    result = _fx_static_result(relative)
    result["outputs"][0]["path"] = "res://assets/generated/fx-bundle/other/other.png"
    result_path = _write_json(tmp_path / "fx-result.json", result)

    with pytest.raises(CurationEntryDraftError):
        _publish_fx_static(tmp_path, report_path, request_path, result_path)


# --------------------------------------------------------------------------
# CLI wiring: the documented command is what /gm-asset actually runs.
# --------------------------------------------------------------------------

TOOLS = ROOT / "tools"


def _run(tool: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOLS / tool), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_animated_fx_cli_promotes_the_compiled_entry(tmp_path):
    request_path, metadata_path, root = _fx_animated_inputs(tmp_path)
    _compile_fx_animated(tmp_path, request_path, metadata_path)
    result_path = _write_json(tmp_path / "fx-result.json", _fx_animated_result(root))
    out = tmp_path / ".godotmaker/asset-generation/work/entries/fx.json"

    completed = _run(
        "asset_action_entry_draft.py",
        "--metadata", str(metadata_path),
        "--request", str(request_path),
        "--result", str(result_path),
        "--asset-id", FX_ANIMATED_ID,
        "--tag", TAG,
        "--production-family", "fx-bundle",
        "--project-root", str(tmp_path),
        "--out", str(out),
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(completed.stdout)["processing_status"] == "ready"
    assert json.loads(out.read_text(encoding="utf-8"))["processing_status"] == "ready"


def test_static_fx_cli_promotes_the_compiled_entry(tmp_path):
    report_path, request_path, relative = _fx_static_inputs(tmp_path)
    _publish_fx_static(tmp_path, report_path, request_path)
    result_path = _write_json(tmp_path / "fx-result.json", _fx_static_result(relative))
    out = tmp_path / ".godotmaker/asset-generation/work/entries/spark.json"

    completed = _run(
        "asset_curation_entry_draft.py",
        "--report", str(report_path),
        "--candidate", FX_STATIC_ID,
        "--request", str(request_path),
        "--result", str(result_path),
        "--asset-id", FX_STATIC_ID,
        "--tag", TAG,
        "--production-family", "fx-bundle",
        "--project-root", str(tmp_path),
        "--out", str(out),
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(out.read_text(encoding="utf-8"))["processing_status"] == "ready"


def test_tileset_cli_writes_the_ready_draft(tmp_path):
    request_path, result_path = _tileset_delivery(tmp_path)
    out = tmp_path / ".godotmaker/asset-generation/work/entries/grassland.json"

    completed = _run(
        "asset_tileset_entry_draft.py",
        "--request", str(request_path),
        "--result", str(result_path),
        "--tag", TAG,
        "--project-root", str(tmp_path),
        "--out", str(out),
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    entry = json.loads(out.read_text(encoding="utf-8"))
    assert entry["godot_artifact"]["type"] == "TileSet"
    assert entry["processing_status"] == "ready"


def test_bundle_rows_cli_declares_and_supersedes(tmp_path):
    request_path, _ = _kit_delivery(tmp_path, "card-kit")
    assets_md = _planned_assets_md(tmp_path, [CARD_REQUEST_ROW])

    completed = _run(
        "asset_bundle_rows.py",
        "--assets-md", str(assets_md),
        "--request", str(request_path),
        "--tag", TAG,
        "--supersede", "card_frame",
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["created"] == [
        "arcane_deck--card_theme",
        "arcane_deck--rare_card_normal",
        "arcane_deck--mana_badge",
    ]
    assert payload["superseded"] == ["card_frame"]
    assert _row(assets_md, "card_frame")[7] == "N/A"


def test_kit_cli_writes_one_draft_per_runtime_output(tmp_path):
    request_path, result_path = _kit_delivery(tmp_path, "card-kit")
    out_dir = tmp_path / ".godotmaker/asset-generation/work/entries"

    completed = _run(
        "asset_ui_card_entry_draft.py",
        "--request", str(request_path),
        "--result", str(result_path),
        "--tag", TAG,
        "--project-root", str(tmp_path),
        "--out-dir", str(out_dir),
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(completed.stdout)["count"] == 3
    assert sorted(path.name for path in out_dir.glob("*.json")) == [
        "arcane_deck--card_theme.json",
        "arcane_deck--mana_badge.json",
        "arcane_deck--rare_card_normal.json",
    ]
