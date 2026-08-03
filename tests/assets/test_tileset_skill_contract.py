"""Public contract checks for the standalone TileSet Asset Skill."""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = REPO_ROOT / "skills" / "assets" / "tileset"
FIXTURE = SKILL_DIR / "fixtures" / "orthogonal-square-recipe.json"
sys.path.insert(0, str(REPO_ROOT / "skills" / "assets" / "_shared"))
sys.path.insert(0, str(REPO_ROOT / "tools"))
sys.path.insert(0, str(SKILL_DIR))

from asset_compiler import CompileRequest, CompilerError  # noqa: E402
from asset_compiler import tileset as compiler  # noqa: E402
from asset_validation import ProbeReport, ProbeRequest, ProbeResult, ValidationError  # noqa: E402
from asset_validation.godot_probe import GodotProbe  # noqa: E402
from standalone_validation import TileSetSkillError, compile_and_validate  # noqa: E402
from asset_tileset_profile import (  # noqa: E402
    build_profile_recipe,
    compile_profile_recipe,
    get_profile,
    profile_manifest,
)
from asset_tileset_contract_check import (  # noqa: E402
    TileSetRequestError,
    check_tileset_request,
)
from PIL import Image  # noqa: E402


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _public_request(asset_id: str = "grassland") -> dict:
    return {
        "asset_type": "tileset",
        "asset_id": asset_id,
        "brief": "A grassland tile atlas.",
        "provider": "codex",
        "spec": {
            "autotile_profile": "marching_squares_15",
            "tile_size": {"width": 16, "height": 16},
            "terrain": {
                "name": "grassland",
                "foreground_material": "dirt",
                "background_material": "grass",
            },
        },
    }


def test_tileset_skill_is_standalone_and_reuses_shared_contracts():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: tileset\n")
    for shared_path in (
        ".godotmaker/asset-runtime/asset-skill-contract.md",
        "asset_compiler.tileset.register_into()",
        "asset_validation.tileset.register_into()",
        "standalone_validation.compile_and_validate()",
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
        "Physics, navigation",
        "custom data",
        "does not support animated TileSets",
        "Unknown or misspelled",
    ):
        assert field in text
    assert "never inferred from pixels" in text
    for level in ("L0", "L1", "L2", "L3", "L4"):
        assert level in text


def test_tileset_skill_limits_production_to_fixed_profile_templates():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "marching_squares_15" in text
    assert "blob_47" in text
    assert "`spec.autotile_profile` is required" in text
    assert "Agents must not enumerate 15/47 cells" in text
    assert "asset_tileset_profile.py" in text
    assert ".godotmaker/asset-runtime/tools/codex_image_claim.py --plan" in text
    assert "--material-source" in text
    assert "GM_EVAL_GODOT_PATH" in text


def test_tileset_request_contract_is_typed_and_has_no_output_paths():
    assert check_tileset_request(_public_request())["asset_id"] == "grassland"
    invalid = _public_request()
    invalid["spec"]["output_path"] = "res://assets/generated/tileset/grassland/grassland.tres"
    with pytest.raises(TileSetRequestError, match="unknown fields"):
        check_tileset_request(invalid)
    missing_profile = _public_request()
    missing_profile["spec"].pop("autotile_profile")
    with pytest.raises(TileSetRequestError, match="autotile_profile"):
        check_tileset_request(missing_profile)
    animation = _public_request()
    animation["spec"]["semantic_metadata"] = {"roles": {"foreground_full": {"animation": {}}}}
    with pytest.raises(TileSetRequestError, match="unknown fields"):
        check_tileset_request(animation)
    obsolete_role = _public_request()
    obsolete_role["spec"]["semantic_metadata"] = {"roles": {"background_full": {}}}
    with pytest.raises(TileSetRequestError, match="unknown roles"):
        check_tileset_request(obsolete_role)


