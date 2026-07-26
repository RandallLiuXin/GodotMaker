"""StyleBoxTexture compiler contracts for explicit nine-slice recipes."""
import struct
import sys
import zlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "skills" / "assets" / "_shared"
sys.path.insert(0, str(SHARED_DIR))

from asset_compiler import CompileRequest, CompilerError, build_default_registry  # noqa: E402
from asset_compiler import stylebox_texture  # noqa: E402
from asset_validation import (  # noqa: E402
    ProbeResult,
    StructureRequest,
    ValidationError,
    validate_stylebox_texture,
)


def _png(width: int, height: int) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    rows = b"".join(b"\x00" + b"\x80\x40\x20\xff" * width for _ in range(height))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    directory = tmp_path / "assets/generated/ui-kit/panel"
    directory.mkdir(parents=True)
    (directory / "panel.png").write_bytes(_png(16, 12))
    return tmp_path


def _request(project: Path, *, layout: str = "single", **overrides) -> CompileRequest:
    root = "res://assets/generated/ui-kit/panel"
    values = {
        "production_family": "ui-kit",
        "asset_id": "panel",
        "source_layout_type": layout,
        "source_path": f"{root}/panel.png",
        "artifact_type": "StyleBoxTexture",
        "artifact_path": f"{root}/panel.tres",
        "project_root": project,
        "spec": {
            "texture_region": [2, 1, 12, 10],
            "border": [3, 2, 3, 2],
            "expand_margin": [1, 1.5, 2, 0],
            "axis_stretch": {"horizontal": "tile_fit", "vertical": "stretch"},
        },
    }
    values.update(overrides)
    return CompileRequest(**values)


@pytest.mark.parametrize("layout", ["single", "region_atlas"])
def test_compiles_each_legal_layout_from_the_explicit_recipe(project, layout):
    result = build_default_registry().compile(_request(project, layout=layout))

    assert result.receipt.compiler_id == stylebox_texture.COMPILER_ID
    assert result.receipt.details == {
        "texture_path": "res://assets/generated/ui-kit/panel/panel.png",
        "texture_region": [2, 1, 12, 10],
        "border": [3, 2, 3, 2],
        "expand_margin": [1.0, 1.5, 2.0, 0.0],
        "axis_stretch": {"horizontal": "tile_fit", "vertical": "stretch"},
    }
    tres = (project / "assets/generated/ui-kit/panel/panel.tres").read_text(encoding="utf-8")
    assert 'texture = ExtResource("1_texture")' in tres
    assert "region_rect = Rect2(2, 1, 12, 10)" in tres
    assert "texture_margin_left = 3" in tres
    assert "expand_margin_top = 1.5" in tres
    assert "axis_stretch_horizontal = 2" in tres
    assert "axis_stretch_vertical = 0" in tres


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda spec: spec.__setitem__("texture_region", [12, 0, 5, 4]), "outside source PNG bounds"),
        (lambda spec: spec.__setitem__("border", [7, 2, 7, 2]), "exceeds texture_region"),
        (lambda spec: spec.__setitem__("expand_margin", [0, -1, 0, 0]), "finite non-negative"),
        (lambda spec: spec.__setitem__("axis_stretch", {"horizontal": "repeat", "vertical": "stretch"}), "must be one of"),
        (lambda spec: spec.__setitem__("unexpected", True), "contain exactly"),
    ],
)
def test_invalid_recipe_fails_closed_without_an_artifact(project, mutate, message):
    request = _request(project)
    spec = dict(request.spec)
    mutate(spec)
    request = _request(project, spec=spec)

    with pytest.raises(CompilerError, match=message):
        build_default_registry().compile(request)
    assert not (project / "assets/generated/ui-kit/panel/panel.tres").exists()


def test_l4_rejects_a_loaded_stylebox_with_tampered_recipe_facts(project):
    request = _request(project)
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
            expected_type="StyleBoxTexture",
            loaded=True,
            godot_class="StyleBoxTexture",
            type_matches=True,
            structure={
                "stylebox_texture": {
                    "has_texture": True,
                    "texture_path": request.source_path,
                    "texture_region": [2, 1, 12, 10],
                    "border": [3, 2, 3, 2],
                    "expand_margin": [1, 1.5, 2, 0],
                    "axis_stretch": [1, 0],
                }
            },
        ),
    )

    with pytest.raises(ValidationError, match="axis_stretch"):
        validate_stylebox_texture(structure_request)
