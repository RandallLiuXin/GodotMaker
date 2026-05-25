import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_image_finalize import ImageFinalizeError, finalize_image_asset  # noqa: E402


def make_png(path: Path, size=(8, 6), color=(255, 200, 0, 255)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, color).save(path)


def test_finalize_copies_and_reports_image_metadata(tmp_path):
    source = tmp_path / "generated" / "coin.png"
    output = tmp_path / "assets" / "coin.png"
    make_png(source, size=(8, 6))

    result = finalize_image_asset(source, output, label="coin")

    assert result["ok"] is True
    assert result["path"] == str(output)
    assert result["label"] == "coin"
    assert result["asset_id"] == "coin"
    assert result["width"] == 8
    assert result["height"] == 6
    assert output.exists()


def test_finalize_resizes_to_requested_dimensions(tmp_path):
    source = tmp_path / "generated" / "gem.png"
    output = tmp_path / "assets" / "gem.png"
    make_png(source, size=(16, 12))

    result = finalize_image_asset(source, output, resize="4x3")

    assert result["width"] == 4
    assert result["height"] == 3
    with Image.open(output) as image:
        assert image.size == (4, 3)


def test_finalize_rejects_non_image_source(tmp_path):
    source = tmp_path / "generated" / "not-image.txt"
    source.parent.mkdir()
    source.write_text("not an image", encoding="utf-8")

    with pytest.raises(ImageFinalizeError):
        finalize_image_asset(source, tmp_path / "assets" / "out.png")


def test_cli_outputs_json(tmp_path):
    source = tmp_path / "generated" / "coin.png"
    output = tmp_path / "assets" / "coin.png"
    make_png(source)

    result = subprocess.run(
        [
            sys.executable,
            str(TOOLS_DIR / "asset_image_finalize.py"),
            "--source",
            str(source),
            "--out",
            str(output),
            "--resize",
            "2x2",
            "--label",
            "coin",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["label"] == "coin"
    assert data["asset_id"] == "coin"
    assert data["width"] == 2
    assert data["height"] == 2
    assert output.exists()


def test_finalize_pads_instead_of_stretching_on_aspect_mismatch(tmp_path):
    # A square source forced into a wide target must NOT be stretched: it is
    # scaled proportionally and centered on a transparent canvas.
    source = tmp_path / "generated" / "hero.png"
    output = tmp_path / "assets" / "img" / "hero.png"
    make_png(source, size=(10, 10), color=(255, 0, 0, 255))

    result = finalize_image_asset(source, output, resize="10x4")

    assert (result["width"], result["height"]) == (10, 4)
    with Image.open(output) as image:
        assert image.size == (10, 4)
        rgba = image.convert("RGBA")
        # Centered art stays opaque...
        assert rgba.getpixel((5, 2))[3] == 255
        # ...while the horizontal padding is fully transparent.
        assert rgba.getpixel((0, 2))[3] == 0
        assert rgba.getpixel((9, 2))[3] == 0


def test_finalize_keeps_matching_aspect_without_padding(tmp_path):
    source = tmp_path / "generated" / "bar.png"
    output = tmp_path / "assets" / "img" / "bar.png"
    make_png(source, size=(8, 4), color=(0, 128, 255, 255))

    result = finalize_image_asset(source, output, resize="4x2")

    assert (result["width"], result["height"]) == (4, 2)
    with Image.open(output) as image:
        rgba = image.convert("RGBA")
        # Same aspect ratio -> no transparent padding anywhere.
        assert all(
            rgba.getpixel((x, y))[3] == 255 for x in range(4) for y in range(2)
        )


def test_finalize_archives_original_by_default(tmp_path):
    source = tmp_path / "generated" / "coin.png"
    output = tmp_path / "assets" / "img" / "coin.png"
    make_png(source, size=(16, 8))

    result = finalize_image_asset(source, output, resize="4x4")

    origin = tmp_path / "assets" / "origin" / "coin.png"
    assert result["origin"] == str(origin)
    assert origin.exists()
    with Image.open(origin) as image:
        # Original resolution preserved for comparison/debugging.
        assert image.size == (16, 8)


def test_finalize_skips_origin_when_disabled(tmp_path):
    source = tmp_path / "generated" / "coin.png"
    output = tmp_path / "assets" / "img" / "coin.png"
    make_png(source, size=(16, 8))

    result = finalize_image_asset(source, output, resize="4x4", archive_original=False)

    assert "origin" not in result
    assert not (tmp_path / "assets" / "origin" / "coin.png").exists()


def test_finalize_skips_origin_without_resize(tmp_path):
    source = tmp_path / "generated" / "coin.png"
    output = tmp_path / "assets" / "img" / "coin.png"
    make_png(source, size=(16, 8))

    result = finalize_image_asset(source, output)

    assert "origin" not in result
    assert not (tmp_path / "assets" / "origin" / "coin.png").exists()


def test_cli_no_origin_flag(tmp_path):
    source = tmp_path / "generated" / "coin.png"
    output = tmp_path / "assets" / "img" / "coin.png"
    make_png(source)

    result = subprocess.run(
        [
            sys.executable,
            str(TOOLS_DIR / "asset_image_finalize.py"),
            "--source",
            str(source),
            "--out",
            str(output),
            "--resize",
            "2x2",
            "--no-origin",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "origin" not in data
    assert not (tmp_path / "assets" / "origin" / "coin.png").exists()
