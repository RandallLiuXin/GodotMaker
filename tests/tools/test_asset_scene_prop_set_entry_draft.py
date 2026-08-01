"""Ready stable-entry draft coverage for scene-prop-set atlases."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from asset_scene_prop_set_entry_draft import (  # noqa: E402
    ScenePropSetEntryDraftError,
    build_scene_prop_set_entry_draft,
    write_scene_prop_set_entry_draft,
)


ASSET_ID = "market-scene"
TAG = "chapter-1"
SAMPLE_ROOT = REPO_ROOT / "skills" / "assets" / "scene-prop-set" / "samples"


def _prepare_delivery(tmp_path: Path) -> tuple[Path, Path, dict]:
    stable = tmp_path / "assets" / "generated" / "scene-prop-set" / ASSET_ID
    stable.mkdir(parents=True)
    (stable / f"{ASSET_ID}.png").write_bytes(
        (SAMPLE_ROOT / "atlas" / f"{ASSET_ID}.png").read_bytes()
    )
    (stable / f"{ASSET_ID}.json").write_text(
        (SAMPLE_ROOT / "atlas" / f"{ASSET_ID}.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    declaration = json.loads(
        (SAMPLE_ROOT / "declaration" / "spec.json").read_text(encoding="utf-8")
    )
    result = json.loads(
        (SAMPLE_ROOT / "result" / f"{ASSET_ID}.json").read_text(encoding="utf-8")
    )
    for slot in declaration["slots"]:
        (stable / f"{slot['name']}.tres").write_text(
            '[gd_resource type="AtlasTexture"]\n', encoding="utf-8"
        )
    declaration_path = tmp_path / "declaration.json"
    declaration_path.write_text(json.dumps(declaration), encoding="utf-8")
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps(result), encoding="utf-8")
    return result_path, declaration_path, result


def _build(tmp_path: Path, *, primary: str = "market_stall") -> dict:
    result_path, declaration_path, _ = _prepare_delivery(tmp_path)
    return build_scene_prop_set_entry_draft(
        result_path,
        declaration_path,
        asset_id=ASSET_ID,
        tag=TAG,
        primary_output=primary,
        project_root=tmp_path,
    )


def test_builds_ready_region_atlas_entry_from_complete_delivery(tmp_path):
    entry = _build(tmp_path)

    assert entry == {
        "version": 1,
        "asset_id": ASSET_ID,
        "tag": TAG,
        "production_family": "scene-prop-set",
        "source_layout": {
            "type": "region_atlas",
            "path": "res://assets/generated/scene-prop-set/market-scene/market-scene.png",
        },
        "godot_artifact": {
            "type": "AtlasTexture",
            "path": "res://assets/generated/scene-prop-set/market-scene/market_stall.tres",
        },
        "processing_status": "ready",
    }


def test_uses_an_explicit_declared_primary_output(tmp_path):
    entry = _build(tmp_path, primary="water_well")

    assert entry["godot_artifact"]["path"].endswith("/water_well.tres")


def test_accepts_reading_order_declaration_with_canonical_metadata_resources(tmp_path):
    result_path, declaration_path, _ = _prepare_delivery(tmp_path)
    declaration = json.loads(declaration_path.read_text(encoding="utf-8"))
    declaration["slots"] = [
        declaration["slots"][2],
        declaration["slots"][0],
        declaration["slots"][1],
    ]
    declaration_path.write_text(json.dumps(declaration), encoding="utf-8")

    entry = build_scene_prop_set_entry_draft(
        result_path,
        declaration_path,
        asset_id=ASSET_ID,
        tag=TAG,
        primary_output="water_well",
        project_root=tmp_path,
    )

    assert entry["godot_artifact"]["path"].endswith("/water_well.tres")


def test_rejects_missing_or_partial_runtime_delivery(tmp_path):
    result_path, declaration_path, result = _prepare_delivery(tmp_path)
    broken = copy.deepcopy(result)
    broken["outputs"].pop()
    result_path.write_text(json.dumps(broken), encoding="utf-8")

    with pytest.raises(ScenePropSetEntryDraftError, match="exactly match"):
        build_scene_prop_set_entry_draft(
            result_path,
            declaration_path,
            asset_id=ASSET_ID,
            tag=TAG,
            primary_output="market_stall",
            project_root=tmp_path,
        )


def test_rejects_unvalidated_result_and_metadata_drift(tmp_path):
    result_path, declaration_path, result = _prepare_delivery(tmp_path)
    broken = copy.deepcopy(result)
    broken["validation"]["levels"]["L4"] = False
    result_path.write_text(json.dumps(broken), encoding="utf-8")

    with pytest.raises(ScenePropSetEntryDraftError, match="passed L0 through L4"):
        build_scene_prop_set_entry_draft(
            result_path,
            declaration_path,
            asset_id=ASSET_ID,
            tag=TAG,
            primary_output="market_stall",
            project_root=tmp_path,
        )

    result_path.write_text(json.dumps(result), encoding="utf-8")
    metadata_path = tmp_path / "assets/generated/scene-prop-set/market-scene/market-scene.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["regions"].reverse()
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ScenePropSetEntryDraftError, match="slot order"):
        build_scene_prop_set_entry_draft(
            result_path,
            declaration_path,
            asset_id=ASSET_ID,
            tag=TAG,
            primary_output="market_stall",
            project_root=tmp_path,
        )


def test_writes_draft_only_after_all_delivery_checks(tmp_path):
    result_path, declaration_path, _ = _prepare_delivery(tmp_path)
    out = tmp_path / "work" / "entry.json"

    receipt = write_scene_prop_set_entry_draft(
        result_path,
        declaration_path,
        asset_id=ASSET_ID,
        tag=TAG,
        primary_output="market_stall",
        project_root=tmp_path,
        out=out,
    )

    assert receipt["ok"] is True
    assert json.loads(out.read_text(encoding="utf-8"))["processing_status"] == "ready"
