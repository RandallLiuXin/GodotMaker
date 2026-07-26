"""Contract tests for the deterministic JSON Theme compiler."""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "skills" / "assets" / "_shared"))

from asset_compiler import CompileRequest, CompilerError, build_default_registry, theme  # noqa: E402


def _recipe(**overrides):
    value = {
        "version": 1,
        "colors": [{"type": "Button", "name": "font_color", "value": "#FFFFFF"}],
        "font_sizes": [{"type": "Button", "name": "font_size", "value": 18}],
        "constants": [{"type": "Button", "name": "outline_size", "value": 1}],
        "fonts": [],
        "icons": [],
        "styleboxes": {
            "button_normal": {
                "type": "StyleBoxFlat",
                "properties": {"bg_color": "#102030", "corner_radius": 8},
            }
        },
        "styles": [{"type": "Button", "name": "normal", "stylebox": "button_normal"}],
        "variations": [{"name": "PrimaryButton", "base_type": "Button"}],
    }
    value.update(overrides)
    return value


def _request(root: Path):
    return CompileRequest(
        production_family="ui-kit",
        asset_id="main",
        source_layout_type="theme_recipe",
        source_path="res://assets/generated/ui-kit/main/main.json",
        artifact_type="Theme",
        artifact_path="res://assets/generated/ui-kit/main/main.tres",
        project_root=root,
    )


def _write_recipe(root: Path, recipe):
    path = root / "assets/generated/ui-kit/main/main.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(recipe), encoding="utf-8")


def _compile(root: Path):
    registry = build_default_registry()
    theme.register_into(registry)
    return registry.compile(_request(root))


def test_compiles_a_complete_theme_with_a_variation_deterministically(tmp_path):
    _write_recipe(tmp_path, _recipe())
    first = _compile(tmp_path)
    first_bytes = (tmp_path / "assets/generated/ui-kit/main/main.tres").read_bytes()
    second = _compile(tmp_path)
    assert first.godot_artifact.to_dict() == {"type": "Theme", "path": "res://assets/generated/ui-kit/main/main.tres"}
    assert second.receipt.details == {"variations": ["PrimaryButton"], "theme_items": 4, "styleboxes": ["button_normal"]}
    assert (tmp_path / "assets/generated/ui-kit/main/main.tres").read_bytes() == first_bytes
    text = first_bytes.decode()
    assert 'PrimaryButton/variation_base = &"Button"' in text
    assert "Button/colors/font_color = Color(1, 1, 1, 1)" in text
    assert 'Button/styles/normal = SubResource("StyleBox_button_normal")' in text


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda recipe: recipe["colors"].__setitem__(0, {"type": "Node", "name": "font_color", "value": "#FFFFFF"}), "ClassDB type"),
        (lambda recipe: recipe["colors"].__setitem__(0, {"type": "Button", "name": "script", "value": "#FFFFFF"}), "allowed colors property"),
        (lambda recipe: recipe["colors"].__setitem__(0, {"type": "Label", "name": "icon_normal_color", "value": "#FFFFFF"}), "allowed colors property for Label"),
        (lambda recipe: recipe["styles"].__setitem__(0, {"type": "Button", "name": "normal", "stylebox": "missing"}), "unknown StyleBox"),
        (lambda recipe: recipe["styleboxes"]["button_normal"].__setitem__("type", "Resource"), "StyleBoxFlat or StyleBoxEmpty"),
    ],
)
def test_rejects_untrusted_type_property_and_stylebox_references(tmp_path, mutate, message):
    recipe = _recipe()
    mutate(recipe)
    _write_recipe(tmp_path, recipe)
    with pytest.raises(CompilerError, match=message):
        _compile(tmp_path)


def test_rejects_missing_or_wrongly_typed_external_resources(tmp_path):
    recipe = _recipe(fonts=[{"type": "Button", "name": "font", "value": {"type": "FontFile", "path": "res://outside.ttf"}}])
    _write_recipe(tmp_path, recipe)
    with pytest.raises(CompilerError, match="does not exist"):
        _compile(tmp_path)


def test_registers_only_once_and_is_not_part_of_the_shared_default_registry():
    registry = build_default_registry()
    assert [route.key for route in registry.routes()] == [("single", "Texture2D")]
    theme.register_into(registry)
    with pytest.raises(CompilerError, match="already registered"):
        theme.register_into(registry)
