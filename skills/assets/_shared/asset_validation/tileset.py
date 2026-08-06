"""L4 structural contract for a declared TileSet atlas recipe."""
from __future__ import annotations

import math
from typing import Any

from .errors import ValidationError
from .structure import StructureRequest, StructureValidatorRegistry

VALIDATOR_ID = "tileset_atlas_structure_v1"
CHECKS = ("tileset",)

_SHAPES = {"square": 0, "isometric": 1, "half_offset_square": 2, "hexagon": 3}
_ANIMATION_MODES = {"default": 0, "random_start_times": 1, "max": 2}
_FLOAT32_ROUND_TRIP_TOLERANCE = 1e-6
_CUSTOM_DATA_DEFAULTS = {0: None, 1: False, 2: 0, 3: 0.0, 4: ""}


def _same_float32_round_trip(actual: Any, expected: Any) -> bool:
    """Compare a finite decimal after Godot's float32 resource round trip."""
    if type(actual) not in (int, float) or type(expected) not in (int, float):
        return False
    return (
        math.isfinite(float(actual))
        and math.isfinite(float(expected))
        and math.isclose(
            float(actual), float(expected),
            rel_tol=_FLOAT32_ROUND_TRIP_TOLERANCE,
            abs_tol=_FLOAT32_ROUND_TRIP_TOLERANCE,
        )
    )


def _same_terrain_sets(actual: Any, expected: Any) -> bool:
    if not isinstance(actual, list) or not isinstance(expected, list) or len(actual) != len(expected):
        return False
    for actual_set, expected_set in zip(actual, expected):
        if not isinstance(actual_set, dict) or not isinstance(expected_set, dict):
            return False
        if actual_set.get("mode") != expected_set.get("mode"):
            return False
        actual_terrains = actual_set.get("terrains")
        expected_terrains = expected_set.get("terrains")
        if not isinstance(actual_terrains, list) or not isinstance(expected_terrains, list) or len(actual_terrains) != len(expected_terrains):
            return False
        for actual_terrain, expected_terrain in zip(actual_terrains, expected_terrains):
            if not isinstance(actual_terrain, dict) or not isinstance(expected_terrain, dict):
                return False
            if actual_terrain.get("name") != expected_terrain.get("name"):
                return False
            if "color" in expected_terrain:
                actual_color = actual_terrain.get("color")
                expected_color = expected_terrain["color"]
                if not isinstance(actual_color, list) or not isinstance(expected_color, list) or len(actual_color) != len(expected_color):
                    return False
                if not all(_same_float32_round_trip(value, expected_value) for value, expected_value in zip(actual_color, expected_color)):
                    return False
    return True


def _same_polygon_layers(actual: Any, expected: Any) -> bool:
    if not isinstance(actual, list) or not isinstance(expected, list) or len(actual) != len(expected):
        return False
    for actual_layer, expected_layer in zip(actual, expected):
        if not isinstance(actual_layer, list) or not isinstance(expected_layer, list) or len(actual_layer) != len(expected_layer):
            return False
        for actual_polygon, expected_polygon in zip(actual_layer, expected_layer):
            if not isinstance(actual_polygon, list) or not isinstance(expected_polygon, list) or len(actual_polygon) != len(expected_polygon):
                return False
            for actual_point, expected_point in zip(actual_polygon, expected_polygon):
                if not isinstance(actual_point, list) or not isinstance(expected_point, list) or len(actual_point) != 2 or len(expected_point) != 2:
                    return False
                if not all(_same_float32_round_trip(value, wanted) for value, wanted in zip(actual_point, expected_point)):
                    return False
    return True


def _same_navigation_polygons(actual: Any, expected: Any) -> bool:
    if not isinstance(actual, list) or not isinstance(expected, list) or len(actual) != len(expected):
        return False
    for actual_polygon, expected_polygon in zip(actual, expected):
        if not isinstance(actual_polygon, list) or not isinstance(expected_polygon, list) or len(actual_polygon) != len(expected_polygon):
            return False
        for actual_point, expected_point in zip(actual_polygon, expected_polygon):
            if not isinstance(actual_point, list) or not isinstance(expected_point, list) or len(actual_point) != 2 or len(expected_point) != 2:
                return False
            if not all(_same_float32_round_trip(value, wanted) for value, wanted in zip(actual_point, expected_point)):
                return False
    return True


