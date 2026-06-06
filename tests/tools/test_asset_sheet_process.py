import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_sheet_process import SheetProcessError, process_sheet  # noqa: E402


def make_sheet(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((2, 2, 7, 7), fill=(255, 0, 0, 255))
    draw.rectangle((12, 2, 17, 7), fill=(0, 255, 0, 255))
    draw.rectangle((2, 12, 7, 17), fill=(0, 0, 255, 255))
    image.save(path)


def test_process_sheet_splits_and_reports_cells(tmp_path):
    source = tmp_path / "sheet.png"
    make_sheet(source)

    result = process_sheet(
        source,
        tmp_path / "out",
        grid="2x2",
        names="a,b,c,d",
        report=tmp_path / "report.json",
    )

    assert result["accepted_count"] == 3
    assert result["rejected_count"] == 1
    assert (tmp_path / "out" / "a.png").exists()
    assert (tmp_path / "report.json").exists()
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["rejected"][0]["reason"] == "empty_cell"


def test_process_sheet_rejects_edge_touch_when_requested(tmp_path):
    source = tmp_path / "sheet.png"
    image = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 4, 4), fill=(255, 0, 0, 255))
    image.save(source)

    result = process_sheet(
        source,
        tmp_path / "out",
        grid="1x1",
        names="edge",
        reject_edge_touch=True,
    )

    assert result["accepted_count"] == 0
    assert result["rejected"][0]["reason"] == "edge_touch"
    assert not (tmp_path / "out" / "edge.png").exists()


def test_process_sheet_rejects_non_divisible_grid(tmp_path):
    source = tmp_path / "sheet.png"
    image = Image.new("RGBA", (9, 10), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((1, 1, 3, 3), fill=(255, 0, 0, 255))
    image.save(source)

    with pytest.raises(SheetProcessError, match="divide evenly"):
        process_sheet(source, tmp_path / "out", grid="2x2")


def test_process_sheet_rejects_opaque_source(tmp_path):
    source = tmp_path / "opaque.png"
    Image.new("RGBA", (10, 10), (255, 255, 255, 255)).save(source)

    with pytest.raises(SheetProcessError, match="transparency"):
        process_sheet(source, tmp_path / "out", grid="1x1")


def test_process_sheet_rejects_unsafe_names(tmp_path):
    source = tmp_path / "sheet.png"
    make_sheet(source)

    with pytest.raises(SheetProcessError, match="safe file names"):
        process_sheet(source, tmp_path / "out", grid="2x2", names="a,../b,c,d")


def test_cli_outputs_json(tmp_path):
    source = tmp_path / "sheet.png"
    make_sheet(source)

    result = subprocess.run(
        [
            sys.executable,
            str(TOOLS_DIR / "asset_sheet_process.py"),
            "--source",
            str(source),
            "--out-dir",
            str(tmp_path / "out"),
            "--grid",
            "2x2",
            "--names",
            "a,b,c,d",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["accepted_count"] == 3
