"""Contract tests for the explicit v1 TileSet atlas path."""
from pathlib import Path
import shutil
import sys
import struct
import subprocess
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


def test_l4_normalizes_rgb_and_default_layer_recipe_values():
    normalized = structures._expected_layers({
        "physics_layers": [{}],
        "terrain_sets": [{"terrains": [{"name": "grass", "color": [0.2, 0.4, 0.6]}]}],
    })
    assert normalized["physics_layers"] == [{"collision_layer": 1, "collision_mask": 1}]
    assert normalized["terrain_sets"][0] == {
        "mode": 0,
        "terrains": [{"name": "grass", "color": [0.2, 0.4, 0.6, 1.0]}],
    }


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


def test_tileset_compiler_imports_before_running_the_builder(tmp_path, monkeypatch):
    request = CompileRequest(
        production_family="tileset", asset_id="grass", source_layout_type="tile_atlas",
        source_path="res://assets/generated/tileset/grass/atlas.png", artifact_type="TileSet",
        artifact_path="res://assets/generated/tileset/grass/grass.tres", project_root=tmp_path,
        spec=_spec(),
    )
    calls = []

    class Result:
        returncode = 0
        stderr = ""
        stdout = ""

    def fake_run(args, **_kwargs):
        calls.append(args)
        return Result()

    monkeypatch.setattr(compiler.subprocess, "run", fake_run)
    assert compiler.compile_tileset(request) == {"sources": 1, "tile_size": [16, 16]}
    assert calls[0][-1] == "--import"
    assert "--script" in calls[1]


def test_tileset_builder_failure_preserves_existing_artifact(godot_bin, godot_project):
    artifact = godot_project / "assets/generated/tileset/grass/grass.tres"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"previous-good-artifact")
    request = CompileRequest(
        production_family="tileset", asset_id="grass", source_layout_type="tile_atlas",
        source_path="res://assets/generated/tileset/grass/missing.png", artifact_type="TileSet",
        artifact_path="res://assets/generated/tileset/grass/grass.tres", project_root=godot_project,
        spec={
            "godot_path": godot_bin, "tile_size": [16, 16],
            "sources": [{"texture": "res://assets/generated/tileset/grass/missing.png", "tiles": [{"coords": [0, 0]}]}],
        },
    )
    with pytest.raises(CompilerError, match="TileSet Godot compiler failed"):
        compiler.compile_tileset(request)
    assert artifact.read_bytes() == b"previous-good-artifact"


def test_tileset_builder_accepts_json_integer_float_tile_shape(godot_bin, godot_project):
    source = godot_project / "assets/generated/tileset/grass/atlas.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(_png(32, 16))
    request = CompileRequest(
        production_family="tileset", asset_id="grass", source_layout_type="tile_atlas",
        source_path="res://assets/generated/tileset/grass/atlas.png", artifact_type="TileSet",
        artifact_path="res://assets/generated/tileset/grass/hex.tres", project_root=godot_project,
        spec={
            "godot_path": godot_bin, "tile_shape": "hexagon", "tile_size": [16, 16],
            "sources": [{"texture": "res://assets/generated/tileset/grass/atlas.png", "tiles": [{"coords": [0, 0]}]}],
        },
    )
    registry = CompilerRegistry()
    compiler.register_into(registry)
    registry.compile(request)
    report = GodotProbe(godot_bin).probe(godot_project, [ProbeRequest(request.artifact_path, "TileSet", ("tileset",))])
    assert report.resources[0].structure["tileset"]["tile_shape"] == 3


def test_tileset_l4_accepts_omitted_animation_defaults(godot_bin, godot_project):
    source = godot_project / "assets/generated/tileset/grass/atlas.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(_png(16, 16))
    request = CompileRequest(
        production_family="tileset", asset_id="grass", source_layout_type="tile_atlas",
        source_path="res://assets/generated/tileset/grass/atlas.png", artifact_type="TileSet",
        artifact_path="res://assets/generated/tileset/grass/defaults.tres", project_root=godot_project,
        spec={
            "godot_path": godot_bin, "tile_size": [16, 16],
            "sources": [{
                "texture": "res://assets/generated/tileset/grass/atlas.png",
                "tiles": [{"coords": [0, 0], "animation": {"frames_count": 1}}],
            }],
        },
    )
    registry = CompilerRegistry()
    compiler.register_into(registry)
    registry.compile(request)
    report = GodotProbe(godot_bin).probe(
        godot_project, [ProbeRequest(request.artifact_path, "TileSet", ("tileset",))]
    )
    structures.validate_tileset(StructureRequest(
        production_family="tileset", asset_id="grass", source_layout_type="tile_atlas",
        source_path=request.source_path, artifact_type="TileSet", artifact_path=request.artifact_path,
        project_root=godot_project, probe=report.resources[0], spec=request.spec,
    ))


