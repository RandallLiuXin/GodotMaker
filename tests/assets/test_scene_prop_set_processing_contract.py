"""Regression coverage for the scene-prop-set source-sheet production path."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_atlas_assemble import assemble_atlas  # noqa: E402
from asset_image_finalize import finalize_image_asset  # noqa: E402
from asset_sheet_process import process_sheet  # noqa: E402


def _write_source_sheet(path: Path) -> None:
    """Write disconnected wide and tall props on one real-shaped source sheet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (180, 120), (255, 0, 255, 255))
    for x in range(10, 80):
        for y in range(20, 40):
            image.putpixel((x, y), (210, 70, 40, 255))
    for x in range(120, 140):
        for y in range(10, 100):
            image.putpixel((x, y), (45, 90, 190, 255))
    image.save(path)


def _alpha_bbox(image: Image.Image) -> tuple[int, int]:
    alpha = image.convert("RGBA").getchannel("A")
    bbox = alpha.getbbox()
    assert bbox is not None
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def test_scene_props_autoslice_one_source_then_finalize_each_prop_without_stretching(tmp_path):
    source = tmp_path / ".godotmaker" / "asset-generation" / "sources" / "mixed_source.png"
    _write_source_sheet(source)
    candidates = tmp_path / ".godotmaker" / "asset-generation" / "candidates" / "mixed"
    sheet_report = process_sheet(
        source,
        candidates,
        snap_mode="autoslice",
        names="wide_banner,tall_post",
        asset_id="mixed",
        background="magenta",
        report=tmp_path / ".godotmaker" / "asset-generation" / "reports" / "mixed_autoslice.json",
    )

    assert sheet_report["ok"] is True
    assert sheet_report["status"] == "candidate_extracted"
    assert sheet_report["grid"] is None
    assert [item["name"] for item in sheet_report["candidates"]] == ["wide_banner", "tall_post"]

    normalized = tmp_path / ".godotmaker" / "asset-generation" / "normalized" / "mixed"
    normalized.mkdir(parents=True)
    targets = {"wide_banner": "80x40", "tall_post": "40x100"}
    candidate_sizes = {}
    source_paths = {}
    for candidate in sheet_report["candidates"]:
        name = candidate["name"]
        source_path = Path(candidate["path"])
        with Image.open(source_path) as image:
            candidate_sizes[name] = _alpha_bbox(image)
        output = normalized / f"{name}.png"
        finalize_image_asset(source_path, output, resize=targets[name], label=name, archive_original=False)
        source_paths[name] = output.relative_to(tmp_path).as_posix()

    final_sizes = {}
    for name in targets:
        with Image.open(normalized / f"{name}.png") as image:
            final_sizes[name] = _alpha_bbox(image)
    # The alpha AABB preserves each source ratio, proving padding rather than
    # slot-shaped stretching for two deliberately opposite aspect ratios.
    for name in targets:
        original_ratio = candidate_sizes[name][0] / candidate_sizes[name][1]
        final_ratio = final_sizes[name][0] / final_sizes[name][1]
        assert abs(original_ratio - final_ratio) / original_ratio < 0.06

    declaration = {
        "version": 1,
        "atlas": {"width": 144, "height": 100},
        "slots": [
            {"name": "wide_banner", "rect": [0, 0, 80, 40], "source": source_paths["wide_banner"]},
            {"name": "tall_post", "rect": [96, 0, 40, 100], "source": source_paths["tall_post"], "pivot": [0.5, 1.0]},
        ],
    }
    declaration_path = tmp_path / "declaration.json"
    declaration_path.write_text(json.dumps(declaration), encoding="utf-8")
    atlas = tmp_path / "assets" / "generated" / "scene-prop-set" / "mixed" / "mixed.png"
    metadata = atlas.with_suffix(".json")
    result = assemble_atlas(
        declaration_path,
        atlas,
        metadata,
        production_family="scene-prop-set",
        asset_id="mixed",
        project_root=tmp_path,
    )

    assert result["atlas_path"] == "res://assets/generated/scene-prop-set/mixed/mixed.png"
    assert {
        region["name"]: region["rect"] for region in result["regions"]
    } == {"wide_banner": [0, 0, 80, 40], "tall_post": [96, 0, 40, 100]}
    with Image.open(atlas) as image:
        assert image.size == (144, 100)
        assert image.getpixel((88, 10))[3] == 0


def test_scene_props_name_count_mismatch_is_a_regeneration_diagnostic_without_partial_candidates(tmp_path):
    source = tmp_path / "source.png"
    _write_source_sheet(source)
    output = tmp_path / "candidates"

    report = process_sheet(
        source,
        output,
        snap_mode="autoslice",
        names="wide_banner",
        asset_id="mixed",
        background="magenta",
    )

    assert report["ok"] is False
    assert report["status"] == "needs_regeneration"
    assert report["accepted_count"] == 0
    assert not list(output.glob("*.png"))