def _same_custom_data(actual: Any, expected: Any, layers: list[dict[str, Any]]) -> bool:
    if not isinstance(actual, list) or not isinstance(expected, list) or len(actual) != len(expected) or len(actual) != len(layers):
        return False
    expected_types = {0: type(None), 1: bool, 2: int, 4: str}
    for actual_value, expected_value, layer in zip(actual, expected, layers):
        value_type = layer.get("type", 0)
        if value_type == 3:
            if not _same_float32_round_trip(actual_value, expected_value):
                return False
        elif value_type not in expected_types or type(actual_value) is not expected_types[value_type] or type(expected_value) is not expected_types[value_type]:
            return False
        elif actual_value != expected_value:
            return False
    return True


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
    custom = [
        _CUSTOM_DATA_DEFAULTS.get(layer.get("type", 0))
        for layer in spec.get("custom_data_layers", [])
    ]
    for item in tile.get("custom_data", []):
        custom[item["layer"]] = item.get("value")
    return {"id": tile.get("id", 0 if not alternative else None), "texture_origin": tile.get("texture_origin", [0, 0]), "z_index": tile.get("z_index", 0), "y_sort_origin": tile.get("y_sort_origin", 0), "probability": tile.get("probability", 1.0), "terrain_set": tile.get("terrain_set", -1), "terrain": tile.get("terrain", -1), "peering_bits": peering, "custom_data": custom, "collision_polygons": physics, "occlusion_polygons": occlusion, "navigation_polygons": navigation}


