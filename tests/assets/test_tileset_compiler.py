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


def _recipe_request(tmp_path, spec):
    return CompileRequest(
        production_family="tileset", asset_id="grass", source_layout_type="tile_atlas",
        source_path="res://assets/generated/tileset/grass/atlas.png", artifact_type="TileSet",
        artifact_path="res://assets/generated/tileset/grass/grass.tres", project_root=tmp_path,
        spec=spec,
    )


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


def test_tileset_l4_matches_sources_tiles_and_alternatives_by_identity_not_declaration_order():
    def loaded_tile(coords, alternatives=None):
        return {
            "coords": coords, "texture_origin": [0, 0], "z_index": 0,
            "y_sort_origin": 0, "probability": 1.0, "terrain_set": -1,
            "terrain": -1, "peering_bits": [-1] * 16, "custom_data": [],
            "collision_polygons": [], "occlusion_polygons": [],
            "navigation_polygons": [], "alternatives": alternatives or [],
        }

    alternative_one = {**loaded_tile([1, 0]), "id": 1}
    alternative_three = {**loaded_tile([1, 0]), "id": 3}
    spec = _spec(sources=[
        {"id": 5, "texture": "res://assets/generated/tileset/grass/first.png", "tile_size": [32, 32], "tiles": [{
            "coords": [1, 0], "alternatives": [{"id": 3}, {"id": 1}],
        }]},
        {"id": 3, "texture": "res://assets/generated/tileset/grass/second.png", "tiles": [{"coords": [0, 0]}]},
    ])
    facts = {"tileset": {
        "source_count": 2, "tile_count": 2, "alternative_count": 2,
        "tile_shape": 0, "tile_size": [16, 16],
        "sources": [
            {"id": 3, "region_size": [16, 16], "margins": [0, 0], "separation": [0, 0], "tiles": [loaded_tile([0, 0])]},
            {"id": 5, "region_size": [32, 32], "margins": [0, 0], "separation": [0, 0], "tiles": [loaded_tile([1, 0], [alternative_one, alternative_three])]},
        ],
        "physics_layers_count": 0, "navigation_layers_count": 0,
        "occlusion_layers_count": 0, "custom_data_layers_count": 0,
        "terrain_sets_count": 0, "physics_layers": [], "navigation_layers": [],
        "occlusion_layers": [], "custom_data_layers": [], "terrain_sets": [],
    }}
    request = StructureRequest(
        production_family="tileset", asset_id="grass", source_layout_type="tile_atlas",
        source_path="res://assets/generated/tileset/grass/atlas.png", artifact_type="TileSet",
        artifact_path="res://assets/generated/tileset/grass/grass.tres", project_root=Path("."),
        probe=ProbeResult("res://x", "TileSet", True, "TileSet", True, structure=facts), spec=spec,
    )
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


@pytest.mark.parametrize("alternative", [False, True])
def test_tileset_recipe_rejects_duplicate_navigation_polygon_layers(tmp_path, alternative):
    tile = {"coords": [0, 0]}
    polygons = [
        {"layer": 0, "points": [[0, 0], [16, 0], [0, 16]]},
        {"layer": 0, "points": [[1, 1], [15, 1], [1, 15]]},
    ]
    if alternative:
        tile["alternatives"] = [{"id": 1, "navigation_polygons": polygons}]
    else:
        tile["navigation_polygons"] = polygons
    request = CompileRequest(
        production_family="tileset", asset_id="grass", source_layout_type="tile_atlas",
        source_path="res://assets/generated/tileset/grass/atlas.png", artifact_type="TileSet",
        artifact_path="res://assets/generated/tileset/grass/grass.tres", project_root=tmp_path,
        spec=_spec(navigation_layers=[{}], sources=[{
            "texture": "res://assets/generated/tileset/grass/atlas.png", "tiles": [tile],
        }]),
    )
    with pytest.raises(CompilerError, match="duplicate navigation polygons"):
        compiler._recipe(request)


def test_tileset_recipe_accepts_only_the_five_v1_custom_data_scalars(tmp_path):
    recipe = compiler._recipe(_recipe_request(tmp_path, _spec(
        custom_data_layers=[
            {"name": "nothing", "type": 0}, {"name": "enabled", "type": 1},
            {"name": "count", "type": 2}, {"name": "weight", "type": 3},
            {"name": "label", "type": 4},
        ],
        sources=[{"texture": "res://assets/generated/tileset/grass/atlas.png", "tiles": [{
            "coords": [0, 0],
            "custom_data": [
                {"layer": 0, "value": None}, {"layer": 1, "value": True},
                {"layer": 2, "value": 7}, {"layer": 3, "value": -0.25},
                {"layer": 4, "value": "grass"},
            ],
            "alternatives": [{"id": 1, "custom_data": [{"layer": 4, "value": "alt"}]}],
        }]}],
    )))
    assert recipe["sources"][0]["tiles"][0]["custom_data"][-1]["value"] == "grass"
    assert recipe["sources"][0]["tiles"][0]["alternatives"][0]["custom_data"] == [{"layer": 4, "value": "alt"}]


