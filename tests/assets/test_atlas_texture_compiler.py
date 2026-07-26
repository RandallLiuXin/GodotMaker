"""Fixed-slot AtlasTexture compiler contracts."""
import json
import struct
import sys
import zlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "skills" / "assets" / "_shared"
sys.path.insert(0, str(SHARED_DIR))
sys.path.insert(0, str(REPO_ROOT / "tools"))

from asset_compiler import CompileRequest, CompilerError, build_default_registry  # noqa: E402
from asset_compiler import atlas_texture  # noqa: E402
from asset_validation import (  # noqa: E402
    ProbeResult,
    StructureRequest,
    ValidationError,
    validate_atlas_texture,
)


def _png(width: int, height: int) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    pixels = b"\x00" + b"\x80\x40\x20\xff" * width
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(pixels * height))
        + chunk(b"IEND", b"")
    )


def _request(project: Path, logical_asset_id: str = "button", **overrides):
    root = "res://assets/generated/ui-kit/main_atlas"
    values = {
        "production_family": "ui-kit",
        "asset_id": "main_atlas",
        "source_layout_type": "region_atlas",
        "source_path": f"{root}/main_atlas.png",
        "artifact_type": "AtlasTexture",
        "artifact_path": f"{root}/{logical_asset_id}.tres",
        "project_root": project,
        "spec": {
            "metadata_path": f"{root}/main_atlas.json",
            "logical_asset_id": logical_asset_id,
        },
    }
    values.update(overrides)
    return CompileRequest(**values)


@pytest.fixture
def atlas_project(tmp_path: Path) -> Path:
    directory = tmp_path / "assets/generated/ui-kit/main_atlas"
    directory.mkdir(parents=True)
    (directory / "main_atlas.png").write_bytes(_png(12, 8))
    (directory / "main_atlas.json").write_text(
        json.dumps(
            {
                "version": 1,
                "atlas_path": "res://assets/generated/ui-kit/main_atlas/main_atlas.png",
                "regions": [
                    {"name": "button", "rect": [0, 0, 4, 4], "pivot": [0.5, 0.5], "nine_slice": None},
                    {"name": "icon", "rect": [6, 2, 2, 3], "pivot": [0.0, 1.0], "nine_slice": None},
                ],
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_one_fixed_atlas_compiles_multiple_independent_tres(atlas_project):
    registry = build_default_registry()
    button = registry.compile(_request(atlas_project, "button"))
    icon = registry.compile(_request(atlas_project, "icon"))

    assert button.receipt.compiler_id == atlas_texture.COMPILER_ID
    assert button.receipt.details["region"] == [0, 0, 4, 4]
    assert icon.receipt.details["region"] == [6, 2, 2, 3]
    button_tres = (atlas_project / "assets/generated/ui-kit/main_atlas/button.tres").read_text()
    icon_tres = (atlas_project / "assets/generated/ui-kit/main_atlas/icon.tres").read_text()
    assert 'atlas = ExtResource("1_atlas")' in button_tres
    assert "region = Rect2(0, 0, 4, 4)" in button_tres
    assert "region = Rect2(6, 2, 2, 3)" in icon_tres
    assert "margin = Rect2(0, 0, 0, 0)" in button_tres
    assert button_tres != icon_tres


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda data: data.update(atlas_path="res://assets/generated/ui-kit/main_atlas/other.png"), "exactly match"),
        (lambda data: data.__setitem__("regions", [data["regions"][1]]), "no region"),
        (lambda data: data["regions"].__setitem__(0, {**data["regions"][0], "rect": [11, 0, 4, 4]}), "outside atlas bounds"),
        (lambda data: data["regions"].__setitem__(0, {**data["regions"][0], "nine_slice": {}}), "must be null"),
    ],
)
def test_atlas_metadata_fails_closed(atlas_project, mutate, message):
    metadata = atlas_project / "assets/generated/ui-kit/main_atlas/main_atlas.json"
    data = json.loads(metadata.read_text())
    mutate(data)
    metadata.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(CompilerError, match=message):
        build_default_registry().compile(_request(atlas_project))
    assert not (atlas_project / "assets/generated/ui-kit/main_atlas/button.tres").exists()


def test_atlas_texture_rejects_another_output_type(atlas_project):
    request = _request(atlas_project, artifact_type="StyleBoxTexture")
    with pytest.raises(CompilerError, match="requires artifact_type 'AtlasTexture'"):
        atlas_texture.compile_atlas_texture(request)


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        ({"metadata_path": "res://assets/generated/ui-kit/main_atlas/main_atlas.json", "logical_asset_id": "../button"}, "safe path segment"),
        ({"metadata_path": "res://assets/generated/ui-kit/main_atlas/main_atlas.json", "logical_asset_id": "AUX"}, "reserved device name"),
        ({"metadata_path": "res://assets/generated/ui-kit/main_atlas/main_atlas.json", "logical_asset_id": "button\u001f"}, "safe path segment"),
        ({"metadata_path": "res://assets/generated/ui-kit/main_atlas/main_atlas.json", "logical_asset_id": "icon"}, "filename must match"),
    ],
)
def test_atlas_texture_binds_the_logical_id_to_a_safe_output_name(
    atlas_project, spec, message
):
    with pytest.raises(CompilerError, match=message):
        build_default_registry().compile(_request(atlas_project, spec=spec))


def test_l4_rejects_a_loaded_atlas_texture_bound_to_another_png(atlas_project):
    request = _request(atlas_project)
    structure_request = StructureRequest(
        production_family=request.production_family,
        asset_id=request.asset_id,
        source_layout_type=request.source_layout_type,
        source_path=request.source_path,
        artifact_type=request.artifact_type,
        artifact_path=request.artifact_path,
        project_root=request.project_root,
        spec=request.spec,
        probe=ProbeResult(
            res_path=request.artifact_path,
            expected_type="AtlasTexture",
            loaded=True,
            godot_class="AtlasTexture",
            type_matches=True,
            structure={
                "atlas_texture": {
                    "has_atlas": True,
                    "atlas_path": "res://assets/generated/ui-kit/main_atlas/other.png",
                    "region": [0, 0, 4, 4],
                    "margin": [0, 0, 0, 0],
                }
            },
        ),
    )

    with pytest.raises(ValidationError, match="atlas_path"):
        validate_atlas_texture(structure_request)
