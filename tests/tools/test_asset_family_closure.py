"""Registration closure for every public family route.

The request/result pair for a registration test is a handoff from that
family's standalone validator.  Fixtures that the validator would reject are
not valid registration fixtures: they cannot occur on the production route.
"""
from __future__ import annotations

import json
import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "skills" / "assets" / "_shared")]

from asset_result_registration import register_result, runtime_snapshot  # noqa: E402
from asset_family_registry import routes  # noqa: E402
from asset_validation import ProbeReport, ProbeResult  # noqa: E402
import missing_family_standalone_validation as missing_runner  # noqa: E402
import ui_card_standalone_validation as ui_card_runner  # noqa: E402


TAG = "v0.1.0"
CLOSED_ROUTES = {
    ("background-map", "default"), ("card-kit", "default"),
    ("character-bundle", "default"), ("compact-prop-pack", "default"),
    ("fx-bundle", "static"), ("fx-bundle", "animated"),
    ("platform-strip", "single"), ("platform-strip", "atlas"),
    ("scene-prop-set", "default"), ("screen-reference", "default"),
    ("tileset", "default"), ("ui-kit", "default"),
}


def test_closure_cases_cover_every_declared_registry_route():
    assert CLOSED_ROUTES == {(family.family, variant.variant) for family, variant in routes()}


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _source_adapter(family: str):
    path = ROOT / "skills" / "assets" / family / "standalone_validation.py"
    spec = importlib.util.spec_from_file_location(f"closure_{family}_adapter", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _test_support(filename: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, ROOT / "tests" / "assets" / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _props(family: str) -> tuple[dict, dict]:
    asset_id = "market"
    root = f"res://assets/generated/{family}/{asset_id}"
    slots = [
        {"name": "crate", "rect": [0, 0, 16, 16], "source": "source/crate.png"},
        {"name": "lamp", "rect": [16, 0, 16, 16], "source": "source/lamp.png"},
    ]
    return (
        {
            "asset_type": family,
            "asset_id": asset_id,
            "brief": "Two clearly separated scene props.",
            "spec": {"version": 1, "atlas": {"width": 32, "height": 16}, "slots": slots},
        },
        {
            "asset_type": family,
            "outputs": [
                {"role": "runtime", "name": slot["name"], "path": f"{root}/{slot['name']}.tres", "godot_type": "AtlasTexture"}
                for slot in slots
            ],
            "sources": [{"path": f"{root}/{asset_id}.png", "layout": "region_atlas"}],
            "previews": [],
            "validation": {"passed": True, "levels": {level: True for level in ("L0", "L1", "L2", "L3", "L4")}},
        },
    )


def _platform(kind: str) -> tuple[dict, dict]:
    asset_id = "bridge"
    root = f"res://assets/generated/platform-strip/{asset_id}"
    segments = [
        {"name": "left", "role": "left_cap", "slot": [0, 0]},
        {"name": "middle", "role": "repeat_middle", "slot": [1, 0]},
        {"name": "right", "role": "right_cap", "slot": [2, 0]},
    ]
    suffix, godot_type, layout = (".png", "Texture2D", "single") if kind == "single" else (".tres", "AtlasTexture", "region_atlas")
    source = f"{root}/{asset_id}.png" if kind == "atlas" else None
    return (
        {"asset_type": "platform-strip", "asset_id": asset_id, "brief": "A three-piece bridge.", "spec": {"kind": kind, "grid": {"columns": 3, "rows": 1, "cell_width": 16, "cell_height": 16}, "segments": segments}},
        {
            "asset_type": "platform-strip",
            "outputs": [{"role": "runtime", "name": item["name"], "path": f"{root}/{item['name']}{suffix}", "godot_type": godot_type} for item in segments],
            "sources": ([{"path": source, "layout": layout}] if source else [{"path": f"{root}/{item['name']}.png", "layout": layout} for item in segments]),
            "previews": [],
            "validation": {"passed": True, "levels": {level: True for level in ("L0", "L1", "L2", "L3", "L4")}},
        },
    )


def _background() -> tuple[dict, dict]:
    asset_id = "sunset"
    path = f"res://assets/generated/background-map/{asset_id}/{asset_id}.png"
    return (
        {"asset_type": "background-map", "asset_id": asset_id, "brief": "A quiet sunset background."},
        {"asset_type": "background-map", "outputs": [{"role": "runtime", "name": asset_id, "path": path, "godot_type": "Texture2D"}], "sources": [{"path": path, "layout": "single"}], "previews": [], "validation": {"passed": True, "levels": {level: True for level in ("L0", "L1", "L2", "L3", "L4")}}},
    )


def _fixture(family: str, request_name: str, result_name: str) -> tuple[dict, dict]:
    fixtures = ROOT / "skills" / "assets" / family / "fixtures"
    return _json(fixtures / request_name), _json(fixtures / result_name)


def _assets_md(path: Path, request: dict, result: dict) -> list[str]:
    runtime = [output for output in result["outputs"] if output["role"] == "runtime"]
    names = [output.get("name", request["asset_id"]) for output in runtime]
    if not runtime:
        names = [request["asset_id"]]
    rows = "\n".join(
        f"| {index} | {TAG} | {name} | prop | 64x64 | family={request['asset_type']} | - | - | MISSING |"
        for index, name in enumerate(names, 1)
    )
    path.write_text(
        "# Assets\n\n"
        "| # | Tag | Name | Type | Size | Generation Params | Runtime Type | Runtime Path | Status |\n"
        "|---|-----|------|------|------|-------------------|--------------|--------------|--------|\n"
        + rows + "\n",
        encoding="utf-8",
    )
    return names


def _register_validated(tmp_path: Path, request: dict, result: dict) -> None:
    """Register the exact result returned by a family standalone adapter."""
    assert result["validation"]["passed"] is True, result["validation"]
    assets_md = tmp_path / "ASSETS.md"
    names = _assets_md(assets_md, request, result)
    request_path, result_path = tmp_path / "request.json", tmp_path / "result.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    result_path.write_text(json.dumps(result), encoding="utf-8")
    registered = register_result(
        assets_md, result_path, tag=TAG, request_path=request_path, loader=lambda *_: None
    )
    assert registered["updated"] == names
    if request["asset_type"] == "screen-reference":
        assert "| reference |" in assets_md.read_text(encoding="utf-8")
    else:
        assert [entry["asset_id"] for entry in runtime_snapshot(assets_md, tag=TAG, asset_ids=names)] == names


def _passing_probe(structures: dict[str, dict]):
    class Probe:
        def __init__(self, _path):
            pass

        def probe(self, _root, requests):
            return ProbeReport(
                "fake",
                tuple(
                    ProbeResult(
                        item.res_path, item.expected_type, True, item.expected_type, True,
                        structure=structures[item.res_path],
                    )
                    for item in requests
                ),
            )

    return Probe


def _write_prop_delivery(root: Path, request: dict) -> None:
    from PIL import Image

    family, asset_id = request["asset_type"], request["asset_id"]
    output = root / "assets" / "generated" / family / asset_id
    output.mkdir(parents=True)
    atlas = request["spec"]["atlas"]
    image = Image.new("RGBA", (atlas["width"], atlas["height"]), (0, 0, 0, 0))
    for slot in request["spec"]["slots"]:
        x, y, width, height = slot["rect"]
        image.putpixel((x + width // 2, y + height // 2), (1, 2, 3, 255))
    image.save(output / f"{asset_id}.png")
    (output / f"{asset_id}.json").write_text(
        json.dumps({
            "version": 1,
            "atlas_path": f"res://assets/generated/{family}/{asset_id}/{asset_id}.png",
            "regions": [
                {"name": item["name"], "rect": item["rect"], "pivot": [0.5, 0.5], "nine_slice": None}
                for item in request["spec"]["slots"]
            ],
        }),
        encoding="utf-8",
    )


@pytest.mark.parametrize("family", ["compact-prop-pack", "scene-prop-set"])
def test_prop_routes_use_their_actual_standalone_result(monkeypatch, tmp_path, family):
    request, result = _props(family)
    _write_prop_delivery(tmp_path, request)
    root = f"res://assets/generated/{family}/market"
    structures = {
        f"{root}/{slot['name']}.tres": {
            "atlas_texture": {
                "has_atlas": True, "atlas_path": f"{root}/market.png",
                "region": slot["rect"], "margin": [0, 0, 0, 0],
            }
        }
        for slot in request["spec"]["slots"]
    }
    monkeypatch.setattr(missing_runner, "GodotProbe", _passing_probe(structures))
    validated = _source_adapter(family).compile_and_validate(
        request, result, project_root=tmp_path, godot_path="fake"
    )
    assert validated["validation"]["levels"] == {level: True for level in ("L0", "L1", "L2", "L3", "L4")}
    _register_validated(tmp_path, request, validated)


@pytest.mark.parametrize("kind", ["single", "atlas"])
def test_platform_routes_use_their_actual_standalone_result(monkeypatch, tmp_path, kind):
    from PIL import Image

    request, result = _platform(kind)
    root = "res://assets/generated/platform-strip/bridge"
    output = tmp_path / "assets/generated/platform-strip/bridge"
    output.mkdir(parents=True)
    if kind == "single":
        for name in ("left", "middle", "right"):
            Image.new("RGBA", (16, 16), (1, 2, 3, 255)).save(output / f"{name}.png")
        structures = {f"{root}/{name}.png": {"texture2d": {"width": 16, "height": 16}} for name in ("left", "middle", "right")}
    else:
        Image.new("RGBA", (48, 16), (1, 2, 3, 255)).save(output / "bridge.png")
        (output / "bridge.json").write_text(json.dumps({
            "version": 1, "atlas_path": f"{root}/bridge.png",
            "regions": [
                {"name": name, "rect": [index * 16, 0, 16, 16], "pivot": [0.5, 1.0], "nine_slice": None}
                for index, name in enumerate(("left", "middle", "right"))
            ],
        }), encoding="utf-8")
        structures = {
            f"{root}/{name}.tres": {"atlas_texture": {"has_atlas": True, "atlas_path": f"{root}/bridge.png", "region": [index * 16, 0, 16, 16], "margin": [0, 0, 0, 0]}}
            for index, name in enumerate(("left", "middle", "right"))
        }
    raw = tmp_path / ".godotmaker/asset-generation/sources/bridge_source.png"
    raw.parent.mkdir(parents=True)
    Image.new("RGBA", (48, 16), (1, 2, 3, 255)).save(raw)
    monkeypatch.setattr(missing_runner, "GodotProbe", _passing_probe(structures))
    validated = _source_adapter("platform-strip").compile_and_validate(request, result, project_root=tmp_path, godot_path="fake")
    assert validated["validation"]["passed"] is True, validated["validation"]
    _register_validated(tmp_path, request, validated)


def test_background_route_uses_its_actual_standalone_result(monkeypatch, tmp_path):
    from PIL import Image

    request, result = _background()
    artifact = tmp_path / result["outputs"][0]["path"].removeprefix("res://")
    artifact.parent.mkdir(parents=True)
    Image.new("RGBA", (2, 3), (1, 2, 3, 255)).save(artifact)
    monkeypatch.setattr(
        missing_runner,
        "GodotProbe",
        _passing_probe({result["outputs"][0]["path"]: {"texture2d": {"width": 2, "height": 3}}}),
    )
    validated = _source_adapter("background-map").compile_and_validate(
        request, result, project_root=tmp_path, godot_path="fake"
    )
    assert validated["validation"]["passed"] is True
    _register_validated(tmp_path, request, validated)


def test_screen_reference_route_uses_its_actual_standalone_result(tmp_path):
    from PIL import Image

    request = {"asset_type": "screen-reference", "asset_id": "title", "brief": "A title scene."}
    result = {
        "asset_type": "screen-reference",
        "outputs": [{"role": "reference", "name": "title", "path": "references/title.png"}],
        "sources": [{"path": ".godotmaker/asset-generation/sources/title_source.png", "layout": "single"}],
        "previews": [], "validation": {"passed": False},
    }
    for path in ("references/title.png", ".godotmaker/asset-generation/sources/title_source.png"):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (2, 2), (1, 2, 3, 255)).save(target)
    validated = _source_adapter("screen-reference").compile_and_validate(
        request, result, project_root=tmp_path, godot_path="not-used"
    )
    assert validated["validation"] == {"passed": True, "levels": {"L0": True, "L1": True}}
    _register_validated(tmp_path, request, validated)


@pytest.mark.parametrize(
    ("family", "request_name", "result_name", "generated_canonical"),
    [
        ("fx-bundle", "static-request.json", "static-result.json", False),
        ("fx-bundle", "animated-request.json", "animated-result.json", False),
        ("character-bundle", "valid-resolved-request.json", "valid-result.json", False),
        ("character-bundle", "valid-resolved-request.json", "valid-result.json", True),
    ],
)
def test_bundle_routes_use_their_actual_standalone_result(
    monkeypatch, tmp_path, family, request_name, result_name, generated_canonical
):
    from PIL import Image

    request, result = _fixture(family, request_name, result_name)
    asset_id = request["asset_id"]
    if generated_canonical:
        request.pop("references")
        result["outputs"].append(
            {
                "role": "reference", "name": "canonical",
                "path": f"res://assets/generated/{family}/{asset_id}/{asset_id}_canonical.png",
                "godot_type": "Texture2D",
            }
        )
    output = tmp_path / "assets/generated" / family / asset_id
    output.mkdir(parents=True)
    for preview in result["previews"]:
        preview_file = tmp_path / preview["path"].removeprefix("res://")
        preview_file.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (8, 8), (1, 2, 3, 255)).save(preview_file)
    runtime = next(item for item in result["outputs"] if item["role"] == "runtime")
    if runtime["godot_type"] == "Texture2D":
        Image.new("RGBA", (8, 8), (1, 2, 3, 255)).save(output / f"{asset_id}.png")
        structures = {runtime["path"]: {"texture2d": {"width": 8, "height": 8}}}
    else:
        for source in result["sources"]:
            Image.new("RGBA", (8, 8), (1, 2, 3, 255)).save(output / Path(source["path"]).name)
        for action in request["spec"]["actions"]:
            for frame in action["frame_names"]:
                Image.new("RGBA", (1, 1), (1, 2, 3, 255)).save(output / f"{asset_id}_{action['name']}_{frame}.png")
        animations = [
            {
                "name": action["name"], "loop": action["loop"], "fps": action["fps"],
                "frame_paths": [f"res://assets/generated/{family}/{asset_id}/{asset_id}_{action['name']}_{frame}.png" for frame in action["frame_names"]],
                "frame_count": len(action["frame_names"]), "frame_durations": action["frame_durations"],
            }
            for action in request["spec"]["actions"]
        ]
        structures = {runtime["path"]: {"spriteframes": {"animations": animations}}}
    if family == "character-bundle":
        if generated_canonical:
            Image.new("RGBA", (8, 8), (1, 2, 3, 255)).save(output / f"{asset_id}_canonical.png")
        else:
            reference = tmp_path / "references/player_canonical.png"
            reference.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGBA", (8, 8), (1, 2, 3, 255)).save(reference)
    monkeypatch.setattr(missing_runner, "GodotProbe", _passing_probe(structures))
    validated = _source_adapter(family).compile_and_validate(request, result, project_root=tmp_path, godot_path="fake")
    assert validated["validation"]["passed"] is True, validated["validation"]
    _register_validated(tmp_path, request, validated)


@pytest.mark.parametrize("family", ["ui-kit", "card-kit"])
def test_ui_card_routes_use_their_actual_standalone_result(monkeypatch, tmp_path, family):
    support = _test_support("test_ui_card_skill_contract.py", "closure_ui_card_support")
    request = support._request(family)
    result = support._result(request)
    support._write_sources(tmp_path, request)
    monkeypatch.setattr(ui_card_runner.GodotProbe, "probe", support._good_probe(request, result))
    monkeypatch.setattr(ui_card_runner, "_run_consumer_smoke", lambda *_: None)
    validated = _source_adapter(family).compile_and_validate(
        request, result, project_root=tmp_path, godot_path="fake"
    )
    assert validated["validation"]["passed"] is True, validated["validation"]
    _register_validated(tmp_path, request, validated)


def test_tileset_route_uses_its_actual_standalone_result(monkeypatch, tmp_path):
    """Reuse the complete mocked-Godot TileSet ladder, then register its return."""
    support = _test_support("test_tileset_skill_contract.py", "closure_tileset_support")
    captured: dict[str, dict] = {}
    original = support.compile_and_validate

    def capture(request, result, **kwargs):
        validated = original(request, result, **kwargs)
        captured["request"] = request
        captured["result"] = validated
        return validated

    monkeypatch.setattr(support, "compile_and_validate", capture)
    support.test_standalone_runner_maps_request_result_l0_to_l4_without_a_stable_entry(
        tmp_path, monkeypatch
    )
    assert captured["result"]["validation"]["passed"] is True
    _register_validated(tmp_path, captured["request"], captured["result"])
