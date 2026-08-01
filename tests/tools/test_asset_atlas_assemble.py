import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import asset_atlas_assemble as atlas_assemble  # noqa: E402
from asset_atlas_assemble import AtlasAssemblyError, assemble_atlas  # noqa: E402
from asset_image_finalize import finalize_image_asset  # noqa: E402


FAMILY = "ui-kit"
ASSET_ID = "main_atlas"
OUTPUT_DIR = Path("assets/generated") / FAMILY / ASSET_ID
ATLAS_OUTPUT = OUTPUT_DIR / "main_atlas.png"
METADATA_OUTPUT = OUTPUT_DIR / "main_atlas.json"


def write_png(path: Path, size: tuple[int, int], color: tuple[int, int, int, int]):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, color).save(path)


def write_declaration(path: Path, slots: list[dict], size=(12, 8)):
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "atlas": {"width": size[0], "height": size[1]},
                "slots": slots,
            }
        ),
        encoding="utf-8",
    )


def valid_slots():
    return [
        {"name": "button", "rect": [0, 0, 4, 4], "source": "button.png"},
        {"name": "icon", "rect": [6, 2, 2, 3], "source": "icon.png", "pivot": [0, 1]},
    ]


def prepare_valid_declaration(tmp_path: Path) -> Path:
    button = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
    button.putpixel((1, 1), (255, 64, 32, 0))
    button.save(tmp_path / "button.png")
    write_png(tmp_path / "icon.png", (2, 3), (0, 255, 0, 128))
    declaration = tmp_path / "slots.json"
    write_declaration(declaration, valid_slots())
    return declaration


def assemble(tmp_path: Path, declaration: Path, atlas=ATLAS_OUTPUT, metadata=METADATA_OUTPUT):
    return assemble_atlas(
        declaration,
        atlas,
        metadata,
        production_family=FAMILY,
        asset_id=ASSET_ID,
        project_root=tmp_path,
    )


def test_assemble_atlas_places_multiple_explicit_slots_and_preserves_pixels(tmp_path):
    declaration = prepare_valid_declaration(tmp_path)

    result = assemble(tmp_path, declaration)

    assert result["ok"] is True
    assert result["atlas_path"] == "res://assets/generated/ui-kit/main_atlas/main_atlas.png"
    assert result["slot_count"] == 2
    atlas = Image.open(tmp_path / ATLAS_OUTPUT)
    try:
        assert atlas.size == (12, 8)
        assert atlas.getpixel((0, 0)) == (255, 0, 0, 255)
        assert atlas.getpixel((1, 1)) == (255, 64, 32, 0)
        assert atlas.getpixel((6, 2)) == (0, 255, 0, 128)
        assert atlas.getpixel((5, 2)) == (0, 0, 0, 0)
    finally:
        atlas.close()
    metadata = json.loads((tmp_path / METADATA_OUTPUT).read_text())
    assert metadata == {
        "version": 1,
        "atlas_path": "res://assets/generated/ui-kit/main_atlas/main_atlas.png",
        "regions": [
            {
                "name": "button",
                "rect": [0, 0, 4, 4],
                "pivot": [0.5, 0.5],
                "nine_slice": None,
            },
            {
                "name": "icon",
                "rect": [6, 2, 2, 3],
                "pivot": [0.0, 1.0],
                "nine_slice": None,
            },
        ],
    }


