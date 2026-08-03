import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_sheet_process import MAGENTA_RGB, SheetProcessError, _color_distance, process_sheet  # noqa: E402


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
        draw.rectangle((1, 1, 8, 8), fill=(250, 20, 250, 255))
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
    assert result["cleanup"]["algorithm"] == "pymatting_closed_form"
    assert result["cleanup"]["strict_background_pixels"] > 0
    assert result["accepted_count"] == 3
    assert result["rejected_count"] == 1
    candidate = Image.open(tmp_path / "out" / "a.png").convert("RGBA")
    try:
        assert candidate.getchannel("A").getextrema()[0] == 255
    finally:
        candidate.close()
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["cleanup"]["background"] == "magenta"


def test_process_sheet_preserves_fixed_grid_cell_bounds_for_atlas_assembly(tmp_path):
    source = tmp_path / "magenta_sheet.png"
    make_magenta_sheet(source)

    result = process_sheet(
        source,
        tmp_path / "out",
        grid="2x2",
        snap_mode="grid",
        names="a,b,c,d",
        background="magenta",
        preserve_cell_bounds=True,
    )

    assert result["preserve_cell_bounds"] is True
    assert result["accepted"][0]["output_box"] == [0, 0, 10, 10]
    with Image.open(tmp_path / "out" / "a.png") as candidate:
        assert candidate.size == (10, 10)
        assert candidate.convert("RGBA").getchannel("A").getextrema()[0] == 0


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


def test_process_sheet_autoslice_extracts_independent_regions_without_grid(tmp_path):
    source = tmp_path / "autoslice_sheet.png"
    make_autoslice_sheet(source)

    result = process_sheet(
        source,
        tmp_path / "out",
        names="wide_button,right_icon",
        asset_id="ui_kit_source",
        snap_mode="autoslice",
    )

    assert result["snap_mode"] == "autoslice"
    assert result["strategy"] == "transparent_autoslice"
    assert result["grid"] is None
    assert result["detected_region_count"] == 2
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


def test_autoslice_writes_cleaned_rgba_sheet_only_after_successful_binding(tmp_path):
    source = tmp_path / "magenta_source.png"
    make_magenta_sheet(source)
    processed = tmp_path / "processed" / "sheet-transparent.png"

    result = process_sheet(
        source,
        tmp_path / "out",
        names="red,green,blue",
        asset_id="props",
        background="magenta",
        snap_mode="autoslice",
        processed_out=processed,
    )

    assert result["processed_path"] == str(processed)
    with Image.open(processed) as image:
        assert image.mode == "RGBA"
        assert image.getchannel("A").getextrema()[0] == 0
        assert all(
            pixel[:3] != (255, 0, 255) or pixel[3] == 0
            for pixel in image.get_flattened_data()
        )


def test_process_sheet_autoslice_reports_name_count_mismatch_without_outputs(tmp_path):
    source = tmp_path / "autoslice_sheet.png"
    make_autoslice_sheet(source)
    report = tmp_path / "report.json"
    processed = tmp_path / "processed" / "sheet-transparent.png"

    result = process_sheet(
        source,
        tmp_path / "out",
        names="wide_button",
        asset_id="ui_kit_source",
        snap_mode="autoslice",
        processed_out=processed,
        report=report,
    )

    assert result["ok"] is False
    assert result["status"] == "needs_regeneration"
    assert result["expected_region_count"] == 1
    assert result["detected_region_count"] == 2
    assert result["accepted_count"] == 0
    assert result["rejected"] == [{
        "state": "rejected",
        "reason": "name_count_mismatch",
        "expected_count": 1,
        "detected_count": 2,
    }]
    assert not list((tmp_path / "out").glob("*.png"))
    assert result["processed_path"] is None
    assert not processed.exists()
    assert json.loads(report.read_text(encoding="utf-8"))["detected_region_count"] == 2


def test_process_sheet_removes_strict_near_key_background(tmp_path):
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

    assert result["cleanup"]["strict_background_pixels"] > 0
    assert result["accepted"][0]["crop_bbox"] == [2, 2, 8, 8]


def test_process_sheet_mattes_provider_style_residual_without_changing_foreground(tmp_path):
    """Synthetic, author-created WOR-58 matte fixture; licensed with this repository."""
    source = tmp_path / "wor58-pymatting-fixture.png"
    image = Image.new("RGBA", (72, 64), MAGENTA_RGB + (255,))
    draw = ImageDraw.Draw(image)
    core = (40, 35, 23)
    draw.rectangle((18, 14, 47, 48), fill=core + (255,))
    # These non-ideal edge colours are reduced versions of the observed dark
    # and bright provider spill around the night-market rug, not a source crop.
    for y in range(16, 47):
        draw.point((48, y), fill=(140 + (y % 3), 23 + (y % 5), 143 + (y % 7), 255))
        draw.point((49, y), fill=(184 + (y % 5), 22 + (y % 3), 202 - (y % 4), 255))
        draw.point((50, y), fill=(234 - (y % 4), 9 + (y % 6), 194 + (y % 3), 255))
    for x in range(20, 48):
        draw.point((x, 48), fill=(140 + (x % 3), 23 + (x % 5), 143 + (x % 7), 255))
        draw.point((x, 49), fill=(237 - (x % 4), 67 + (x % 3), 202 + (x % 5), 255))
    image.save(source)

    result = process_sheet(
        source,
        tmp_path / "out",
        grid="1x1",
        snap_mode="grid",
        names="fixture",
        background="magenta",
        preserve_cell_bounds=True,
        processed_out=tmp_path / "processed.png",
    )

    with Image.open(tmp_path / "processed.png") as processed:
        rgba = processed.convert("RGBA")
        assert rgba.getpixel((34, 32)) == core + (255,)
        assert rgba.getpixel((48, 30))[3] < 255
        assert _color_distance(rgba.getpixel((50, 30))[:3]) > _color_distance((234, 9, 194))
        assert _color_distance(rgba.getpixel((34, 49))[:3]) > _color_distance((237, 67, 202))
        assert rgba.getchannel("A").getbbox() == (18, 14, 51, 50)
    assert result["cleanup"]["algorithm"] == "pymatting_closed_form"
    assert result["cleanup"]["matted_pixels"] > 0


