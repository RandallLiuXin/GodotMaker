from collections import Counter
import sys
from pathlib import Path

from PIL import Image, ImageDraw

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_action_process import process_action_sheet  # noqa: E402
from asset_image_finalize import finalize_image_asset  # noqa: E402
from asset_sheet_process import _color_distance, process_sheet  # noqa: E402


def _fixture(path: Path) -> None:
    image = Image.new("RGBA", (24, 24), (255, 0, 255, 255))
    draw = ImageDraw.Draw(image)
    # A locally smooth backdrop reaches well beyond the strict-key radius.
    # Every entry point must remove it through the shared cleanup contract.
    for left, colour in zip(
        range(0, 24, 4),
        [(255, 0, 255), (245, 4, 245), (235, 8, 235), (225, 12, 225), (205, 20, 205), (195, 24, 195)],
    ):
        draw.rectangle((left, 0, left + 3, 23), fill=colour)
    draw.rectangle((7, 6, 15, 14), fill=(100, 200, 100, 255))
    # The outline is a real 50% composite of the green foreground and key.
    draw.rectangle((6, 5, 16, 15), outline=(178, 100, 178, 255))
    # Independent foreground details must not be mistaken for that composite.
    draw.line((2, 19, 21, 19), fill=(130, 20, 185, 255), width=1)
    draw.line((2, 21, 21, 21), fill=(90, 30, 175, 255), width=1)
    image.save(path)


def _visible_counter(image: Image.Image) -> Counter[tuple[int, int, int, int]]:
    return Counter(pixel for pixel in image.convert("RGBA").get_flattened_data() if pixel[3] > 0)


def test_sheet_finalize_and_action_share_the_magenta_cleanup_contract(tmp_path):
    source = tmp_path / "provider-fixture.png"
    _fixture(source)

    process_sheet(
        source,
        tmp_path / "sheet-candidates",
        grid="1x1",
        snap_mode="grid",
        names="fixture",
        background="magenta",
        preserve_cell_bounds=True,
        processed_out=tmp_path / "sheet.png",
    )
    finalize_image_asset(source, tmp_path / "final.png", background="magenta")
    action = process_action_sheet(
        source,
        tmp_path / "action",
        grid="1x1",
        names="fixture",
        asset_id="fixture",
        component_mode="all",
        component_padding=0,
        action_name="idle",
        fps=8,
        loop=False,
        frame_durations=[1],
    )

    with Image.open(tmp_path / "sheet.png") as sheet, Image.open(tmp_path / "final.png") as final:
        assert list(sheet.convert("RGBA").get_flattened_data()) == list(final.convert("RGBA").get_flattened_data())
        assert all(
            pixel[3] < 255 or _color_distance(pixel[:3]) > 120
            for pixel in sheet.convert("RGBA").get_flattened_data()
        )
        expected = _visible_counter(sheet)
    with Image.open(tmp_path / "action" / "candidates" / "fixture.png") as candidate:
        assert _visible_counter(candidate) == expected
        rgba = candidate.convert("RGBA")
        assert sum(pixel == (130, 20, 185, 255) for pixel in rgba.get_flattened_data()) == 20
        assert sum(pixel == (90, 30, 175, 255) for pixel in rgba.get_flattened_data()) == 20
        assert sum(pixel == (100, 200, 100, 255) for pixel in rgba.get_flattened_data()) == 81
    assert action["frame_count"] == 1
