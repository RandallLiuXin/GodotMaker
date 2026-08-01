"""FX-specific regression coverage for static and animated processing routes."""
from pathlib import Path
import sys

from PIL import Image, ImageDraw


TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_action_process import process_action_sheet  # noqa: E402
from asset_sheet_process import process_sheet  # noqa: E402


def _static_components(path: Path) -> None:
    image = Image.new("RGBA", (32, 16), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((2, 2, 9, 10), fill=(255, 160, 32, 255))
    draw.rectangle((23, 4, 27, 8), fill=(255, 224, 96, 255))
    image.save(path)


def _single_static(path: Path) -> None:
    image = Image.new("RGBA", (32, 16), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.polygon(((4, 12), (12, 2), (20, 12), (12, 10)), fill=(255, 160, 32, 255))
    image.save(path)


def _action_sheet(path: Path) -> None:
    image = Image.new("RGBA", (80, 80), (255, 0, 255, 255))
    draw = ImageDraw.Draw(image)
    for box in ((10, 8, 30, 36), (52, 10, 68, 34), (8, 48, 32, 72), (50, 50, 70, 74)):
        draw.rectangle(box, fill=(40, 120, 230, 255))
    image.save(path)


def _visible_colors(path: Path) -> set[tuple[int, int, int]]:
    with Image.open(path).convert("RGBA") as image:
        pixels = image.tobytes()
    return {
        (pixels[index], pixels[index + 1], pixels[index + 2])
        for index in range(0, len(pixels), 4)
        if pixels[index + 3] > 0
    }


def test_fx_static_autoslice_extracts_one_independent_effect(tmp_path):
    source = tmp_path / "static.png"
    _single_static(source)

    result = process_sheet(
        source,
        tmp_path / "out",
        names="flare",
        asset_id="sun_pollen",
        snap_mode="autoslice",
    )

    assert result["snap_mode"] == "autoslice"
    assert result["grid"] is None
    assert result["accepted_count"] == 1


def test_fx_static_collective_components_stay_in_one_grid_cell(tmp_path):
    source = tmp_path / "collective.png"
    _static_components(source)

    result = process_sheet(
        source,
        tmp_path / "out",
        grid="1x1",
        names="sun_pollen_flare",
        asset_id="sun_pollen",
        snap_mode="grid",
        component_mode="all",
        min_component_area=1,
    )

    assert result["accepted_count"] == 1
    assert result["accepted"][0]["component_count"] == 2
    assert _visible_colors(tmp_path / "out" / "sun_pollen_flare.png") == {
        (255, 160, 32), (255, 224, 96),
    }


def test_fx_static_autoslice_name_mismatch_is_a_repair_diagnostic(tmp_path):
    source = tmp_path / "static.png"
    _static_components(source)

    result = process_sheet(
        source,
        tmp_path / "out",
        names="only_one_name",
        asset_id="sun_pollen",
        snap_mode="autoslice",
    )

    assert result["status"] == "needs_regeneration"
    assert result["accepted_count"] == 0
    assert not list((tmp_path / "out").glob("*.png"))


def test_fx_animation_uses_explicit_grid_and_centered_action_frames(tmp_path):
    source = tmp_path / "impact-source.png"
    _action_sheet(source)
    final_dir = tmp_path / "assets" / "generated" / "fx-bundle" / "forge-impact"

    result = process_action_sheet(
        source,
        tmp_path / "work",
        grid="2x2",
        names="impact_01,impact_02,impact_03,impact_04",
        asset_id="forge-impact",
        tag="v0.1.0",
        action_name="impact",
        fps=16,
        loop=False,
        frame_durations=[1, 1, 1, 2],
        align="center",
        final_dir=final_dir,
        final_prefix="forge-impact_impact",
    )

    assert result["grid"] == {"cols": 2, "rows": 2}
    assert result["align"] == "center"
    assert result["frame_labels"] == ["impact_01", "impact_02", "impact_03", "impact_04"]
    assert [Path(frame).name for frame in result["final_frame_paths"]] == [
        "forge-impact_impact_impact_01.png",
        "forge-impact_impact_impact_02.png",
        "forge-impact_impact_impact_03.png",
        "forge-impact_impact_impact_04.png",
    ]
