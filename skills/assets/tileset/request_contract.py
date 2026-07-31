"""Typed public request contract for the fixed-profile TileSet Skill."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class TileSetRequestError(ValueError):
    """Raised when a TileSet caller supplies an unsupported request."""


_PROFILES = {"marching_squares_15", "blob_47"}
_TOP_LEVEL = {"asset_type", "asset_id", "brief", "provider", "references", "spec"}
_SPEC = {"autotile_profile", "tile_size", "terrain", "semantic_metadata"}
_TERRAIN = {"name", "foreground_material", "background_material"}
_METADATA = {"custom_data_layers", "physics_layers", "navigation_layers", "roles"}
_ROLE_NAMES = {"foreground_full", "foreground_isolated"}
_ROLE = {"custom_data", "physics", "navigation"}


def check_tileset_request(request: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize the public, non-recipe TileSet request."""
    if not isinstance(request, Mapping):
        raise TileSetRequestError("tileset request must be an object")
    unknown = set(request).difference(_TOP_LEVEL)
    if unknown:
        raise TileSetRequestError("tileset request has unknown fields: " + ", ".join(sorted(unknown)))
    if request.get("asset_type") != "tileset":
        raise TileSetRequestError("asset_type must be 'tileset'")
    spec = request.get("spec")
    if not isinstance(spec, Mapping):
        raise TileSetRequestError("tileset spec must be an object")
    unknown = set(spec).difference(_SPEC)
    if unknown:
        raise TileSetRequestError("tileset spec has unknown fields: " + ", ".join(sorted(unknown)))
    profile = spec.get("autotile_profile")
    if profile not in _PROFILES:
        raise TileSetRequestError("spec.autotile_profile must be one of: " + ", ".join(sorted(_PROFILES)))
    size = spec.get("tile_size")
    if not isinstance(size, Mapping) or set(size) != {"width", "height"}:
        raise TileSetRequestError("spec.tile_size must contain exactly width and height")
    for key in ("width", "height"):
        if type(size[key]) is not int or size[key] <= 0:
            raise TileSetRequestError(f"spec.tile_size.{key} must be a positive integer")
    terrain = spec.get("terrain")
    if not isinstance(terrain, Mapping) or set(terrain) != _TERRAIN:
        raise TileSetRequestError("spec.terrain must contain name, foreground_material, and background_material")
    for key in _TERRAIN:
        if not isinstance(terrain[key], str) or not terrain[key].strip():
            raise TileSetRequestError(f"spec.terrain.{key} must be a non-empty string")
    if terrain["foreground_material"].strip() == terrain["background_material"].strip():
        raise TileSetRequestError("terrain foreground_material and background_material must differ")
    metadata = spec.get("semantic_metadata")
    if metadata is not None:
        _check_semantic_metadata(metadata)
    return dict(request)


def _check_semantic_metadata(metadata: Any) -> None:
    if not isinstance(metadata, Mapping):
        raise TileSetRequestError("semantic_metadata must be an object")
    unknown = set(metadata).difference(_METADATA)
    if unknown:
        raise TileSetRequestError("semantic_metadata has unknown fields: " + ", ".join(sorted(unknown)))
    for key in ("custom_data_layers", "physics_layers", "navigation_layers"):
        if key in metadata and not isinstance(metadata[key], list):
            raise TileSetRequestError(f"semantic_metadata.{key} must be an array")
    custom_names: set[str] = set()
    for item in metadata.get("custom_data_layers", []):
        if not isinstance(item, Mapping) or set(item) != {"name", "type"}:
            raise TileSetRequestError("custom_data_layers entries require name and type")
        if not isinstance(item["name"], str) or not item["name"].strip():
            raise TileSetRequestError("custom data layer name must be non-empty")
        if item["type"] not in {"bool", "int", "float", "String"}:
            raise TileSetRequestError("custom data layer type must be bool, int, float, or String")
        if item["name"] in custom_names:
            raise TileSetRequestError("custom data layer names must be unique")
        custom_names.add(item["name"])
    for item in metadata.get("physics_layers", []):
        if not isinstance(item, Mapping) or set(item) != {"name", "collision_layer", "collision_mask"}:
            raise TileSetRequestError("physics_layers entries require name, collision_layer, and collision_mask")
        _check_layer_numbers(item, "physics")
    for item in metadata.get("navigation_layers", []):
        if not isinstance(item, Mapping) or set(item) != {"name"} or not isinstance(item["name"], str) or not item["name"].strip():
            raise TileSetRequestError("navigation_layers entries require a non-empty name")
    roles = metadata.get("roles", {})
    if not isinstance(roles, Mapping):
        raise TileSetRequestError("semantic_metadata.roles must be an object")
    unknown_roles = set(roles).difference(_ROLE_NAMES)
    if unknown_roles:
        raise TileSetRequestError("semantic_metadata.roles has unknown roles: " + ", ".join(sorted(unknown_roles)))
    for name, role in roles.items():
        if not isinstance(role, Mapping):
            raise TileSetRequestError(f"semantic_metadata.roles.{name} must be an object")
        unknown = set(role).difference(_ROLE)
        if unknown:
            raise TileSetRequestError(f"semantic metadata role {name} has unknown fields: " + ", ".join(sorted(unknown)))
        if "custom_data" in role:
            if not isinstance(role["custom_data"], Mapping) or set(role["custom_data"]).difference(custom_names):
                raise TileSetRequestError(f"semantic metadata role {name} references an undeclared custom data layer")
        for key, count in (("physics", len(metadata.get("physics_layers", []))), ("navigation", len(metadata.get("navigation_layers", [])))):
            if key in role:
                value = role[key]
                if value not in {"none", "full_cell"}:
                    raise TileSetRequestError(f"semantic metadata role {name}.{key} must be none or full_cell")
                if value == "full_cell" and count != 1:
                    raise TileSetRequestError(f"semantic metadata role {name}.{key} requires exactly one declared layer")


def _check_layer_numbers(item: Mapping[str, Any], label: str) -> None:
    if not isinstance(item.get("name"), str) or not item["name"].strip():
        raise TileSetRequestError(f"{label} layer name must be non-empty")
    for key in ("collision_layer", "collision_mask"):
        if type(item.get(key)) is not int or item[key] < 0 or item[key] > 0xFFFFFFFF:
            raise TileSetRequestError(f"{label} layer {key} must be an unsigned 32-bit integer")
