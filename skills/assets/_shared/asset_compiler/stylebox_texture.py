"""Compile explicit nine-slice recipes into ``StyleBoxTexture`` resources."""
from __future__ import annotations

import math
import re
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._asset_paths import resolve_res_path
from .contract import CompileRequest, CompilerError
from .registry import CompilerRegistry, CompilerRoute

COMPILER_ID = "stylebox_texture_nine_slice"
COMPILER_VERSION = 3

_REQUIRED_SPEC_KEYS = {
    "border", "content_margin", "expand_margin", "axis_stretch", "texture_region",
}
_OPTIONAL_SPEC_KEYS = {"modulate_color"}
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_AXIS_STRETCH = {"stretch": 0, "tile": 1, "tile_fit": 2}
_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?$")


@dataclass(frozen=True)
class StyleBoxTextureInput:
    """The normalized recipe facts represented by one StyleBoxTexture."""

    texture_path: str
    texture_region: tuple[int, int, int, int]
    border: tuple[int, int, int, int]
    content_margin: tuple[float, float, float, float]
    expand_margin: tuple[float, float, float, float]
    axis_stretch: tuple[str, str]
    modulate_color: str


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CompilerError(f"{label} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], keys: set[str], label: str) -> None:
    if set(value) != keys:
        raise CompilerError(f"{label} must contain exactly {', '.join(sorted(keys))}")


def _integer_rect(value: Any, label: str) -> tuple[int, int, int, int]:
    if not isinstance(value, list) or len(value) != 4:
        raise CompilerError(f"{label} must be [x, y, width, height]")
    x, y, width, height = value
    if any(type(component) is not int for component in value):
        raise CompilerError(f"{label} values must be integers")
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise CompilerError(f"{label} needs non-negative x/y and positive width/height")
    return x, y, width, height


def _border(value: Any) -> tuple[int, int, int, int]:
    if not isinstance(value, list) or len(value) != 4:
        raise CompilerError("StyleBoxTexture spec.border must be [left, top, right, bottom]")
    if any(type(component) is not int or component < 0 for component in value):
        raise CompilerError("StyleBoxTexture spec.border values must be non-negative integers")
    return tuple(value)


def _margin_numbers(value: Any, label: str) -> tuple[float, float, float, float]:
    if not isinstance(value, list) or len(value) != 4:
        raise CompilerError(f"StyleBoxTexture spec.{label} must be [left, top, right, bottom]")
    normalized: list[float] = []
    for component in value:
        if type(component) not in (int, float) or isinstance(component, bool):
            raise CompilerError(
                f"StyleBoxTexture spec.{label} values must be finite non-negative numbers"
            )
        number = float(component)
        if not math.isfinite(number) or number < 0:
            raise CompilerError(
                f"StyleBoxTexture spec.{label} values must be finite non-negative numbers"
            )
        normalized.append(number)
    return tuple(normalized)


def _axis_stretch(value: Any) -> tuple[str, str]:
    axis = _object(value, "StyleBoxTexture spec.axis_stretch")
    _exact_keys(axis, {"horizontal", "vertical"}, "StyleBoxTexture spec.axis_stretch")
    horizontal, vertical = axis.get("horizontal"), axis.get("vertical")
    if horizontal not in _AXIS_STRETCH or vertical not in _AXIS_STRETCH:
        allowed = ", ".join(_AXIS_STRETCH)
        raise CompilerError(
            "StyleBoxTexture spec.axis_stretch.horizontal and .vertical must be one of: "
            + allowed
        )
    return horizontal, vertical


def _color(value: Any) -> str:
    if not isinstance(value, str) or not _COLOR.fullmatch(value):
        raise CompilerError("StyleBoxTexture spec.modulate_color must be #RRGGBB or #RRGGBBAA")
    return value.upper() if len(value) == 9 else value.upper() + "FF"


def _godot_color(value: str) -> str:
    channels = [int(value[index:index + 2], 16) / 255 for index in range(1, 9, 2)]
    return "Color(" + ", ".join(f"{channel:.6g}" for channel in channels) + ")"


def _png_size(path: Path) -> tuple[int, int]:
    try:
        header = path.read_bytes()[:24]
    except OSError as exc:
        raise CompilerError(f"cannot read StyleBoxTexture source PNG {path}: {exc}") from exc
    if len(header) != 24 or header[:8] != _PNG_SIGNATURE or header[12:16] != b"IHDR":
        raise CompilerError(f"StyleBoxTexture source_path is not a PNG with an IHDR header: {path}")
    width, height = struct.unpack(">II", header[16:24])
    if width <= 0 or height <= 0:
        raise CompilerError(f"StyleBoxTexture source PNG has invalid dimensions: {path}")
    return width, height


def read_stylebox_texture_input(request: Any) -> StyleBoxTextureInput:
    """Validate the explicit StyleBoxTexture recipe for compilation or L4."""
    if request.source_layout_type not in ("single", "region_atlas"):
        raise CompilerError(
            "StyleBoxTexture compilation requires source_layout_type 'single' or 'region_atlas'"
        )
    if request.artifact_type != "StyleBoxTexture":
        raise CompilerError("StyleBoxTexture compilation requires artifact_type 'StyleBoxTexture'")
    if not isinstance(request.artifact_path, str) or not request.artifact_path.endswith(".tres"):
        raise CompilerError("StyleBoxTexture artifact_path must end in .tres")

    spec = _object(request.spec, "StyleBoxTexture spec")
    actual_keys = set(spec)
    if not _REQUIRED_SPEC_KEYS.issubset(actual_keys) or actual_keys - _REQUIRED_SPEC_KEYS - _OPTIONAL_SPEC_KEYS:
        allowed = sorted(_REQUIRED_SPEC_KEYS | _OPTIONAL_SPEC_KEYS)
        raise CompilerError(f"StyleBoxTexture spec must contain required fields and only: {', '.join(allowed)}")
    texture_region = _integer_rect(spec.get("texture_region"), "StyleBoxTexture spec.texture_region")
    border = _border(spec.get("border"))
    content_margin = _margin_numbers(spec.get("content_margin"), "content_margin")
    expand_margin = _margin_numbers(spec.get("expand_margin"), "expand_margin")
    axis_stretch = _axis_stretch(spec.get("axis_stretch"))
    modulate_color = _color(spec.get("modulate_color", "#FFFFFFFF"))

    try:
        source_file = resolve_res_path(request.project_root, request.source_path, label="source_path")
    except Exception as exc:
        raise CompilerError(str(exc)) from exc
    if source_file.suffix.lower() != ".png":
        raise CompilerError("StyleBoxTexture source_path must end in .png")
    image_width, image_height = _png_size(source_file)
    x, y, width, height = texture_region
    if x + width > image_width or y + height > image_height:
        raise CompilerError(
            "StyleBoxTexture spec.texture_region is outside source PNG bounds "
            f"{image_width}x{image_height}"
        )
    left, top, right, bottom = border
    if left + right >= width or top + bottom >= height:
        raise CompilerError("StyleBoxTexture spec.border leaves no stretchable center in texture_region")
    return StyleBoxTextureInput(
        texture_path=request.source_path,
        texture_region=texture_region,
        border=border,
        content_margin=content_margin,
        expand_margin=expand_margin,
        axis_stretch=axis_stretch,
        modulate_color=modulate_color,
    )


def _escape(path: str) -> str:
    return path.replace("\\", "\\\\").replace('"', '\\"')


def _tres(recipe: StyleBoxTextureInput) -> str:
    x, y, width, height = recipe.texture_region
    left, top, right, bottom = recipe.border
    content_left, content_top, content_right, content_bottom = recipe.content_margin
    expand_left, expand_top, expand_right, expand_bottom = recipe.expand_margin
    horizontal, vertical = recipe.axis_stretch
    return (
        '[gd_resource type="StyleBoxTexture" load_steps=2 format=3]\n\n'
        f'[ext_resource type="Texture2D" path="{_escape(recipe.texture_path)}" id="1_texture"]\n\n'
        "[resource]\n"
        'texture = ExtResource("1_texture")\n'
        f"modulate_color = {_godot_color(recipe.modulate_color)}\n"
        f"region_rect = Rect2({x}, {y}, {width}, {height})\n"
        f"texture_margin_left = {left}\n"
        f"texture_margin_top = {top}\n"
        f"texture_margin_right = {right}\n"
        f"texture_margin_bottom = {bottom}\n"
        f"content_margin_left = {content_left!r}\n"
        f"content_margin_top = {content_top!r}\n"
        f"content_margin_right = {content_right!r}\n"
        f"content_margin_bottom = {content_bottom!r}\n"
        f"expand_margin_left = {expand_left!r}\n"
        f"expand_margin_top = {expand_top!r}\n"
        f"expand_margin_right = {expand_right!r}\n"
        f"expand_margin_bottom = {expand_bottom!r}\n"
        f"axis_stretch_horizontal = {_AXIS_STRETCH[horizontal]}\n"
        f"axis_stretch_vertical = {_AXIS_STRETCH[vertical]}\n"
    )


def compile_stylebox_texture(request: CompileRequest) -> dict[str, Any]:
    """Write one StyleBoxTexture with recipe-owned margins, stretch, and region."""
    recipe = read_stylebox_texture_input(request)
    target = request.artifact_file()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_tres(recipe), encoding="utf-8", newline="\n")
    except OSError as exc:
        raise CompilerError(
            f"cannot write StyleBoxTexture artifact {request.artifact_path}: {exc}"
        ) from exc
    return {
        "texture_path": recipe.texture_path,
        "texture_region": list(recipe.texture_region),
        "border": list(recipe.border),
        "content_margin": list(recipe.content_margin),
        "expand_margin": list(recipe.expand_margin),
        "axis_stretch": {"horizontal": recipe.axis_stretch[0], "vertical": recipe.axis_stretch[1]},
        "modulate_color": recipe.modulate_color,
    }


def register_into(registry: CompilerRegistry) -> tuple[CompilerRoute, CompilerRoute]:
    """Register both legal layout routes for the same explicit recipe compiler."""
    return (
        registry.register(
            source_layout_type="single",
            artifact_type="StyleBoxTexture",
            compiler_id=COMPILER_ID,
            compiler_version=COMPILER_VERSION,
            compiler=compile_stylebox_texture,
        ),
        registry.register(
            source_layout_type="region_atlas",
            artifact_type="StyleBoxTexture",
            compiler_id=COMPILER_ID,
            compiler_version=COMPILER_VERSION,
            compiler=compile_stylebox_texture,
        ),
    )
