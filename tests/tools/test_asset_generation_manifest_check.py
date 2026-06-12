import json
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_generation_manifest_check import ManifestCheckError, check_manifest  # noqa: E402


def write_manifest(path: Path, asset_overrides=None):
    asset = {
        "asset_id": "player_idle",
        "tag": "v0.1.0",
        "family": "character_action_source",
        "production_shape": "action_sheet",
        "runtime_role": "player",
        "source_path": ".godotmaker/asset-generation/sources/player_idle_source.png",
        "final_path": "assets/sprites/player_idle.png",
        "derived_from": "player_canonical",
        "canonical_reference": "player_canonical",
        "prompt_path": ".godotmaker/asset-generation/prompts/player_idle.txt",
        "processing_status": "ready",
        "extraction_status": "processed",
        "curation": {
            "status": "selected",
            "strategy": "transparent_grid",
            "report_path": ".godotmaker/asset-generation/curation/player_idle.json",
            "selected_count": 4,
            "rejected_count": 0,
        },
        "qc": {"alpha": "ok"},
        "preview_path": None,
        "notes": "",
    }
    if asset_overrides:
        asset.update(asset_overrides)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": 1, "assets": [asset]}),
        encoding="utf-8",
    )


def touch(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")


def write_action_runtime_metadata(
    project_root: Path,
    *,
    path: str = "assets/sprites/player_idle.json",
    asset_id: str = "player_idle_delivery",
    tag: str = "v0.1.0",
    runtime_artifact: str = "grid_sheet",
    sheet_path: str = "assets/sprites/player_idle.png",
    frame_count: int = 4,
    edge_touch_frames=None,
):
    edge_touch_frames = edge_touch_frames or []
    metadata = {
        "version": 1,
        "runtime_artifact": runtime_artifact,
        "asset_id": asset_id,
        "tag": tag,
        "sheet_path": sheet_path,
        "frame_count": frame_count,
        "frame_paths": [
            "assets/sprites/player_idle_01.png",
            "assets/sprites/player_idle_02.png",
            "assets/sprites/player_idle_03.png",
            "assets/sprites/player_idle_04.png",
        ][:frame_count],
        "align": "feet",
        "shared_scale": True,
        "edge_touch_frames": edge_touch_frames,
        "scale_reference": {"checked": False},
    }
    target = project_root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(metadata), encoding="utf-8")


def write_atlas_runtime_metadata(
    project_root: Path,
    *,
    path: str = "assets/ui/main_atlas.json",
    asset_id: str = "ui_main_kit",
    tag: str = "v0.1.0",
    runtime_artifact: str = "region_atlas",
    atlas_path: str | None = "assets/ui/main_atlas.png",
):
    metadata = {
        "version": 1,
        "runtime_artifact": runtime_artifact,
        "asset_id": asset_id,
        "tag": tag,
        "regions": [
            {"name": "battle_button", "rect": [0, 0, 256, 96]},
            {"name": "quest_tile", "rect": [256, 0, 256, 96]},
        ],
    }
    if atlas_path is not None:
        metadata["atlas_path"] = atlas_path
    target = project_root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(metadata), encoding="utf-8")