@pytest.mark.parametrize(
    "layer_type, value, message",
    [
        (0, "not-nil", "NIL scalar"),
        (1, 1, "bool scalar"),
        (2, True, "int scalar"),
        (3, float("nan"), "finite number"),
        (4, ["nested"], "String scalar"),
    ],
)
def test_tileset_recipe_rejects_non_scalar_or_mismatched_custom_data(tmp_path, layer_type, value, message):
    request = _recipe_request(tmp_path, _spec(
        custom_data_layers=[{"name": "value", "type": layer_type}],
        sources=[{"texture": "res://assets/generated/tileset/grass/atlas.png", "tiles": [{
            "coords": [0, 0], "custom_data": [{"layer": 0, "value": value}],
        }]}],
    ))
    with pytest.raises(CompilerError, match=message):
        compiler._recipe(request)


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"sources": [{"texture": "res://assets/generated/tileset/grass/atlas.png", "tiles": [{"coords": [0, 0], "texture_origin": [0, "bad"]}]}]}, "texture_origin"),
        ({"sources": [{"texture": "res://assets/generated/tileset/grass/atlas.png", "tiles": [{"coords": [0, 0], "z_index": 1.5}]}]}, "z_index"),
        ({"sources": [{"texture": "res://assets/generated/tileset/grass/atlas.png", "tiles": [{"coords": [0, 0], "y_sort_origin": 1.5}]}]}, "y_sort_origin"),
        ({"sources": [{"texture": "res://assets/generated/tileset/grass/atlas.png", "tiles": [{"coords": [0, 0], "probability": float("inf")}]}]}, "probability"),
        ({"physics_layers": [{}], "sources": [{"texture": "res://assets/generated/tileset/grass/atlas.png", "tiles": [{"coords": [0, 0], "collision_polygons": [{"layer": 1, "points": [[0, 0], [1, 0], [0, 1]]}]}]}]}, "collision polygon layer"),
        ({"terrain_sets": [{"terrains": [{"name": "grass"}]}], "sources": [{"texture": "res://assets/generated/tileset/grass/atlas.png", "tiles": [{"coords": [0, 0], "terrain_set": 1}]}]}, "terrain_set"),
        ({"terrain_sets": [{"terrains": [{"name": "grass"}]}], "sources": [{"texture": "res://assets/generated/tileset/grass/atlas.png", "tiles": [{"coords": [0, 0], "terrain_set": 0, "peering_bits": [{"bit": 16, "terrain": 0}]}]}]}, "peering bit"),
        ({"terrain_sets": [{"terrains": [{"name": "grass"}]}], "sources": [{"texture": "res://assets/generated/tileset/grass/atlas.png", "tiles": [{"coords": [0, 0], "terrain_set": 0, "peering_bits": [{"bit": 0, "terrain": 1}]}]}]}, "peering terrain"),
        ({"physics_layers": [{}], "sources": [{"texture": "res://assets/generated/tileset/grass/atlas.png", "tiles": [{"coords": [0, 0], "collision_polygons": [{"layer": 0, "points": [[0, 0], [1, 0]]}]}]}]}, "at least three points"),
        ({"terrain_sets": [{"terrains": [{"name": "grass"}]}], "sources": [{"texture": "res://assets/generated/tileset/grass/atlas.png", "tiles": [{"coords": [0, 0], "terrain_set": 0, "peering_bits": [{"bit": 0, "terrain": 0}, {"bit": 0, "terrain": 0}]}]}]}, "duplicate peering bits"),
        ({"custom_data_layers": [{"name": "value", "type": 2}], "sources": [{"texture": "res://assets/generated/tileset/grass/atlas.png", "tiles": [{"coords": [0, 0], "custom_data": [{"layer": 0, "value": 1}, {"layer": 0, "value": 2}]}]}]}, "duplicate custom data layers"),
    ],
)
def test_tileset_recipe_rejects_invalid_declared_tile_semantics(tmp_path, changes, message):
    with pytest.raises(CompilerError, match=message):
        compiler._recipe(_recipe_request(tmp_path, _spec(**changes)))


