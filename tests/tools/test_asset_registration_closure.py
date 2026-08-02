"""End-to-end registration closure for every v1 runtime artifact type.

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
from asset_ui_card_entry_draft import (  # noqa: E402
    UICardEntryDraftError,
    build_ui_card_entry_drafts,
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
        last = max(
            index
            for index, line in enumerate(lines)
            if split_assets_md_row(line) is not None
        )
        lines[last + 1 : last + 1] = [row + "\n" for row in extra_rows]
    path = project_root / "ASSETS.md"
    path.write_text("".join(lines), encoding="utf-8")
    return path


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

    with pytest.raises(BundleRowError, match="no current-tag rows to supersede"):
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