def test_check_manifest_accepts_valid_schema(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(manifest)

    result = check_manifest(manifest, project_root=tmp_path)

    assert result["ok"] is True
    assert result["asset_count"] == 1
    assert result["check_files"] is False


def test_check_manifest_accepts_target_size_and_aspect_metadata(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(
        manifest,
        {
            "family": "screen_reference",
            "production_shape": "reference_only",
            "target_size": "1280x720",
            "target_aspect": "16:9",
            "curation": None,
        },
    )

    result = check_manifest(manifest, project_root=tmp_path)

    assert result["asset_count"] == 1


def test_check_manifest_rejects_non_string_target_metadata(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(
        manifest,
        {
            "family": "screen_reference",
            "production_shape": "reference_only",
            "target_size": [1280, 720],
            "target_aspect": {"w": 16, "h": 9},
            "curation": None,
        },
    )

    with pytest.raises(ManifestCheckError, match="target_size"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_rejects_invalid_target_metadata_format(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(
        manifest,
        {
            "family": "screen_reference",
            "production_shape": "reference_only",
            "target_size": "large",
            "target_aspect": "wide",
            "curation": None,
        },
    )

    with pytest.raises(ManifestCheckError, match="target_size"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_requires_screen_reference_target_geometry(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(
        manifest,
        {
            "family": "screen_reference",
            "production_shape": "reference_only",
            "curation": None,
        },
    )

    with pytest.raises(ManifestCheckError, match="missing target_size"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_requires_background_target_geometry(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(
        manifest,
        {
            "family": "background",
            "production_shape": "single_image",
            "curation": None,
        },
    )

    with pytest.raises(ManifestCheckError, match="missing target_size"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_accepts_scene_prop_platform_and_card_families(tmp_path):
    for family in (
        "scene_prop_set",
        "platform_strip",
        "card_component_sheet",
        "card_frame_source",
        "portrait_frame_source",
    ):
        manifest = tmp_path / family / ".godotmaker" / "asset-generation" / "manifest.json"
        write_manifest(
            manifest,
            {
                "asset_id": f"{family}_source",
                "family": family,
                "production_shape": "grid_sheet",
                "processing_status": "needs_curation",
                "extraction_status": "extracted",
                "final_path": None,
                "curation": {
                    "status": "candidate_extracted",
                    "strategy": "solid_background_autoslice",
                    "report_path": f".godotmaker/asset-generation/curation/{family}.json",
                    "selected_count": 0,
                    "rejected_count": 0,
                },
            },
        )

        result = check_manifest(manifest, project_root=tmp_path / family)

        assert result["asset_count"] == 1


def test_check_manifest_accepts_card_frame_single_image_without_curation(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(
        manifest,
        {
            "asset_id": "card_frame_gold",
            "family": "card_frame_source",
            "production_shape": "single_image",
            "runtime_artifact": "single",
            "runtime_role": "card frame",
            "source_path": ".godotmaker/asset-generation/sources/card_frame_gold_source.png",
            "final_path": "assets/ui/card_frame_gold.png",
            "prompt_path": ".godotmaker/asset-generation/prompts/card_frame_gold.txt",
            "processing_status": "ready",
            "extraction_status": "not_required",
            "curation": {
                "status": "not_required",
                "strategy": "none",
                "report_path": None,
            },
        },
    )

    result = check_manifest(manifest, project_root=tmp_path)

    assert result["asset_count"] == 1


def test_check_manifest_accepts_character_portrait_single_image(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(
        manifest,
        {
            "asset_id": "player_portrait",
            "family": "character_portrait",
            "production_shape": "single_image",
            "runtime_artifact": "single",
            "runtime_role": "character select portrait",
            "source_path": ".godotmaker/asset-generation/sources/player_portrait_source.png",
            "final_path": "assets/portraits/player.png",
            "prompt_path": ".godotmaker/asset-generation/prompts/player_portrait.txt",
            "processing_status": "ready",
            "extraction_status": "not_required",
            "derived_from": "player_canonical",
            "curation": {
                "status": "not_required",
                "strategy": "none",
                "report_path": None,
            },
        },
    )

    result = check_manifest(manifest, project_root=tmp_path)

    assert result["asset_count"] == 1


def test_check_manifest_allows_deferred_background_without_target_geometry(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(
        manifest,
        {
            "family": "background",
            "production_shape": "single_image",
            "source_path": None,
            "final_path": None,
            "prompt_path": None,
            "processing_status": "deferred",
            "extraction_status": "not_required",
            "curation": None,
        },
    )

    result = check_manifest(manifest, project_root=tmp_path)

    assert result["asset_count"] == 1


def test_check_manifest_accepts_character_frame_output_delivery_sheet(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_action_runtime_metadata(tmp_path)
    write_manifest(
        manifest,
        {
            "asset_id": "player_idle_delivery",
            "family": "character_frame_output",
            "production_shape": "delivery_sheet",
            "source_path": ".godotmaker/asset-generation/curation/player_idle/sheet.png",
            "final_path": "assets/sprites/player_idle.png",
            "derived_from": "player_idle",
            "canonical_reference": "player_canonical",
            "qc": {
                "action_processing": {
                    "frame_count": 4,
                    "metadata_path": "assets/sprites/player_idle.json",
                }
            },
        },
    )

    result = check_manifest(manifest, project_root=tmp_path)

    assert result["asset_count"] == 1


def test_check_manifest_requires_character_frame_output_action_metadata(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(
        manifest,
        {
            "asset_id": "player_idle_delivery",
            "family": "character_frame_output",
            "production_shape": "delivery_sheet",
            "derived_from": "",
            "canonical_reference": "",
            "qc": {},
        },
    )

    with pytest.raises(ManifestCheckError, match="qc.action_processing"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_rejects_character_frame_output_edge_touch(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_action_runtime_metadata(tmp_path, frame_count=1, edge_touch_frames=["player_idle.idle_01"])
    write_manifest(
        manifest,
        {
            "asset_id": "player_idle_delivery",
            "family": "character_frame_output",
            "production_shape": "delivery_sheet",
            "source_path": ".godotmaker/asset-generation/curation/player_idle/sheet.png",
            "final_path": "assets/sprites/player_idle.png",
            "derived_from": "player_idle",
            "canonical_reference": "player_canonical",
            "qc": {
                "action_processing": {
                    "frame_count": 1,
                    "metadata_path": "assets/sprites/player_idle.json",
                }
            },
        },
    )

    with pytest.raises(ManifestCheckError, match="edge_touch_frames must be empty"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_rejects_action_runtime_metadata_identity_mismatch(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_action_runtime_metadata(tmp_path, asset_id="enemy_idle_delivery")
    write_manifest(
        manifest,
        {
            "asset_id": "player_idle_delivery",
            "family": "character_frame_output",
            "production_shape": "delivery_sheet",
            "source_path": ".godotmaker/asset-generation/curation/player_idle/sheet.png",
            "final_path": "assets/sprites/player_idle.png",
            "derived_from": "player_idle",
            "canonical_reference": "player_canonical",
            "qc": {
                "action_processing": {
                    "frame_count": 4,
                    "metadata_path": "assets/sprites/player_idle.json",
                }
            },
        },
    )

    with pytest.raises(ManifestCheckError, match="asset_id must match manifest"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_rejects_action_runtime_metadata_sheet_mismatch(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_action_runtime_metadata(tmp_path, sheet_path="assets/sprites/other_sheet.png")
    write_manifest(
        manifest,
        {
            "asset_id": "player_idle_delivery",
            "family": "character_frame_output",
            "production_shape": "delivery_sheet",
            "source_path": ".godotmaker/asset-generation/curation/player_idle/sheet.png",
            "final_path": "assets/sprites/player_idle.png",
            "derived_from": "player_idle",
            "canonical_reference": "player_canonical",
            "qc": {
                "action_processing": {
                    "frame_count": 4,
                    "metadata_path": "assets/sprites/player_idle.json",
                }
            },
        },
    )

    with pytest.raises(ManifestCheckError, match="sheet_path must match final_path"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_rejects_unknown_family(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(manifest, {"family": "model_reference"})

    with pytest.raises(ManifestCheckError, match="family is not allowed"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_rejects_unknown_extraction_status(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(manifest, {"extraction_status": "garbage"})

    with pytest.raises(ManifestCheckError, match="extraction_status is not allowed"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_rejects_unknown_curation_status(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(manifest, {"curation": {"status": "garbage", "strategy": "transparent_grid"}})

    with pytest.raises(ManifestCheckError, match="curation.status is not allowed"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_accepts_autoslice_curation_strategy(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(
        manifest,
        {
            "family": "ui_component_sheet",
            "production_shape": "grid_sheet",
            "curation": {
                "status": "candidate_extracted",
                "strategy": "solid_background_autoslice",
                "report_path": ".godotmaker/asset-generation/curation/ui_kit.json",
                "selected_count": 0,
                "rejected_count": 0,
            },
            "processing_status": "needs_curation",
            "extraction_status": "extracted",
            "final_path": None,
        },
    )

    result = check_manifest(manifest, project_root=tmp_path)

    assert result["asset_count"] == 1


def test_check_manifest_allows_needs_curation_status(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(
        manifest,
        {
            "processing_status": "needs_curation",
            "extraction_status": "extracted",
            "final_path": None,
            "curation": {
                "status": "needs_curation",
                "strategy": "transparent_grid",
                "report_path": ".godotmaker/asset-generation/curation/player_idle.json",
                "selected_count": 3,
                "rejected_count": 1,
            },
        },
    )

    result = check_manifest(manifest, project_root=tmp_path)

    assert result["asset_count"] == 1


def test_check_manifest_rejects_ready_asset_with_unselected_curation(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(
        manifest,
        {
            "curation": {
                "status": "candidate_extracted",
                "strategy": "transparent_grid",
                "report_path": ".godotmaker/asset-generation/curation/player_idle.json",
                "selected_count": 0,
                "rejected_count": 0,
            },
        },
    )

    with pytest.raises(ManifestCheckError, match="must be selected or not_required"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_rejects_foreground_ready_without_curation(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(
        manifest,
        {
            "family": "runtime_sprite",
            "production_shape": "single_image",
            "extraction_status": "not_required",
            "curation": None,
        },
    )

    with pytest.raises(ManifestCheckError, match="single"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_rejects_foreground_ready_with_not_required_curation(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(
        manifest,
        {
            "family": "projectile_fx_source",
            "production_shape": "single_image",
            "extraction_status": "not_required",
            "curation": {
                "status": "not_required",
                "strategy": "none",
                "report_path": None,
                "selected_count": 0,
                "rejected_count": 0,
            },
        },
    )

    with pytest.raises(ManifestCheckError, match="single"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_accepts_foreground_ready_with_selected_curation(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(
        manifest,
        {
            "family": "icon_pack",
            "production_shape": "single_image",
            "runtime_artifact": "single",
            "extraction_status": "processed",
            "curation": {
                "status": "selected",
                "strategy": "solid_background_autoslice",
                "report_path": ".godotmaker/asset-generation/curation/icon_pack.json",
                "selected_count": 1,
                "rejected_count": 0,
            },
        },
    )

    result = check_manifest(manifest, project_root=tmp_path)

    assert result["asset_count"] == 1


def test_check_manifest_accepts_foreground_ready_region_atlas(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_atlas_runtime_metadata(tmp_path)
    write_manifest(
        manifest,
        {
            "asset_id": "ui_main_kit",
            "family": "ui_component_sheet",
            "production_shape": "grid_sheet",
            "runtime_artifact": "region_atlas",
            "source_path": ".godotmaker/asset-generation/sources/ui_main_kit_source.png",
            "final_path": "assets/ui/main_atlas.png",
            "prompt_path": ".godotmaker/asset-generation/prompts/ui_main_kit_source.txt",
            "extraction_status": "processed",
            "curation": {
                "status": "selected",
                "strategy": "solid_background_autoslice",
                "report_path": ".godotmaker/asset-generation/curation/ui_kit.json",
                "selected_count": 8,
                "rejected_count": 0,
            },
            "qc": {
                "atlas_metadata": {
                    "metadata_path": "assets/ui/main_atlas.json",
                    "region_count": 2,
                }
            },
        },
    )

    result = check_manifest(manifest, project_root=tmp_path)

    assert result["asset_count"] == 1


def test_check_manifest_rejects_foreground_ready_region_atlas_without_metadata(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(
        manifest,
        {
            "family": "ui_component_sheet",
            "production_shape": "grid_sheet",
            "runtime_artifact": "region_atlas",
            "extraction_status": "processed",
            "curation": {
                "status": "selected",
                "strategy": "solid_background_autoslice",
                "report_path": ".godotmaker/asset-generation/curation/ui_kit.json",
                "selected_count": 8,
                "rejected_count": 0,
            },
            "qc": {},
        },
    )

    with pytest.raises(ManifestCheckError, match="atlas_metadata"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_rejects_region_atlas_runtime_metadata_identity_mismatch(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_atlas_runtime_metadata(tmp_path, runtime_artifact="grid_sheet")
    write_manifest(
        manifest,
        {
            "asset_id": "ui_main_kit",
            "family": "ui_component_sheet",
            "production_shape": "grid_sheet",
            "runtime_artifact": "region_atlas",
            "extraction_status": "processed",
            "curation": {
                "status": "selected",
                "strategy": "solid_background_autoslice",
                "report_path": ".godotmaker/asset-generation/curation/ui_kit.json",
                "selected_count": 8,
                "rejected_count": 0,
            },
            "final_path": "assets/ui/main_atlas.png",
            "qc": {
                "atlas_metadata": {
                    "metadata_path": "assets/ui/main_atlas.json",
                    "region_count": 2,
                }
            },
        },
    )

    with pytest.raises(ManifestCheckError, match="runtime_artifact must be region_atlas"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_rejects_region_atlas_runtime_metadata_path_mismatch(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_atlas_runtime_metadata(tmp_path, atlas_path="assets/ui/other_atlas.png")
    write_manifest(
        manifest,
        {
            "asset_id": "ui_main_kit",
            "family": "ui_component_sheet",
            "production_shape": "grid_sheet",
            "runtime_artifact": "region_atlas",
            "extraction_status": "processed",
            "curation": {
                "status": "selected",
                "strategy": "solid_background_autoslice",
                "report_path": ".godotmaker/asset-generation/curation/ui_kit.json",
                "selected_count": 8,
                "rejected_count": 0,
            },
            "final_path": "assets/ui/main_atlas.png",
            "qc": {
                "atlas_metadata": {
                    "metadata_path": "assets/ui/main_atlas.json",
                    "region_count": 2,
                }
            },
        },
    )

    with pytest.raises(ManifestCheckError, match="atlas_path must match final_path"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_rejects_region_atlas_runtime_metadata_missing_atlas_path(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_atlas_runtime_metadata(tmp_path, atlas_path=None)
    write_manifest(
        manifest,
        {
            "asset_id": "ui_main_kit",
            "family": "ui_component_sheet",
            "production_shape": "grid_sheet",
            "runtime_artifact": "region_atlas",
            "extraction_status": "processed",
            "curation": {
                "status": "selected",
                "strategy": "solid_background_autoslice",
                "report_path": ".godotmaker/asset-generation/curation/ui_kit.json",
                "selected_count": 8,
                "rejected_count": 0,
            },
            "final_path": "assets/ui/main_atlas.png",
            "qc": {
                "atlas_metadata": {
                    "metadata_path": "assets/ui/main_atlas.json",
                    "region_count": 2,
                }
            },
        },
    )

    with pytest.raises(ManifestCheckError, match="atlas_path must be a non-empty string"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_rejects_foreground_ready_with_unprocessed_extraction(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(
        manifest,
        {
            "family": "ui_component_sheet",
            "production_shape": "curation_required",
            "runtime_artifact": "single",
            "extraction_status": "source_sheet",
            "curation": {
                "status": "selected",
                "strategy": "solid_background_autoslice",
                "report_path": ".godotmaker/asset-generation/curation/ui_kit.json",
                "selected_count": 1,
                "rejected_count": 0,
            },
        },
    )

    with pytest.raises(ManifestCheckError, match="extraction_status"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_rejects_foreground_ready_reference_artifact(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(
        manifest,
        {
            "family": "runtime_sprite",
            "production_shape": "single_image",
            "runtime_artifact": "reference",
            "extraction_status": "not_required",
            "curation": {
                "status": "not_required",
                "strategy": "none",
                "report_path": None,
            },
        },
    )

    with pytest.raises(ManifestCheckError, match="runtime_artifact"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_rejects_selected_curation_without_selected_count(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(
        manifest,
        {
            "curation": {
                "status": "selected",
                "strategy": "transparent_grid",
                "report_path": ".godotmaker/asset-generation/curation/player_idle.json",
                "selected_count": 0,
                "rejected_count": 0,
            },
        },
    )

    with pytest.raises(ManifestCheckError, match="selected_count must be positive"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_requires_curation_for_source_sheets(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(manifest, {"curation": None})

    with pytest.raises(ManifestCheckError, match="missing curation"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_allows_deferred_source_sheet_without_curation(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(
        manifest,
        {
            "source_path": None,
            "final_path": None,
            "prompt_path": None,
            "processing_status": "deferred",
            "extraction_status": "not_required",
            "curation": None,
        },
    )

    result = check_manifest(manifest, project_root=tmp_path)

    assert result["asset_count"] == 1


def test_check_manifest_rejects_duplicate_asset_id_within_same_tag(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(manifest)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["assets"].append(dict(data["assets"][0]))
    manifest.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ManifestCheckError, match="Duplicate asset_id for tag"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_allows_shared_source_sheet_and_prompt(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(manifest)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    duplicate = dict(data["assets"][0])
    duplicate["asset_id"] = "player_run"
    duplicate["final_path"] = "assets/sprites/player_run.png"
    data["assets"].append(duplicate)
    manifest.write_text(json.dumps(data), encoding="utf-8")

    result = check_manifest(manifest, project_root=tmp_path)

    assert result["asset_count"] == 2


def test_check_manifest_rejects_duplicate_final_paths(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(manifest)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    duplicate = dict(data["assets"][0])
    duplicate["asset_id"] = "enemy_idle"
    data["assets"].append(duplicate)
    manifest.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ManifestCheckError, match="Duplicate final_path path"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_rejects_missing_ready_final_path(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(manifest, {"final_path": None})

    with pytest.raises(ManifestCheckError, match="missing final_path"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_allows_needs_curation_without_final_path(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(
        manifest,
        {
            "final_path": None,
            "processing_status": "needs_curation",
            "extraction_status": "pending",
        },
    )

    result = check_manifest(manifest, project_root=tmp_path)

    assert result["asset_count"] == 1


def test_check_manifest_checks_files_when_requested(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(manifest)
    touch(tmp_path / ".godotmaker" / "asset-generation" / "sources" / "player_idle_source.png")
    touch(tmp_path / ".godotmaker" / "asset-generation" / "prompts" / "player_idle.txt")
    touch(tmp_path / ".godotmaker" / "asset-generation" / "curation" / "player_idle.json")
    touch(tmp_path / "assets" / "sprites" / "player_idle.png")

    result = check_manifest(manifest, project_root=tmp_path, check_files=True)

    assert result["file_checks"] == 4


def test_check_manifest_reports_missing_file(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(manifest)

    with pytest.raises(ManifestCheckError, match="Source path not found"):
        check_manifest(manifest, project_root=tmp_path, check_files=True)


def test_cli_outputs_json(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(manifest)

    result = subprocess.run(
        [
            sys.executable,
            str(TOOLS_DIR / "asset_generation_manifest_check.py"),
            str(manifest),
            "--project-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["asset_count"] == 1