@pytest.mark.parametrize("alternative", [False, True])
def test_tileset_recipe_rejects_empty_collision_polygons_for_tiles_and_alternatives(tmp_path, alternative):
    collision = {"layer": 0, "points": []}
    tile = {"coords": [0, 0]}
    if alternative:
        tile["alternatives"] = [{"id": 1, "collision_polygons": [collision]}]
    else:
        tile["collision_polygons"] = [collision]
    request = _recipe_request(tmp_path, _spec(
        physics_layers=[{}],
        sources=[{"texture": "res://assets/generated/tileset/grass/atlas.png", "tiles": [tile]}],
    ))
    with pytest.raises(CompilerError, match="collision polygon points must contain at least three points"):
        compiler._recipe(request)


def test_tileset_recipe_continues_to_allow_empty_occlusion_and_navigation_polygons(tmp_path):
    recipe = compiler._recipe(_recipe_request(tmp_path, _spec(
        occlusion_layers=[{}], navigation_layers=[{}],
        sources=[{"texture": "res://assets/generated/tileset/grass/atlas.png", "tiles": [{
            "coords": [0, 0],
            "occlusion_polygons": [{"layer": 0, "points": []}],
            "navigation_polygons": [{"layer": 0, "points": []}],
        }]}],
    )))
    tile = recipe["sources"][0]["tiles"][0]
    assert tile["occlusion_polygons"][0]["points"] == []
    assert tile["navigation_polygons"][0]["points"] == []


def test_tileset_recipe_rejects_duplicate_tile_coords_and_alternative_ids(tmp_path):
    source = "res://assets/generated/tileset/grass/atlas.png"
    duplicate_coords = _recipe_request(tmp_path, _spec(sources=[{
        "texture": source, "tiles": [{"coords": [0, 0]}, {"coords": [0, 0]}],
    }]))
    duplicate_alternatives = _recipe_request(tmp_path, _spec(sources=[{
        "texture": source, "tiles": [{"coords": [0, 0], "alternatives": [{"id": 1}, {"id": 1}]}],
    }]))
    with pytest.raises(CompilerError, match="duplicate tile coords"):
        compiler._recipe(duplicate_coords)
    with pytest.raises(CompilerError, match="duplicate alternative ids"):
        compiler._recipe(duplicate_alternatives)


def test_tileset_recipe_keeps_probability_as_a_non_negative_relative_weight(tmp_path):
    recipe = compiler._recipe(_recipe_request(tmp_path, _spec(sources=[{
        "texture": "res://assets/generated/tileset/grass/atlas.png",
        "tiles": [{"coords": [0, 0], "probability": 3.0}],
    }])))
    assert recipe["sources"][0]["tiles"][0]["probability"] == 3.0
    negative = _recipe_request(tmp_path, _spec(sources=[{
        "texture": "res://assets/generated/tileset/grass/atlas.png",
        "tiles": [{"coords": [0, 0], "probability": -0.1}],
    }]))
    with pytest.raises(CompilerError, match="probability must be non-negative"):
        compiler._recipe(negative)


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"sources": [{"texture": "res://assets/generated/tileset/grass/atlas.png", "tiles": [{"coords": [0, 0], "probabilty": 0.25}]}]}, "unsupported fields: probabilty"),
        ({"sources": [{"texture": "res://assets/generated/tileset/grass/atlas.png", "tiles": [{"coords": [0, 0], "alternatives": [{"id": 1, "z-index": 2}]}]}]}, "unsupported fields: z-index"),
        ({"physics_layers": [{"collision-layer": 1}]}, "unsupported fields: collision-layer"),
        ({"terrain_sets": [{"terrains": [{"name": "grass", "colour": [1, 1, 1]}]}]}, "unsupported fields: colour"),
    ],
)
def test_tileset_recipe_rejects_unknown_recipe_fields(tmp_path, changes, message):
    with pytest.raises(CompilerError, match=message):
        compiler._recipe(_recipe_request(tmp_path, _spec(**changes)))


