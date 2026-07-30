#!/usr/bin/env python3
"""Build deterministic Godot TileSet recipes from supported terrain profiles."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image


class TileSetProfileError(Exception):
    """Raised when an atlas cannot satisfy a fixed TileSet profile."""


@dataclass(frozen=True)
class ProfileTile:
    coords: tuple[int, int]
    peering_bits: tuple[int, ...]


@dataclass(frozen=True)
class TileSetProfile:
    name: str
    terrain_mode: int
    columns: int
    rows: int
    tiles: tuple[ProfileTile, ...]
    reserved_slots: tuple[tuple[int, int], ...]


_CORNERS = (3, 7, 11, 15)
_SIDES = (0, 4, 8, 12)
_DIRECTION_NAMES = {
    0: "right", 3: "bottom_right", 4: "bottom", 7: "bottom_left",
    8: "left", 11: "top_left", 12: "top", 15: "top_right",
}


def _marching_squares_15() -> TileSetProfile:
    """Return the fixed 4x4, 15-piece corner-mask layout.

    Mask zero is the intentionally unused transparent slot at (0, 0).  The
    remaining cells are row-major by their four-corner mask.  This makes the
    guide, Python gate and Godot recipe use one stable layout.
    """
    tiles = tuple(
        ProfileTile(
            coords=(mask % 4, mask // 4),
            peering_bits=tuple(bit for index, bit in enumerate(_CORNERS) if mask & (1 << index)),
        )
        for mask in range(1, 16)
    )
    return TileSetProfile(
        name="marching_squares_15",
        terrain_mode=1,
        columns=4,
        rows=4,
        tiles=tiles,
        reserved_slots=((0, 0),),
    )


def _blob_47() -> TileSetProfile:
    """Return the canonical 47 legal mixed-neighbor masks in an 8x6 atlas.

    A diagonal is legal only when its two adjacent sides are present.  This is
    the usual 47-piece Blob reduction of the 256 mixed-neighbor combinations.
    Slots are ordered deterministically by side mask then legal corner mask;
    slot (7, 5) is intentionally unused.
    """
    adjacent_sides = ((0, 1), (1, 2), (2, 3), (3, 0))
    combinations: list[tuple[int, ...]] = []
    for side_mask in range(16):
        allowed_corners = [
            corner_index
            for corner_index, (first_side, second_side) in enumerate(adjacent_sides)
            if side_mask & (1 << first_side) and side_mask & (1 << second_side)
        ]
        for corner_mask in range(1 << len(allowed_corners)):
            bits = [side for index, side in enumerate(_SIDES) if side_mask & (1 << index)]
            bits.extend(
                _CORNERS[corner_index]
                for local_index, corner_index in enumerate(allowed_corners)
                if corner_mask & (1 << local_index)
            )
            combinations.append(tuple(bits))
    if len(combinations) != 47:  # Defensive guard for the profile definition itself.
        raise AssertionError(f"blob_47 profile must contain 47 masks, got {len(combinations)}")
    return TileSetProfile(
        name="blob_47",
        terrain_mode=0,
        columns=8,
        rows=6,
        tiles=tuple(
            ProfileTile(coords=(index % 8, index // 8), peering_bits=bits)
            for index, bits in enumerate(combinations)
        ),
        reserved_slots=((7, 5),),
    )


_PROFILES = {profile.name: profile for profile in (_marching_squares_15(), _blob_47())}


def profile_names() -> tuple[str, ...]:
    return tuple(_PROFILES)


def get_profile(name: str) -> TileSetProfile:
    try:
        return _PROFILES[name]
    except KeyError as exc:
        raise TileSetProfileError(
            f"unsupported TileSet profile {name!r}; choose one of: {', '.join(profile_names())}"
        ) from exc


def profile_manifest(profile_name: str) -> dict[str, Any]:
    """Return the versioned, provider-visible fixed layout manifest."""
    profile = get_profile(profile_name)
    slots = []
    tiles = {tile.coords: tile for tile in profile.tiles}
    for row in range(profile.rows):
        for column in range(profile.columns):
            coords = (column, row)
            tile = tiles.get(coords)
            if tile is None:
                slots.append({"coords": [column, row], "reserved": True, "label": "reserved_transparent"})
                continue
            directions = [_DIRECTION_NAMES[bit] for bit in tile.peering_bits]
            slots.append({
                "coords": [column, row],
                "reserved": False,
                "label": "terrain_" + ("_".join(directions) if directions else "center"),
                "peering_bits": list(tile.peering_bits),
            })
    return {
        "schema_version": 1,
        "profile": profile.name,
        "grid": {"columns": profile.columns, "rows": profile.rows},
        "terrain_mode": profile.terrain_mode,
        "slots": slots,
    }


def create_profile_guide(profile_name: str, output: Path, *, cell_width: int, cell_height: int) -> dict[str, Any]:
    """Render the profile's exact slot labels into a provider-facing guide."""
    cell_width = _positive_int(cell_width, "cell_width")
    cell_height = _positive_int(cell_height, "cell_height")
    profile = get_profile(profile_name)
    manifest = profile_manifest(profile_name)
    from asset_layout_guide import create_layout_guide  # pylint: disable=import-outside-toplevel

    labels = [slot["label"] for slot in manifest["slots"]]
    create_layout_guide(
        output,
        rows=profile.rows,
        cols=profile.columns,
        cell_width=cell_width,
        cell_height=cell_height,
        labels=labels,
    )
    return manifest