def test_magenta_cleanup_preserves_non_key_foreground_colours_and_alpha(tmp_path):
    source = tmp_path / "provider-regression.png"
    image = Image.new("RGBA", (48, 32), (245, 2, 243, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((4, 4, 14, 24), fill=(190, 30, 45, 255))
    draw.rectangle((18, 4, 28, 24), fill=(130, 20, 185, 255))
    draw.rectangle((32, 4, 42, 24), fill=(90, 30, 175, 255))
    image.save(source)

    result = process_sheet(
        source,
        tmp_path / "out",
        grid="1x1",
        snap_mode="grid",
        names="prop",
        background="magenta",
        preserve_cell_bounds=True,
        processed_out=tmp_path / "processed.png",
    )

    with Image.open(tmp_path / "processed.png") as processed:
        rgba = processed.convert("RGBA")
        assert rgba.getpixel((0, 0))[3] == 0
        assert rgba.getpixel((9, 14)) == (190, 30, 45, 255)
        assert rgba.getpixel((23, 14)) == (130, 20, 185, 255)
        assert rgba.getpixel((37, 14)) == (90, 30, 175, 255)
        assert not any(
            pixel[:3] == (255, 0, 255) and pixel[3] > 0
            for pixel in rgba.get_flattened_data()
        )
    assert result["cleanup"]["matted_pixels"] > 0


def test_process_sheet_rejects_magenta_edge_touch_when_requested(tmp_path):
    source = tmp_path / "magenta_edge.png"
    image = Image.new("RGBA", (80, 80), MAGENTA_RGB + (255,))
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 8, 23, 23), fill=(255, 0, 0, 255))
    draw.rectangle((48, 8, 63, 23), fill=(0, 255, 0, 255))
    draw.rectangle((8, 48, 23, 63), fill=(0, 0, 255, 255))
    draw.rectangle((40, 40, 79, 79), fill=(255, 255, 0, 255))
    image.save(source)

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


def test_process_sheet_partitions_non_divisible_grid_with_full_coverage(tmp_path):
    source = tmp_path / "sheet.png"
    image = Image.new("RGBA", (9, 10), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((1, 1, 3, 3), fill=(255, 0, 0, 255))
    image.save(source)

    result = process_sheet(
        source,
        tmp_path / "out",
        grid="2x2",
        names="a,b,c,d",
        snap_mode="grid",
        preserve_cell_bounds=True,
    )

    assert result["cell_bounds"] == {"columns": [0, 4, 9], "rows": [0, 5, 10]}
    assert result["accepted"][0]["source_box"] == [0, 0, 4, 5]


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


def test_cli_autoslice_outputs_json(tmp_path):
    source = tmp_path / "autoslice_sheet.png"
    make_autoslice_sheet(source)

    result = subprocess.run(
        [
            sys.executable,
            str(TOOLS_DIR / "asset_sheet_process.py"),
            "--source",
            str(source),
            "--out-dir",
            str(tmp_path / "out"),
            "--names",
            "wide_button,right_icon",
            "--asset-id",
            "ui_kit_source",
            "--snap-mode",
            "autoslice",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["snap_mode"] == "autoslice"
    assert data["strategy"] == "transparent_autoslice"
    assert data["accepted_count"] == 2


def test_cli_requires_grid_in_grid_mode(tmp_path):
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
            "--names",
            "a,b,c,d",
            "--snap-mode",
            "grid",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "--grid" in json.loads(result.stdout)["error"]


def test_cli_rejects_malformed_grid_in_grid_mode(tmp_path):
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
            "2",
            "--snap-mode",
            "grid",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["ok"] is False
    assert "--grid" in data["error"]


def test_cli_rejects_grid_in_autoslice_mode(tmp_path):
    source = tmp_path / "autoslice_sheet.png"
    make_autoslice_sheet(source)

    result = subprocess.run(
        [
            sys.executable,
            str(TOOLS_DIR / "asset_sheet_process.py"),
            "--source",
            str(source),
            "--out-dir",
            str(tmp_path / "out"),
            "--grid",
            "2x1",
            "--snap-mode",
            "autoslice",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["ok"] is False
    assert "not accepted" in data["error"]
