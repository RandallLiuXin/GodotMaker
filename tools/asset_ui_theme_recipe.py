#!/usr/bin/env python3
"""Build the fixed ui-kit Theme recipe from visual tokens and named resources.

This tool creates Theme data only. It neither generates nor changes image pixels.
"""
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
_TOKENS = (
    "text", "text_hover", "text_pressed", "text_disabled", "text_outline",
    "text_placeholder", "selection", "focus",
)
_STYLEBOXES = (
    "button_normal", "button_hover", "button_pressed", "button_disabled", "button_focus",
    "primary_normal", "primary_hover", "primary_pressed", "primary_disabled", "primary_focus",
    "secondary_normal", "secondary_hover", "secondary_pressed", "secondary_disabled", "secondary_focus",
    "danger_normal", "danger_hover", "danger_pressed", "danger_disabled", "danger_focus",
    "panel_base", "panel_raised", "line_normal", "line_focus", "line_disabled",
    "text_normal", "text_focus", "text_disabled", "progress_background", "progress_fill",
    "tab_selected", "tab_unselected", "tooltip_panel", "popup_menu_panel",
    "popup_menu_hover", "popup_menu_disabled", "popup_menu_separator",
)
_ICONS = (
    "icon_left_arrow", "icon_right_arrow", "icon_up_arrow", "icon_down_arrow",
    "icon_back", "icon_close", "icon_confirm", "icon_warning", "icon_information",
    "icon_settings", "icon_add", "icon_remove", "icon_lock", "icon_unlock",
    "icon_checkbox_checked", "icon_checkbox_unchecked", "icon_radio_selected",
    "icon_radio_unselected", "icon_submenu", "icon_status",
)
_BUTTON_STATES = ("normal", "hover", "pressed", "disabled", "focus")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UIThemeRecipeError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise UIThemeRecipeError(f"JSON object required: {path}")
    return value


def _tokens(theme_plan: dict[str, Any]) -> dict[str, str]:
    value = theme_plan.get("tokens")
    if not isinstance(value, dict) or set(value) != set(_TOKENS):
        raise UIThemeRecipeError("theme_plan.tokens must declare the complete ui-kit token set")
    if any(not isinstance(value[name], str) or not _COLOR.fullmatch(value[name]) for name in _TOKENS):
        raise UIThemeRecipeError("theme_plan.tokens values must be #RRGGBB or #RRGGBBAA colors")
    return {name: value[name].upper() for name in _TOKENS}


def _styles() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for theme_type, prefix in (("Button", "button"), ("PrimaryButton", "primary"), ("SecondaryButton", "secondary"), ("DangerButton", "danger")):
        rows.extend({"type": theme_type, "name": state, "stylebox": f"{prefix}_{state}"} for state in _BUTTON_STATES)
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
        {"type": "TabBar", "name": "tab_unselected", "stylebox": "tab_unselected"},
        {"type": "TabContainer", "name": "tab_selected", "stylebox": "tab_selected"},
        {"type": "TabContainer", "name": "tab_unselected", "stylebox": "tab_unselected"},
    ])
    for theme_type in ("CheckBox", "CheckButton", "OptionButton"):
        rows.extend({"type": theme_type, "name": state, "stylebox": f"button_{state}"} for state in _BUTTON_STATES)
    for theme_type in ("HSlider", "VSlider"):
        rows.extend([
            {"type": theme_type, "name": "slider", "stylebox": "line_normal"},
            {"type": theme_type, "name": "grabber_area", "stylebox": "secondary_normal"},
            {"type": theme_type, "name": "grabber_area_highlight", "stylebox": "primary_normal"},
        ])
    for theme_type in ("HScrollBar", "VScrollBar"):
        rows.extend([
            {"type": theme_type, "name": "scroll", "stylebox": "line_normal"},
            {"type": theme_type, "name": "scroll_focus", "stylebox": "line_focus"},
            {"type": theme_type, "name": "grabber", "stylebox": "secondary_normal"},
            {"type": theme_type, "name": "grabber_highlight", "stylebox": "primary_normal"},
        ])
    rows.extend([
        {"type": "PopupMenu", "name": "panel", "stylebox": "popup_menu_panel"},
        {"type": "PopupMenu", "name": "panel_disabled", "stylebox": "popup_menu_disabled"},
        {"type": "PopupMenu", "name": "hover", "stylebox": "popup_menu_hover"},
        {"type": "PopupMenu", "name": "separator", "stylebox": "popup_menu_separator"},
    ])
    return rows