def _positive_int(value: int, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise TileSetProfileError(f"{label} must be a positive integer")
    return value


def _slot_alpha_count(image: Image.Image, left: int, top: int, width: int, height: int) -> int:
    alpha = image.crop((left, top, left + width, top + height)).getchannel("A")
    return int(alpha.getbbox() is not None)


def validate_profile_atlas(
    atlas_path: Path,
    profile_name: str,
    *,
    tile_width: int,
    tile_height: int,
) -> dict[str, Any]:
    """Verify one processed atlas against a fixed profile's physical slots."""
    profile = get_profile(profile_name)
    tile_width = _positive_int(tile_width, "tile_width")
    tile_height = _positive_int(tile_height, "tile_height")
    try:
        with Image.open(atlas_path) as opened:
            image = opened.convert("RGBA")
    except Exception as exc:
        raise TileSetProfileError(f"TileSet atlas is not a readable image: {atlas_path}") from exc

    expected_size = (profile.columns * tile_width, profile.rows * tile_height)
    if image.size != expected_size:
        raise TileSetProfileError(
            f"{profile.name} atlas must be exactly {expected_size[0]}x{expected_size[1]}, got {image.width}x{image.height}"
        )

    missing: list[list[int]] = []
    for tile in profile.tiles:
        left, top = tile.coords[0] * tile_width, tile.coords[1] * tile_height
        if _slot_alpha_count(image, left, top, tile_width, tile_height) == 0:
            missing.append(list(tile.coords))
    if missing:
        raise TileSetProfileError(f"{profile.name} atlas has empty required slots: {missing}")

    occupied_reserved: list[list[int]] = []
    for coords in profile.reserved_slots:
        left, top = coords[0] * tile_width, coords[1] * tile_height
        if _slot_alpha_count(image, left, top, tile_width, tile_height) != 0:
            occupied_reserved.append(list(coords))
    if occupied_reserved:
        raise TileSetProfileError(
            f"{profile.name} atlas has non-transparent reserved slots: {occupied_reserved}"
        )

    return {
        "profile": profile.name,
        "grid": {"columns": profile.columns, "rows": profile.rows},
        "tile_size": [tile_width, tile_height],
        "required_slot_count": len(profile.tiles),
        "reserved_slots": [list(coords) for coords in profile.reserved_slots],
        "atlas": str(atlas_path),
    }


def build_profile_recipe(
    profile_name: str,
    *,
    texture_path: str,
    tile_width: int,
    tile_height: int,
    godot_path: str,
    terrain_name: str,
    terrain_color: list[float] | None = None,
    source_id: int = 0,
    overrides: dict[tuple[int, int], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the complete compiler recipe without asking an agent for bitmasks."""
    profile = get_profile(profile_name)
    tile_width = _positive_int(tile_width, "tile_width")
    tile_height = _positive_int(tile_height, "tile_height")
    if not texture_path.startswith("res://"):
        raise TileSetProfileError("texture_path must be a res:// path")
    if not isinstance(godot_path, str) or not godot_path.strip():
        raise TileSetProfileError("godot_path must be a non-empty string")
    if not isinstance(terrain_name, str) or not terrain_name.strip():
        raise TileSetProfileError("terrain_name must be a non-empty string")
    if type(source_id) is not int or source_id < 0:
        raise TileSetProfileError("source_id must be a non-negative integer")

    overrides = overrides or {}
    profile_coords = {tile.coords for tile in profile.tiles}
    unknown = set(overrides).difference(profile_coords)
    if unknown:
        raise TileSetProfileError(f"overrides reference slots outside {profile.name}: {sorted(unknown)}")
    tiles = []
    for tile in profile.tiles:
        item: dict[str, Any] = {
            "coords": list(tile.coords),
            "terrain_set": 0,
            "terrain": 0,
            "peering_bits": [{"bit": bit, "terrain": 0} for bit in tile.peering_bits],
        }
        item.update(overrides.get(tile.coords, {}))
        tiles.append(item)
    terrain: dict[str, Any] = {"name": terrain_name.strip()}
    if terrain_color is not None:
        terrain["color"] = terrain_color
    return {
        "godot_path": godot_path.strip(),
        "tile_shape": "square",
        "tile_size": [tile_width, tile_height],
        "terrain_sets": [{"mode": profile.terrain_mode, "terrains": [terrain]}],
        "sources": [{
            "id": source_id,
            "texture": texture_path,
            "region_size": [tile_width, tile_height],
            "margins": [0, 0],
            "separation": [0, 0],
            "tiles": tiles,
        }],
    }


def compile_profile_recipe(
    recipe: dict[str, Any],
    *,
    project_root: Path,
    asset_id: str,
    texture_path: str,
    artifact_path: str,
) -> dict[str, Any]:
    """Compile a profile recipe through the existing native TileSet compiler."""
    if not asset_id or not isinstance(asset_id, str):
        raise TileSetProfileError("asset_id must be a non-empty string")
    if not artifact_path.startswith("res://"):
        raise TileSetProfileError("artifact_path must be a res:// path")
    runtime_root = Path(__file__).resolve().parents[1] / "skills" / "assets" / "_shared"
    if not runtime_root.is_dir():
        raise TileSetProfileError(f"asset runtime is missing: {runtime_root}")
    if str(runtime_root) not in sys.path:
        sys.path.append(str(runtime_root))
    from asset_compiler import CompileRequest, CompilerRegistry  # pylint: disable=import-outside-toplevel
    from asset_compiler import tileset as tileset_compiler  # pylint: disable=import-outside-toplevel

    request = CompileRequest(
        production_family="tileset",
        asset_id=asset_id,
        source_layout_type="tile_atlas",
        source_path=texture_path,
        artifact_type="TileSet",
        artifact_path=artifact_path,
        project_root=Path(project_root),
        spec=recipe,
    )
    registry = CompilerRegistry()
    tileset_compiler.register_into(registry)
    return registry.compile(request).godot_artifact.to_dict()


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def _parse_size(raw: str) -> tuple[int, int]:
    try:
        width, height = (int(value) for value in raw.lower().split("x", 1))
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("tile size must be WIDTHxHEIGHT") from exc
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("tile size values must be positive")
    return width, height


def _main() -> int:
    parser = argparse.ArgumentParser(description="Build a deterministic TileSet recipe from a fixed terrain profile")
    parser.add_argument("--profile", choices=profile_names(), required=True)
    parser.add_argument("--atlas", type=Path, help="Processed final atlas PNG")
    parser.add_argument("--texture", help="Matching res:// atlas path")
    parser.add_argument("--tile-size", type=_parse_size)
    parser.add_argument("--godot-path")
    parser.add_argument("--terrain-name")
    parser.add_argument("--recipe-out", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--manifest-out", type=Path)
    parser.add_argument("--guide-out", type=Path)
    parser.add_argument("--guide-cell-size", type=_parse_size, default=(256, 256))
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--asset-id")
    parser.add_argument("--artifact", help="res:// TileSet path to compile after recipe generation")
    arguments = parser.parse_args()
    if arguments.manifest_out:
        _write_json_atomic(arguments.manifest_out, profile_manifest(arguments.profile))
    if arguments.guide_out:
        guide_width, guide_height = arguments.guide_cell_size
        create_profile_guide(arguments.profile, arguments.guide_out, cell_width=guide_width, cell_height=guide_height)
    recipe_values = (arguments.atlas, arguments.texture, arguments.tile_size, arguments.godot_path, arguments.terrain_name, arguments.recipe_out)
    if all(value is None for value in recipe_values):
        if arguments.manifest_out or arguments.guide_out:
            return 0
        parser.error("supply --manifest-out, --guide-out, or all recipe-generation inputs")
    if any(value is None for value in recipe_values):
        parser.error("--atlas, --texture, --tile-size, --godot-path, --terrain-name, and --recipe-out are required together")
    width, height = arguments.tile_size
    compile_values = (arguments.project_root, arguments.asset_id, arguments.artifact)
    if any(value is not None for value in compile_values) and any(value is None for value in compile_values):
        parser.error("--project-root, --asset-id, and --artifact must be supplied together")
    try:
        report = validate_profile_atlas(arguments.atlas, arguments.profile, tile_width=width, tile_height=height)
        recipe = build_profile_recipe(
            arguments.profile,
            texture_path=arguments.texture,
            tile_width=width,
            tile_height=height,
            godot_path=arguments.godot_path,
            terrain_name=arguments.terrain_name,
        )
        _write_json_atomic(arguments.recipe_out, recipe)
        if arguments.artifact:
            report["godot_artifact"] = compile_profile_recipe(
                recipe,
                project_root=arguments.project_root,
                asset_id=arguments.asset_id,
                texture_path=arguments.texture,
                artifact_path=arguments.artifact,
            )
        if arguments.report:
            _write_json_atomic(arguments.report, report)
    except TileSetProfileError as exc:
        print(f"asset_tileset_profile: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
