"""Compile declared fixed atlas regions into independent ``AtlasTexture`` files.

The physical atlas and its slot metadata come from ``asset_atlas_assemble``.
This compiler never packs, trims, discovers, or adjusts a region: it selects one
declared region by its logical asset id and serializes that exact rectangle with
an all-zero ``AtlasTexture.margin``.
"""
from __future__ import annotations

import json
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._stable_entry import resolve_res_path
from .contract import CompileRequest, CompilerError, require_text
from .registry import CompilerRegistry, CompilerRoute

COMPILER_ID = "atlas_texture_fixed_slot"
COMPILER_VERSION = 1
METADATA_VERSION = 1

_SPEC_KEYS = {"metadata_path", "logical_asset_id"}
_METADATA_KEYS = {"version", "atlas_path", "regions"}
_REGION_KEYS = {"name", "rect", "pivot", "nine_slice"}
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class AtlasTextureInput:
    """The one declared region a compile request is allowed to serialize."""

    metadata_path: str
    logical_asset_id: str
    atlas_path: str
    region: tuple[int, int, int, int]


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CompilerError(f"{label} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], keys: set[str], label: str) -> None:
    actual = set(value)
    if actual != keys:
        missing = sorted(keys - actual)
        extra = sorted(actual - keys)
        parts: list[str] = []
        if missing:
            parts.append("missing " + ", ".join(missing))
        if extra:
            parts.append("unexpected " + ", ".join(extra))
        raise CompilerError(f"{label} must contain exactly {', '.join(sorted(keys))}; " + "; ".join(parts))


def _rect(value: Any, label: str) -> tuple[int, int, int, int]:
    if not isinstance(value, list) or len(value) != 4:
        raise CompilerError(f"{label} must be [x, y, width, height]")
    x, y, width, height = value
    if type(x) is not int or type(y) is not int or x < 0 or y < 0:
        raise CompilerError(f"{label} x and y must be non-negative integers")
    if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
        raise CompilerError(f"{label} width and height must be positive integers")
    return x, y, width, height


def _validate_pivot(value: Any, label: str) -> None:
    if not isinstance(value, list) or len(value) != 2:
        raise CompilerError(f"{label} must be [x, y]")
    if any(type(component) not in (int, float) or not 0 <= component <= 1 for component in value):
        raise CompilerError(f"{label} values must be numbers from 0 to 1")


def _png_size(path: Path) -> tuple[int, int]:
    """Read a PNG IHDR without adding an image-library dependency to L2."""
    try:
        header = path.read_bytes()[:24]
    except OSError as exc:
        raise CompilerError(f"cannot read atlas PNG {path}: {exc}") from exc
    if len(header) != 24 or header[:8] != _PNG_SIGNATURE or header[12:16] != b"IHDR":
        raise CompilerError(f"source_path is not a PNG with an IHDR header: {path}")
    width, height = struct.unpack(">II", header[16:24])
    if width <= 0 or height <= 0:
        raise CompilerError(f"source_path PNG has invalid dimensions: {path}")
    return width, height


def read_atlas_texture_input(request: Any) -> AtlasTextureInput:
    """Validate the fixed-slot metadata selected by a compiler or L4 request."""
    if request.source_layout_type != "region_atlas":
        raise CompilerError("AtlasTexture compilation requires source_layout_type 'region_atlas'")
    if request.artifact_type != "AtlasTexture":
        raise CompilerError("AtlasTexture compilation requires artifact_type 'AtlasTexture'")
    if not request.artifact_path.endswith(".tres"):
        raise CompilerError("AtlasTexture artifact_path must end in .tres")

    spec = _object(request.spec, "AtlasTexture spec")
    _exact_keys(spec, _SPEC_KEYS, "AtlasTexture spec")
    metadata_path = require_text(spec.get("metadata_path"), "AtlasTexture spec.metadata_path")
    logical_asset_id = require_text(
        spec.get("logical_asset_id"), "AtlasTexture spec.logical_asset_id"
    )
    if (
        logical_asset_id in {".", ".."}
        or logical_asset_id != logical_asset_id.strip()
        or logical_asset_id.endswith(".")
        or any(char in logical_asset_id for char in "\\/:;*?\"<>|")
    ):
        raise CompilerError(
            "AtlasTexture spec.logical_asset_id must be a single safe path segment"
        )
    if not metadata_path.endswith(".json"):
        raise CompilerError("AtlasTexture spec.metadata_path must end in .json")
    artifact_stem = Path(request.artifact_path).stem
    if artifact_stem != logical_asset_id and not artifact_stem.startswith(
        logical_asset_id + ".staging-"
    ):
        raise CompilerError(
            "AtlasTexture artifact_path filename must match spec.logical_asset_id"
        )

    try:
        metadata_file = resolve_res_path(request.project_root, metadata_path, label="AtlasTexture spec.metadata_path")
    except Exception as exc:  # stable-entry error vocabulary belongs behind CompilerError
        raise CompilerError(str(exc)) from exc
    try:
        source_file = resolve_res_path(
            request.project_root, request.source_path, label="source_path"
        )
    except Exception as exc:  # stable-entry error vocabulary belongs behind CompilerError
        raise CompilerError(str(exc)) from exc
    if metadata_file.parent != source_file.parent:
        raise CompilerError("AtlasTexture metadata_path must be beside source_path")
    if not metadata_file.is_file():
        raise CompilerError(f"AtlasTexture metadata_path not found: {metadata_path}")
    try:
        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CompilerError(f"AtlasTexture metadata_path is not valid JSON: {metadata_path}") from exc
    metadata = _object(metadata, "AtlasTexture metadata")
    _exact_keys(metadata, _METADATA_KEYS, "AtlasTexture metadata")
    if type(metadata.get("version")) is not int or metadata["version"] != METADATA_VERSION:
        raise CompilerError(f"AtlasTexture metadata.version must be integer {METADATA_VERSION}")
    atlas_path = require_text(metadata.get("atlas_path"), "AtlasTexture metadata.atlas_path")
    if atlas_path != request.source_path:
        raise CompilerError(
            "AtlasTexture metadata.atlas_path must exactly match source_path; "
            f"got {atlas_path!r} instead of {request.source_path!r}"
        )
    regions = metadata.get("regions")
    if not isinstance(regions, list) or not regions:
        raise CompilerError("AtlasTexture metadata.regions must be a non-empty list")

    selected: tuple[int, int, int, int] | None = None
    names: set[str] = set()
    for index, raw_region in enumerate(regions):
        label = f"AtlasTexture metadata.regions[{index}]"
        region = _object(raw_region, label)
        _exact_keys(region, _REGION_KEYS, label)
        name = require_text(region.get("name"), f"{label}.name")
        if name in names:
            raise CompilerError(f"AtlasTexture metadata has duplicate region name: {name}")
        names.add(name)
        rect = _rect(region.get("rect"), f"{label}.rect")
        _validate_pivot(region.get("pivot"), f"{label}.pivot")
        if region.get("nine_slice") is not None:
            raise CompilerError(f"{label}.nine_slice must be null for AtlasTexture")
        if name == logical_asset_id:
            selected = rect
    if selected is None:
        raise CompilerError(
            f"AtlasTexture metadata declares no region for logical_asset_id {logical_asset_id!r}"
        )

    atlas_width, atlas_height = _png_size(source_file)
    x, y, width, height = selected
    if x + width > atlas_width or y + height > atlas_height:
        raise CompilerError(
            f"AtlasTexture region for {logical_asset_id!r} is outside atlas bounds "
            f"{atlas_width}x{atlas_height}"
        )
    return AtlasTextureInput(
        metadata_path=metadata_path,
        logical_asset_id=logical_asset_id,
        atlas_path=atlas_path,
        region=selected,
    )


def _tres(atlas_path: str, region: tuple[int, int, int, int]) -> str:
    x, y, width, height = region
    escaped_path = atlas_path.replace("\\", "\\\\").replace('"', '\\"')
    return (
        '[gd_resource type="AtlasTexture" load_steps=2 format=3]\n\n'
        f'[ext_resource type="Texture2D" path="{escaped_path}" id="1_atlas"]\n\n'
        '[resource]\n'
        'atlas = ExtResource("1_atlas")\n'
        f"region = Rect2({x}, {y}, {width}, {height})\n"
        "margin = Rect2(0, 0, 0, 0)\n"
    )


def compile_atlas_texture(request: CompileRequest) -> dict[str, Any]:
    """Write one deterministic AtlasTexture resource for one declared region."""
    selected = read_atlas_texture_input(request)
    target = request.artifact_file()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_tres(selected.atlas_path, selected.region), encoding="utf-8", newline="\n")
    except OSError as exc:
        raise CompilerError(f"cannot write AtlasTexture artifact {request.artifact_path}: {exc}") from exc
    return {
        "atlas_path": selected.atlas_path,
        "metadata_path": selected.metadata_path,
        "logical_asset_id": selected.logical_asset_id,
        "region": list(selected.region),
        "margin": [0, 0, 0, 0],
    }


def register_into(registry: CompilerRegistry) -> CompilerRoute:
    """Register the fixed-slot ``region_atlas -> AtlasTexture`` compiler."""
    return registry.register(
        source_layout_type="region_atlas",
        artifact_type="AtlasTexture",
        compiler_id=COMPILER_ID,
        compiler_version=COMPILER_VERSION,
        compiler=compile_atlas_texture,
    )
