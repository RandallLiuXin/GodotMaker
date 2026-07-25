import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_atlas_assemble import AtlasAssemblyError, assemble_atlas  # noqa: E402


def write_png(path: Path, size: tuple[int, int], color: tuple[int, int, int, int]):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, color).save(path)


def write_declaration(path: Path, slots: list[dict], size=(12, 8)):
    path.write_text(
        json.dumps({"version": 1, "atlas": {"width": size[0], "height": size[1]}, "slots": slots}),
        encoding="utf-8",
    )


def valid_slots():
    return [
        {"name": "button", "rect": [0, 0, 4, 4], "source": "button.png"},
        {"name": "icon", "rect": [6, 2, 2, 3], "source": "icon.png", "pivot": [0, 1]},
    ]


def prepare_valid_declaration(tmp_path: Path) -> Path:
    write_png(tmp_path / "button.png", (4, 4), (255, 0, 0, 255))
    write_png(tmp_path / "icon.png", (2, 3), (0, 255, 0, 128))
    declaration = tmp_path / "slots.json"
    write_declaration(declaration, valid_slots())
    return declaration


def test_assemble_atlas_places_multiple_explicit_slots_and_writes_metadata(tmp_path):
    declaration = prepare_valid_declaration(tmp_path)

    result = assemble_atlas(
        declaration,
        Path("assets/generated/ui-kit/main_atlas/main_atlas.png"),
        Path("assets/generated/ui-kit/main_atlas/main_atlas.json"),
        project_root=tmp_path,
    )

    assert result["ok"] is True
    assert result["atlas_path"] == "res://assets/generated/ui-kit/main_atlas/main_atlas.png"
    assert result["slot_count"] == 2
    atlas = Image.open(tmp_path / "assets/generated/ui-kit/main_atlas/main_atlas.png")
    try:
        assert atlas.size == (12, 8)
        assert atlas.getpixel((0, 0)) == (255, 0, 0, 255)
        assert atlas.getpixel((6, 2)) == (0, 255, 0, 128)
        assert atlas.getpixel((5, 2))[3] == 0
    finally:
        atlas.close()
    metadata = json.loads((tmp_path / "assets/generated/ui-kit/main_atlas/main_atlas.json").read_text())
    assert metadata == {
        "version": 1,
        "atlas_path": "res://assets/generated/ui-kit/main_atlas/main_atlas.png",
        "regions": [
            {"name": "button", "rect": [0, 0, 4, 4], "pivot": [0.5, 0.5], "nine_slice": None},
            {"name": "icon", "rect": [6, 2, 2, 3], "pivot": [0.0, 1.0], "nine_slice": None},
        ],
    }


def test_assemble_atlas_is_reproducible_and_metadata_order_is_stable(tmp_path):
    declaration = prepare_valid_declaration(tmp_path)
    atlas = Path("out/atlas.png")
    metadata = Path("out/atlas.json")
    first = assemble_atlas(declaration, atlas, metadata, project_root=tmp_path)
    first_png = (tmp_path / atlas).read_bytes()
    first_json = (tmp_path / metadata).read_bytes()
    second = assemble_atlas(declaration, atlas, metadata, project_root=tmp_path)

    assert first == second
    assert (tmp_path / atlas).read_bytes() == first_png
    assert (tmp_path / metadata).read_bytes() == first_json


@pytest.mark.parametrize(
    ("slots", "message"),
    [
        ([{"name": "one", "rect": [0, 0, 4, 4], "source": "button.png"}, {"name": "two", "rect": [3, 0, 4, 4], "source": "button.png"}], "overlaps"),
        ([{"name": "one", "rect": [10, 0, 4, 4], "source": "button.png"}], "outside"),
        ([{"name": "one", "rect": [0, 0, 4, 4], "source": "missing.png"}], "missing"),
        ([{"name": "one", "rect": [0, 0, 3, 4], "source": "button.png"}], "does not match"),
    ],
)
def test_assemble_atlas_fails_closed_for_invalid_slot_declarations(tmp_path, slots, message):
    write_png(tmp_path / "button.png", (4, 4), (255, 0, 0, 255))
    declaration = tmp_path / "slots.json"
    write_declaration(declaration, slots)
    output = tmp_path / "atlas.png"

    with pytest.raises(AtlasAssemblyError, match=message):
        assemble_atlas(declaration, output, tmp_path / "atlas.json", project_root=tmp_path)
    assert not output.exists()


def test_assemble_atlas_rejects_implicit_or_unsupported_slot_features(tmp_path):
    write_png(tmp_path / "button.png", (4, 4), (255, 0, 0, 255))
    declaration = tmp_path / "slots.json"
    write_declaration(
        declaration,
        [{"name": "button", "rect": [0, 0, 4, 4], "source": "button.png", "trim": True}],
    )
    with pytest.raises(AtlasAssemblyError, match="unexpected fields"):
        assemble_atlas(declaration, tmp_path / "atlas.png", tmp_path / "atlas.json", project_root=tmp_path)


def test_cli_outputs_json(tmp_path):
    declaration = prepare_valid_declaration(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            str(TOOLS_DIR / "asset_atlas_assemble.py"),
            "--declaration", str(declaration),
            "--atlas-out", "assets/generated/ui-kit/main_atlas/main_atlas.png",
            "--metadata-out", "assets/generated/ui-kit/main_atlas/main_atlas.json",
            "--project-root", str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["ok"] is True
