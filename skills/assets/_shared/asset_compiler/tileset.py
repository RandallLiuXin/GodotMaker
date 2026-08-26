"""Native, recipe-only TileSet compiler for orthogonal square atlases.

The compiler intentionally delegates resource construction to Godot.  Text
``.tres`` generation is brittle for TileSetAtlasSource and, more importantly,
would not prove the engine accepts the declared polygons and terrain data.
"""
from __future__ import annotations

import json
import math
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from .contract import CompileRequest, CompilerError
from .registry import CompilerRegistry, CompilerRoute

COMPILER_ID = "tileset_atlas_v1"
COMPILER_VERSION = 1

_SCRIPT = Path(__file__).with_name("tileset_compiler.gd")

_SHAPES = {"square": 0, "isometric": 1, "half_offset_square": 2, "hexagon": 3}
_ANIMATION_MODES = {"default": 0, "random_start_times": 1, "max": 2}
_TERRAIN_MODES = {0, 1, 2}
_CUSTOM_DATA_TYPES = {0: type(None), 1: bool, 2: int, 3: float, 4: str}
_UINT32_MAX = 2**32 - 1
_TILE_DATA_KEYS = {
    "texture_origin", "z_index", "y_sort_origin", "probability", "terrain_set",
    "terrain", "peering_bits", "custom_data", "collision_polygons",
    "occlusion_polygons", "navigation_polygons",
}
_PEERING_BITS = {
    0: ({0, 4, 8, 12}, {3, 7, 11, 15}),
    1: ({2, 6, 10, 14}, {1, 5, 9, 13}),
    # Half-offset square and hexagon use Godot's default horizontal offset axis.
    2: ({0, 2, 6, 8, 10, 14}, {3, 5, 7, 11, 13, 15}),
    3: ({0, 2, 6, 8, 10, 14}, {3, 5, 7, 11, 13, 15}),
}


def _pair(value: Any, label: str, *, positive: bool = False) -> list[int]:
    if not isinstance(value, list) or len(value) != 2 or any(type(v) is not int for v in value):
        raise CompilerError(f"{label} must be [integer, integer]")
    if positive and any(v <= 0 for v in value):
        raise CompilerError(f"{label} values must be positive integers")
    return list(value)


def _finite_number(value: Any, label: str, *, positive: bool = False, non_negative: bool = False, maximum: float | None = None) -> float:
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise CompilerError(f"{label} must be a finite number")
    number = float(value)
    if positive and number <= 0:
        raise CompilerError(f"{label} must be positive")
    if non_negative and number < 0:
        raise CompilerError(f"{label} must be non-negative")
    if maximum is not None and number > maximum:
        raise CompilerError(f"{label} must be at most {maximum:g}")
    return number