def _icons(asset_root: str) -> list[dict[str, Any]]:
    path = {name: {"type": "AtlasTexture", "path": f"{asset_root}/{name}.tres"} for name in _ICONS}
    return [
        {"type": "CheckBox", "name": "checked", "value": path["icon_checkbox_checked"]},
        {"type": "CheckBox", "name": "unchecked", "value": path["icon_checkbox_unchecked"]},
        {"type": "CheckButton", "name": "checked", "value": path["icon_checkbox_checked"]},
        {"type": "CheckButton", "name": "unchecked", "value": path["icon_checkbox_unchecked"]},
        {"type": "OptionButton", "name": "arrow", "value": path["icon_submenu"]},
        {"type": "TabBar", "name": "increment", "value": path["icon_right_arrow"]},
        {"type": "TabBar", "name": "decrement", "value": path["icon_left_arrow"]},
        {"type": "PopupMenu", "name": "checked", "value": path["icon_checkbox_checked"]},
        {"type": "PopupMenu", "name": "unchecked", "value": path["icon_checkbox_unchecked"]},
        {"type": "PopupMenu", "name": "radio_checked", "value": path["icon_radio_selected"]},
        {"type": "PopupMenu", "name": "radio_unchecked", "value": path["icon_radio_unselected"]},
        {"type": "PopupMenu", "name": "submenu", "value": path["icon_submenu"]},
        {"type": "PopupMenu", "name": "submenu_mirrored", "value": path["icon_submenu"]},
    ]


def build_theme_recipe(theme_plan: dict[str, Any], *, asset_id: str) -> dict[str, Any]:
    if not _ASSET_ID.fullmatch(asset_id):
        raise UIThemeRecipeError("asset_id must use only letters, digits, underscores, and hyphens")
    tokens = _tokens(theme_plan)
    asset_root = f"res://assets/generated/ui-kit/{asset_id}"
    colors = []
    for theme_type in ("Button", "LineEdit", "TextEdit", "TooltipLabel"):
        colors.extend([
            {"type": theme_type, "name": "font_color", "value": tokens["text"]},
            {"type": theme_type, "name": "font_outline_color", "value": tokens["text_outline"]},
        ])
    colors.extend([
        {"type": "Button", "name": "font_hover_color", "value": tokens["text_hover"]},
        {"type": "Button", "name": "font_pressed_color", "value": tokens["text_pressed"]},
        {"type": "Button", "name": "font_disabled_color", "value": tokens["text_disabled"]},
        {"type": "Button", "name": "font_focus_color", "value": tokens["focus"]},
        {"type": "LineEdit", "name": "font_placeholder_color", "value": tokens["text_placeholder"]},
        {"type": "LineEdit", "name": "selection_color", "value": tokens["selection"]},
        {"type": "TextEdit", "name": "selection_color", "value": tokens["selection"]},
    ])
    return {
        "version": 1,
        "colors": colors,
        "font_sizes": [{"type": "Button", "name": "font_size", "value": 18}],
        "constants": [
            {"type": "Button", "name": "outline_size", "value": 1},
            {"type": "Button", "name": "h_separation", "value": 8},
        ],
        "fonts": [],
        "icons": _icons(asset_root),
        "styleboxes": {
            name: {
                "type": "StyleBoxTexture",
                "properties": {"path": f"{asset_root}/{name}.tres"},
            }
            for name in _STYLEBOXES
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
    print(json.dumps({"ok": True, "path": args.out, "styleboxes": len(_STYLEBOXES), "icons": len(_ICONS)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