def test_tileset_recipe_rejects_invalid_peering_bits_for_shape_and_mode(tmp_path):
    source = "res://assets/generated/tileset/grass/atlas.png"
    invalid_square = _recipe_request(tmp_path, _spec(terrain_sets=[{"mode": 0, "terrains": [{"name": "grass"}]}], sources=[{
        "texture": source, "tiles": [{"coords": [0, 0], "terrain_set": 0, "peering_bits": [{"bit": 2, "terrain": 0}]}],
    }]))
    invalid_corners = _recipe_request(tmp_path, _spec(terrain_sets=[{"mode": 1, "terrains": [{"name": "grass"}]}], sources=[{
        "texture": source, "tiles": [{"coords": [0, 0], "terrain_set": 0, "peering_bits": [{"bit": 0, "terrain": 0}]}],
    }]))
    valid_square = _recipe_request(tmp_path, _spec(terrain_sets=[{"mode": 0, "terrains": [{"name": "grass"}]}], sources=[{
        "texture": source, "tiles": [{"coords": [0, 0], "terrain_set": 0, "peering_bits": [{"bit": 3, "terrain": 0}]}],
    }]))
    with pytest.raises(CompilerError, match="invalid for the tile_shape and terrain mode"):
        compiler._recipe(invalid_square)
    with pytest.raises(CompilerError, match="invalid for the tile_shape and terrain mode"):
        compiler._recipe(invalid_corners)
    compiler._recipe(valid_square)


def test_tileset_recipe_rejects_duplicate_custom_data_layer_names_and_empty_declared_durations(tmp_path):
    duplicate_names = _recipe_request(tmp_path, _spec(
        custom_data_layers=[{"name": "cost", "type": 2}, {"name": "cost", "type": 3}],
    ))
    empty_durations = _recipe_request(tmp_path, _spec(sources=[{
        "texture": "res://assets/generated/tileset/grass/atlas.png",
        "tiles": [{"coords": [0, 0], "animation": {"frames_count": 2, "frame_durations": []}}],
    }]))
    with pytest.raises(CompilerError, match="layer names must be unique"):
        compiler._recipe(duplicate_names)
    with pytest.raises(CompilerError, match="frame_durations must declare every frame"):
        compiler._recipe(empty_durations)


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

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return Result()

    monkeypatch.setattr(compiler.subprocess, "run", fake_run)
    assert compiler.compile_tileset(request) == {"sources": 1, "tile_size": [16, 16]}
    assert calls[0][0][-1] == "--import"
    assert "--script" in calls[1][0]
    for _args, kwargs in calls:
        assert kwargs["encoding"] == "utf-8"
        assert kwargs["errors"] == "replace"

    GodotProbe("godot")._run(["godot", "--version"], timeout=1)
    assert calls[-1][1]["encoding"] == "utf-8"
    assert calls[-1][1]["errors"] == "replace"


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


def test_tileset_real_godot_handles_multiple_sources_defaults_and_polygon_float32(godot_bin, godot_project):
    for name in ("first", "second"):
        source = godot_project / f"assets/generated/tileset/grass/{name}.png"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(_png(32, 16))
    integer_points = [[0, 0], [16, 0], [0, 16]]
    decimal_points = [[0.3, 0.7], [15.5, 0.7], [0.3, 15.2]]
    request = CompileRequest(
        production_family="tileset", asset_id="grass", source_layout_type="tile_atlas",
        source_path="res://assets/generated/tileset/grass/first.png", artifact_type="TileSet",
        artifact_path="res://assets/generated/tileset/grass/matrix.tres", project_root=godot_project,
        spec={
            "godot_path": godot_bin, "tile_size": [16, 16],
            "physics_layers": [{}], "navigation_layers": [{}], "occlusion_layers": [{}],
            "custom_data_layers": [
                {"name": "enabled", "type": 1}, {"name": "count", "type": 2},
                {"name": "weight", "type": 3}, {"name": "label", "type": 4},
            ],
            "terrain_sets": [{"terrains": [{"name": "grass"}]}],
            "sources": [
                {"id": 3, "texture": "res://assets/generated/tileset/grass/first.png", "region_size": [16, 16], "tiles": [
                    {"coords": [0, 0], "terrain_set": 0, "terrain": 0,
                     "custom_data": [{"layer": 0, "value": True}],
                     "collision_polygons": [{"layer": 0, "points": integer_points}],
                     "occlusion_polygons": [{"layer": 0, "points": integer_points}],
                     "navigation_polygons": [{"layer": 0, "points": integer_points}]},
                    {"coords": [1, 0]},
                ]},
                {"id": 4, "texture": "res://assets/generated/tileset/grass/second.png", "region_size": [16, 16], "tiles": [
                    {"coords": [0, 0], "terrain_set": 0, "terrain": 0,
                     "alternatives": [{"id": 1, "terrain_set": 0, "terrain": 0,
                         "custom_data": [{"layer": 3, "value": "alt"}],
                         "collision_polygons": [{"layer": 0, "points": decimal_points}],
                         "occlusion_polygons": [{"layer": 0, "points": decimal_points}],
                         "navigation_polygons": [{"layer": 0, "points": decimal_points}]}]},
                    {"coords": [1, 0]},
                ]},
            ],
        },
    )
    registry = CompilerRegistry()
    compiler.register_into(registry)
    registry.compile(request)
    report = GodotProbe(godot_bin).probe(
        godot_project, [ProbeRequest(request.artifact_path, "TileSet", ("tileset",))]
    )
    facts = report.resources[0].structure["tileset"]
    assert facts["source_count"] == 2
    assert [len(source["tiles"]) for source in facts["sources"]] == [2, 2]
    assert facts["sources"][0]["tiles"][1]["custom_data"] == [False, 0, 0.0, ""]
    alternative = facts["sources"][1]["tiles"][0]["alternatives"][0]
    assert alternative["custom_data"] == [False, 0, 0.0, "alt"]
    assert alternative["collision_polygons"][0][0][0] == pytest.approx([0.3, 0.7], abs=1e-6)
    structures.validate_tileset(StructureRequest(
        production_family="tileset", asset_id="grass", source_layout_type="tile_atlas",
        source_path=request.source_path, artifact_type="TileSet", artifact_path=request.artifact_path,
        project_root=godot_project, probe=report.resources[0], spec=request.spec,
    ))
    alternative["collision_polygons"][0][0][0] = [0.7, 0.7]
    with pytest.raises(ValidationError, match="alternative data"):
        structures.validate_tileset(StructureRequest(
            production_family="tileset", asset_id="grass", source_layout_type="tile_atlas",
            source_path=request.source_path, artifact_type="TileSet", artifact_path=request.artifact_path,
            project_root=godot_project, probe=report.resources[0], spec=request.spec,
        ))