def test_tileset_l4_accepts_float32_round_trips(godot_bin, godot_project):
    source = godot_project / "assets/generated/tileset/grass/atlas.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(_png(32, 16))
    request = CompileRequest(
        production_family="tileset", asset_id="grass", source_layout_type="tile_atlas",
        source_path="res://assets/generated/tileset/grass/atlas.png", artifact_type="TileSet",
        artifact_path="res://assets/generated/tileset/grass/float32.tres", project_root=godot_project,
        spec={
            "godot_path": godot_bin, "tile_size": [16, 16],
            "terrain_sets": [{"terrains": [{"name": "grass", "color": [0.2, 0.8, 0.3]}]}],
            "sources": [{
                "texture": "res://assets/generated/tileset/grass/atlas.png",
                "region_size": [16, 16],
                "tiles": [{
                    "coords": [0, 0], "probability": 0.3,
                    "animation": {
                        "columns": 2, "frames_count": 2, "speed": 1.3,
                        "frame_durations": [
                            {"frame": 0, "duration": 0.1},
                            {"frame": 1, "duration": 0.9},
                        ],
                    },
                    "alternatives": [{"id": 1, "probability": 0.3}],
                }],
            }],
        },
    )
    registry = CompilerRegistry()
    compiler.register_into(registry)
    registry.compile(request)
    report = GodotProbe(godot_bin).probe(
        godot_project, [ProbeRequest(request.artifact_path, "TileSet", ("tileset",))]
    )
    facts = report.resources[0].structure["tileset"]
    loaded_tile = facts["sources"][0]["tiles"][0]
    assert loaded_tile["probability"] == pytest.approx(0.3, abs=1e-6)
    assert loaded_tile["animation"]["speed"] == pytest.approx(1.3, abs=1e-6)
    assert loaded_tile["animation"]["frame_durations"] == pytest.approx([0.1, 0.9], abs=1e-6)
    assert loaded_tile["alternatives"][0]["probability"] == pytest.approx(0.3, abs=1e-6)
    assert facts["terrain_sets"][0]["terrains"][0]["color"] == pytest.approx([0.2, 0.8, 0.3, 1.0], abs=1e-6)
    structures.validate_tileset(StructureRequest(
        production_family="tileset", asset_id="grass", source_layout_type="tile_atlas",
        source_path=request.source_path, artifact_type="TileSet", artifact_path=request.artifact_path,
        project_root=godot_project, probe=report.resources[0], spec=request.spec,
    ))


def test_orthogonal_fixture_compiles_and_loads_through_godot(godot_bin, godot_project):
    """Real compiler → ResourceLoader coverage for the v1 square atlas path."""
    fixture = REPO_ROOT / "tests" / "assets" / "fixtures" / "orthogonal_tileset_tilemap.tscn"
    assert fixture.is_file()
    fixture_target = godot_project / "orthogonal_tileset_tilemap.tscn"
    shutil.copyfile(fixture, fixture_target)
    source = godot_project / "assets/generated/tileset/grass/atlas.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(_png(16, 16))
    request = CompileRequest(
        production_family="tileset", asset_id="grass", source_layout_type="tile_atlas",
        source_path="res://assets/generated/tileset/grass/atlas.png", artifact_type="TileSet",
        artifact_path="res://assets/generated/tileset/grass/grass.tres", project_root=godot_project,
        spec={
            "godot_path": godot_bin,
            "tile_shape": "square",
            "tile_size": [16, 16],
            "physics_layers": [{}],
            "navigation_layers": [{}],
            "occlusion_layers": [{}],
            "custom_data_layers": [{"name": "kind", "type": 4}],
            "terrain_sets": [{"terrains": [{"name": "grass", "color": [0.2, 0.8, 0.3]}]}],
            "sources": [{
                "id": 3,
                "texture": "res://assets/generated/tileset/grass/atlas.png",
                "region_size": [16, 16],
                "margins": [0, 0],
                "separation": [0, 0],
                "tiles": [{
                    "coords": [0, 0],
                    "terrain_set": 0,
                    "terrain": 0,
                    "peering_bits": [{"bit": 0, "terrain": 0}],
                    "custom_data": [{"layer": 0, "value": "grass"}],
                    "collision_polygons": [{"layer": 0, "points": [[0, 0], [16, 0], [16, 16]]}],
                    "occlusion_polygons": [{"layer": 0, "points": [[0, 0], [16, 0], [16, 16]]}],
                    "navigation_polygons": [{"layer": 0, "points": [[0, 0], [16, 0], [16, 16]]}],
                    "alternatives": [{"id": 1, "z_index": 2, "custom_data": [{"layer": 0, "value": "alt"}]}],
                    "animation": {"mode": "default", "columns": 1, "frames_count": 1, "separation": [0, 0], "speed": 1.0, "frame_durations": [{"frame": 0, "duration": 1.0}]},
                }],
            }],
        },
    )
    registry = CompilerRegistry()
    compiler.register_into(registry)
    registry.compile(request)
    report = GodotProbe(godot_bin).probe(godot_project, [ProbeRequest(request.artifact_path, "TileSet", ("tileset",))])
    assert report.resources[0].type_matches is True
    assert report.resources[0].structure["tileset"]["sources"][0]["id"] == 3
    loaded_tile = report.resources[0].structure["tileset"]["sources"][0]["tiles"][0]
    assert loaded_tile["custom_data"] == ["grass"]
    assert loaded_tile["collision_polygons"] == [[[[0, 0], [16, 0], [16, 16]]]]
    assert loaded_tile["occlusion_polygons"] == [[[[0, 0], [16, 0], [16, 16]]]]
    assert loaded_tile["navigation_polygons"] == [[[0, 0], [16, 0], [16, 16]]]
    binding_script = godot_project / "bind_fixture.gd"
    binding_script.write_text(
        "extends SceneTree\nfunc _init():\n\tvar scene = load('res://orthogonal_tileset_tilemap.tscn').instantiate()\n\tscene.get_node('TileMap').tile_set = load('res://assets/generated/tileset/grass/grass.tres')\n\tquit()\n",
        encoding="utf-8",
    )
    bound = subprocess.run(
        [godot_bin, "--headless", "--path", str(godot_project), "--script", str(binding_script)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert bound.returncode == 0, bound.stderr or bound.stdout
    structures.validate_tileset(StructureRequest(
        production_family="tileset", asset_id="grass", source_layout_type="tile_atlas",
        source_path=request.source_path, artifact_type="TileSet", artifact_path=request.artifact_path,
        project_root=godot_project, probe=report.resources[0], spec=request.spec,
    ))