def _expected_layers(spec: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    terrain_sets = []
    for terrain_set in spec.get("terrain_sets", []):
        terrains = []
        for terrain in terrain_set.get("terrains", []):
            expected_terrain = {"name": terrain.get("name", "")}
            if "color" in terrain:
                color = terrain["color"]
                if len(color) == 3:
                    color = [*color, 1.0]
                expected_terrain["color"] = color
            terrains.append(expected_terrain)
        terrain_sets.append({"mode": terrain_set.get("mode", 0), "terrains": terrains})
    return {
        "physics_layers": [{"collision_layer": item.get("collision_layer", 1), "collision_mask": item.get("collision_mask", 1)} for item in spec.get("physics_layers", [])],
        "navigation_layers": [{"layers": item.get("layers", 1)} for item in spec.get("navigation_layers", [])],
        "occlusion_layers": [{"light_mask": item.get("light_mask", 1)} for item in spec.get("occlusion_layers", [])],
        "custom_data_layers": [{"name": item.get("name", ""), "type": item.get("type", 0)} for item in spec.get("custom_data_layers", [])],
        "terrain_sets": terrain_sets,
    }


def _source_id(source: dict[str, Any], index: int) -> int:
    return source.get("id", index)


def _source_region_size(source: dict[str, Any], tile_size: Any) -> Any:
    return source.get("region_size", source.get("tile_size", tile_size))


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
    expected_sources = {
        _source_id(source, index): source
        for index, source in enumerate(sources)
        if isinstance(source, dict)
    }
    actual_sources_by_id = {
        source.get("id"): source
        for source in actual_sources
        if isinstance(source, dict)
    }
    if set(actual_sources_by_id) != set(expected_sources):
        raise ValidationError("loaded TileSet source ids do not match the recipe")
    for source_id, expected in expected_sources.items():
        actual = actual_sources_by_id[source_id]
        if not isinstance(actual, dict):
            raise ValidationError("TileSet source descriptor is malformed")
        for key, default in (("id", source_id), ("region_size", _source_region_size(expected, expected_size)), ("margins", [0, 0]), ("separation", [0, 0])):
            if actual.get(key) != expected.get(key, default):
                raise ValidationError(f"loaded TileSet source {source_id} {key} does not match the recipe")
        actual_tiles = actual.get("tiles")
        if not isinstance(actual_tiles, list) or len(actual_tiles) != len(expected.get("tiles", [])):
            raise ValidationError(f"loaded TileSet source {source_id} tile descriptors are incomplete")
        expected_tiles = {
            tuple(tile.get("coords", [])): tile
            for tile in expected.get("tiles", [])
            if isinstance(tile, dict)
        }
        actual_tiles_by_coords = {
            tuple(tile.get("coords", [])): tile
            for tile in actual_tiles
            if isinstance(tile, dict)
        }
        if set(actual_tiles_by_coords) != set(expected_tiles):
            raise ValidationError(f"loaded TileSet source {source_id} tile coordinates do not match the recipe")
        for coords, tile in expected_tiles.items():
            loaded = actual_tiles_by_coords[coords]
            for key, default in (("coords", None), ("texture_origin", [0, 0]), ("z_index", 0), ("y_sort_origin", 0), ("probability", 1.0), ("terrain_set", -1), ("terrain", -1)):
                actual_value = loaded.get(key)
                expected_value = tile.get(key, default)
                matches = (
                    _same_float32_round_trip(actual_value, expected_value)
                    if key == "probability"
                    else actual_value == expected_value
                )
                if not matches:
                    raise ValidationError(f"loaded TileSet tile {key} does not match the recipe")
            if "animation" in tile:
                for key, default in (
                    ("mode", "default"),
                    ("columns", 1),
                    ("frames_count", None),
                    ("separation", [0, 0]),
                    ("speed", 1.0),
                ):
                    expected_value = tile["animation"].get(key, default)
                    if key == "mode":
                        expected_value = _ANIMATION_MODES.get(expected_value, expected_value)
                    actual_value = loaded.get("animation", {}).get(key)
                    matches = (
                        _same_float32_round_trip(actual_value, expected_value)
                        if key == "speed"
                        else actual_value == expected_value
                    )
                    if not matches:
                        raise ValidationError(f"loaded TileSet animation {key} does not match the recipe")
                if "frame_durations" in tile["animation"]:
                    expected_durations = [item.get("duration") for item in tile["animation"]["frame_durations"]]
                    actual_durations = loaded.get("animation", {}).get("frame_durations")
                    if not isinstance(actual_durations, list) or len(actual_durations) != len(expected_durations) or not all(
                        _same_float32_round_trip(actual, expected)
                        for actual, expected in zip(actual_durations, expected_durations)
                    ):
                        raise ValidationError("loaded TileSet animation frame durations do not match the recipe")
            expected_tile = _expected_tile(tile, request.spec)
            for key, value in expected_tile.items():
                matches = (
                    _same_float32_round_trip(loaded.get(key), value)
                    if key == "probability"
                    else _same_polygon_layers(loaded.get(key), value)
                    if key in {"collision_polygons", "occlusion_polygons"}
                    else _same_navigation_polygons(loaded.get(key), value)
                    if key == "navigation_polygons"
                    else _same_custom_data(loaded.get(key), value, request.spec.get("custom_data_layers", []))
                    if key == "custom_data"
                    else loaded.get(key) == value
                )
                if key != "id" and not matches:
                    raise ValidationError(f"loaded TileSet tile {key} does not match the recipe")
            loaded_alternatives = loaded.get("alternatives", [])
            expected_alternatives = tile.get("alternatives", [])
            if len(loaded_alternatives) != len(expected_alternatives):
                raise ValidationError("loaded TileSet alternatives do not match the recipe")
            expected_alternatives_by_id = {
                alternative.get("id"): alternative
                for alternative in expected_alternatives
                if isinstance(alternative, dict)
            }
            actual_alternatives_by_id = {
                alternative.get("id"): alternative
                for alternative in loaded_alternatives
                if isinstance(alternative, dict)
            }
            if set(actual_alternatives_by_id) != set(expected_alternatives_by_id):
                raise ValidationError("loaded TileSet alternative ids do not match the recipe")
            for alternative_id, alternative in expected_alternatives_by_id.items():
                actual_alternative = actual_alternatives_by_id[alternative_id]
                expected_alternative = _expected_tile(
                    alternative, request.spec, alternative=True
                )
                alternative_matches = all(
                    _same_float32_round_trip(actual_alternative.get(key), expected_value)
                    if key == "probability"
                    else _same_polygon_layers(actual_alternative.get(key), expected_value)
                    if key in {"collision_polygons", "occlusion_polygons"}
                    else _same_navigation_polygons(actual_alternative.get(key), expected_value)
                    if key == "navigation_polygons"
                    else _same_custom_data(actual_alternative.get(key), expected_value, request.spec.get("custom_data_layers", []))
                    if key == "custom_data"
                    else actual_alternative.get(key) == expected_value
                    for key, expected_value in expected_alternative.items()
                )
                if not alternative_matches:
                    raise ValidationError("loaded TileSet alternative data does not match the recipe")
    normalized_layers = _expected_layers(request.spec)
    for key in ("physics_layers", "navigation_layers", "occlusion_layers", "custom_data_layers", "terrain_sets"):
        expected = len(request.spec.get(key, []))
        if facts.get(key + "_count") != expected:
            raise ValidationError(f"loaded TileSet {key} count does not match the recipe")
        layers_match = (
            _same_terrain_sets(facts.get(key), normalized_layers[key])
            if key == "terrain_sets"
            else facts.get(key) == normalized_layers[key]
        )
        if not layers_match:
            raise ValidationError(f"loaded TileSet {key} data does not match the recipe")
    return dict(facts)


def register_into(registry: StructureValidatorRegistry):
    return registry.register(
        artifact_type="TileSet", validator_id=VALIDATOR_ID,
        validator=validate_tileset, checks=CHECKS,
    )