def test_finalize_mixed_candidate_sizes_before_fixed_slot_assembly(tmp_path):
    """Each prop is fit independently; the assembler only copies fixed slots."""
    write_png(tmp_path / "candidates" / "wide.png", (8, 4), (240, 80, 40, 255))
    write_png(tmp_path / "candidates" / "tall.png", (4, 8), (40, 160, 220, 255))
    finalize_image_asset(
        tmp_path / "candidates" / "wide.png",
        tmp_path / "normalized" / "wide.png",
        resize="10x10",
    )
    finalize_image_asset(
        tmp_path / "candidates" / "tall.png",
        tmp_path / "normalized" / "tall.png",
        resize="10x10",
    )
    declaration = tmp_path / "slots.json"
    write_declaration(
        declaration,
        [
            {"name": "wide", "rect": [0, 0, 10, 10], "source": "normalized/wide.png"},
            {"name": "tall", "rect": [12, 0, 10, 10], "source": "normalized/tall.png"},
        ],
        size=(22, 10),
    )

    result = assemble(tmp_path, declaration)

    assert result["regions"] == [
        {"name": "tall", "rect": [12, 0, 10, 10], "pivot": [0.5, 0.5], "nine_slice": None},
        {"name": "wide", "rect": [0, 0, 10, 10], "pivot": [0.5, 0.5], "nine_slice": None},
    ]
    with Image.open(tmp_path / "normalized" / "wide.png") as wide, Image.open(
        tmp_path / "normalized" / "tall.png"
    ) as tall, Image.open(tmp_path / ATLAS_OUTPUT) as atlas:
        assert wide.size == tall.size == (10, 10)
        assert wide.getchannel("A").getbbox() == (0, 2, 10, 7)
        assert tall.getchannel("A").getbbox() == (2, 0, 7, 10)
        assert atlas.crop((0, 0, 10, 10)).tobytes() == wide.convert("RGBA").tobytes()
        assert atlas.crop((12, 0, 22, 10)).tobytes() == tall.convert("RGBA").tobytes()


def test_assemble_atlas_accepts_slots_flush_with_the_atlas_boundary(tmp_path):
    write_png(tmp_path / "edge.png", (4, 4), (30, 40, 50, 255))
    declaration = tmp_path / "slots.json"
    write_declaration(
        declaration,
        [{"name": "edge", "rect": [8, 4, 4, 4], "source": "edge.png"}],
    )

    assemble(tmp_path, declaration)

    atlas = Image.open(tmp_path / ATLAS_OUTPUT)
    try:
        assert atlas.getpixel((11, 7)) == (30, 40, 50, 255)
    finally:
        atlas.close()


def test_assemble_atlas_is_reproducible_and_metadata_order_is_stable(tmp_path):
    declaration = prepare_valid_declaration(tmp_path)
    first = assemble(tmp_path, declaration)
    first_png = (tmp_path / ATLAS_OUTPUT).read_bytes()
    first_json = (tmp_path / METADATA_OUTPUT).read_bytes()
    second = assemble(tmp_path, declaration)

    assert first == second
    assert (tmp_path / ATLAS_OUTPUT).read_bytes() == first_png
    assert (tmp_path / METADATA_OUTPUT).read_bytes() == first_json


@pytest.mark.parametrize(
    ("slots", "message"),
    [
        (
            [
                {"name": "one", "rect": [0, 0, 4, 4], "source": "button.png"},
                {"name": "two", "rect": [3, 0, 4, 4], "source": "button.png"},
            ],
            "overlaps",
        ),
        ([{"name": "one", "rect": [10, 0, 4, 4], "source": "button.png"}], "outside"),
        ([{"name": "one", "rect": [0, 0, 4, 4], "source": "missing.png"}], "missing"),
        (
            [{"name": "one", "rect": [0, 0, 3, 4], "source": "button.png"}],
            "does not match",
        ),
        (
            [
                {"name": "one", "rect": [0, 0, 4, 4], "source": "button.png"},
                {"name": "one", "rect": [4, 0, 4, 4], "source": "button.png"},
            ],
            "duplicated",
        ),
        ([{"name": "../outside", "rect": [0, 0, 4, 4], "source": "button.png"}], "safe path segment"),
        ([{"name": "one", "rect": [0, 0, 0, 4], "source": "button.png"}], "positive"),
    ],
)
def test_assemble_atlas_fails_closed_for_invalid_slot_declarations(tmp_path, slots, message):
    write_png(tmp_path / "button.png", (4, 4), (255, 0, 0, 255))
    declaration = tmp_path / "slots.json"
    write_declaration(declaration, slots)

    with pytest.raises(AtlasAssemblyError, match=message):
        assemble(tmp_path, declaration)
    assert not (tmp_path / ATLAS_OUTPUT).exists()
    assert not (tmp_path / METADATA_OUTPUT).exists()


