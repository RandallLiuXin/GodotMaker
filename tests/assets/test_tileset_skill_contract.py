"""Public contract checks for the standalone TileSet Asset Skill."""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = REPO_ROOT / "skills" / "assets" / "tileset"
FIXTURE = SKILL_DIR / "fixtures" / "orthogonal-square-recipe.json"
sys.path.insert(0, str(REPO_ROOT / "skills" / "assets" / "_shared"))

from asset_compiler import CompileRequest, CompilerError  # noqa: E402
from asset_compiler import tileset as compiler  # noqa: E402


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_tileset_skill_is_standalone_and_reuses_shared_contracts():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: tileset\n")
    for shared_path in (
        "skills/assets/_shared/asset-skill-contract.md",
        "asset_compiler.tileset.register_into()",
        "asset_validation.tileset.register_into()",
    ):
        assert shared_path in text
    for forbidden_dependency in (
        "Do not read or require tags",
        "ASSETS.md",
        "either generated\nmanifest",
        "Do not register outputs",
    ):
        assert forbidden_dependency in text


def test_tileset_skill_documents_recipe_only_semantics_and_l0_to_l4():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    for field in (
        "tile_size",
        "margins",
        "separation",
        "terrain_sets",
        "peering_bits",
        "collision polygons",
        "navigation polygons",
        "occlusion polygons",
        "alternatives",
        "animation",
    ):
        assert field in text
    assert "Never infer them from the atlas image." in text
    for level in ("L0", "L1", "L2", "L3", "L4"):
        assert level in text


def test_orthogonal_square_fixture_is_compiler_acceptable_except_for_its_placeholder_binary(tmp_path):
    recipe = _fixture()
    assert recipe["tile_shape"] == "square"
    assert recipe["tile_size"] == [16, 16]
    assert recipe["sources"][0]["tiles"][0]["alternatives"] == [{"id": 1, "probability": 0.25}]
    request = CompileRequest(
        production_family="tileset",
        asset_id="grassland",
        source_layout_type="tile_atlas",
        source_path="res://assets/generated/tileset/grassland/grassland_atlas.png",
        artifact_type="TileSet",
        artifact_path="res://assets/generated/tileset/grassland/grassland.tres",
        project_root=tmp_path,
        spec=recipe,
    )
    with pytest.raises(CompilerError, match="Godot binary was not found"):
        compiler.compile_tileset(request)
