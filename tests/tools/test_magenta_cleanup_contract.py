from collections import Counter
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_action_process import process_action_sheet  # noqa: E402
from asset_image_finalize import finalize_image_asset  # noqa: E402
from asset_sheet_process import _color_distance, process_sheet  # noqa: E402


def _fixture(path: Path) -> int:
    image = Image.new("RGBA", (48, 48), (255, 0, 255, 255))
    draw = ImageDraw.Draw(image)
    # Every entry point must remove non-exact near-key backdrop pixels through
    # the shared strict cleanup contract without using path expansion.
    for left, colour in zip(
        range(0, 48, 8),
        [(255, 0, 255), (245, 4, 245), (235, 8, 235), (225, 12, 225), (220, 15, 220), (218, 18, 218)],
    ):
        draw.rectangle((left, 0, left + 7, 47), fill=colour)
    draw.rectangle((7, 6, 15, 14), fill=(100, 200, 100, 255))
    # The outline is a real 50% composite of the green foreground and key.
    draw.rectangle((6, 5, 16, 15), outline=(178, 100, 178, 255))
    # Independent foreground details must not be mistaken for that composite.
    draw.line((2, 19, 21, 19), fill=(130, 20, 185, 255), width=1)
    draw.line((2, 21, 21, 21), fill=(90, 30, 175, 255), width=1)
    violet = (150, 10, 200)
    soft_violet = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(soft_violet).rectangle((27, 27, 42, 42), fill=violet + (255,))
    image.alpha_composite(soft_violet.filter(ImageFilter.GaussianBlur(radius=2)))
    image.save(path)
    return sum(pixel == violet + (255,) for pixel in image.get_flattened_data())


def _visible_counter(image: Image.Image) -> Counter[tuple[int, int, int, int]]:
    return Counter(pixel for pixel in image.convert("RGBA").get_flattened_data() if pixel[3] > 0)


def test_sheet_finalize_and_action_share_the_magenta_cleanup_contract(tmp_path):
    source = tmp_path / "provider-fixture.png"
    source_violet_count = _fixture(source)
    assert source_violet_count > 0

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
            pixel[3] < 255 or _color_distance(pixel[:3]) > 60
            for pixel in sheet.convert("RGBA").get_flattened_data()
        )
        assert sum(pixel == (150, 10, 200, 255) for pixel in sheet.convert("RGBA").get_flattened_data()) == source_violet_count
        expected = _visible_counter(sheet)
    with Image.open(tmp_path / "action" / "candidates" / "fixture.png") as candidate:
        assert _visible_counter(candidate) == expected
        rgba = candidate.convert("RGBA")
        assert sum(pixel == (130, 20, 185, 255) for pixel in rgba.get_flattened_data()) == 20
        assert sum(pixel == (90, 30, 175, 255) for pixel in rgba.get_flattened_data()) == 20
        assert sum(pixel == (100, 200, 100, 255) for pixel in rgba.get_flattened_data()) == 81
        assert sum(pixel == (150, 10, 200, 255) for pixel in rgba.get_flattened_data()) == source_violet_count
    assert action["frame_count"] == 1


def test_sheet_finalize_and_action_clear_a_configured_wider_key_radius(tmp_path):
    """All entry points honour an explicit strict radius beyond the default."""
    source = tmp_path / "wider-key-radius.png"
    image = Image.new("RGBA", (30, 20), (255, 0, 255, 255))
    draw = ImageDraw.Draw(image)
    for left, colour in zip(
        range(0, 30, 5),
        [(255, 0, 255), (245, 4, 245), (235, 8, 235), (225, 12, 225), (205, 20, 205), (195, 24, 195)],
    ):
        draw.rectangle((left, 0, left + 4, 19), fill=colour)
    draw.rectangle((11, 6, 18, 13), fill=(100, 200, 100, 255))
    image.save(source)

    process_sheet(
        source,
        tmp_path / "sheet-candidates",
        grid="1x1",
        snap_mode="grid",
        names="fixture",
        background="magenta",
        magenta_threshold=120,
        preserve_cell_bounds=True,
        processed_out=tmp_path / "sheet.png",
    )
    finalize_image_asset(source, tmp_path / "final.png", background="magenta", magenta_threshold=120)
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
        magenta_threshold=120,
    )

    with Image.open(tmp_path / "sheet.png") as sheet, Image.open(tmp_path / "final.png") as final:
        sheet_rgba = sheet.convert("RGBA")
        assert list(sheet_rgba.get_flattened_data()) == list(final.convert("RGBA").get_flattened_data())
        assert all(
            pixel[3] < 255 or _color_distance(pixel[:3]) > 120
            for pixel in sheet_rgba.get_flattened_data()
        )
        expected = _visible_counter(sheet_rgba)
    with Image.open(tmp_path / "action" / "candidates" / "fixture.png") as candidate:
        assert _visible_counter(candidate) == expected
    assert action["frame_count"] == 1
