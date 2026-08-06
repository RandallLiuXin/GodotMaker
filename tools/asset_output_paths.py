#!/usr/bin/env python3
"""Path and layout checks for direct Asset Skill request/result outputs.

This module has no persisted asset schema.  It only keeps compilers inside the
directory named by the request's ``asset_type`` and ``asset_id`` and checks the
layout-to-Godot-type relation for the output currently being compiled.
"""
from __future__ import annotations

from pathlib import Path

from asset_family_registry import FAMILY_NAMES, REFERENCE_FAMILY_NAMES

GENERATED_ROOT = "assets/generated"
WORK_ROOT = ".godotmaker/asset-generation/work"
_RES_PREFIX = "res://"
_RESERVED_PATH_CHARS = set('<>:"/\\|?*;')
_RESERVED_DEVICE_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

# Pixel layouts are checked at compile time, independently of registration.
LAYOUT_ARTIFACT_TYPES = {
    "single": ("Texture2D", "StyleBoxTexture"),
    "grid_sheet": ("SpriteFrames",),
    "region_atlas": ("AtlasTexture", "StyleBoxTexture"),
    "theme_recipe": ("Theme",),
    "tile_atlas": ("TileSet",),
}
REFERENCE_LAYOUTS = {"reference"}
SOURCE_LAYOUT_TYPES = set(LAYOUT_ARTIFACT_TYPES) | REFERENCE_LAYOUTS
PRODUCTION_FAMILIES = set(FAMILY_NAMES)
REFERENCE_FAMILIES = set(REFERENCE_FAMILY_NAMES)


class AssetOutputPathError(Exception):
    """Raised when a direct output path or compile input is unsafe."""


def safe_identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AssetOutputPathError(f"{label} must be a non-empty string")
    if value in (".", ".."):
        raise AssetOutputPathError(f"{label} must not be '.' or '..'")
    if any(char in _RESERVED_PATH_CHARS or ord(char) < 32 for char in value):
        raise AssetOutputPathError(
            f"{label} must be a single safe path segment "
            "(no path separators, ':', ';' or reserved characters)"
        )
    if value != value.strip() or value.endswith("."):
        raise AssetOutputPathError(
            f"{label} must not have leading/trailing spaces or a trailing dot"
        )
    if value.split(".", 1)[0].upper() in _RESERVED_DEVICE_NAMES:
        raise AssetOutputPathError(f"{label} must not be a Windows reserved device name")
    return value


def _check_res_path(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.startswith(_RES_PREFIX):
        raise AssetOutputPathError(f"{label} must be a res:// path")
    remainder = value[len(_RES_PREFIX):]
    if not remainder.strip():
        raise AssetOutputPathError(f"{label} must name a resource under res://")
    if "\\" in remainder:
        raise AssetOutputPathError(f"{label} must use forward slashes")
    for segment in remainder.split("/"):
        if segment in ("", ".", ".."):
            raise AssetOutputPathError(
                f"{label} must be a relative resource path with no empty, '.' or '..' segments"
            )
        if ":" in segment:
            raise AssetOutputPathError(f"{label} must not contain a drive letter or scheme")
    return value


def resolve_res_path(project_root: Path, res_path: str, *, label: str = "path") -> Path:
    _check_res_path(res_path, label)
    root = Path(project_root).resolve()
    candidate = (root / res_path[len(_RES_PREFIX):]).resolve()
    if not candidate.is_relative_to(root):
        raise AssetOutputPathError(f"{label} resolves outside the project root")
    return candidate


def generated_output_dir(asset_type: str, asset_id: str) -> str:
    if asset_type not in FAMILY_NAMES:
        raise AssetOutputPathError(f"asset_type is not allowed: {asset_type}")
    safe_identifier(asset_id, "asset_id")
    return f"{GENERATED_ROOT}/{asset_type}/{asset_id}"


def check_output_path(
    value: str,
    *,
    asset_type: str | None = None,
    production_family: str | None = None,
    asset_id: str,
    label: str,
) -> str:
    asset_type = asset_type or production_family
    if asset_type is None:
        raise AssetOutputPathError("asset_type is required")
    _check_res_path(value, label)
    remainder = value[len(_RES_PREFIX):]
    if remainder == WORK_ROOT or remainder.startswith(WORK_ROOT + "/"):
        raise AssetOutputPathError(f"{label} must not depend on the generation work/ workspace")
    output_dir = generated_output_dir(asset_type, asset_id)
    if not remainder.startswith(output_dir + "/"):
        raise AssetOutputPathError(f"{label} must be a file under res://{output_dir}/")
    return value


def assert_within_output_dir(
    project_root: Path,
    target: Path | str,
    *,
    asset_type: str | None = None,
    production_family: str | None = None,
    asset_id: str,
    label: str = "output",
) -> Path:
    asset_type = asset_type or production_family
    if asset_type is None:
        raise AssetOutputPathError("asset_type is required")
    root = Path(project_root).resolve()
    relative_dir = generated_output_dir(asset_type, asset_id)
    output_dir = (root / relative_dir).resolve()
    if output_dir != root and not output_dir.is_relative_to(root):
        raise AssetOutputPathError(f"{label} output directory resolves outside the project root")
    resolved = Path(target)
    if not resolved.is_absolute():
        resolved = root / resolved
    resolved = resolved.resolve()
    if resolved == output_dir or not resolved.is_relative_to(output_dir):
        raise AssetOutputPathError(f"{label} must be written under {relative_dir}/")
    return resolved
