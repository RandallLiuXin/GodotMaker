"""Contract tests for the explicit v1 TileSet atlas path."""
from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "skills" / "assets" / "_shared"))

from asset_compiler import CompileRequest, CompilerError, CompilerRegistry  # noqa: E402
from asset_compiler import tileset as compiler  # noqa: E402
from asset_validation import ProbeResult, ValidationError  # noqa: E402
from asset_validation.structure import StructureRequest, StructureValidatorRegistry  # noqa: E402
from asset_validation import tileset as structures  # noqa: E402


def _spec(**changes):
    recipe = {
        "godot_path": "godot",
        "tile_size": [16, 16],
        "sources": [{"texture": "res://assets/generated/tileset/grass/atlas.png", "tiles": [{"coords": [0, 0]}]}],
    }
    recipe.update(changes)
    return recipe


def test_tileset_route_is_explicit_and_does_not_mutate_the_shared_default_registry():
    registry = CompilerRegistry()
    compiler.register_into(registry)
    assert registry.resolve("tile_atlas", "TileSet").compiler_id == compiler.COMPILER_ID


@pytest.mark.parametrize("spec, message", [
    ({}, "godot_path"),
    ({"godot_path": "godot", "tile_size": [0, 16], "sources": []}, "tile_size"),
    ({"godot_path": "godot", "tile_size": [16, 16], "sources": []}, "sources"),
])
def test_tileset_recipe_rejects_implicit_or_incomplete_input(tmp_path, spec, message):
    request = CompileRequest(
        production_family="tileset", asset_id="grass", source_layout_type="tile_atlas",
        source_path="res://assets/generated/tileset/grass/atlas.png", artifact_type="TileSet",
        artifact_path="res://assets/generated/tileset/grass/grass.tres", project_root=tmp_path,
        spec=spec,
    )
    with pytest.raises(CompilerError, match=message):
        compiler.compile_tileset(request)


def test_tileset_structure_validator_compares_loaded_recipe_facts():
    registry = StructureValidatorRegistry()
    structures.register_into(registry)
    spec = _spec(physics_layers=[{}], custom_data_layers=[{"name": "kind"}])
    probe = ProbeResult(
        res_path="res://assets/generated/tileset/grass/grass.tres", expected_type="TileSet",
        loaded=True, godot_class="TileSet", type_matches=True,
        structure={"tileset": {"source_count": 1, "tile_count": 1, "alternative_count": 0,
            "tile_size": [16, 16], "physics_layers_count": 1, "navigation_layers_count": 0,
			"occlusion_layers_count": 0, "custom_data_layers_count": 1, "terrain_sets_count": 0}},
    )
    details = registry.validate(StructureRequest(
        production_family="tileset", asset_id="grass", source_layout_type="tile_atlas",
        source_path="res://assets/generated/tileset/grass/atlas.png", artifact_type="TileSet",
        artifact_path=probe.res_path, project_root=Path("."), probe=probe, spec=spec,
    ))
    assert details["tile_count"] == 1


def test_tileset_structure_validator_fails_on_unexpected_loaded_tile_count():
    request = StructureRequest(
        production_family="tileset", asset_id="grass", source_layout_type="tile_atlas",
        source_path="res://assets/generated/tileset/grass/atlas.png", artifact_type="TileSet",
        artifact_path="res://assets/generated/tileset/grass/grass.tres", project_root=Path("."),
        probe=ProbeResult("res://x", "TileSet", True, "TileSet", True, structure={"tileset": {
            "source_count": 1, "tile_count": 0, "alternative_count": 0, "tile_size": [16, 16],
            "physics_layers_count": 0, "navigation_layers_count": 0, "occlusion_layers_count": 0,
			"custom_data_layers_count": 0, "terrain_sets_count": 0}}), spec=_spec(),
    )
    with pytest.raises(ValidationError, match="tile count"):
        structures.validate_tileset(request)
