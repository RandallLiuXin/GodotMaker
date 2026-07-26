"""Contract tests for the deterministic JSON Theme compiler."""
import json
import struct
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


def test_serializes_stylebox_flat_border_width_to_its_real_edge_properties(tmp_path):
    recipe = _recipe()
    recipe["styleboxes"]["button_normal"]["properties"]["border_width"] = 3
    _write_recipe(tmp_path, recipe)
    _compile(tmp_path)

    text = (tmp_path / "assets/generated/ui-kit/main/main.tres").read_text(encoding="utf-8")
    for edge in ("left", "top", "right", "bottom"):
        assert f"border_width_{edge} = 3" in text
    assert "border_width_top_left" not in text


def test_allows_an_empty_stylebox_without_flat_only_properties(tmp_path):
    recipe = _recipe(
        styleboxes={"focus": {"type": "StyleBoxEmpty", "properties": {}}},
        styles=[{"type": "Button", "name": "focus", "stylebox": "focus"}],
    )
    _write_recipe(tmp_path, recipe)
    _compile(tmp_path)
    text = (tmp_path / "assets/generated/ui-kit/main/main.tres").read_text(encoding="utf-8")
    assert '[sub_resource type="StyleBoxEmpty" id="StyleBox_focus"]' in text


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda recipe: recipe["colors"].__setitem__(0, {"type": "Node", "name": "font_color", "value": "#FFFFFF"}), "ClassDB type"),
        (lambda recipe: recipe["colors"].__setitem__(0, {"type": "Button", "name": "script", "value": "#FFFFFF"}), "allowed colors property"),
        (lambda recipe: recipe["colors"].__setitem__(0, {"type": "Label", "name": "icon_normal_color", "value": "#FFFFFF"}), "allowed colors property for Label"),
        (lambda recipe: recipe["styles"].__setitem__(0, {"type": "Button", "name": "normal", "stylebox": "missing"}), "unknown StyleBox"),
        (lambda recipe: recipe["styleboxes"]["button_normal"].__setitem__("type", "Resource"), "StyleBoxFlat or StyleBoxEmpty"),
        (lambda recipe: recipe["styleboxes"]["button_normal"].update({"type": "StyleBoxEmpty", "properties": {"bg_color": "#FFFFFF"}}), "unsupported StyleBoxEmpty property"),
    ],
)
def test_rejects_untrusted_type_property_and_stylebox_references(tmp_path, mutate, message):
    recipe = _recipe()
    mutate(recipe)
    _write_recipe(tmp_path, recipe)
    with pytest.raises(CompilerError, match=message):
        _compile(tmp_path)


def test_rejects_missing_external_resources(tmp_path):
    recipe = _recipe(fonts=[{"type": "Button", "name": "font", "value": {"type": "FontFile", "path": "res://outside.ttf"}}])
    _write_recipe(tmp_path, recipe)
    with pytest.raises(CompilerError, match="does not exist"):
        _compile(tmp_path)


@pytest.mark.parametrize(
    ("section", "resource_type", "path"),
    [
        ("fonts", "FontFile", "res://fake.ttf"),
        ("icons", "Texture2D", "res://fake.png"),
    ],
)
def test_rejects_wrongly_typed_external_resource_content(tmp_path, section, resource_type, path):
    (tmp_path / path[len("res://"):]).write_bytes(b"not a resource")
    item = {"type": "Button", "name": "font" if section == "fonts" else "icon", "value": {"type": resource_type, "path": path}}
    _write_recipe(tmp_path, _recipe(**{section: [item]}))
    with pytest.raises(CompilerError, match=f"not valid {resource_type} content"):
        _compile(tmp_path)


def test_rejects_a_truncated_png_with_valid_magic_and_iend(tmp_path):
    # This satisfies the previous magic-byte-only check but has no IDAT chunk
    # and no valid CRCs, so it cannot be a loadable Texture2D.
    fake_png = (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
        + b"\x00\x00\x00\x00"
        + b"\x00\x00\x00\x00IEND\x00\x00\x00\x00"
    )
    (tmp_path / "fake.png").write_bytes(fake_png)
    recipe = _recipe(icons=[{"type": "Button", "name": "icon", "value": {"type": "Texture2D", "path": "res://fake.png"}}])
    _write_recipe(tmp_path, recipe)
    with pytest.raises(CompilerError, match="not valid Texture2D content"):
        _compile(tmp_path)


def test_rejects_a_minimal_sfnt_without_required_font_tables(tmp_path):
    # The former bounds-only parser accepted this single empty cmap record.
    fake_sfnt = b"\x00\x01\x00\x00" + struct.pack(">HHHH", 1, 0, 0, 0) + b"cmap" + struct.pack(">III", 0, 28, 0)
    (tmp_path / "fake.ttf").write_bytes(fake_sfnt)
    recipe = _recipe(fonts=[{"type": "Button", "name": "font", "value": {"type": "FontFile", "path": "res://fake.ttf"}}])
    _write_recipe(tmp_path, recipe)
    with pytest.raises(CompilerError, match="not valid FontFile content"):
        _compile(tmp_path)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_rejects_non_finite_json_numbers_before_serialization(tmp_path, value):
    recipe = _recipe()
    recipe["styleboxes"]["button_normal"]["properties"]["content_margin"] = value
    _write_recipe(tmp_path, recipe)
    with pytest.raises(CompilerError, match="non-finite JSON number"):
        _compile(tmp_path)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_rejects_non_finite_vector_values_before_serialization(tmp_path, value):
    recipe = _recipe()
    recipe["styleboxes"]["button_normal"]["properties"]["shadow_offset"] = [value, 1]
    _write_recipe(tmp_path, recipe)
    with pytest.raises(CompilerError, match="non-finite JSON number"):
        _compile(tmp_path)


def test_registers_only_once_and_is_not_part_of_the_shared_default_registry():
    registry = build_default_registry()
    assert [route.key for route in registry.routes()] == [("single", "Texture2D")]
    theme.register_into(registry)
    with pytest.raises(CompilerError, match="already registered"):
        theme.register_into(registry)
