"""Regression coverage for deterministic TileSet terrain profiles."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from asset_tileset_profile import (  # noqa: E402
    TileSetProfileError,
    _resolve_runtime_root,
    build_profile_atlas_declaration,
    build_profile_recipe,
    compose_profile_material_atlas,
    create_profile_guide,
    diagnose_profile_edge_semantics,
    get_profile,
    profile_manifest,
    write_transparent_profile_slot,
    validate_profile_atlas,
)


def _atlas(path: Path, profile_name: str, cell_size: int = 8) -> None:
    profile = get_profile(profile_name)
    image = Image.new("RGBA", (profile.columns * cell_size, profile.rows * cell_size), (0, 0, 0, 0))
    for index, tile in enumerate(profile.tiles, start=1):
        image.putpixel((tile.coords[0] * cell_size, tile.coords[1] * cell_size), (index % 255, 80, 160, 255))
    image.save(path)


def _semantic_atlas(path: Path, profile_name: str, cell_size: int = 24) -> None:
    profile = get_profile(profile_name)
    grass, dirt = (45, 165, 70, 255), (180, 105, 45, 255)
    image = Image.new("RGBA", (profile.columns * cell_size, profile.rows * cell_size), (0, 0, 0, 0))
    patch = cell_size // 6
    for tile in profile.tiles:
        left, top = tile.coords[0] * cell_size, tile.coords[1] * cell_size
        image.paste(grass, (left, top, left + cell_size, top + cell_size))
        if set((3, 7, 11, 15)).issubset(tile.peering_bits):
            image.paste(dirt, (left, top, left + cell_size, top + cell_size))
            continue
        for bit, x_offset, y_offset in ((11, 0, 0), (15, cell_size - patch, 0), (7, 0, cell_size - patch), (3, cell_size - patch, cell_size - patch)):
            if bit in tile.peering_bits:
                image.paste(dirt, (left + x_offset, top + y_offset, left + x_offset + patch, top + y_offset + patch))
    image.save(path)


@pytest.mark.parametrize(("profile_name", "expected_count", "expected_grid"), [
    ("marching_squares_15", 15, (4, 4)),
    ("blob_47", 47, (8, 6)),
])
def test_profile_atlas_validation_accepts_every_required_slot(tmp_path, profile_name, expected_count, expected_grid):
    atlas = tmp_path / f"{profile_name}.png"
    _atlas(atlas, profile_name)
    report = validate_profile_atlas(atlas, profile_name, tile_width=8, tile_height=8)
    assert report["required_slot_count"] == expected_count
    assert report["grid"] == {"columns": expected_grid[0], "rows": expected_grid[1]}


def test_profile_atlas_validation_rejects_missing_and_reserved_slots(tmp_path):
    atlas = tmp_path / "blob.png"
    _atlas(atlas, "blob_47")
    with Image.open(atlas) as opened:
        image = opened.convert("RGBA")
    image.putpixel((0, 0), (0, 0, 0, 0))
    image.save(atlas)
    with pytest.raises(TileSetProfileError, match="empty required slots"):
        validate_profile_atlas(atlas, "blob_47", tile_width=8, tile_height=8)

    _atlas(atlas, "blob_47")
    with Image.open(atlas) as opened:
        image = opened.convert("RGBA")
    image.putpixel((7 * 8, 5 * 8), (255, 255, 255, 255))
    image.save(atlas)
    with pytest.raises(TileSetProfileError, match="reserved slots"):
        validate_profile_atlas(atlas, "blob_47", tile_width=8, tile_height=8)


def test_profile_recipe_generates_complete_fixed_terrain_metadata():
    recipe = build_profile_recipe(
        "blob_47",
        texture_path="res://assets/generated/tileset/coast/coast_atlas.png",
        tile_width=32,
        tile_height=32,
        godot_path="C:/Godot/godot.exe",
        terrain_name="coast",
        terrain_color=[0.2, 0.7, 0.4],
    )
    assert recipe["terrain_sets"] == [{"mode": 0, "terrains": [{"name": "coast", "color": [0.2, 0.7, 0.4]}]}]
    tiles = recipe["sources"][0]["tiles"]
    assert len(tiles) == 47
    assert {tuple(tile["coords"]) for tile in tiles} == {tile.coords for tile in get_profile("blob_47").tiles}
    assert all(tile["terrain_set"] == 0 and tile["terrain"] == 0 for tile in tiles)
    assert all(all(item["terrain"] == 0 for item in tile["peering_bits"]) for tile in tiles)


def test_profile_recipe_maps_role_based_physics_navigation_and_custom_data():
    recipe = build_profile_recipe(
        "blob_47",
        texture_path="res://assets/generated/tileset/shrine/shrine_atlas.png",
        tile_width=32,
        tile_height=32,
        godot_path="godot",
        terrain_name="shrine_water",
        semantic_metadata={
            "custom_data_layers": [{"name": "surface_kind", "type": "String"}],
            "physics_layers": [{"name": "water_blocker", "collision_layer": 1, "collision_mask": 0}],
            "navigation_layers": [{"name": "walkable_ground"}],
            "roles": {
                "foreground_full": {"custom_data": {"surface_kind": "water"}, "physics": "full_cell", "navigation": "none"},
                "background_full": {"custom_data": {"surface_kind": "ground"}, "physics": "none", "navigation": "full_cell"},
            },
        },
    )
    assert recipe["physics_layers"] == [{"collision_layer": 1, "collision_mask": 0}]
    assert recipe["navigation_layers"] == [{"layers": 1}]
    foreground = next(tile for tile in recipe["sources"][0]["tiles"] if {3, 7, 11, 15}.issubset({item["bit"] for item in tile["peering_bits"]}))
    background = next(tile for tile in recipe["sources"][0]["tiles"] if not tile["peering_bits"])
    assert foreground["custom_data"] == [{"layer": 0, "value": "water"}]
    assert foreground["collision_polygons"][0]["points"] == [[0, 0], [32, 0], [32, 32], [0, 32]]
    assert background["custom_data"] == [{"layer": 0, "value": "ground"}]
    assert background["navigation_polygons"][0]["points"] == [[0, 0], [32, 0], [32, 32], [0, 32]]


def test_blob_profile_corner_bits_always_have_their_adjacent_sides():
    dependencies = {3: {0, 4}, 7: {4, 8}, 11: {8, 12}, 15: {12, 0}}
    manifest = profile_manifest("blob_47")
    slots = [slot for slot in manifest["slots"] if not slot["reserved"]]
    assert len(slots) == 47
    for slot in slots:
        bits = set(slot["peering_bits"])
        for corner, sides in dependencies.items():
            if corner in bits:
                assert sides.issubset(bits), slot


def test_profile_manifest_and_guide_expose_every_fixed_slot(tmp_path):
    manifest = profile_manifest("marching_squares_15")
    assert manifest["slots"][0] == {"coords": [0, 0], "reserved": True, "label": "reserved_transparent"}
    guide = tmp_path / "marching-guide.png"
    returned = create_profile_guide("marching_squares_15", guide, cell_width=32, cell_height=32)
    assert returned == manifest
    with Image.open(guide) as image:
        assert image.size == (128, 128)


def test_profile_manifest_exposes_fixed_edge_signatures():
    manifest = profile_manifest("marching_squares_15")
    first_terrain = manifest["slots"][1]
    assert first_terrain["coords"] == [1, 0]
    assert first_terrain["edge_signature"] == {
        "top": [0, 0], "right": [0, 1], "bottom": [1, 0], "left": [0, 0],
    }


def test_profile_seam_diagnostics_report_incorrect_corner_material(tmp_path):
    atlas = tmp_path / "semantic.png"
    _semantic_atlas(atlas, "marching_squares_15")
    with Image.open(atlas) as opened:
        image = opened.convert("RGBA")
    profile = get_profile("marching_squares_15")
    passed = diagnose_profile_edge_semantics(image, profile, tile_width=24, tile_height=24)
    assert passed["mismatch_count"] == 0

    image.paste((45, 165, 70, 255), (24 + 20, 20, 24 + 24, 24))
    image.save(atlas)
    report = validate_profile_atlas(atlas, "marching_squares_15", tile_width=24, tile_height=24, check_seams=True)
    assert report["seam_diagnostics"]["mismatch_count"] == 1
    assert report["seam_diagnostics"]["mismatches"][0]["coords"] == [1, 0]
    assert report["seam_diagnostics"]["mismatches"][0]["corner"] == "bottom_right"


def test_material_composition_repairs_topology_without_flat_color_corner_patches(tmp_path):
    material_source = tmp_path / "materials.png"
    image = Image.new("RGBA", (96, 96), (45, 165, 70, 255))
    image.paste((185, 105, 45, 255), (48, 0, 96, 96))
    material_source.parent.mkdir(parents=True, exist_ok=True)
    image.save(material_source)
    atlas = tmp_path / "composed.png"
    report = compose_profile_material_atlas(
        "marching_squares_15",
        material_source=material_source,
        output=atlas,
        tile_width=24,
        tile_height=24,
    )
    assert report["operation"] == "deterministic_profile_material_composite_v1"
    validated = validate_profile_atlas(atlas, "marching_squares_15", tile_width=24, tile_height=24, check_seams=True)
    assert validated["seam_diagnostics"]["mismatch_count"] == 0
    with Image.open(atlas) as composed:
        assert composed.convert("RGBA").crop((0, 0, 24, 24)).getchannel("A").getbbox() is None


def test_material_composition_selects_named_water_and_vegetation_materials(tmp_path):
    material_source = tmp_path / "riverside-materials.png"
    image = Image.new("RGBA", (96, 96), (48, 156, 68, 255))
    image.paste((42, 118, 205, 255), (48, 0, 96, 96))
    image.save(material_source)
    atlas = tmp_path / "riverside-blob.png"
    report = compose_profile_material_atlas(
        "blob_47",
        material_source=material_source,
        output=atlas,
        tile_width=24,
        tile_height=24,
        foreground_material="shallow_water",
        background_material="riverbank_vegetation",
    )
    assert report["materials"]["foreground"]["name"] == "shallow_water"
    assert report["materials"]["background"]["name"] == "riverbank_vegetation"
    with Image.open(atlas) as composed:
        background = composed.convert("RGBA").crop((0, 0, 24, 24))
        red, green, blue, _alpha = background.getpixel((12, 12))
        assert green > blue > red
        full_foreground = composed.convert("RGBA").crop((6 * 24, 5 * 24, 7 * 24, 6 * 24))
        red, green, blue, _alpha = full_foreground.getpixel((12, 12))
        assert blue > green > red


def test_profile_declaration_uses_fixed_row_major_cell_sources(tmp_path):
    cells = tmp_path / "cells"
    reserved = tmp_path / "reserved.png"
    write_transparent_profile_slot(reserved, tile_width=32, tile_height=16)
    declaration = build_profile_atlas_declaration(
        "marching_squares_15",
        cells_dir=cells,
        reserved_source=reserved,
        tile_width=32,
        tile_height=16,
    )
    assert declaration["atlas"] == {"width": 128, "height": 64}
    assert declaration["slots"][0] == {
        "name": "cell_0_0", "rect": [0, 0, 32, 16], "source": reserved.as_posix(),
    }
    assert declaration["slots"][1] == {
        "name": "cell_1_0", "rect": [32, 0, 32, 16], "source": (cells / "02.png").as_posix(),
    }
    with Image.open(reserved) as image:
        assert image.size == (32, 16)
        assert image.getchannel("A").getbbox() is None


def test_profile_runtime_resolution_prefers_published_runtime(tmp_path):
    runtime = tmp_path / ".godotmaker" / "asset-runtime"
    runtime.mkdir(parents=True)
    assert _resolve_runtime_root(tmp_path) == runtime


def test_profile_recipe_rejects_unknown_overrides():
    with pytest.raises(TileSetProfileError, match="outside marching_squares_15"):
        build_profile_recipe(
            "marching_squares_15",
            texture_path="res://assets/generated/tileset/road/road_atlas.png",
            tile_width=16,
            tile_height=16,
            godot_path="godot",
            terrain_name="road",
            overrides={(0, 0): {"z_index": 1}},
        )
