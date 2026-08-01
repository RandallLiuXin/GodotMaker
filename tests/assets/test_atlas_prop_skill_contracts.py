"""Public contracts for standalone atlas-based prop Skills."""
import json
import sys
from pathlib import Path

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "skills" / "assets" / "_shared"
TOOLS_DIR = REPO_ROOT / "tools"
sys.path.insert(0, str(SHARED_DIR))
sys.path.insert(0, str(TOOLS_DIR))

from asset_skill_contract_check import check_result  # noqa: E402
from asset_atlas_assemble import assemble_atlas  # noqa: E402


FAMILIES = {
    "compact-prop-pack": ("market-props", ("coin", "crate", "lantern")),
    "scene-prop-set": ("market-scene", ("market_stall", "signpost", "water_well")),
}


def _result(family: str) -> dict:
    fixture = next((REPO_ROOT / "skills" / "assets" / family / "samples" / "result").glob("*.json"))
    return json.loads(fixture.read_text(encoding="utf-8"))


def _atlas(family: str) -> dict:
    fixture = next((REPO_ROOT / "skills" / "assets" / family / "samples" / "atlas").glob("*.json"))
    return json.loads(fixture.read_text(encoding="utf-8"))


def _atlas_png(family: str) -> Path:
    return next((REPO_ROOT / "skills" / "assets" / family / "samples" / "atlas").glob("*.png"))


def _declaration(family: str) -> dict:
    return json.loads(
        (REPO_ROOT / "skills" / "assets" / family / "samples" / "declaration" / "spec.json").read_text(
            encoding="utf-8"
        )
    )


def test_atlas_prop_skills_are_standalone_and_use_shared_runtime_contracts():
    for family in FAMILIES:
        skill = (REPO_ROOT / "skills" / "assets" / family / "SKILL.md").read_text(encoding="utf-8")
        assert "asset-skill-contract.md" in skill
        assert "asset_atlas_assemble.py" in skill
        assert "asset_compiler/atlas_texture.py" in skill
        assert "L0-L4" in skill
        assert "packing" in skill
        assert "scene placement" in skill
        if family == "scene-prop-set":
            assert "asset_scene_prop_set_entry_draft.py" in skill
            assert "asset_scene_prop_set_validate.py" in skill
            assert "require_provider_trace: true" in skill
            assert "--background magenta" in skill
            assert "configured `godot_path`" in skill
            assert "GM_EVAL_GODOT_PATH" not in skill
        else:
            assert "/gm-asset" not in skill


def test_atlas_prop_specs_are_direct_assembler_declarations_with_default_pivots():
    for family in FAMILIES:
        declaration = _declaration(family)
        assert set(declaration) == {"version", "atlas", "slots"}
        assert declaration["version"] == 1
        assert set(declaration["atlas"]) == {"width", "height"}
        assert declaration["slots"]
        assert all(slot["source"].endswith(".png") for slot in declaration["slots"])
        assert "pivot" not in declaration["slots"][0]
        assert declaration["slots"][1]["pivot"] == [0.5, 1.0]


def test_atlas_prop_fixtures_have_deterministic_multi_output_runtime_results():
    for family, (asset_id, expected_names) in FAMILIES.items():
        result = _result(family)
        assert check_result(result)["ok"] is True
        assert result["asset_type"] == family
        assert result["sources"] == [
            {
                "path": f"res://assets/generated/{family}/{asset_id}/{asset_id}.png",
                "layout": "region_atlas",
            }
        ]
        assert [output["name"] for output in result["outputs"]] == list(expected_names)
        assert all(output["godot_type"] == "AtlasTexture" for output in result["outputs"])
        assert [output["path"] for output in result["outputs"]] == [
            f"res://assets/generated/{family}/{asset_id}/{name}.tres"
            for name in expected_names
        ]
        assert result["validation"] == {
            "passed": True,
            "levels": {"L0": True, "L1": True, "L2": True, "L3": True, "L4": True},
        }
        atlas = _atlas(family)
        assert atlas["atlas_path"] == result["sources"][0]["path"]
        assert [region["name"] for region in atlas["regions"]] == list(expected_names)
        assert all(region["nine_slice"] is None for region in atlas["regions"])
        assert all(
            len(region["rect"]) == 4 and all(type(value) is int for value in region["rect"])
            for region in atlas["regions"]
        )


def test_public_atlas_fixtures_are_rgba_and_preserve_transparency():
    for family, (_, expected_names) in FAMILIES.items():
        atlas = _atlas(family)
        with Image.open(_atlas_png(family)) as image:
            assert image.mode == "RGBA"
            assert image.size == (max(region["rect"][0] + region["rect"][2] for region in atlas["regions"]), max(region["rect"][1] + region["rect"][3] for region in atlas["regions"]))
            assert image.getpixel((image.width - 1, image.height - 1))[3] == 0
            for region, expected_name in zip(atlas["regions"], expected_names):
                x, y, width, height = region["rect"]
                with image.crop((x, y, x + width, y + height)) as slot_image:
                    pixels = list(slot_image.get_flattened_data())
                assert any(pixel[3] == 0 for pixel in pixels)
                assert any(pixel[3] > 0 for pixel in pixels)
                assert all(pixel[:3] != (255, 0, 255) for pixel in pixels if pixel[3] > 0), expected_name


def test_public_atlas_declarations_assemble_to_the_result_source_path(tmp_path):
    for family, (asset_id, _) in FAMILIES.items():
        declaration = _declaration(family)
        source_atlas = _atlas_png(family)
        with Image.open(source_atlas) as image:
            for slot in declaration["slots"]:
                x, y, width, height = slot["rect"]
                source = tmp_path / slot["source"]
                source.parent.mkdir(parents=True, exist_ok=True)
                image.crop((x, y, x + width, y + height)).save(source)
        declaration_path = tmp_path / f"{family}.json"
        declaration_path.write_text(json.dumps(declaration), encoding="utf-8")
        output = Path("assets/generated") / family / asset_id / f"{asset_id}.png"
        metadata = output.with_suffix(".json")
        assembled = assemble_atlas(
            declaration_path,
            output,
            metadata,
            production_family=family,
            asset_id=asset_id,
            project_root=tmp_path,
        )
        assert assembled["atlas_path"] == _result(family)["sources"][0]["path"]
        assert assembled["regions"] == _atlas(family)["regions"]
        with Image.open(source_atlas) as expected, Image.open(tmp_path / output) as actual:
            assert actual.mode == "RGBA"
            assert list(actual.get_flattened_data()) == list(expected.get_flattened_data())