@pytest.mark.parametrize("feature", ["trim", "rotate", "padding", "nine_slice"])
def test_assemble_atlas_rejects_implicit_or_unsupported_slot_features(tmp_path, feature):
    write_png(tmp_path / "button.png", (4, 4), (255, 0, 0, 255))
    declaration = tmp_path / "slots.json"
    slot = {"name": "button", "rect": [0, 0, 4, 4], "source": "button.png"}
    slot[feature] = True
    write_declaration(declaration, [slot])

    with pytest.raises(AtlasAssemblyError, match="unexpected fields"):
        assemble(tmp_path, declaration)


@pytest.mark.parametrize("source_name", ["button.jpg", "not_png.png"])
def test_assemble_atlas_rejects_non_png_sources(tmp_path, source_name):
    source = tmp_path / source_name
    Image.new("RGB", (4, 4), (255, 0, 0)).save(source, format="JPEG")
    declaration = tmp_path / "slots.json"
    write_declaration(
        declaration,
        [{"name": "button", "rect": [0, 0, 4, 4], "source": source_name}],
    )

    with pytest.raises(AtlasAssemblyError, match="PNG"):
        assemble(tmp_path, declaration)


def test_assemble_atlas_rejects_outside_source_and_output_paths(tmp_path):
    outside = tmp_path.parent / "outside.png"
    write_png(outside, (4, 4), (255, 0, 0, 255))
    declaration = tmp_path / "slots.json"
    write_declaration(
        declaration,
        [{"name": "button", "rect": [0, 0, 4, 4], "source": str(outside)}],
    )
    with pytest.raises(AtlasAssemblyError, match="outside the project root"):
        assemble(tmp_path, declaration)

    declaration = prepare_valid_declaration(tmp_path)
    with pytest.raises(AtlasAssemblyError, match="must be written under"):
        assemble(tmp_path, declaration, Path("addons/icon.png"), METADATA_OUTPUT)


def test_assemble_atlas_rejects_using_its_output_as_a_source(tmp_path):
    write_png(tmp_path / ATLAS_OUTPUT, (4, 4), (255, 0, 0, 255))
    declaration = tmp_path / "slots.json"
    write_declaration(
        declaration,
        [{"name": "button", "rect": [0, 0, 4, 4], "source": ATLAS_OUTPUT.as_posix()}],
    )
    original = (tmp_path / ATLAS_OUTPUT).read_bytes()

    with pytest.raises(AtlasAssemblyError, match="must not be the atlas output"):
        assemble(tmp_path, declaration)
    assert (tmp_path / ATLAS_OUTPUT).read_bytes() == original


def test_assemble_atlas_rejects_an_excessively_large_atlas(tmp_path):
    declaration = tmp_path / "slots.json"
    write_declaration(
        declaration,
        [{"name": "button", "rect": [0, 0, 4, 4], "source": "button.png"}],
        size=(200000, 200000),
    )

    with pytest.raises(AtlasAssemblyError, match="safety limit"):
        assemble(tmp_path, declaration)


