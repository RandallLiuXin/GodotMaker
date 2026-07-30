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
    build_profile_recipe,
    create_profile_guide,
    get_profile,
    profile_manifest,
    validate_profile_atlas,
)


def _atlas(path: Path, profile_name: str, cell_size: int = 8) -> None:
    profile = get_profile(profile_name)
    image = Image.new("RGBA", (profile.columns * cell_size, profile.rows * cell_size), (0, 0, 0, 0))
    for index, tile in enumerate(profile.tiles, start=1):
        image.putpixel((tile.coords[0] * cell_size, tile.coords[1] * cell_size), (index % 255, 80, 160, 255))
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
