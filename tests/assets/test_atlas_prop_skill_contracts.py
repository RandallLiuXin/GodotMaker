"""Public contracts for standalone atlas-based prop Skills."""
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "skills" / "assets" / "_shared"
sys.path.insert(0, str(SHARED_DIR))

from asset_skill_contract_check import check_result  # noqa: E402


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


def test_atlas_prop_skills_are_standalone_and_use_shared_runtime_contracts():
    for family in FAMILIES:
        skill = (REPO_ROOT / "skills" / "assets" / family / "SKILL.md").read_text(encoding="utf-8")
        assert "asset-skill-contract.md" in skill
        assert "asset_atlas_assemble.py" in skill
        assert "asset_compiler/atlas_texture.py" in skill
        assert "L0-L4" in skill
        assert "packing" in skill
        assert "scene placement" in skill
        assert "/gm-asset" not in skill


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
