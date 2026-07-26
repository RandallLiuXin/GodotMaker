"""Compile a closed JSON UI recipe into a deterministic Godot ``Theme``.

The recipe is deliberately data, not a fragment of a ``.tres`` file.  In
particular, it cannot name arbitrary Godot classes or set arbitrary properties:
the compiler owns the small allow-lists below and serializes the corresponding
Theme API fields itself.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .contract import CompileRequest, CompilerError
from .registry import CompilerRegistry, CompilerRoute

COMPILER_ID = "theme_recipe"
COMPILER_VERSION = 1
STRUCTURE_VALIDATOR_ID = "theme_recipe_structure"
THEME_CHECKS = ("theme",)

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?$")
_RES_PATH = re.compile(r"^res://(?!.*(?:^|/)\.\.?/)[^\s]+$")
_THEME_TYPES = frozenset(
    {
        "Button", "CheckBox", "CheckButton", "Label", "LineEdit",
        "OptionButton", "Panel", "PanelContainer", "ProgressBar",
        "RichTextLabel", "TabBar", "TabContainer", "TextEdit", "TooltipLabel",
    }
)
_PROPERTY_NAMES = {
    "colors": frozenset({
        "font_color", "font_hover_color", "font_pressed_color", "font_disabled_color",
        "font_outline_color", "font_shadow_color", "icon_normal_color",
        "icon_hover_color", "icon_pressed_color", "icon_focus_color",
        "icon_hover_pressed_color", "caret_color", "selection_color",
        "font_placeholder_color", "font_selected_color", "font_uneditable_color",
    }),
    "font_sizes": frozenset({"font_size"}),
    "constants": frozenset({
        "outline_size", "shadow_outline_size", "shadow_offset_x", "shadow_offset_y",
        "h_separation", "v_separation", "icon_max_width", "line_spacing",
    }),
    "fonts": frozenset({"font", "bold_font", "italics_font", "bold_italics_font"}),
    "icons": frozenset({"icon", "checked", "unchecked", "arrow", "increment", "decrement"}),
    "styles": frozenset({
        "normal", "hover", "pressed", "disabled", "focus", "read_only",
        "panel", "background", "fill", "tab_selected", "tab_unselected",
    }),
}
_BUTTON_TYPES = frozenset({"Button", "CheckBox", "CheckButton", "OptionButton"})
_TEXT_TYPES = frozenset({"Button", "CheckBox", "CheckButton", "Label", "LineEdit", "OptionButton", "ProgressBar", "RichTextLabel", "TabBar", "TextEdit", "TooltipLabel"})


def _property_allowed(section: str, theme_type: str, name: str, variation_bases: Mapping[str, str]) -> bool:
    """Check the exact Theme item family for the control class (or variation)."""
    base_type = variation_bases.get(theme_type, theme_type)
    if name not in _PROPERTY_NAMES[section]:
        return False
    if section == "colors":
        if name.startswith("icon_"):
            return base_type in _BUTTON_TYPES
        if name in {"caret_color", "selection_color", "font_placeholder_color", "font_selected_color", "font_uneditable_color"}:
            return base_type in {"LineEdit", "TextEdit"}
        return base_type in _TEXT_TYPES
    if section in {"font_sizes", "fonts"}:
        return base_type in _TEXT_TYPES
    if section == "icons":
        return base_type in _BUTTON_TYPES or (base_type == "TabBar" and name in {"increment", "decrement"})
    if section == "constants":
        if name in {"icon_max_width", "h_separation"}:
            return base_type in _BUTTON_TYPES
        if name == "line_spacing":
            return base_type in {"Label", "RichTextLabel", "TextEdit"}
        return base_type in _TEXT_TYPES
    if section == "styles":
        if name in {"normal", "hover", "pressed", "disabled", "focus"}:
            return base_type in _BUTTON_TYPES or base_type in {"LineEdit", "TextEdit"}
        if name == "read_only":
            return base_type in {"LineEdit", "TextEdit"}
        if name == "panel":
            return base_type in {"Panel", "PanelContainer"}
        if name in {"background", "fill"}:
            return base_type == "ProgressBar"
        return base_type in {"TabBar", "TabContainer"}
    return False
_RESOURCE_EXTENSIONS = {
    "FontFile": frozenset({".ttf", ".otf", ".woff", ".woff2"}),
    "Texture2D": frozenset({".png", ".webp", ".jpg", ".jpeg", ".svg"}),
}
_STYLEBOX_PROPERTIES = frozenset({
    "bg_color", "border_color", "corner_radius", "border_width", "content_margin",
    "expand_margin", "shadow_color", "shadow_size", "shadow_offset", "anti_aliasing",
})


def _fail(message: str) -> None:
    raise CompilerError(f"theme recipe: {message}")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"{label} must be an object")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(f"{label} must be an array")
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        _fail(f"{label} must be an ASCII identifier")
    return value


def _theme_type(value: Any, label: str, *, variations: set[str]) -> str:
    theme_type = _identifier(value, label)
    if theme_type not in _THEME_TYPES and theme_type not in variations:
        _fail(f"{label} is not an allowed Theme ClassDB type or declared variation: {theme_type}")
    return theme_type


def _color(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _COLOR.fullmatch(value):
        _fail(f"{label} must be #RRGGBB or #RRGGBBAA")
    hex_value = value[1:]
    channels = [int(hex_value[index:index + 2], 16) / 255 for index in range(0, 6, 2)]
    channels.append(int(hex_value[6:8], 16) / 255 if len(hex_value) == 8 else 1.0)
    return "Color(" + ", ".join(f"{channel:.6g}" for channel in channels) + ")"


def _number(value: Any, label: str, *, minimum: float = 0, integer: bool = False) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < minimum:
        _fail(f"{label} must be a {'non-negative ' if minimum == 0 else ''}number")
    if integer and (type(value) is not int or value < minimum):
        _fail(f"{label} must be a non-negative integer")
    return value


def _vector2(value: Any, label: str) -> str:
    values = _list(value, label)
    if len(values) != 2:
        _fail(f"{label} must contain exactly two numbers")
    return "Vector2(" + ", ".join(str(_number(part, label)) for part in values) + ")"


def _resource(value: Any, label: str, *, expected_type: str, root: Path) -> tuple[str, str]:
    item = _mapping(value, label)
    if set(item) != {"type", "path"} or item.get("type") != expected_type:
        _fail(f"{label} must have exactly type {expected_type!r} and path")
    path = item.get("path")
    if not isinstance(path, str) or not _RES_PATH.fullmatch(path):
        _fail(f"{label}.path must be a safe res:// path")
    suffix = Path(path).suffix.lower()
    if suffix not in _RESOURCE_EXTENSIONS[expected_type]:
        _fail(f"{label}.path is not a supported {expected_type} resource")
    file_path = root / path[len("res://"):]
    if not file_path.is_file():
        _fail(f"{label}.path does not exist: {path}")
    return path, expected_type


def _item_rows(recipe: Mapping[str, Any], section: str, variations: set[str], variation_bases: Mapping[str, str], root: Path) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for index, raw in enumerate(_list(recipe[section], section)):
        item = _mapping(raw, f"{section}[{index}]")
        if set(item) != {"type", "name", "value"}:
            _fail(f"{section}[{index}] must contain exactly type, name, value")
        theme_type = _theme_type(item["type"], f"{section}[{index}].type", variations=variations)
        name = _identifier(item["name"], f"{section}[{index}].name")
        if not _property_allowed(section, theme_type, name, variation_bases):
            _fail(f"{section}[{index}].name is not an allowed {section} property for {theme_type}: {name}")
        value = item["value"]
        if section == "colors":
            encoded = _color(value, f"{section}[{index}].value")
        elif section == "font_sizes":
            encoded = str(_number(value, f"{section}[{index}].value", minimum=1, integer=True))
        elif section == "constants":
            encoded = str(_number(value, f"{section}[{index}].value", integer=True))
        elif section == "fonts":
            path, _ = _resource(value, f"{section}[{index}].value", expected_type="FontFile", root=root)
            encoded = f'ExtResource("Font_{index}")'
        elif section == "icons":
            path, _ = _resource(value, f"{section}[{index}].value", expected_type="Texture2D", root=root)
            encoded = f'ExtResource("Icon_{index}")'
        else:
            encoded = _identifier(value, f"{section}[{index}].value")
        rows.append((theme_type, name, encoded))
    if len({(kind, name) for kind, name, _ in rows}) != len(rows):
        _fail(f"{section} contains a duplicate Theme item")
    return rows


def _styleboxes(recipe: Mapping[str, Any]) -> tuple[dict[str, list[str]], dict[str, str]]:
    result: dict[str, list[str]] = {}
    subresources: dict[str, str] = {}
    raw_boxes = _mapping(recipe["styleboxes"], "styleboxes")
    for box_id in sorted(raw_boxes):
        _identifier(box_id, f"styleboxes.{box_id}")
        box = _mapping(raw_boxes[box_id], f"styleboxes.{box_id}")
        if set(box) != {"type", "properties"} or box["type"] not in {"StyleBoxFlat", "StyleBoxEmpty"}:
            _fail(f"styleboxes.{box_id} must declare StyleBoxFlat or StyleBoxEmpty with properties")
        properties = _mapping(box["properties"], f"styleboxes.{box_id}.properties")
        if not properties and box["type"] == "StyleBoxFlat":
            _fail(f"styleboxes.{box_id}.properties may not be empty for StyleBoxFlat")
        lines: list[str] = []
        for name in sorted(properties):
            if name not in _STYLEBOX_PROPERTIES:
                _fail(f"styleboxes.{box_id}.properties has unsupported StyleBox property: {name}")
            value = properties[name]
            if name in {"bg_color", "border_color", "shadow_color"}:
                lines.append(f"{name} = {_color(value, f'styleboxes.{box_id}.{name}')}")
            elif name in {"corner_radius", "border_width"}:
                number = _number(value, f"styleboxes.{box_id}.{name}", integer=True)
                for edge in ("top_left", "top_right", "bottom_right", "bottom_left"):
                    lines.append(f"{name}_{edge} = {number}")
            elif name in {"content_margin", "expand_margin"}:
                number = _number(value, f"styleboxes.{box_id}.{name}")
                for edge in ("left", "top", "right", "bottom"):
                    lines.append(f"{name}_{edge} = {number}")
            elif name == "shadow_size":
                lines.append(f"shadow_size = {_number(value, f'styleboxes.{box_id}.{name}', integer=True)}")
            elif name == "shadow_offset":
                lines.append(f"shadow_offset = {_vector2(value, f'styleboxes.{box_id}.{name}')}")
            else:
                if type(value) is not bool:
                    _fail(f"styleboxes.{box_id}.anti_aliasing must be a bool")
                lines.append(f"anti_aliasing = {'true' if value else 'false'}")
        result[box_id] = lines
        subresources[box_id] = box["type"]
    return result, subresources


def compile_theme(request: CompileRequest) -> dict[str, Any]:
    """Validate ``theme_recipe`` JSON and write its canonical ``Theme`` resource."""
    if request.source_layout_type != "theme_recipe" or request.artifact_type != "Theme":
        _fail("only compiles theme_recipe -> Theme")
    if Path(request.source_path).suffix.lower() != ".json":
        _fail("source_path must name a JSON theme recipe")
    try:
        recipe = json.loads(request.source_file().read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _fail(f"cannot read valid JSON from {request.source_path}: {exc}")
    recipe = _mapping(recipe, "root")
    required = {"version", "colors", "font_sizes", "constants", "fonts", "icons", "styleboxes", "styles", "variations"}
    if set(recipe) != required or recipe.get("version") != 1:
        _fail("root must contain exactly version 1 and the declared Theme sections")

    variations_raw = _list(recipe["variations"], "variations")
    variation_names = {_identifier(_mapping(item, f"variations[{index}]").get("name"), f"variations[{index}].name") for index, item in enumerate(variations_raw)}
    variations: list[tuple[str, str]] = []
    for index, raw in enumerate(variations_raw):
        item = _mapping(raw, f"variations[{index}]")
        if set(item) != {"name", "base_type"}:
            _fail(f"variations[{index}] must contain exactly name and base_type")
        name = _identifier(item["name"], f"variations[{index}].name")
        base = _theme_type(item["base_type"], f"variations[{index}].base_type", variations=set())
        variations.append((name, base))
    if len(variation_names) != len(variations):
        _fail("variations contains duplicate names")
    variation_bases = dict(variations)

    root = request.project_root
    sections = {section: _item_rows(recipe, section, variation_names, variation_bases, root) for section in ("colors", "font_sizes", "constants", "fonts", "icons")}
    boxes, box_types = _styleboxes(recipe)
    styles: list[tuple[str, str, str]] = []
    for index, raw in enumerate(_list(recipe["styles"], "styles")):
        item = _mapping(raw, f"styles[{index}]")
        if set(item) != {"type", "name", "stylebox"}:
            _fail(f"styles[{index}] must contain exactly type, name, stylebox")
        theme_type = _theme_type(item["type"], f"styles[{index}].type", variations=variation_names)
        name = _identifier(item["name"], f"styles[{index}].name")
        box = _identifier(item["stylebox"], f"styles[{index}].stylebox")
        if not _property_allowed("styles", theme_type, name, variation_bases) or box not in box_types:
            _fail(f"styles[{index}] has an unsupported property or unknown StyleBox reference")
        styles.append((theme_type, name, box))
    if len({(kind, name) for kind, name, _ in styles}) != len(styles):
        _fail("styles contains a duplicate Theme item")
    if not variations or not any(sections.values()) and not styles:
        _fail("recipe must declare at least one variation and one Theme item")

    external: list[tuple[str, str, str]] = []
    for section, resource_type, prefix in (("fonts", "FontFile", "Font"), ("icons", "Texture2D", "Icon")):
        for index, raw in enumerate(_list(recipe[section], section)):
            path, _ = _resource(_mapping(raw, f"{section}[{index}]")["value"], f"{section}[{index}].value", expected_type=resource_type, root=root)
            external.append((f"{prefix}_{index}", resource_type, path))
    lines = ["[gd_resource type=\"Theme\" load_steps=" + str(1 + len(external) + len(boxes)) + " format=3]", ""]
    for resource_id, resource_type, path in external:
        lines.extend([f'[ext_resource type="{resource_type}" path="{path}" id="{resource_id}"]', ""])
    for box_id in sorted(boxes):
        lines.extend([f'[sub_resource type="{box_types[box_id]}" id="StyleBox_{box_id}"]', *boxes[box_id], ""])
    lines.extend(["[resource]"])
    for name, base in sorted(variations):
        lines.append(f'{name}/variation_base = &"{base}"')
    category = {"colors": "colors", "font_sizes": "font_sizes", "constants": "constants", "fonts": "fonts", "icons": "icons"}
    for section in ("colors", "font_sizes", "constants", "fonts", "icons"):
        for theme_type, name, value in sorted(sections[section]):
            lines.append(f"{theme_type}/{category[section]}/{name} = {value}")
    for theme_type, name, box in sorted(styles):
        lines.append(f'{theme_type}/styles/{name} = SubResource("StyleBox_{box}")')
    target = request.artifact_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return {"variations": [name for name, _ in sorted(variations)], "theme_items": sum(len(items) for items in sections.values()) + len(styles), "styleboxes": sorted(boxes)}


def register_into(registry: CompilerRegistry) -> CompilerRoute:
    return registry.register(source_layout_type="theme_recipe", artifact_type="Theme", compiler_id=COMPILER_ID, compiler_version=COMPILER_VERSION, compiler=compile_theme)


def validate_theme_structure(request: Any) -> dict[str, Any]:
    """Require Godot to report a non-empty Theme with a real type variation."""
    from asset_validation.contract import ValidationError

    structure = request.checked_structure("theme")
    types = structure.get("types")
    if not isinstance(types, Mapping) or not types:
        raise ValidationError("the loaded Theme has no declared type items or variations")
    variations = [
        name for name, facts in types.items()
        if isinstance(facts, Mapping) and isinstance(facts.get("variation_base"), str)
        and facts["variation_base"]
    ]
    if not variations:
        raise ValidationError("the loaded Theme has no type variation")
    declared_items = 0
    for facts in types.values():
        if not isinstance(facts, Mapping):
            raise ValidationError("Godot reported malformed Theme structural facts")
        for category in ("colors", "font_sizes", "constants", "fonts", "icons", "styles"):
            values = facts.get(category)
            if not isinstance(values, list):
                raise ValidationError(f"Godot reported no Theme {category} list")
            declared_items += len(values)
    if declared_items == 0:
        raise ValidationError("the loaded Theme has no declared Theme items")
    return {"types": sorted(types), "variations": sorted(variations), "theme_items": declared_items}


def register_structure_into(structures: Any) -> Any:
    """Register the Theme L4 validator beside this family compiler."""
    return structures.register(
        artifact_type="Theme",
        validator_id=STRUCTURE_VALIDATOR_ID,
        validator=validate_theme_structure,
        checks=THEME_CHECKS,
    )
