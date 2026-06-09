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


def make_magenta_sheet(path: Path, *, edge_touch: bool = False, fringe: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (20, 20), (255, 0, 255, 255))
    draw = ImageDraw.Draw(image)
    if fringe:
        draw.rectangle((1, 1, 8, 8), fill=(255, 120, 255, 255))
    draw.rectangle((2, 2, 7, 7), fill=(255, 0, 0, 255))
    draw.rectangle((12, 2, 17, 7), fill=(0, 255, 0, 255))
    draw.rectangle((2, 12, 7, 17), fill=(0, 0, 255, 255))
    if edge_touch:
        draw.rectangle((10, 10, 19, 19), fill=(255, 255, 0, 255))
    image.save(path)


def make_component_sheet(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (24, 12), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((2, 2, 8, 8), fill=(255, 0, 0, 255))
    draw.rectangle((18, 2, 21, 5), fill=(0, 255, 0, 255))
    image.save(path)


def make_autoslice_sheet(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (20, 10), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((2, 2, 13, 7), fill=(255, 0, 0, 255))
    draw.rectangle((16, 2, 18, 7), fill=(0, 255, 0, 255))
    image.save(path)


def visible_colors(image):
    pixels = image.load()
    colors = set()
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue, alpha = pixels[x, y]
            if alpha > 0:
                colors.add((red, green, blue))
    return colors


def test_process_sheet_splits_and_reports_cells(tmp_path):
    source = tmp_path / "sheet.png"
    make_sheet(source)

    result = process_sheet(
        source,
        tmp_path / "out",
        grid="2x2",
        snap_mode="grid",
        names="a,b,c,d",
        asset_id="ui_kit_source",
        tag="v0.1.0",
        report=tmp_path / "report.json",
    )

    assert result["version"] == 1
    assert result["asset_id"] == "ui_kit_source"
    assert result["tag"] == "v0.1.0"
    assert result["strategy"] == "transparent_grid"
    assert result["status"] == "candidate_extracted"
    assert result["accepted_count"] == 3
    assert result["rejected_count"] == 1
    assert result["candidates"][0]["candidate_id"] == "ui_kit_source.a"
    assert result["rejected"][0]["state"] == "rejected"
    assert (tmp_path / "out" / "a.png").exists()
    assert (tmp_path / "report.json").exists()
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["rejected"][0]["reason"] == "empty_cell"
    assert report["candidates"][0]["state"] == "candidate"


def test_process_sheet_splits_magenta_background_source(tmp_path):
    source = tmp_path / "magenta_sheet.png"
    make_magenta_sheet(source)

    result = process_sheet(
        source,
        tmp_path / "out",
        grid="2x2",
        snap_mode="grid",
        names="a,b,c,d",
        asset_id="ui_kit_source",
        tag="v0.1.0",
        background="magenta",
        report=tmp_path / "report.json",
    )

    assert result["strategy"] == "solid_background_grid"
    assert result["background"] == "magenta"
    assert result["cleanup"]["removed_pixels"] > 0
    assert result["accepted_count"] == 3
    assert result["rejected_count"] == 1
    candidate = Image.open(tmp_path / "out" / "a.png").convert("RGBA")
    try:
        assert candidate.getchannel("A").getextrema()[0] == 255
    finally:
        candidate.close()
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["cleanup"]["background"] == "magenta"


def test_process_sheet_largest_component_discards_stray_fragments(tmp_path):
    source = tmp_path / "component_sheet.png"
    make_component_sheet(source)

    result = process_sheet(
        source,
        tmp_path / "out",
        grid="1x1",
        snap_mode="grid",
        names="button",
        asset_id="ui_kit_source",
        component_mode="largest",
        component_padding=1,
        min_component_area=1,
    )

    assert result["accepted_count"] == 1
    accepted = result["accepted"][0]
    assert accepted["component_count"] == 2
    assert accepted["selected_component_area"] == 49
    assert accepted["selected_component_bbox"] == [2, 2, 9, 9]
    assert accepted["crop_bbox"] == [2, 2, 9, 9]
    assert accepted["padded_crop_bbox"] == [1, 1, 10, 10]
    candidate = Image.open(tmp_path / "out" / "button.png").convert("RGBA")
    try:
        assert candidate.size == (9, 9)
        assert visible_colors(candidate) == {(255, 0, 0)}
    finally:
        candidate.close()


def test_process_sheet_all_component_mode_preserves_stray_fragments(tmp_path):
    source = tmp_path / "component_sheet.png"
    make_component_sheet(source)

    result = process_sheet(
        source,
        tmp_path / "out",
        grid="1x1",
        snap_mode="grid",
        names="button",
        asset_id="ui_kit_source",
        component_mode="all",
    )

    assert result["accepted_count"] == 1
    accepted = result["accepted"][0]
    assert accepted["component_count"] == 2
    assert accepted["selected_component_area"] is None
    assert accepted["crop_bbox"] == [2, 2, 22, 9]
    candidate = Image.open(tmp_path / "out" / "button.png").convert("RGBA")
    try:
        assert visible_colors(candidate) == {(255, 0, 0), (0, 255, 0)}
    finally:
        candidate.close()


def test_process_sheet_autoslice_keeps_cross_cell_object_intact(tmp_path):
    source = tmp_path / "autoslice_sheet.png"
    make_autoslice_sheet(source)

    result = process_sheet(
        source,
        tmp_path / "out",
        grid="2x1",
        names="wide_button,right_icon",
        asset_id="ui_kit_source",
        snap_mode="autoslice",
    )

    assert result["snap_mode"] == "autoslice"
    assert result["strategy"] == "transparent_autoslice"
    assert result["accepted_count"] == 2
    wide = result["accepted"][0]
    icon = result["accepted"][1]
    assert wide["name"] == "wide_button"
    assert wide["crop_bbox"] == [2, 2, 14, 8]
    assert wide["width"] == 12
    assert icon["name"] == "right_icon"
    assert icon["crop_bbox"] == [16, 2, 19, 8]
    wide_image = Image.open(tmp_path / "out" / "wide_button.png").convert("RGBA")
    icon_image = Image.open(tmp_path / "out" / "right_icon.png").convert("RGBA")
    try:
        assert visible_colors(wide_image) == {(255, 0, 0)}
        assert visible_colors(icon_image) == {(0, 255, 0)}
    finally:
        wide_image.close()
        icon_image.close()


def test_process_sheet_removes_edge_connected_magenta_fringe(tmp_path):
    source = tmp_path / "magenta_fringe_sheet.png"
    make_magenta_sheet(source, fringe=True)

    result = process_sheet(
        source,
        tmp_path / "out",
        grid="2x2",
        snap_mode="grid",
        names="a,b,c,d",
        asset_id="ui_kit_source",
        background="magenta",
    )

    assert result["cleanup"]["removed_pixels"] > 0
    assert result["cleanup"]["edge_removed_pixels"] > 0
    assert result["accepted"][0]["crop_bbox"] == [2, 2, 8, 8]


def test_process_sheet_rejects_magenta_edge_touch_when_requested(tmp_path):
    source = tmp_path / "magenta_edge.png"
    make_magenta_sheet(source, edge_touch=True)

    result = process_sheet(
        source,
        tmp_path / "out",
        grid="2x2",
        snap_mode="grid",
        names="a,b,c,d",
        background="magenta",
        reject_edge_touch=True,
    )

    assert result["accepted_count"] == 3
    assert result["rejected_count"] == 1
    assert result["rejected"][0]["reason"] == "edge_touch"
    assert not (tmp_path / "out" / "d.png").exists()


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
        snap_mode="grid",
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
        process_sheet(source, tmp_path / "out", grid="2x2", snap_mode="grid")


def test_process_sheet_rejects_opaque_source(tmp_path):
    source = tmp_path / "opaque.png"
    Image.new("RGBA", (10, 10), (255, 255, 255, 255)).save(source)

    with pytest.raises(SheetProcessError, match="transparency"):
        process_sheet(source, tmp_path / "out", grid="1x1", snap_mode="grid")


def test_process_sheet_rejects_unsafe_names(tmp_path):
    source = tmp_path / "sheet.png"
    make_sheet(source)

    with pytest.raises(SheetProcessError, match="safe file names"):
        process_sheet(source, tmp_path / "out", grid="2x2", snap_mode="grid", names="a,../b,c,d")


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
            "--asset-id",
            "ui_kit_source",
            "--tag",
            "v0.1.0",
            "--background",
            "transparent",
            "--snap-mode",
            "grid",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["asset_id"] == "ui_kit_source"
    assert data["tag"] == "v0.1.0"
    assert data["accepted_count"] == 3


def test_cli_requires_snap_mode(tmp_path):
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

    assert result.returncode != 0
    assert "--snap-mode" in result.stderr