def test_blob_profile_compiles_to_a_native_tileset(godot_bin, godot_project):
    profile = get_profile("blob_47")
    atlas = godot_project / "assets/generated/tileset/coast/coast_atlas.png"
    atlas.parent.mkdir(parents=True)
    image = Image.new("RGBA", (profile.columns * 16, profile.rows * 16), (0, 0, 0, 0))
    for index, tile in enumerate(profile.tiles, start=1):
        image.putpixel((tile.coords[0] * 16, tile.coords[1] * 16), (index, 80, 160, 255))
    image.save(atlas)
    recipe = build_profile_recipe(
        "blob_47",
        texture_path="res://assets/generated/tileset/coast/coast_atlas.png",
        tile_width=16,
        tile_height=16,
        godot_path=godot_bin,
        terrain_name="coast",
    )
    artifact = compile_profile_recipe(
        recipe,
        project_root=godot_project,
        asset_id="coast",
        texture_path="res://assets/generated/tileset/coast/coast_atlas.png",
        artifact_path="res://assets/generated/tileset/coast/coast.tres",
    )
    assert artifact == {"type": "TileSet", "path": "res://assets/generated/tileset/coast/coast.tres"}
    report = GodotProbe(godot_bin).probe(
        godot_project,
        [ProbeRequest("res://assets/generated/tileset/coast/coast.tres", "TileSet", ("tileset",))],
    )
    assert report.resources[0].type_matches is True
    tileset = report.resources[0].structure["tileset"]
    assert tileset["tile_count"] == 47
    # Godot reports terrain peering bits in numeric order; compare that loaded
    # representation to the fixed profile without depending on input ordering.
    expected = {
        tuple(slot["coords"]): tuple(sorted(slot["peering_bits"]))
        for slot in profile_manifest("blob_47")["slots"]
        if not slot["reserved"]
    }
    loaded = {
        tuple(tile["coords"]): tuple(index for index, terrain in enumerate(tile["peering_bits"]) if terrain == 0)
        for tile in tileset["sources"][0]["tiles"]
    }
    assert loaded == expected


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


def test_standalone_runner_maps_request_result_l0_to_l4_without_a_stable_entry(
    tmp_path, monkeypatch
):
    """Exercise the executable standalone flow without manifest-shaped state."""
    root = tmp_path
    (root / "project.godot").write_text("[application]\nconfig/name=\"test\"\n", encoding="utf-8")
    request = _public_request()
    source_path = "res://assets/generated/tileset/grassland/grassland_atlas.png"
    source = root / source_path.removeprefix("res://")
    source.parent.mkdir(parents=True)
    source.write_bytes(b"png")
    result = {
        "asset_type": "tileset",
        "outputs": [{"role": "runtime", "path": "res://assets/generated/tileset/grassland/grassland.tres", "godot_type": "TileSet"}],
        "sources": [{"path": source_path, "layout": "tile_atlas"}],
        "previews": [],
        "validation": {"passed": False},
    }

    def fake_compile(compile_request):
        artifact = root / compile_request.artifact_path.removeprefix("res://")
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("[gd_resource type=\"TileSet\"]\n", encoding="utf-8")
        return {"sources": 1, "tile_size": [16, 16]}

    facts = {
        "tileset": {
            "source_count": 1,
            "tile_count": 1,
            "alternative_count": 1,
            "tile_shape": 0,
            "tile_size": [16, 16],
            "sources": [{
                "id": 0,
                "region_size": [16, 16],
                "margins": [0, 0],
                "separation": [0, 0],
                "tiles": [{
                    "coords": [0, 0], "texture_origin": [0, 0], "z_index": 0,
                    "y_sort_origin": 0, "probability": 1.0, "terrain_set": 0,
                    "terrain": 0, "peering_bits": [0] + [-1] * 15,
                    "custom_data": [None, True, 1, 0.5, "grass"], "collision_polygons": [[[[0, 0], [16, 0], [16, 16], [0, 16]]]],
                    "occlusion_polygons": [], "navigation_polygons": [], "alternatives": [{
                        "id": 1, "texture_origin": [0, 0], "z_index": 0, "y_sort_origin": 0,
                        "probability": 0.25, "terrain_set": -1, "terrain": -1,
                        "peering_bits": [-1] * 16, "custom_data": [None, False, 0, 0.0, ""], "collision_polygons": [[]],
                        "occlusion_polygons": [], "navigation_polygons": [],
                    }],
                }],
            }],
            "physics_layers_count": 1, "navigation_layers_count": 0,
            "occlusion_layers_count": 0, "custom_data_layers_count": 5,
            "terrain_sets_count": 1,
            "physics_layers": [{"collision_layer": 1, "collision_mask": 1}],
            "navigation_layers": [], "occlusion_layers": [], "custom_data_layers": [
                {"name": "nothing", "type": 0}, {"name": "walkable", "type": 1},
                {"name": "cost", "type": 2}, {"name": "weight", "type": 3}, {"name": "kind", "type": 4},
            ],
            "terrain_sets": [{"mode": 0, "terrains": [{"name": "grass", "color": [0.2, 0.8, 0.3, 1.0]}]}],
        }
    }

    def fake_probe(self, project_root, requests):
        assert project_root == root
        assert requests[0].checks == ("tileset",)
        return ProbeReport(
            godot_version="test",
            resources=(ProbeResult(requests[0].res_path, "TileSet", True, "TileSet", True, structure=facts),),
        )

    monkeypatch.setattr(compiler, "compile_tileset", fake_compile)
    monkeypatch.setattr(GodotProbe, "probe", fake_probe)
    validated = compile_and_validate(request, result, recipe=_fixture(), project_root=root, godot_path="godot")

    assert validated["validation"] == {
        "passed": True,
        "levels": {"L0": True, "L1": True, "L2": True, "L3": True, "L4": True},
    }
    assert "processing_status" not in validated
    assert "godot_artifact" not in validated


