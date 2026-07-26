"""L4 structural contract for a declared TileSet atlas recipe."""
from __future__ import annotations

from typing import Any

from .contract import ValidationError
from .structure import StructureRequest, StructureValidatorRegistry

VALIDATOR_ID = "tileset_atlas_structure_v1"
CHECKS = ("tileset",)

_SHAPES = {"square": 0, "isometric": 1, "half_offset_square": 2, "hexagon": 3}
_ANIMATION_MODES = {"default": 0, "random_start_times": 1, "max": 2}


def _expected_tile(tile: dict[str, Any], spec: dict[str, Any], *, alternative: bool = False) -> dict[str, Any]:
    physics = [[] for _ in spec.get("physics_layers", [])]
    for item in tile.get("collision_polygons", []):
        physics[item["layer"]].append(item["points"])
    occlusion = [[] for _ in spec.get("occlusion_layers", [])]
    for item in tile.get("occlusion_polygons", []):
        occlusion[item["layer"]].append(item["points"])
    navigation = [[] for _ in spec.get("navigation_layers", [])]
    for item in tile.get("navigation_polygons", []):
        navigation[item["layer"]] = item["points"]
    peering = [-1] * 16
    for item in tile.get("peering_bits", []):
        peering[item["bit"]] = item["terrain"]
    custom = [None] * len(spec.get("custom_data_layers", []))
    for item in tile.get("custom_data", []):
        custom[item["layer"]] = item.get("value")
    return {"id": tile.get("id", 0 if not alternative else None), "texture_origin": tile.get("texture_origin", [0, 0]), "z_index": tile.get("z_index", 0), "y_sort_origin": tile.get("y_sort_origin", 0), "probability": tile.get("probability", 1.0), "terrain_set": tile.get("terrain_set", -1), "terrain": tile.get("terrain", -1), "peering_bits": peering, "custom_data": custom, "collision_polygons": physics, "occlusion_polygons": occlusion, "navigation_polygons": navigation}


def _expected_layers(spec: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    terrain_sets = []
    for terrain_set in spec.get("terrain_sets", []):
        terrains = []
        for terrain in terrain_set.get("terrains", []):
            color = terrain.get("color", [1.0, 1.0, 1.0, 1.0])
            if len(color) == 3:
                color = [*color, 1.0]
            terrains.append({"name": terrain.get("name", ""), "color": color})
        terrain_sets.append({"mode": terrain_set.get("mode", 0), "terrains": terrains})
    return {
        "physics_layers": [{"collision_layer": item.get("collision_layer", 1), "collision_mask": item.get("collision_mask", 1)} for item in spec.get("physics_layers", [])],
        "navigation_layers": [{"layers": item.get("layers", 1)} for item in spec.get("navigation_layers", [])],
        "occlusion_layers": [{"light_mask": item.get("light_mask", 1)} for item in spec.get("occlusion_layers", [])],
        "custom_data_layers": [{"name": item.get("name", ""), "type": item.get("type", 0)} for item in spec.get("custom_data_layers", [])],
        "terrain_sets": terrain_sets,
    }


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
            expected_tile = _expected_tile(tile, request.spec)
            for key, value in expected_tile.items():
                if key != "id" and loaded.get(key) != value:
                    raise ValidationError(f"loaded TileSet tile {key} does not match the recipe")
            loaded_alternatives = loaded.get("alternatives", [])
            expected_alternatives = tile.get("alternatives", [])
            if len(loaded_alternatives) != len(expected_alternatives):
                raise ValidationError("loaded TileSet alternatives do not match the recipe")
            for alternative, actual_alternative in zip(expected_alternatives, loaded_alternatives):
                if actual_alternative != _expected_tile(alternative, request.spec, alternative=True):
                    raise ValidationError("loaded TileSet alternative data does not match the recipe")
    normalized_layers = _expected_layers(request.spec)
    for key in ("physics_layers", "navigation_layers", "occlusion_layers", "custom_data_layers", "terrain_sets"):
        expected = len(request.spec.get(key, []))
        if facts.get(key + "_count") != expected:
            raise ValidationError(f"loaded TileSet {key} count does not match the recipe")
        if facts.get(key) != normalized_layers[key]:
            raise ValidationError(f"loaded TileSet {key} data does not match the recipe")
    return dict(facts)


def register_into(registry: StructureValidatorRegistry):
    return registry.register(
        artifact_type="TileSet", validator_id=VALIDATOR_ID,
        validator=validate_tileset, checks=CHECKS,
    )
