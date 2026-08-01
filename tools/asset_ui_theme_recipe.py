#!/usr/bin/env python3
"""Build a complete flat-first Godot Theme recipe for ui-kit."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


class UIThemeRecipeError(Exception):
    """Raised when a complete ui-kit Theme recipe cannot be derived."""


_ASSET_ID = re.compile(r"^[A-Za-z0-9_-]+$")
_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?$")
UI_THEME_TOKENS = (
    "text", "text_muted", "text_outline", "surface", "surface_raised", "input",
    "primary", "secondary", "danger", "success", "border", "focus", "selection",
    "shadow",
)
UI_GEOMETRY_TOKENS = (
    "corner_radius_small", "corner_radius_medium", "corner_radius_large",
    "border_width", "content_margin", "shadow_size", "shadow_offset", "font_size",
)
UI_TEXTURE_STYLEBOXES = (
    "button_normal", "button_hover", "button_pressed", "button_disabled",
    "primary_normal", "primary_hover", "primary_pressed", "primary_disabled",
    "secondary_normal", "secondary_hover", "secondary_pressed", "secondary_disabled",
    "danger_normal", "danger_hover", "danger_pressed", "danger_disabled",
    "panel_base", "panel_raised", "tab_selected", "tab_hovered", "tab_unselected",
    "tooltip_panel", "popup_menu_panel",
)
UI_ICONS = (
    "icon_left_arrow", "icon_right_arrow", "icon_up_arrow", "icon_down_arrow",
    "icon_back", "icon_close", "icon_confirm", "icon_warning", "icon_information",
    "icon_settings", "icon_add", "icon_remove", "icon_lock", "icon_unlock",
    "icon_checkbox_checked", "icon_checkbox_unchecked", "icon_radio_selected",
    "icon_radio_unselected", "icon_submenu", "icon_status",
    "checkbox_unchecked", "checkbox_checked", "check_button_unchecked",
    "check_button_checked", "hslider_grabber", "hslider_grabber_highlight",
    "hslider_grabber_disabled", "vslider_grabber", "vslider_grabber_highlight",
    "vslider_grabber_disabled", "form_submenu_arrow",
)
UI_STYLEBOXES = UI_TEXTURE_STYLEBOXES
_BUTTON_STATES = ("normal", "hover", "pressed", "disabled", "focus")
_TEXT_THEME_TYPES = (
    "Button", "CheckBox", "CheckButton", "OptionButton", "Label", "LineEdit",
    "TextEdit", "ProgressBar", "RichTextLabel", "TabBar", "TooltipLabel",
)
_INTERACTIVE_TEXT_TYPES = ("Button", "CheckBox", "CheckButton", "OptionButton")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UIThemeRecipeError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise UIThemeRecipeError(f"JSON object required: {path}")
    return value


def theme_tokens(theme_plan: dict[str, Any]) -> dict[str, str]:
    value = theme_plan.get("tokens")
    if not isinstance(value, dict) or set(value) != set(UI_THEME_TOKENS):
        raise UIThemeRecipeError("theme_plan.tokens must declare the complete ui-kit token set")
    if any(not isinstance(value[name], str) or not _COLOR.fullmatch(value[name]) for name in UI_THEME_TOKENS):
        raise UIThemeRecipeError("theme_plan.tokens values must be #RRGGBB or #RRGGBBAA colors")
    return {name: value[name].upper() for name in UI_THEME_TOKENS}


def theme_geometry(theme_plan: dict[str, Any]) -> dict[str, Any]:
    value = theme_plan.get("geometry")
    if not isinstance(value, dict) or set(value) != set(UI_GEOMETRY_TOKENS):
        raise UIThemeRecipeError("theme_plan.geometry must declare the complete ui-kit geometry set")
    result: dict[str, Any] = {}
    for name in UI_GEOMETRY_TOKENS:
        raw = value[name]
        if name == "shadow_offset":
            if not isinstance(raw, list) or len(raw) != 2 or any(type(part) is not int for part in raw):
                raise UIThemeRecipeError("theme_plan.geometry.shadow_offset must be two integers")
            result[name] = list(raw)
        elif type(raw) is not int or raw < 0:
            raise UIThemeRecipeError(f"theme_plan.geometry.{name} must be a non-negative integer")
        else:
            result[name] = raw
    if result["font_size"] <= 0:
        raise UIThemeRecipeError("theme_plan.geometry.font_size must be positive")
    if not (
        result["corner_radius_small"]
        <= result["corner_radius_medium"]
        <= result["corner_radius_large"]
    ):
        raise UIThemeRecipeError("theme_plan corner radii must be ordered small to large")
    return result


def _rgba(value: str) -> tuple[int, int, int, int]:
    source = value.removeprefix("#")
    if len(source) == 6:
        source += "FF"
    return tuple(int(source[index:index + 2], 16) for index in range(0, 8, 2))


def _hex(channels: tuple[int, int, int, int]) -> str:
    return "#" + "".join(f"{max(0, min(255, channel)):02X}" for channel in channels)


def _mix(value: str, target: str, amount: float, *, alpha: float | None = None) -> str:
    source_channels = _rgba(value)
    target_channels = _rgba(target)
    channels = tuple(
        round(source + (wanted - source) * amount)
        for source, wanted in zip(source_channels[:3], target_channels[:3])
    )
    final_alpha = round(source_channels[3] * alpha) if alpha is not None else source_channels[3]
    return _hex((*channels, final_alpha))


def state_color(value: str, state: str, *, disabled_target: str = "#808080FF") -> str:
    if state == "hover":
        return _mix(value, "#FFFFFFFF", 0.14)
    if state == "pressed":
        return _mix(value, "#000000FF", 0.18)
    if state == "disabled":
        return _mix(value, disabled_target, 0.45, alpha=0.58)
    return value


def _flat(
    background: str,
    border: str,
    geometry: dict[str, Any],
    *,
    radius: str = "corner_radius_medium",
    margin: int | None = None,
    shadow: bool = False,
    shadow_color: str = "#00000080",
) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "bg_color": background,
        "border_color": border,
        "border_width": geometry["border_width"],
        "corner_radius": geometry[radius],
        "content_margin": geometry["content_margin"] if margin is None else margin,
        "anti_aliasing": True,
    }
    if shadow and geometry["shadow_size"] > 0:
        properties.update({
            "shadow_color": shadow_color,
            "shadow_size": geometry["shadow_size"],
            "shadow_offset": geometry["shadow_offset"],
        })
    return {"type": "StyleBoxFlat", "properties": properties}


def _styles() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for theme_type, prefix in (
        ("Button", "button"), ("PrimaryButton", "primary"),
        ("SecondaryButton", "secondary"), ("DangerButton", "danger"),
    ):
        rows.extend({
            "type": theme_type,
            "name": state,
            "stylebox": "focus_outline" if state == "focus" else f"{prefix}_{state}",
        } for state in _BUTTON_STATES)
    rows.extend([
        {"type": "Panel", "name": "panel", "stylebox": "panel_base"},
        {"type": "PanelContainer", "name": "panel", "stylebox": "panel_raised"},
        {"type": "TooltipSurface", "name": "panel", "stylebox": "tooltip_panel"},
        {"type": "LineEdit", "name": "normal", "stylebox": "line_normal"},
        {"type": "LineEdit", "name": "focus", "stylebox": "line_focus"},
        {"type": "LineEdit", "name": "disabled", "stylebox": "line_disabled"},
        {"type": "LineEdit", "name": "read_only", "stylebox": "line_disabled"},
        {"type": "TextEdit", "name": "normal", "stylebox": "text_normal"},
        {"type": "TextEdit", "name": "focus", "stylebox": "text_focus"},
        {"type": "TextEdit", "name": "disabled", "stylebox": "text_disabled"},
        {"type": "TextEdit", "name": "read_only", "stylebox": "text_disabled"},
        {"type": "ProgressBar", "name": "background", "stylebox": "progress_background"},
        {"type": "ProgressBar", "name": "fill", "stylebox": "progress_fill"},
        {"type": "TabBar", "name": "tab_selected", "stylebox": "tab_selected"},
        {"type": "TabBar", "name": "tab_hovered", "stylebox": "tab_hovered"},
        {"type": "TabBar", "name": "tab_unselected", "stylebox": "tab_unselected"},
        {"type": "TabBar", "name": "tab_focus", "stylebox": "focus_outline"},
        {"type": "TabContainer", "name": "tab_selected", "stylebox": "tab_selected"},
        {"type": "TabContainer", "name": "tab_hovered", "stylebox": "tab_hovered"},
        {"type": "TabContainer", "name": "tab_unselected", "stylebox": "tab_unselected"},
        {"type": "TabContainer", "name": "tab_focus", "stylebox": "focus_outline"},
        {"type": "TabContainer", "name": "panel", "stylebox": "panel_base"},
    ])
    for theme_type in ("CheckBox", "CheckButton"):
        rows.extend({
            "type": theme_type,
            "name": state,
            "stylebox": "focus_outline" if state == "focus" else "empty_control",
        } for state in _BUTTON_STATES)
    rows.extend({
        "type": "OptionButton", "name": state,
        "stylebox": "focus_outline" if state == "focus" else f"option_button_{state}",
    } for state in _BUTTON_STATES)
    for theme_type, prefix in (("HSlider", "hslider"), ("VSlider", "vslider")):
        rows.extend([
            {"type": theme_type, "name": "slider", "stylebox": f"{prefix}_track"},
            {"type": theme_type, "name": "grabber_area", "stylebox": f"{prefix}_fill"},
            {"type": theme_type, "name": "grabber_area_highlight", "stylebox": f"{prefix}_fill_highlight"},
        ])
    for theme_type, prefix in (("HScrollBar", "hscrollbar"), ("VScrollBar", "vscrollbar")):
        rows.extend([
            {"type": theme_type, "name": "scroll", "stylebox": f"{prefix}_track"},
            {"type": theme_type, "name": "scroll_focus", "stylebox": f"{prefix}_track"},
            {"type": theme_type, "name": "grabber", "stylebox": f"{prefix}_grabber"},
            {"type": theme_type, "name": "grabber_highlight", "stylebox": f"{prefix}_grabber_highlight"},
            {"type": theme_type, "name": "grabber_pressed", "stylebox": f"{prefix}_grabber_pressed"},
        ])
    rows.extend([
        {"type": "PopupMenu", "name": "panel", "stylebox": "popup_menu_panel"},
        {"type": "PopupMenu", "name": "panel_disabled", "stylebox": "popup_menu_disabled"},
        {"type": "PopupMenu", "name": "hover", "stylebox": "popup_menu_hover"},
        {"type": "PopupMenu", "name": "separator", "stylebox": "popup_menu_separator"},
    ])
    return rows


def _icons(asset_root: str) -> list[dict[str, Any]]:
    path = {name: {"type": "AtlasTexture", "path": f"{asset_root}/{name}.tres"} for name in UI_ICONS}
    return [
        {"type": "CheckBox", "name": "checked", "value": path["checkbox_checked"]},
        {"type": "CheckBox", "name": "unchecked", "value": path["checkbox_unchecked"]},
        {"type": "CheckButton", "name": "checked", "value": path["check_button_checked"]},
        {"type": "CheckButton", "name": "unchecked", "value": path["check_button_unchecked"]},
        {"type": "HSlider", "name": "grabber", "value": path["hslider_grabber"]},
        {"type": "HSlider", "name": "grabber_highlight", "value": path["hslider_grabber_highlight"]},
        {"type": "HSlider", "name": "grabber_disabled", "value": path["hslider_grabber_disabled"]},
        {"type": "VSlider", "name": "grabber", "value": path["vslider_grabber"]},
        {"type": "VSlider", "name": "grabber_highlight", "value": path["vslider_grabber_highlight"]},
        {"type": "VSlider", "name": "grabber_disabled", "value": path["vslider_grabber_disabled"]},
        {"type": "OptionButton", "name": "arrow", "value": path["form_submenu_arrow"]},
        {"type": "TabBar", "name": "increment", "value": path["icon_right_arrow"]},
        {"type": "TabBar", "name": "decrement", "value": path["icon_left_arrow"]},
        {"type": "PopupMenu", "name": "checked", "value": path["icon_checkbox_checked"]},
        {"type": "PopupMenu", "name": "unchecked", "value": path["icon_checkbox_unchecked"]},
        {"type": "PopupMenu", "name": "radio_checked", "value": path["icon_radio_selected"]},
        {"type": "PopupMenu", "name": "radio_unchecked", "value": path["icon_radio_unselected"]},
        {"type": "PopupMenu", "name": "submenu", "value": path["form_submenu_arrow"]},
        {"type": "PopupMenu", "name": "submenu_mirrored", "value": path["form_submenu_arrow"]},
    ]


def build_theme_recipe(theme_plan: dict[str, Any], *, asset_id: str) -> dict[str, Any]:
    if not _ASSET_ID.fullmatch(asset_id):
        raise UIThemeRecipeError("asset_id must use only letters, digits, underscores, and hyphens")
    tokens = theme_tokens(theme_plan)
    geometry = theme_geometry(theme_plan)
    asset_root = f"res://assets/generated/ui-kit/{asset_id}"
    text_hover = state_color(tokens["text"], "hover")
    text_pressed = state_color(tokens["text"], "pressed")
    text_disabled = state_color(tokens["text_muted"], "disabled")
    colors = []
    for theme_type in _TEXT_THEME_TYPES:
        colors.extend([
            {"type": theme_type, "name": "font_color", "value": tokens["text"]},
            {"type": theme_type, "name": "font_outline_color", "value": tokens["text_outline"]},
        ])
    for theme_type in _INTERACTIVE_TEXT_TYPES:
        colors.extend([
            {"type": theme_type, "name": "font_hover_color", "value": text_hover},
            {"type": theme_type, "name": "font_pressed_color", "value": text_pressed},
            {"type": theme_type, "name": "font_disabled_color", "value": text_disabled},
            {"type": theme_type, "name": "font_focus_color", "value": tokens["focus"]},
        ])
    colors.extend([
        {"type": "LineEdit", "name": "font_placeholder_color", "value": tokens["text_muted"]},
        {"type": "LineEdit", "name": "selection_color", "value": tokens["selection"]},
        {"type": "TextEdit", "name": "selection_color", "value": tokens["selection"]},
    ])

    flat_boxes = {
        "empty_control": {"type": "StyleBoxEmpty", "properties": {"content_margin": 0}},
        "focus_outline": {
            "type": "StyleBoxFlat",
            "properties": {
                "bg_color": "#00000000", "border_color": tokens["focus"],
                "border_width": max(2, geometry["border_width"]),
                "corner_radius": geometry["corner_radius_medium"], "content_margin": 2,
                "anti_aliasing": True,
            },
        },
        "line_normal": _flat(tokens["input"], tokens["border"], geometry),
        "line_focus": _flat(tokens["input"], tokens["focus"], geometry, shadow=True, shadow_color=tokens["shadow"]),
        "line_disabled": _flat(state_color(tokens["input"], "disabled"), state_color(tokens["border"], "disabled"), geometry),
        "text_normal": _flat(tokens["input"], tokens["border"], geometry, radius="corner_radius_large"),
        "text_focus": _flat(tokens["input"], tokens["focus"], geometry, radius="corner_radius_large", shadow=True, shadow_color=tokens["shadow"]),
        "text_disabled": _flat(state_color(tokens["input"], "disabled"), state_color(tokens["border"], "disabled"), geometry, radius="corner_radius_large"),
        "progress_background": _flat(tokens["surface"], tokens["border"], geometry, radius="corner_radius_small", margin=0),
        "progress_fill": _flat(tokens["success"], tokens["success"], geometry, radius="corner_radius_small", margin=0),
        "popup_menu_hover": _flat(state_color(tokens["primary"], "hover"), tokens["focus"], geometry, margin=geometry["content_margin"] // 2),
        "popup_menu_disabled": _flat(state_color(tokens["surface"], "disabled"), state_color(tokens["border"], "disabled"), geometry, radius="corner_radius_large"),
        "popup_menu_separator": _flat(tokens["border"], tokens["border"], geometry, radius="corner_radius_small", margin=2),
    }
    slider_margin = max(6, geometry["border_width"] * 2)
    for prefix in ("hslider", "vslider"):
        flat_boxes[f"{prefix}_track"] = _flat(tokens["input"], tokens["border"], geometry, radius="corner_radius_small", margin=slider_margin)
        flat_boxes[f"{prefix}_fill"] = _flat(tokens["primary"], tokens["primary"], geometry, radius="corner_radius_small", margin=slider_margin)
        flat_boxes[f"{prefix}_fill_highlight"] = _flat(state_color(tokens["primary"], "hover"), tokens["focus"], geometry, radius="corner_radius_small", margin=slider_margin)
    for prefix in ("hscrollbar", "vscrollbar"):
        flat_boxes[f"{prefix}_track"] = _flat(tokens["surface"], tokens["border"], geometry, radius="corner_radius_small", margin=0)
        flat_boxes[f"{prefix}_grabber"] = _flat(tokens["secondary"], tokens["border"], geometry, radius="corner_radius_small", margin=0)
        flat_boxes[f"{prefix}_grabber_highlight"] = _flat(state_color(tokens["secondary"], "hover"), tokens["focus"], geometry, radius="corner_radius_small", margin=0)
        flat_boxes[f"{prefix}_grabber_pressed"] = _flat(state_color(tokens["secondary"], "pressed"), tokens["border"], geometry, radius="corner_radius_small", margin=0)
    for state in ("normal", "hover", "pressed", "disabled"):
        flat_boxes[f"option_button_{state}"] = _flat(
            state_color(tokens["surface_raised"], state),
            state_color(tokens["border"], state),
            geometry,
            shadow=state in {"normal", "hover"},
            shadow_color=tokens["shadow"],
        )

    return {
        "version": 1,
        "colors": colors,
        "font_sizes": [
            {"type": theme_type, "name": "font_size", "value": geometry["font_size"]}
            for theme_type in _TEXT_THEME_TYPES
        ],
        "constants": [
            *[{"type": theme_type, "name": "outline_size", "value": 1} for theme_type in _TEXT_THEME_TYPES],
            *[{"type": theme_type, "name": "h_separation", "value": max(4, geometry["content_margin"] // 2)} for theme_type in _INTERACTIVE_TEXT_TYPES],
        ],
        "fonts": [],
        "icons": _icons(asset_root),
        "styleboxes": {
            **flat_boxes,
            **{
                name: {"type": "StyleBoxTexture", "properties": {"path": f"{asset_root}/{name}.tres"}}
                for name in UI_TEXTURE_STYLEBOXES
            },
        },
        "styles": _styles(),
        "variations": [
            {"name": "PrimaryButton", "base_type": "Button"},
            {"name": "SecondaryButton", "base_type": "Button"},
            {"name": "DangerButton", "base_type": "Button"},
            {"name": "TooltipSurface", "base_type": "Panel"},
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--theme-plan", required=True)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        recipe = build_theme_recipe(_read_json(Path(args.theme_plan)), asset_id=args.asset_id)
    except UIThemeRecipeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(recipe, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "path": args.out,
        "texture_styleboxes": len(UI_TEXTURE_STYLEBOXES),
        "icons": len(UI_ICONS),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
