"""Native, recipe-only TileSet compiler for orthogonal square atlases.

The compiler intentionally delegates resource construction to Godot.  Text
``.tres`` generation is brittle for TileSetAtlasSource and, more importantly,
would not prove the engine accepts the declared polygons and terrain data.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .contract import CompileRequest, CompilerError
from .registry import CompilerRegistry, CompilerRoute

COMPILER_ID = "tileset_atlas_v1"
COMPILER_VERSION = 1

_SCRIPT = Path(__file__).with_name("tileset_compiler.gd")

_SHAPES = {"square": 0, "isometric": 1, "half_offset_square": 2, "hexagon": 3}
_ANIMATION_MODES = {"default": 0, "random_start_times": 1, "max": 2}


def _pair(value: Any, label: str, *, positive: bool = False) -> list[int]:
    if not isinstance(value, list) or len(value) != 2 or any(type(v) is not int for v in value):
        raise CompilerError(f"{label} must be [integer, integer]")
    if positive and any(v <= 0 for v in value):
        raise CompilerError(f"{label} values must be positive integers")
    return list(value)


def _color(value: Any, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) not in (3, 4) or any(type(v) not in (int, float) for v in value):
        raise CompilerError(f"{label} must be [r, g, b] or [r, g, b, a]")
    result = [float(v) for v in value]
    if any(v < 0 or v > 1 for v in result):
        raise CompilerError(f"{label} channels must be between 0 and 1")
    return result + ([1.0] if len(result) == 3 else [])


def _recipe(request: CompileRequest) -> dict[str, Any]:
    spec = dict(request.spec)
    binary = spec.pop("godot_path", None)
    if not isinstance(binary, str) or not binary.strip():
        raise CompilerError("TileSet spec requires a non-empty godot_path")
    spec["tile_size"] = _pair(spec.get("tile_size"), "TileSet tile_size", positive=True)
    shape = spec.get("tile_shape", "square")
    if not isinstance(shape, str) or shape not in _SHAPES:
        raise CompilerError("tile_shape must be one of: " + ", ".join(_SHAPES))
    spec["tile_shape"] = _SHAPES[shape]
    sources = spec.get("sources")
    if not isinstance(sources, list) or not sources:
        raise CompilerError("TileSet spec requires a non-empty sources list")
    seen_source_ids: set[int] = set()
    for source_index, source in enumerate(sources):
        if not isinstance(source, Mapping):
            raise CompilerError("every TileSet source must be an object")
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
        source["region_size"] = _pair(source.get("region_size", source.get("tile_size", spec["tile_size"])), "source region_size", positive=True)
        source["margins"] = _pair(source.get("margins", [0, 0]), "source margins")
        source["separation"] = _pair(source.get("separation", [0, 0]), "source separation")
        for tile in source["tiles"]:
            if not isinstance(tile, Mapping):
                raise CompilerError("every TileSet tile must be an object")
            tile["coords"] = _pair(tile.get("coords"), "tile coords")
            for alternative in tile.get("alternatives", []):
                if not isinstance(alternative, Mapping) or type(alternative.get("id")) is not int or alternative["id"] <= 0:
                    raise CompilerError("alternative id must be a positive integer")
            animation = tile.get("animation")
            if animation is not None:
                if not isinstance(animation, Mapping):
                    raise CompilerError("tile animation must be an object")
                mode = animation.get("mode", "default")
                if not isinstance(mode, str) or mode not in _ANIMATION_MODES:
                    raise CompilerError("animation mode must be one of: " + ", ".join(_ANIMATION_MODES))
                if type(animation.get("frames_count")) is not int or animation["frames_count"] < 1:
                    raise CompilerError("animation frames_count must be a positive integer")
                animation["mode"] = _ANIMATION_MODES[mode]
                if type(animation.get("columns", 1)) is not int or animation.get("columns", 1) < 1:
                    raise CompilerError("animation columns must be a positive integer")
                animation["columns"] = animation.get("columns", 1)
                animation["separation"] = _pair(animation.get("separation", [0, 0]), "animation separation")
                if type(animation.get("speed", 1.0)) not in (int, float) or animation.get("speed", 1.0) <= 0:
                    raise CompilerError("animation speed must be a positive number")
                animation["speed"] = float(animation.get("speed", 1.0))
                durations = animation.get("frame_durations", [])
                if not isinstance(durations, list):
                    raise CompilerError("animation frame_durations must be a list")
                normalized: list[dict[str, Any]] = []
                for frame, duration in enumerate(durations):
                    if not isinstance(duration, Mapping) or duration.get("frame") != frame:
                        raise CompilerError("animation frame_durations must be ordered, unique, and continuous")
                    if type(duration.get("duration")) not in (int, float) or duration["duration"] <= 0:
                        raise CompilerError("animation frame duration must be a positive number")
                    normalized.append({"frame": frame, "duration": float(duration["duration"])})
                if normalized and len(normalized) != animation["frames_count"]:
                    raise CompilerError("animation frame_durations must declare every frame")
                animation["frame_durations"] = normalized
    for terrain_set in spec.get("terrain_sets", []):
        if not isinstance(terrain_set, Mapping) or type(terrain_set.get("mode", 0)) is not int:
            raise CompilerError("terrain set mode must be an integer")
        for terrain in terrain_set.get("terrains", []):
            if not isinstance(terrain, Mapping) or not isinstance(terrain.get("name", ""), str):
                raise CompilerError("terrain needs a string name")
            if "color" in terrain:
                terrain["color"] = _color(terrain["color"], "terrain color")
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
            completed = subprocess.run(
                [
                    recipe["godot_path"], "--headless", "--path", str(request.project_root),
                    "--script", str(_SCRIPT), "--", "--recipe", str(config),
                    "--output", request.artifact_path,
                ],
                capture_output=True, text=True, timeout=300, check=False,
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
