"""L4 structural contract for a declared TileSet atlas recipe."""
from __future__ import annotations

from typing import Any

from .contract import ValidationError
from .structure import StructureRequest, StructureValidatorRegistry

VALIDATOR_ID = "tileset_atlas_structure_v1"
CHECKS = ("tileset",)

_SHAPES = {"square": 0, "isometric": 1, "half_offset_square": 2, "hexagon": 3}
_ANIMATION_MODES = {"default": 0, "random_start_times": 1, "max": 2}


def validate_tileset(request: StructureRequest) -> dict[str, Any]:
    facts = request.checked_structure("tileset")
    sources = request.spec.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValidationError("TileSet L4 requires the declared non-empty sources recipe")
    expected_tiles = sum(len(source.get("tiles", [])) for source in sources if isinstance(source, dict))
    expected_alternatives = sum(
        len(tile.get("alternatives", []))
        for source in sources if isinstance(source, dict)
        for tile in source.get("tiles", []) if isinstance(tile, dict)
    )
    expected_size = request.spec.get("tile_size")
    if facts.get("source_count") != len(sources):
        raise ValidationError("loaded TileSet source count does not match the recipe")
    if facts.get("tile_count") != expected_tiles:
        raise ValidationError("loaded TileSet tile count does not match the recipe")
    if facts.get("alternative_count") != expected_alternatives:
        raise ValidationError("loaded TileSet alternative count does not match the recipe")
    if facts.get("tile_size") != expected_size:
        raise ValidationError("loaded TileSet tile_size does not match the recipe")
    shape = request.spec.get("tile_shape", "square")
    if facts.get("tile_shape") != _SHAPES.get(shape):
        raise ValidationError("loaded TileSet tile_shape does not match the recipe")
    actual_sources = facts.get("sources")
    if not isinstance(actual_sources, list) or len(actual_sources) != len(sources):
        raise ValidationError("loaded TileSet source descriptors are incomplete")
    for index, (expected, actual) in enumerate(zip(sources, actual_sources)):
        if not isinstance(expected, dict) or not isinstance(actual, dict):
            raise ValidationError("TileSet source descriptor is malformed")
        for key, default in (("id", index), ("region_size", expected_size), ("margins", [0, 0]), ("separation", [0, 0])):
            if actual.get(key) != expected.get(key, default):
                raise ValidationError(f"loaded TileSet source {index} {key} does not match the recipe")
        actual_tiles = actual.get("tiles")
        if not isinstance(actual_tiles, list) or len(actual_tiles) != len(expected.get("tiles", [])):
            raise ValidationError(f"loaded TileSet source {index} tile descriptors are incomplete")
        for tile, loaded in zip(expected.get("tiles", []), actual_tiles):
            for key, default in (("coords", None), ("texture_origin", [0, 0]), ("z_index", 0), ("y_sort_origin", 0), ("probability", 1.0), ("terrain_set", -1), ("terrain", -1)):
                if loaded.get(key) != tile.get(key, default):
                    raise ValidationError(f"loaded TileSet tile {key} does not match the recipe")
            if "animation" in tile:
                for key in ("mode", "columns", "frames_count", "separation", "speed"):
                    expected_value = tile["animation"].get(key)
                    if key == "mode":
                        expected_value = _ANIMATION_MODES.get(expected_value, expected_value)
                    if loaded.get("animation", {}).get(key) != expected_value:
                        raise ValidationError(f"loaded TileSet animation {key} does not match the recipe")
                if "frame_durations" in tile["animation"]:
                    expected_durations = [item.get("duration") for item in tile["animation"]["frame_durations"]]
                    if loaded.get("animation", {}).get("frame_durations") != expected_durations:
                        raise ValidationError("loaded TileSet animation frame durations do not match the recipe")
    for key in ("physics_layers", "navigation_layers", "occlusion_layers", "custom_data_layers", "terrain_sets"):
        expected = len(request.spec.get(key, []))
        if facts.get(key + "_count") != expected:
            raise ValidationError(f"loaded TileSet {key} count does not match the recipe")
    return dict(facts)


def register_into(registry: StructureValidatorRegistry):
    return registry.register(
        artifact_type="TileSet", validator_id=VALIDATOR_ID,
        validator=validate_tileset, checks=CHECKS,
    )