def _integer(value: Any, label: str, *, minimum: int | None = None, maximum: int | None = None) -> int:
    if type(value) is not int:
        raise CompilerError(f"{label} must be an integer")
    if minimum is not None and value < minimum:
        raise CompilerError(f"{label} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise CompilerError(f"{label} must be at most {maximum}")
    return value


def _color(value: Any, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) not in (3, 4) or any(type(v) not in (int, float) for v in value):
        raise CompilerError(f"{label} must be [r, g, b] or [r, g, b, a]")
    result = [float(v) for v in value]
    if any(not math.isfinite(v) or v < 0 or v > 1 for v in result):
        raise CompilerError(f"{label} channels must be between 0 and 1")
    return result + ([1.0] if len(result) == 3 else [])


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise CompilerError(f"{label} must be a list")
    return value


def _reject_unknown_keys(item: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(item).difference(allowed)
    if unknown:
        raise CompilerError(f"{label} has unsupported fields: {', '.join(sorted(unknown))}")


def _layer_index(value: Any, label: str, count: int) -> int:
    index = _integer(value, label, minimum=0)
    if index >= count:
        raise CompilerError(f"{label} is outside the declared layer range")
    return index


def _polygon_points(value: Any, label: str, *, allow_empty: bool = True) -> list[list[float]]:
    points = _list(value, f"{label} points")
    if len(points) < 3 and not allow_empty:
        raise CompilerError(f"{label} points must contain at least three points")
    if len(points) in (1, 2):
        raise CompilerError(f"{label} points must be empty or contain at least three points")
    normalized: list[list[float]] = []
    for point in points:
        if not isinstance(point, list) or len(point) != 2:
            raise CompilerError(f"{label} point must be [number, number]")
        normalized.append([
            _finite_number(point[0], f"{label} point x"),
            _finite_number(point[1], f"{label} point y"),
        ])
    return normalized


def _terrain_index(item: dict[str, Any], terrain_sets: list[Any], label: str) -> None:
    terrain_set = item.get("terrain_set", -1)
    terrain = item.get("terrain", -1)
    _integer(terrain_set, f"{label} terrain_set", minimum=-1)
    _integer(terrain, f"{label} terrain", minimum=-1)
    if terrain_set == -1:
        if terrain != -1:
            raise CompilerError(f"{label} terrain requires a declared terrain_set")
        return
    if terrain_set >= len(terrain_sets):
        raise CompilerError(f"{label} terrain_set is outside the declared terrain set range")
    terrains = terrain_sets[terrain_set]["terrains"]
    if terrain != -1 and terrain >= len(terrains):
        raise CompilerError(f"{label} terrain is outside the declared terrain range")


def _custom_value(value: Any, value_type: int, label: str) -> Any:
    expected = _CUSTOM_DATA_TYPES[value_type]
    if value_type == 3:
        return _finite_number(value, label)
    if type(value) is not expected:
        names = {0: "NIL", 1: "bool", 2: "int", 4: "String"}
        raise CompilerError(f"{label} must be a {names[value_type]} scalar")
    return value


def _valid_peering_bits(shape: int, terrain_mode: int) -> set[int]:
    sides, corners = _PEERING_BITS[shape]
    return (sides if terrain_mode in (0, 2) else set()) | (corners if terrain_mode in (0, 1) else set())


def _validate_tile_data(item: dict[str, Any], spec: dict[str, Any], label: str) -> None:
    if "texture_origin" in item:
        item["texture_origin"] = _pair(item["texture_origin"], f"{label} texture_origin")
    if "z_index" in item:
        _integer(item["z_index"], f"{label} z_index")
    if "y_sort_origin" in item:
        _integer(item["y_sort_origin"], f"{label} y_sort_origin")
    if "probability" in item:
        item["probability"] = _finite_number(item["probability"], f"{label} probability", non_negative=True)

    terrain_sets = spec["terrain_sets"]
    _terrain_index(item, terrain_sets, label)
    terrain_set = item.get("terrain_set", -1)
    seen_bits: set[int] = set()
    for bit in _list(item.get("peering_bits", []), f"{label} peering_bits"):
        if not isinstance(bit, dict):
            raise CompilerError(f"{label} peering bit must be an object")
        _reject_unknown_keys(bit, {"bit", "terrain"}, f"{label} peering bit")
        index = _integer(bit.get("bit"), f"{label} peering bit", minimum=0, maximum=15)
        terrain = _integer(bit.get("terrain"), f"{label} peering terrain", minimum=0)
        if terrain_set == -1:
            raise CompilerError(f"{label} peering bits require a declared terrain_set")
        if terrain >= len(terrain_sets[terrain_set]["terrains"]):
            raise CompilerError(f"{label} peering terrain is outside the declared terrain range")
        terrain_mode = terrain_sets[terrain_set]["mode"]
        if index not in _valid_peering_bits(spec["tile_shape"], terrain_mode):
            raise CompilerError(f"{label} peering bit is invalid for the tile_shape and terrain mode")
        if index in seen_bits:
            raise CompilerError(f"{label} cannot declare duplicate peering bits")
        seen_bits.add(index)

    custom_layers = spec["custom_data_layers"]
    seen_custom_layers: set[int] = set()
    for custom in _list(item.get("custom_data", []), f"{label} custom_data"):
        if not isinstance(custom, dict):
            raise CompilerError(f"{label} custom data must be an object")
        _reject_unknown_keys(custom, {"layer", "value"}, f"{label} custom data")
        layer = _layer_index(custom.get("layer"), f"{label} custom data layer", len(custom_layers))
        if layer in seen_custom_layers:
            raise CompilerError(f"{label} cannot declare duplicate custom data layers")
        seen_custom_layers.add(layer)
        if "value" not in custom:
            raise CompilerError(f"{label} custom data requires a value")
        custom["value"] = _custom_value(custom["value"], custom_layers[layer]["type"], f"{label} custom data value")

    polygon_families = (
        ("collision_polygons", "collision", len(spec["physics_layers"])),
        ("occlusion_polygons", "occlusion", len(spec["occlusion_layers"])),
        ("navigation_polygons", "navigation", len(spec["navigation_layers"])),
    )
    for key, family, layer_count in polygon_families:
        seen_navigation_layers: set[int] = set()
        for polygon in _list(item.get(key, []), f"{label} {key}"):
            if not isinstance(polygon, dict):
                raise CompilerError(f"{label} {family} polygon must be an object")
            _reject_unknown_keys(polygon, {"layer", "points"}, f"{label} {family} polygon")
            layer = _layer_index(polygon.get("layer"), f"{label} {family} polygon layer", layer_count)
            if key == "navigation_polygons" and layer in seen_navigation_layers:
                raise CompilerError(f"{label} cannot declare duplicate navigation polygons for one layer")
            if key == "navigation_polygons":
                seen_navigation_layers.add(layer)
            polygon["points"] = _polygon_points(
                polygon.get("points"), f"{label} {family} polygon",
                allow_empty=key != "collision_polygons",
            )


def _validate_animation(animation: Any) -> dict[str, Any]:
    if not isinstance(animation, dict):
        raise CompilerError("tile animation must be an object")
    _reject_unknown_keys(animation, {"mode", "frames_count", "columns", "separation", "speed", "frame_durations"}, "tile animation")
    mode = animation.get("mode", "default")
    if not isinstance(mode, str) or mode not in _ANIMATION_MODES:
        raise CompilerError("animation mode must be one of: " + ", ".join(_ANIMATION_MODES))
    animation["mode"] = _ANIMATION_MODES[mode]
    animation["frames_count"] = _integer(animation.get("frames_count"), "animation frames_count", minimum=1)
    animation["columns"] = _integer(animation.get("columns", 1), "animation columns", minimum=1)
    animation["separation"] = _pair(animation.get("separation", [0, 0]), "animation separation")
    if any(value < 0 for value in animation["separation"]):
        raise CompilerError("animation separation values must be non-negative integers")
    animation["speed"] = _finite_number(animation.get("speed", 1.0), "animation speed", positive=True)
    if "frame_durations" not in animation:
        return animation
    durations = _list(animation["frame_durations"], "animation frame_durations")
    normalized: list[dict[str, Any]] = []
    for frame, duration in enumerate(durations):
        if not isinstance(duration, dict) or duration.get("frame") != frame:
            raise CompilerError("animation frame_durations must be ordered, unique, and continuous")
        _reject_unknown_keys(duration, {"frame", "duration"}, "animation frame duration")
        normalized.append({"frame": frame, "duration": _finite_number(duration.get("duration"), "animation frame duration", positive=True)})
    if len(normalized) != animation["frames_count"]:
        raise CompilerError("animation frame_durations must declare every frame")
    animation["frame_durations"] = normalized
    return animation


def _recipe(request: CompileRequest) -> dict[str, Any]:
    spec = deepcopy(dict(request.spec))
    _reject_unknown_keys(spec, {
        "godot_path", "tile_shape", "tile_size", "sources", "physics_layers",
        "navigation_layers", "occlusion_layers", "custom_data_layers", "terrain_sets",
    }, "TileSet spec")
    binary = spec.pop("godot_path", None)
    if not isinstance(binary, str) or not binary.strip():
        raise CompilerError("TileSet spec requires a non-empty godot_path")
    spec["tile_size"] = _pair(spec.get("tile_size"), "TileSet tile_size", positive=True)
    shape = spec.get("tile_shape", "square")
    if not isinstance(shape, str) or shape not in _SHAPES:
        raise CompilerError("tile_shape must be one of: " + ", ".join(_SHAPES))
    spec["tile_shape"] = _SHAPES[shape]
    for key in ("physics_layers", "navigation_layers", "occlusion_layers", "custom_data_layers", "terrain_sets"):
        spec[key] = _list(spec.get(key, []), f"TileSet {key}")
    for layer in spec["physics_layers"]:
        if not isinstance(layer, dict):
            raise CompilerError("physics layer must be an object")
        _reject_unknown_keys(layer, {"collision_layer", "collision_mask"}, "physics layer")
        layer["collision_layer"] = _integer(layer.get("collision_layer", 1), "physics collision_layer", minimum=0, maximum=_UINT32_MAX)
        layer["collision_mask"] = _integer(layer.get("collision_mask", 1), "physics collision_mask", minimum=0, maximum=_UINT32_MAX)
    for layer in spec["navigation_layers"]:
        if not isinstance(layer, dict):
            raise CompilerError("navigation layer must be an object")
        _reject_unknown_keys(layer, {"layers"}, "navigation layer")
        layer["layers"] = _integer(layer.get("layers", 1), "navigation layers", minimum=0, maximum=_UINT32_MAX)
    for layer in spec["occlusion_layers"]:
        if not isinstance(layer, dict):
            raise CompilerError("occlusion layer must be an object")
        _reject_unknown_keys(layer, {"light_mask"}, "occlusion layer")
        layer["light_mask"] = _integer(layer.get("light_mask", 1), "occlusion light_mask", minimum=0, maximum=_UINT32_MAX)
    for layer in spec["custom_data_layers"]:
        if not isinstance(layer, dict) or not isinstance(layer.get("name", ""), str):
            raise CompilerError("custom data layer needs a string name")
        _reject_unknown_keys(layer, {"name", "type"}, "custom data layer")
        layer["name"] = layer.get("name", "")
        value_type = _integer(layer.get("type", 0), "custom data layer type", minimum=0)
        if value_type not in _CUSTOM_DATA_TYPES:
            raise CompilerError("custom data layer type must be one of: NIL, bool, int, float, String")
        layer["type"] = value_type
    custom_data_names: set[str] = set()
    for layer in spec["custom_data_layers"]:
        if layer["name"] in custom_data_names:
            raise CompilerError("custom data layer names must be unique")
        custom_data_names.add(layer["name"])
    for terrain_set in spec["terrain_sets"]:
        if not isinstance(terrain_set, dict):
            raise CompilerError("terrain set must be an object")
        _reject_unknown_keys(terrain_set, {"mode", "terrains"}, "terrain set")
        terrain_set["mode"] = _integer(terrain_set.get("mode", 0), "terrain set mode")
        if terrain_set["mode"] not in _TERRAIN_MODES:
            raise CompilerError("terrain set mode must be one of: 0, 1, 2")
        terrain_set["terrains"] = _list(terrain_set.get("terrains", []), "terrain set terrains")
        for terrain in terrain_set["terrains"]:
            if not isinstance(terrain, dict) or not isinstance(terrain.get("name", ""), str):
                raise CompilerError("terrain needs a string name")
            _reject_unknown_keys(terrain, {"name", "color"}, "terrain")
            if "color" in terrain:
                terrain["color"] = _color(terrain["color"], "terrain color")

    sources = spec.get("sources")
    if not isinstance(sources, list) or not sources:
        raise CompilerError("TileSet spec requires a non-empty sources list")
    seen_source_ids: set[int] = set()
    for source_index, source in enumerate(sources):
        if not isinstance(source, dict):
            raise CompilerError("every TileSet source must be an object")
        _reject_unknown_keys(source, {"id", "texture", "tiles", "region_size", "tile_size", "margins", "separation"}, "TileSet source")
        texture = source.get("texture")
        if not isinstance(texture, str) or not texture.startswith("res://"):
            raise CompilerError("every TileSet source requires a res:// texture path")
        if not isinstance(source.get("tiles"), list):
            raise CompilerError("every TileSet source requires a tiles list")
        source_id = source.get("id", source_index)
        if type(source_id) is not int or source_id < 0 or source_id in seen_source_ids:
            raise CompilerError("every TileSet source id must be a unique non-negative integer")
        seen_source_ids.add(source_id)
        source["id"] = source_id
        if "tile_size" in source:
            source["tile_size"] = _pair(source["tile_size"], "source tile_size", positive=True)
        source["region_size"] = _pair(source.get("region_size", source.get("tile_size", spec["tile_size"])), "source region_size", positive=True)
        source["margins"] = _pair(source.get("margins", [0, 0]), "source margins")
        source["separation"] = _pair(source.get("separation", [0, 0]), "source separation")
        if any(value < 0 for value in source["margins"]):
            raise CompilerError("source margins values must be non-negative integers")
        if any(value < 0 for value in source["separation"]):
            raise CompilerError("source separation values must be non-negative integers")
        seen_coords: set[tuple[int, int]] = set()
        for tile in source["tiles"]:
            if not isinstance(tile, dict):
                raise CompilerError("every TileSet tile must be an object")
            _reject_unknown_keys(tile, _TILE_DATA_KEYS | {"coords", "alternatives", "animation"}, "tile")
            tile["coords"] = _pair(tile.get("coords"), "tile coords")
            if any(value < 0 for value in tile["coords"]):
                raise CompilerError("tile coords values must be non-negative integers")
            coords = tuple(tile["coords"])
            if coords in seen_coords:
                raise CompilerError("TileSet source cannot declare duplicate tile coords")
            seen_coords.add(coords)
            _validate_tile_data(tile, spec, "tile")
            alternatives = _list(tile.get("alternatives", []), "tile alternatives")
            seen_alternative_ids: set[int] = set()
            for alternative in alternatives:
                if not isinstance(alternative, dict):
                    raise CompilerError("alternative must be an object")
                _reject_unknown_keys(alternative, _TILE_DATA_KEYS | {"id"}, "alternative")
                alternative_id = _integer(alternative.get("id"), "alternative id", minimum=1)
                if alternative_id in seen_alternative_ids:
                    raise CompilerError("tile cannot declare duplicate alternative ids")
                seen_alternative_ids.add(alternative_id)
                alternative["id"] = alternative_id
                _validate_tile_data(alternative, spec, "alternative")
            tile["alternatives"] = alternatives
            if "animation" in tile:
                tile["animation"] = _validate_animation(tile["animation"])
    spec["godot_path"] = binary.strip()
    return spec


def compile_tileset(request: CompileRequest) -> dict[str, Any]:
    """Write one TileSet resource from its fully declared recipe."""
    recipe = _recipe(request)
    if not _SCRIPT.is_file():
        raise CompilerError(f"TileSet compiler script is missing: {_SCRIPT}")
    with tempfile.TemporaryDirectory(prefix="godotmaker-tileset-") as temp:
        config = Path(temp) / "recipe.json"
        config.write_text(json.dumps(recipe), encoding="utf-8")
        try:
            imported = subprocess.run(
                [recipe["godot_path"], "--headless", "--path", str(request.project_root), "--import"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=300, check=False,
            )
            if imported.returncode != 0:
                message = (imported.stderr or imported.stdout).strip()
                raise CompilerError(f"TileSet Godot import failed: {message[-2000:]}")
            completed = subprocess.run(
                [
                    recipe["godot_path"], "--headless", "--path", str(request.project_root),
                    "--script", str(_SCRIPT), "--", "--recipe", str(config),
                    "--output", request.artifact_path,
                ],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=300, check=False,
            )
        except FileNotFoundError as exc:
            raise CompilerError(f"TileSet Godot binary was not found: {recipe['godot_path']}") from exc
        except subprocess.TimeoutExpired as exc:
            raise CompilerError("TileSet compiler timed out after 300s") from exc
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout).strip()
        raise CompilerError(f"TileSet Godot compiler failed: {message[-2000:]}")
    return {"sources": len(recipe["sources"]), "tile_size": list(recipe["tile_size"])}


def register_into(registry: CompilerRegistry) -> CompilerRoute:
    return registry.register(
        source_layout_type="tile_atlas", artifact_type="TileSet",
        compiler_id=COMPILER_ID, compiler_version=COMPILER_VERSION,
        compiler=compile_tileset,
    )
