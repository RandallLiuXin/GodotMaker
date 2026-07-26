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


def _recipe(request: CompileRequest) -> dict[str, Any]:
    spec = dict(request.spec)
    binary = spec.pop("godot_path", None)
    if not isinstance(binary, str) or not binary.strip():
        raise CompilerError("TileSet spec requires a non-empty godot_path")
    if not isinstance(spec.get("tile_size"), list) or len(spec["tile_size"]) != 2:
        raise CompilerError("TileSet spec requires tile_size as [width, height]")
    if any(type(value) is not int or value <= 0 for value in spec["tile_size"]):
        raise CompilerError("TileSet tile_size values must be positive integers")
    sources = spec.get("sources")
    if not isinstance(sources, list) or not sources:
        raise CompilerError("TileSet spec requires a non-empty sources list")
    for source in sources:
        if not isinstance(source, Mapping):
            raise CompilerError("every TileSet source must be an object")
        texture = source.get("texture")
        if not isinstance(texture, str) or not texture.startswith("res://"):
            raise CompilerError("every TileSet source requires a res:// texture path")
        if not isinstance(source.get("tiles"), list):
            raise CompilerError("every TileSet source requires a tiles list")
        if "region_size" not in source and "tile_size" not in source:
            source["region_size"] = list(spec["tile_size"])
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