def test_tileset_real_godot_validates_collision_polygons_and_rejects_empty_ones_before_invocation(
    godot_bin, godot_project, monkeypatch,
):
    source = godot_project / "assets/generated/tileset/grass/atlas.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(_png(16, 16))

    def request_for(points, binary):
        return CompileRequest(
            production_family="tileset", asset_id="grass", source_layout_type="tile_atlas",
            source_path="res://assets/generated/tileset/grass/atlas.png", artifact_type="TileSet",
            artifact_path="res://assets/generated/tileset/grass/collision.tres", project_root=godot_project,
            spec={"godot_path": binary, "tile_size": [16, 16], "physics_layers": [{}], "sources": [{
                "texture": "res://assets/generated/tileset/grass/atlas.png",
                "tiles": [{"coords": [0, 0], "collision_polygons": [{"layer": 0, "points": points}]}],
            }]},
        )

    valid = request_for([[0, 0], [16, 0], [0, 16]], godot_bin)
    compiler.compile_tileset(valid)
    report = GodotProbe(godot_bin).probe(
        godot_project, [ProbeRequest(valid.artifact_path, "TileSet", ("tileset",))]
    )
    structures.validate_tileset(StructureRequest(
        production_family="tileset", asset_id="grass", source_layout_type="tile_atlas",
        source_path=valid.source_path, artifact_type="TileSet", artifact_path=valid.artifact_path,
        project_root=godot_project, probe=report.resources[0], spec=valid.spec,
    ))

    def must_not_invoke_godot(*args, **kwargs):
        raise AssertionError("empty collision polygons must fail during L2 before Godot is invoked")

    monkeypatch.setattr(compiler.subprocess, "run", must_not_invoke_godot)
    with pytest.raises(CompilerError, match="collision polygon points must contain at least three points"):
        compiler.compile_tileset(request_for([], "not-a-godot-binary"))


def test_compile_tileset_does_not_mutate_nested_spec_across_direct_calls(godot_bin, godot_project):
    source = godot_project / "assets/generated/tileset/grass/atlas.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(_png(16, 16))
    request = CompileRequest(
        production_family="tileset", asset_id="grass", source_layout_type="tile_atlas",
        source_path="res://assets/generated/tileset/grass/atlas.png", artifact_type="TileSet",
        artifact_path="res://assets/generated/tileset/grass/stable.tres", project_root=godot_project,
        spec={"godot_path": godot_bin, "tile_size": [16, 16], "sources": [{
            "texture": "res://assets/generated/tileset/grass/atlas.png",
            "tiles": [{"coords": [0, 0], "animation": {"mode": "random_start_times", "frames_count": 1}}],
        }]},
    )
    compiler.compile_tileset(request)
    compiler.compile_tileset(request)
    assert request.spec["sources"][0]["tiles"][0]["animation"] == {
        "mode": "random_start_times", "frames_count": 1,
    }


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
