"""L4 structural contract for a declared TileSet atlas recipe."""
from __future__ import annotations

from typing import Any

from .contract import ValidationError
from .structure import StructureRequest, StructureValidatorRegistry

VALIDATOR_ID = "tileset_atlas_structure_v1"
CHECKS = ("tileset",)


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
