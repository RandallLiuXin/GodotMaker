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
