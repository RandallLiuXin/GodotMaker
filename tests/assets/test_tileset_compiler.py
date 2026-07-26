"""Contract tests for the explicit v1 TileSet atlas path."""
from pathlib import Path
import sys
import struct
import zlib

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "skills" / "assets" / "_shared"))

from asset_compiler import CompileRequest, CompilerError, CompilerRegistry  # noqa: E402
from asset_compiler import tileset as compiler  # noqa: E402
from asset_validation import ProbeResult, ValidationError  # noqa: E402
from asset_validation.structure import StructureRequest, StructureValidatorRegistry  # noqa: E402
from asset_validation import tileset as structures  # noqa: E402
from asset_validation import GodotProbe, ProbeRequest  # noqa: E402


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
    spec = _spec()
    probe = ProbeResult(
        res_path="res://assets/generated/tileset/grass/grass.tres", expected_type="TileSet",
        loaded=True, godot_class="TileSet", type_matches=True,
        structure={"tileset": {"source_count": 1, "tile_count": 1, "alternative_count": 0,
			"tile_shape": 0, "sources": [{"id": 0, "region_size": [16, 16], "margins": [0, 0], "separation": [0, 0], "tiles": [{"coords": [0, 0], "texture_origin": [0, 0], "z_index": 0, "y_sort_origin": 0, "probability": 1.0, "terrain_set": -1, "terrain": -1, "peering_bits": [-1] * 16, "custom_data": [], "collision_polygons": [], "occlusion_polygons": [], "navigation_polygons": [], "alternatives": [], "animation": {"mode": 0, "columns": 1, "frames_count": 1, "separation": [0, 0], "speed": 1.0}}]}],
			"tile_size": [16, 16], "physics_layers_count": 0, "navigation_layers_count": 0,
			"occlusion_layers_count": 0, "custom_data_layers_count": 0, "terrain_sets_count": 0, "physics_layers": [], "navigation_layers": [], "occlusion_layers": [], "custom_data_layers": [], "terrain_sets": []}},
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
			"source_count": 1, "tile_count": 0, "alternative_count": 0, "tile_shape": 0, "sources": [{"id": 0, "region_size": [16, 16], "margins": [0, 0], "separation": [0, 0], "tiles": []}], "tile_size": [16, 16],
            "physics_layers_count": 0, "navigation_layers_count": 0, "occlusion_layers_count": 0,
			"custom_data_layers_count": 0, "terrain_sets_count": 0}}), spec=_spec(),
    )
    with pytest.raises(ValidationError, match="tile count"):
        structures.validate_tileset(request)


@pytest.mark.parametrize(
    "recipe, message",
    [
        (_spec(tile_shape="triangle"), "tile_shape"),
        (_spec(sources=[{"texture": "res://assets/generated/tileset/grass/atlas.png", "tiles": [{"coords": [0, 0], "animation": {"frames_count": 1, "mode": "loop_forever"}}]}]), "animation mode"),
        (_spec(terrain_sets=[{"terrains": [{"name": "grass", "color": [2, 0, 0]}]}]), "terrain color"),
    ],
)
def test_tileset_recipe_rejects_unknown_enums_and_invalid_colours(recipe, message, tmp_path):
    request = CompileRequest(
        production_family="tileset", asset_id="grass", source_layout_type="tile_atlas",
        source_path="res://assets/generated/tileset/grass/atlas.png", artifact_type="TileSet",
        artifact_path="res://assets/generated/tileset/grass/grass.tres", project_root=tmp_path,
        spec=recipe,
    )
    with pytest.raises(CompilerError, match=message):
        compiler.compile_tileset(request)


def _png(width: int, height: int) -> bytes:
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"".join(b"\0" + b"\xff\xff\xff\xff" * width for _ in range(height)))) + chunk(b"IEND", b"")


def test_orthogonal_fixture_compiles_and_loads_through_godot(godot_bin, godot_project):
    """Real compiler → ResourceLoader coverage for the v1 square atlas path."""
    fixture = REPO_ROOT / "tests" / "assets" / "fixtures" / "orthogonal_tileset_tilemap.tscn"
    assert fixture.is_file()
    source = godot_project / "assets/generated/tileset/grass/atlas.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(_png(16, 16))
    request = CompileRequest(
        production_family="tileset", asset_id="grass", source_layout_type="tile_atlas",
        source_path="res://assets/generated/tileset/grass/atlas.png", artifact_type="TileSet",
        artifact_path="res://assets/generated/tileset/grass/grass.tres", project_root=godot_project,
        spec={"godot_path": godot_bin, "tile_shape": "square", "tile_size": [16, 16], "sources": [{"id": 3, "texture": "res://assets/generated/tileset/grass/atlas.png", "region_size": [16, 16], "margins": [0, 0], "separation": [0, 0], "tiles": [{"coords": [0, 0], "animation": {"mode": "default", "columns": 1, "frames_count": 1, "speed": 1.0, "frame_durations": [{"frame": 0, "duration": 1.0}]}}]}]},
    )
    registry = CompilerRegistry(); compiler.register_into(registry)
    registry.compile(request)
    report = GodotProbe(godot_bin).probe(godot_project, [ProbeRequest(request.artifact_path, "TileSet", ("tileset",))])
    assert report.resources[0].type_matches is True
    assert report.resources[0].structure["tileset"]["sources"][0]["id"] == 3