def test_standalone_runner_maps_a_godot_setup_failure_to_l3(tmp_path, monkeypatch):
    root = tmp_path
    request = _public_request()
    source_path = "res://assets/generated/tileset/grassland/grassland_atlas.png"
    source = root / source_path.removeprefix("res://")
    source.parent.mkdir(parents=True)
    source.write_bytes(b"png")
    result = {
        "asset_type": "tileset",
        "outputs": [{"role": "runtime", "path": "res://assets/generated/tileset/grassland/grassland.tres", "godot_type": "TileSet"}],
        "sources": [{"path": source_path, "layout": "tile_atlas"}],
        "previews": [],
        "validation": {"passed": False},
    }

    def fake_compile(compile_request):
        artifact = root / compile_request.artifact_path.removeprefix("res://")
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("[gd_resource type=\"TileSet\"]\n", encoding="utf-8")
        return {"sources": 1, "tile_size": [16, 16]}

    monkeypatch.setattr(compiler, "compile_tileset", fake_compile)
    validated = compile_and_validate(request, result, recipe=_fixture(), project_root=root, godot_path="")

    assert validated["validation"]["passed"] is False
    assert validated["validation"]["levels"] == {
        "L0": True, "L1": True, "L2": True, "L3": False, "L4": False,
    }
    assert "godot_path must be a non-empty string" in validated["validation"]["notes"]


def test_standalone_runner_reports_l1_before_an_l2_validation_error(tmp_path, monkeypatch):
    request = _public_request()
    source_path = "res://assets/generated/tileset/grassland/grassland_atlas.png"
    source = tmp_path / source_path.removeprefix("res://")
    source.parent.mkdir(parents=True)
    source.write_bytes(b"png")
    result = {
        "asset_type": "tileset",
        "outputs": [{"role": "runtime", "path": "res://assets/generated/tileset/grassland/grassland.tres", "godot_type": "TileSet"}],
        "sources": [{"path": source_path, "layout": "tile_atlas"}],
        "previews": [],
        "validation": {"passed": False},
    }

    def fail_compile(_request):
        raise ValidationError("compiler result disagrees with request")

    monkeypatch.setattr(compiler, "compile_tileset", fail_compile)
    validated = compile_and_validate(request, result, recipe=_fixture(), project_root=tmp_path, godot_path="godot")

    assert validated["validation"]["levels"] == {
        "L0": True, "L1": True, "L2": False, "L3": False, "L4": False,
    }


def test_standalone_runner_rejects_an_unvalidated_extra_runtime_output(tmp_path):
    request = _public_request()
    result = {
        "asset_type": "tileset",
        "outputs": [
            {"role": "runtime", "path": "res://assets/generated/tileset/grassland/grassland.tres", "godot_type": "TileSet"},
            {"role": "runtime", "path": "res://assets/generated/tileset/grassland/unvalidated.tres", "godot_type": "Texture2D"},
        ],
        "sources": [{"path": "res://assets/generated/tileset/grassland/grassland_atlas.png", "layout": "tile_atlas"}],
        "previews": [],
        "validation": {"passed": False},
    }

    with pytest.raises(TileSetSkillError, match="exactly one stable TileSet runtime output"):
        compile_and_validate(request, result, recipe=_fixture(), project_root=tmp_path, godot_path="godot")


@pytest.mark.parametrize("mutation", ["runtime", "result-source", "recipe-source", "multiple-sources"])
def test_standalone_runner_rejects_noncanonical_stable_tileset_paths(tmp_path, mutation):
    request = _public_request()
    recipe = _fixture()
    result = {
        "asset_type": "tileset",
        "outputs": [{"role": "runtime", "path": "res://assets/generated/tileset/grassland/grassland.tres", "godot_type": "TileSet"}],
        "sources": [{"path": "res://assets/generated/tileset/grassland/grassland_atlas.png", "layout": "tile_atlas"}],
        "previews": [], "validation": {"passed": False},
    }
    if mutation == "runtime":
        result["outputs"][0]["path"] = "res://assets/generated/tileset/grassland/not-the-asset-id.tres"
    elif mutation == "result-source":
        result["sources"][0]["path"] = "res://assets/generated/tileset/grassland/not-the-asset-id.png"
    elif mutation == "recipe-source":
        recipe["sources"][0]["texture"] = "res://assets/generated/tileset/grassland/not-the-asset-id.png"
    else:
        recipe["sources"].append(dict(recipe["sources"][0]))
    with pytest.raises(TileSetSkillError, match="L0 standalone contract failed"):
        compile_and_validate(request, result, recipe=recipe, project_root=tmp_path, godot_path="godot")
