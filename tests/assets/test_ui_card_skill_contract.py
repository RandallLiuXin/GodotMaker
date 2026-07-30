"""Executable standalone contracts for ui-kit and card-kit Asset Skills."""
import json
import importlib.util
import struct
import sys
import zlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED = REPO_ROOT / "skills" / "assets" / "_shared"
TOOLS = REPO_ROOT / "tools"
sys.path.insert(0, str(SHARED))
sys.path.insert(0, str(TOOLS))

from asset_ui_card_contract_check import (  # noqa: E402
    UICardContractError,
    check_ui_card_handoff,
    check_ui_card_request,
)
from asset_validation import ProbeReport, ProbeResult  # noqa: E402
from asset_validation.godot_probe import GodotProbe  # noqa: E402
from ui_card_standalone_validation import UICardSkillError, compile_and_validate  # noqa: E402
from asset_compiler import CompileRequest, build_default_registry, theme  # noqa: E402


def _source_plan_tool():
    path = TOOLS / "asset_ui_source_sheet_plan.py"
    spec = importlib.util.spec_from_file_location("asset_ui_source_sheet_plan", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _theme_recipe_tool():
    path = TOOLS / "asset_ui_theme_recipe.py"
    spec = importlib.util.spec_from_file_location("asset_ui_theme_recipe", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _png(width: int, height: int) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    rows = b"".join(b"\x00" + b"\x40\x80\xc0\xff" * width for _ in range(height))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


def _request(family: str) -> dict:
    asset_id = "hud" if family == "ui-kit" else "deck"
    root = f"res://assets/generated/{family}/{asset_id}"
    stylebox = {
        "output_name": "button_normal" if family == "ui-kit" else "rare_normal",
        "state": "normal",
        "source_path": f"{root}/components.png",
        "layout": "region_atlas",
        "texture_region": [0, 0, 16, 16],
        "border": [4, 4, 4, 4],
        "expand_margin": [0, 0, 0, 0],
        "axis_stretch": {"horizontal": "stretch", "vertical": "stretch"},
    }
    spec = {
        "theme": {
            "output_name": "theme",
            "recipe_path": f"{root}/theme_recipe.json",
            "variation": "PrimaryButton" if family == "ui-kit" else "CardButton",
        },
        "required_states": ["normal"],
        "styleboxes": [stylebox],
        "required_regions": ["icon"],
        "atlas_regions": [{
            "output_name": "icon",
            "source_path": f"{root}/components.png",
            "metadata_path": f"{root}/components.json",
            "logical_asset_id": "icon",
        }],
    }
    if family == "card-kit":
        stylebox["frame"] = "rare_card"
        spec["required_frames"] = ["rare_card"]
    else:
        states = ["normal", "hover", "pressed", "disabled", "focus"]
        spec["required_states"] = states
        spec["styleboxes"] = [{
            **stylebox, "output_name": f"style_{index}", "state": states[index % len(states)],
            "source_path": f"{root}/components.png",
        } for index in range(27)]
        spec["required_regions"] = [f"icon_{index}" for index in range(16)]
        spec["atlas_regions"] = [{
            "output_name": f"icon_{index}", "source_path": f"{root}/icons.png",
            "metadata_path": f"{root}/icons.json", "logical_asset_id": f"icon_{index}",
        } for index in range(16)]
    request = {"asset_type": family, "asset_id": asset_id, "brief": "A valid UI recipe.", "spec": spec}
    if family == "ui-kit":
        request["provider"] = "codex"
        request["references"] = [{"role": "style", "path": "references/test-ui.png"}]
    return request


def _result(request: dict) -> dict:
    root = f"res://assets/generated/{request['asset_type']}/{request['asset_id']}"
    boxes = request["spec"]["styleboxes"]
    regions = request["spec"]["atlas_regions"]
    outputs = [
        *[{"role": "runtime", "name": box["output_name"], "path": f"{root}/{box['output_name']}.tres", "godot_type": "StyleBoxTexture"} for box in boxes],
        *[{"role": "runtime", "name": region["output_name"], "path": f"{root}/{region['output_name']}.tres", "godot_type": "AtlasTexture"} for region in regions],
    ]
    sources = [
        {"path": source_path, "layout": "region_atlas"}
        for source_path in sorted(
            {box["source_path"] for box in boxes}
            | {region["source_path"] for region in regions}
        )
    ]
    theme = request["spec"].get("theme")
    if theme is not None:
        outputs.insert(0, {
            "role": "runtime", "name": theme["output_name"],
            "path": f"{root}/{request['asset_id']}_theme.tres", "godot_type": "Theme",
        })
        sources.insert(0, {"path": theme["recipe_path"], "layout": "theme_recipe"})
    return {
        "asset_type": request["asset_type"],
        "outputs": outputs,
        "sources": sources,
        "previews": [],
        "validation": {"passed": False},
    }


def _source_adapter(family: str):
    path = REPO_ROOT / "skills" / "assets" / family / "standalone_validation.py"
    spec = importlib.util.spec_from_file_location(f"{family}_adapter", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_sources(root: Path, request: dict, *, recipe_variation: str | None = None) -> None:
    spec = request["spec"]
    if request["asset_type"] == "ui-kit":
        reference = root / "references/test-ui.png"
        reference.parent.mkdir(parents=True, exist_ok=True)
        reference.write_bytes(_png(1, 1))
    theme = spec.get("theme")
    if theme is not None:
        recipe = {
            "version": 1,
            "colors": [{"type": "Button", "name": "font_color", "value": "#FFFFFFFF"}],
            "font_sizes": [], "constants": [], "fonts": [], "icons": [],
            "styleboxes": {}, "styles": [],
            "variations": [{"name": recipe_variation or theme["variation"], "base_type": "Button"}],
        }
        recipe_file = root / theme["recipe_path"].removeprefix("res://")
        recipe_file.parent.mkdir(parents=True, exist_ok=True)
        recipe_file.write_text(json.dumps(recipe), encoding="utf-8")
    for source_path in {box["source_path"] for box in spec["styleboxes"]} | {region["source_path"] for region in spec["atlas_regions"]}:
        image_file = root / source_path.removeprefix("res://")
        image_file.parent.mkdir(parents=True, exist_ok=True)
        image_file.write_bytes(_png(32, 32))
    region = spec["atlas_regions"][0]
    metadata = {
        "version": 1,
        "atlas_path": region["source_path"],
        "regions": [{"name": item["logical_asset_id"], "rect": [16, 0, 8, 8], "pivot": [0.5, 0.5], "nine_slice": None} for item in spec["atlas_regions"]],
    }
    (root / region["metadata_path"].removeprefix("res://")).write_text(json.dumps(metadata), encoding="utf-8")


def _good_probe(request: dict, result: dict, *, theme_variation: str | None = None):
    box = request["spec"]["styleboxes"][0]
    atlas = request["spec"]["atlas_regions"][0]
    theme = request["spec"].get("theme")
    variation = theme_variation or (theme["variation"] if theme is not None else None)

    def fake_probe(self, project_root, requests):
        resources = []
        for item in requests:
            if item.expected_type == "Theme":
                button = {
                    "variation_base": "", "colors": ["font_color"], "font_sizes": [],
                    "constants": [], "fonts": [], "icons": [], "styles": [],
                    "color_values": {"font_color": [1.0, 1.0, 1.0, 1.0]},
                    "font_size_values": {}, "constant_values": {}, "font_paths": {}, "icon_paths": {},
                }
                structure = {"theme": {"types": {"Button": button, variation: {
                    "variation_base": "Button", "colors": ["font_color"], "font_sizes": [],
                    "constants": [], "fonts": [], "icons": [], "styles": [],
                    "color_values": {"font_color": [1.0, 1.0, 1.0, 1.0]},
                    "font_size_values": {}, "constant_values": {}, "font_paths": {}, "icon_paths": {},
                }}}}
            elif item.expected_type == "StyleBoxTexture":
                structure = {"stylebox_texture": {
                    "has_texture": True, "texture_path": box["source_path"],
                    "texture_region": box["texture_region"], "border": box["border"],
                    "expand_margin": box["expand_margin"], "axis_stretch": [0, 0],
                }}
            else:
                structure = {"atlas_texture": {
                    "has_atlas": True, "atlas_path": atlas["source_path"],
                    "region": [16, 0, 8, 8], "margin": [0, 0, 0, 0],
                }}
            resources.append(ProbeResult(item.res_path, item.expected_type, True, item.expected_type, True, structure=structure))
        return ProbeReport(godot_version="test", resources=tuple(resources))

    return fake_probe


@pytest.mark.parametrize("family", ["ui-kit", "card-kit"])
def test_closed_family_contract_binds_every_declared_output_and_source(family):
    request = _request(family)
    result = _result(request)

    checked = check_ui_card_handoff(request, result)

    assert checked["ok"] is True
    assert checked["asset_type"] == family


def test_ui_contract_rejects_a_missing_requested_hover_state():
    request = _request("ui-kit")
    request["spec"]["required_states"].remove("hover")

    with pytest.raises(UICardContractError, match="required_state"):
        check_ui_card_request(request)


def test_source_sheet_plan_requires_magenta_color_key_and_positive_medium_prompts():
    tool = _source_plan_tool()
    request = _request("ui-kit")
    request["brief"] = "Create a non-pixel-art hand-painted fantasy shrine theme."
    scheme = json.loads((REPO_ROOT / "skills" / "assets" / "ui-kit" / "references" / "source-sheet-scheme.json").read_text(encoding="utf-8"))

    plan = tool.build_source_sheet_plan(request, scheme, rendering_medium="hand-painted fantasy illustration")

    assert plan["scheme"]["background"]["color"] == "#FF00FF"
    assert len(plan["sheets"]) == 3
    assert all("#FF00FF" in sheet["prompt"] for sheet in plan["sheets"])
    assert all("pixel-art" not in sheet["prompt"].lower() and "pixel art" not in sheet["prompt"].lower() for sheet in plan["sheets"])
    assert all(len(sheet["components"]) >= 16 for sheet in plan["sheets"])


def test_ui_theme_recipe_uses_named_stylebox_textures_and_atlas_textures(tmp_path):
    tool = _theme_recipe_tool()
    plan = {"tokens": {
        "text": "#F8F2E8", "text_hover": "#FFFFFF", "text_pressed": "#F0C15A",
        "text_disabled": "#8B8490", "text_outline": "#241B2F",
        "text_placeholder": "#A79FB0", "selection": "#7154C9AA", "focus": "#F0C15A",
    }}
    recipe = tool.build_theme_recipe(plan, asset_id="hud")
    asset_root = tmp_path / "assets/generated/ui-kit/hud"
    asset_root.mkdir(parents=True)
    for name in tool._STYLEBOXES:
        (asset_root / f"{name}.tres").write_text('[gd_resource type="StyleBoxTexture" format=3]\n', encoding="utf-8")
    for name in tool._ICONS:
        (asset_root / f"{name}.tres").write_text('[gd_resource type="AtlasTexture" format=3]\n', encoding="utf-8")
    recipe_path = asset_root / "theme_recipe.json"
    recipe_path.write_text(json.dumps(recipe), encoding="utf-8")
    request = CompileRequest(
        production_family="ui-kit", asset_id="hud", source_layout_type="theme_recipe",
        source_path="res://assets/generated/ui-kit/hud/theme_recipe.json", artifact_type="Theme",
        artifact_path="res://assets/generated/ui-kit/hud/hud_theme.tres", project_root=tmp_path,
        spec={
            "allowed_external_stylebox_paths": [
                f"res://assets/generated/ui-kit/hud/{name}.tres"
                for name in tool._STYLEBOXES
            ],
        },
    )
    registry = build_default_registry()
    theme.register_into(registry)

    registry.compile(request)

    compiled = (asset_root / "hud_theme.tres").read_text(encoding="utf-8")
    assert 'ext_resource type="AtlasTexture"' in compiled
    assert 'PopupMenu/styles/panel_disabled' in compiled
    assert len(recipe["styleboxes"]) == 37


@pytest.mark.parametrize("field", ["references", "provider"])
def test_ui_contract_requires_a_binding_reference_and_provider_pin(field):
    request = _request("ui-kit")
    request.pop(field)

    with pytest.raises(UICardContractError, match="ui-kit"):
        check_ui_card_request(request)


def test_card_contract_rejects_a_missing_requested_frame_and_region():
    request = _request("card-kit")
    request["spec"]["required_frames"].append("portrait")
    request["spec"]["required_regions"] = ["icon", "rarity"]

    with pytest.raises(UICardContractError, match="required_frame"):
        check_ui_card_request(request)


def test_card_contract_rejects_pixel_art_requests():
    request = _request("card-kit")
    request["brief"] = "A pixel-art card frame."

    with pytest.raises(UICardContractError, match="does not support pixel-art"):
        check_ui_card_request(request)


@pytest.mark.parametrize("brief", ["A non-pixel-art card frame.", "A card frame, not pixel art."])
def test_card_contract_allows_explicit_non_pixel_art_requests(brief):
    request = _request("card-kit")
    request["brief"] = brief

    assert check_ui_card_request(request)["ok"] is True


@pytest.mark.parametrize("family", ["ui-kit", "card-kit"])
def test_family_contract_allows_a_declared_resource_bundle_without_theme(tmp_path, monkeypatch, family):
    request = _request(family)
    request["spec"].pop("theme")
    result = _result(request)
    _write_sources(tmp_path, request)
    monkeypatch.setattr(GodotProbe, "probe", _good_probe(request, result))

    validated = compile_and_validate(request, result, project_root=tmp_path, godot_path="godot")

    assert validated["validation"]["levels"] == {
        "L0": True, "L1": True, "L2": True, "L3": True, "L4": True,
    }


@pytest.mark.parametrize("family", ["ui-kit", "card-kit"])
def test_standalone_runner_executes_l0_to_l5_for_every_runtime_output(tmp_path, monkeypatch, family):
    request = _request(family)
    result = _result(request)
    _write_sources(tmp_path, request)
    monkeypatch.setattr(GodotProbe, "probe", _good_probe(request, result))
    monkeypatch.setattr("ui_card_standalone_validation._run_consumer_smoke", lambda *args: None)

    validated = compile_and_validate(request, result, project_root=tmp_path, godot_path="godot")

    assert validated["validation"] == {
        "passed": True,
        "levels": {"L0": True, "L1": True, "L2": True, "L3": True, "L4": True, "L5": True},
    }
    assert all((tmp_path / item["path"].removeprefix("res://")).is_file() for item in result["outputs"])


def test_standalone_runner_maps_missing_source_to_l1(tmp_path):
    request = _request("ui-kit")
    result = _result(request)

    validated = compile_and_validate(request, result, project_root=tmp_path, godot_path="godot")

    assert validated["validation"]["levels"] == {"L0": True, "L1": False, "L2": False, "L3": False, "L4": False, "L5": False}


@pytest.mark.parametrize(("adapter", "other"), [("ui-kit", "card-kit"), ("card-kit", "ui-kit")])
def test_skill_local_ui_card_adapter_rejects_the_other_legal_family(tmp_path, adapter, other):
    with pytest.raises(UICardSkillError, match="L0 standalone contract failed"):
        _source_adapter(adapter).compile_and_validate(
            _request(other), _result(_request(other)), project_root=tmp_path, godot_path="godot"
        )


@pytest.mark.parametrize("adapter", ["ui-kit", "card-kit"])
@pytest.mark.parametrize("invalid_input", ["request", "result"])
def test_skill_local_ui_card_adapter_maps_non_objects_to_l0(tmp_path, adapter, invalid_input):
    request = _request(adapter)
    result = _result(request)
    if invalid_input == "request":
        request = []
    else:
        result = []
    with pytest.raises(UICardSkillError, match="L0 standalone contract failed"):
        _source_adapter(adapter).compile_and_validate(
            request, result, project_root=tmp_path, godot_path="godot"
        )


@pytest.mark.parametrize("family", ["ui-kit", "card-kit"])
def test_theme_runtime_output_requires_the_declared_stable_path(family):
    request = _request(family)
    result = _result(request)
    result["outputs"][0]["path"] = result["outputs"][0]["path"].replace("_theme.tres", ".tres")
    with pytest.raises(UICardContractError, match="theme.output_name"):
        check_ui_card_handoff(request, result)


def test_standalone_runner_maps_invalid_nine_slice_to_l2(tmp_path):
    request = _request("ui-kit")
    request["spec"]["styleboxes"][0]["border"] = [9, 4, 9, 4]
    result = _result(request)
    _write_sources(tmp_path, request)

    validated = compile_and_validate(request, result, project_root=tmp_path, godot_path="godot")

    assert validated["validation"]["levels"] == {"L0": True, "L1": True, "L2": False, "L3": False, "L4": False, "L5": False}, validated["validation"]["notes"]
    assert "border exceeds" in validated["validation"]["notes"]


def test_standalone_runner_maps_missing_declared_atlas_region_to_l2(tmp_path):
    request = _request("card-kit")
    result = _result(request)
    _write_sources(tmp_path, request)
    metadata_path = request["spec"]["atlas_regions"][0]["metadata_path"]
    (tmp_path / metadata_path.removeprefix("res://")).write_text(
        json.dumps({
            "version": 1,
            "atlas_path": request["spec"]["atlas_regions"][0]["source_path"],
            "regions": [{"name": "other", "rect": [16, 0, 8, 8], "pivot": [0.5, 0.5], "nine_slice": None}],
        }),
        encoding="utf-8",
    )

    validated = compile_and_validate(request, result, project_root=tmp_path, godot_path="godot")

    assert validated["validation"]["levels"] == {"L0": True, "L1": True, "L2": False, "L3": False, "L4": False, "L5": False}
    assert "declares no region" in validated["validation"]["notes"]


def test_standalone_runner_rejects_theme_binding_to_an_undeclared_stylebox(tmp_path):
    request = _request("card-kit")
    result = _result(request)
    _write_sources(tmp_path, request)
    root = f"res://assets/generated/card-kit/{request['asset_id']}"
    undeclared_path = f"{root}/leftover.tres"
    (tmp_path / undeclared_path.removeprefix("res://")).write_text(
        '[gd_resource type="StyleBoxTexture" format=3]\n', encoding="utf-8"
    )
    recipe_path = tmp_path / request["spec"]["theme"]["recipe_path"].removeprefix("res://")
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    recipe["styleboxes"] = {
        "leftover": {"type": "StyleBoxTexture", "properties": {"path": undeclared_path}},
    }
    recipe["styles"] = [{"type": "CardButton", "name": "normal", "stylebox": "leftover"}]
    recipe_path.write_text(json.dumps(recipe), encoding="utf-8")

    validated = compile_and_validate(request, result, project_root=tmp_path, godot_path="godot")

    assert validated["validation"]["levels"] == {
        "L0": True, "L1": True, "L2": False, "L3": False, "L4": False,
        "L5": False,
    }
    assert "declared StyleBoxTexture runtime output" in validated["validation"]["notes"]


def test_standalone_runner_loads_a_theme_bound_to_its_declared_stylebox_texture(godot_project, godot_bin):
    request = _request("card-kit")
    result = _result(request)
    _write_sources(godot_project, request)
    stylebox = next(item for item in result["outputs"] if item["godot_type"] == "StyleBoxTexture")
    recipe_path = godot_project / request["spec"]["theme"]["recipe_path"].removeprefix("res://")
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    recipe["styleboxes"] = {
        "rare_normal": {"type": "StyleBoxTexture", "properties": {"path": stylebox["path"]}},
    }
    recipe["styles"] = [{"type": "CardButton", "name": "normal", "stylebox": "rare_normal"}]
    recipe_path.write_text(json.dumps(recipe), encoding="utf-8")

    validated = compile_and_validate(request, result, project_root=godot_project, godot_path=godot_bin)

    assert validated["validation"]["levels"] == {
        "L0": True, "L1": True, "L2": True, "L3": True, "L4": True,
        "L5": True,
    }


def test_standalone_runner_maps_godot_type_failure_to_l3(tmp_path, monkeypatch):
    request = _request("card-kit")
    result = _result(request)
    _write_sources(tmp_path, request)

    def wrong_type(self, project_root, requests):
        return ProbeReport(
            godot_version="test",
            resources=tuple(ProbeResult(item.res_path, item.expected_type, True, "Theme", False, error="wrong type") for item in requests),
        )

    monkeypatch.setattr(GodotProbe, "probe", wrong_type)
    validated = compile_and_validate(request, result, project_root=tmp_path, godot_path="godot")

    assert validated["validation"]["levels"] == {"L0": True, "L1": True, "L2": True, "L3": False, "L4": False, "L5": False}


def test_standalone_runner_maps_structure_failure_to_l4(tmp_path, monkeypatch):
    request = _request("ui-kit")
    result = _result(request)
    _write_sources(tmp_path, request)
    good_probe = _good_probe(request, result)

    def invalid_structure(self, project_root, requests):
        report = good_probe(self, project_root, requests)
        broken = list(report.resources)
        broken[0] = ProbeResult(broken[0].res_path, "Theme", True, "Theme", True, structure={"theme": {"types": {}}})
        return ProbeReport(godot_version="test", resources=tuple(broken))

    monkeypatch.setattr(GodotProbe, "probe", invalid_structure)
    validated = compile_and_validate(request, result, project_root=tmp_path, godot_path="godot")

    assert validated["validation"]["levels"] == {"L0": True, "L1": True, "L2": True, "L3": True, "L4": False, "L5": False}


def test_standalone_runner_maps_requested_theme_variation_mismatch_to_l4(tmp_path, monkeypatch):
    request = _request("ui-kit")
    result = _result(request)
    _write_sources(tmp_path, request, recipe_variation="OtherVariation")
    monkeypatch.setattr(GodotProbe, "probe", _good_probe(request, result, theme_variation="OtherVariation"))

    validated = compile_and_validate(request, result, project_root=tmp_path, godot_path="godot")

    assert validated["validation"]["levels"] == {"L0": True, "L1": True, "L2": True, "L3": True, "L4": False, "L5": False}
    assert "requested variation" in validated["validation"]["notes"]