def test_assemble_atlas_rolls_back_both_outputs_when_second_commit_fails(
    tmp_path, monkeypatch
):
    declaration = prepare_valid_declaration(tmp_path)
    write_png(tmp_path / ATLAS_OUTPUT, (12, 8), (10, 20, 30, 255))
    (tmp_path / METADATA_OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / METADATA_OUTPUT).write_text('{"old": true}\n', encoding="utf-8")
    original_png = (tmp_path / ATLAS_OUTPUT).read_bytes()
    original_json = (tmp_path / METADATA_OUTPUT).read_bytes()
    real_replace = atlas_assemble.os.replace
    metadata_path = (tmp_path / METADATA_OUTPUT).resolve()
    failed = False

    def fail_metadata_commit(source, destination):
        nonlocal failed
        if Path(destination).resolve() == metadata_path and not failed:
            failed = True
            raise OSError("simulated metadata commit failure")
        return real_replace(source, destination)

    monkeypatch.setattr(atlas_assemble.os, "replace", fail_metadata_commit)

    with pytest.raises(AtlasAssemblyError, match="rolled back"):
        assemble(tmp_path, declaration)
    assert (tmp_path / ATLAS_OUTPUT).read_bytes() == original_png
    assert (tmp_path / METADATA_OUTPUT).read_bytes() == original_json


def test_assemble_atlas_keeps_backup_when_commit_and_rollback_fail(
    tmp_path, monkeypatch
):
    declaration = prepare_valid_declaration(tmp_path)
    atlas_output = tmp_path / ATLAS_OUTPUT
    metadata_output = tmp_path / METADATA_OUTPUT
    write_png(atlas_output, (12, 8), (10, 20, 30, 255))
    metadata_output.parent.mkdir(parents=True, exist_ok=True)
    metadata_output.write_text('{"old": true}\n', encoding="utf-8")
    original_png = atlas_output.read_bytes()
    real_replace = atlas_assemble.os.replace
    atlas_path = atlas_output.resolve()
    metadata_path = metadata_output.resolve()
    metadata_commit_failed = False
    rollback_failed = False

    def fail_commit_and_rollback(source, destination):
        nonlocal metadata_commit_failed, rollback_failed
        destination_path = Path(destination).resolve()
        if destination_path == metadata_path and not metadata_commit_failed:
            metadata_commit_failed = True
            raise OSError("simulated metadata commit failure")
        if (
            destination_path == atlas_path
            and metadata_commit_failed
            and not rollback_failed
        ):
            rollback_failed = True
            raise OSError("simulated atlas rollback failure")
        return real_replace(source, destination)

    monkeypatch.setattr(atlas_assemble.os, "replace", fail_commit_and_rollback)

    with pytest.raises(AtlasAssemblyError, match="rollback failed") as exc_info:
        assemble(tmp_path, declaration)

    backups = [path for path in atlas_output.parent.glob("*.png") if path != atlas_output]
    assert len(backups) == 1
    assert backups[0].read_bytes() == original_png
    assert str(atlas_output) in str(exc_info.value)
    assert str(backups[0]) in str(exc_info.value)
    assert list(metadata_output.parent.glob("*.json")) == [metadata_output]


def test_cli_reports_write_failures_as_json_and_leaves_no_orphan_atlas(tmp_path):
    declaration = prepare_valid_declaration(tmp_path)
    blocked_parent = tmp_path / OUTPUT_DIR / "blocked"
    blocked_parent.parent.mkdir(parents=True, exist_ok=True)
    blocked_parent.write_text("not a directory", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(TOOLS_DIR / "asset_atlas_assemble.py"),
            "--declaration",
            str(declaration),
            "--atlas-out",
            str(ATLAS_OUTPUT),
            "--metadata-out",
            str(OUTPUT_DIR / "blocked" / "metadata.json"),
            "--family",
            FAMILY,
            "--asset-id",
            ASSET_ID,
            "--project-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert json.loads(result.stdout)["ok"] is False
    assert not (tmp_path / ATLAS_OUTPUT).exists()


def test_cli_outputs_json(tmp_path):
    declaration = prepare_valid_declaration(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            str(TOOLS_DIR / "asset_atlas_assemble.py"),
            "--declaration",
            str(declaration),
            "--atlas-out",
            str(ATLAS_OUTPUT),
            "--metadata-out",
            str(METADATA_OUTPUT),
            "--family",
            FAMILY,
            "--asset-id",
            ASSET_ID,
            "--project-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["ok"] is True
