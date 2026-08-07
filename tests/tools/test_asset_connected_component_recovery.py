"""Contracts for the family-neutral whole-sheet component recovery CLI."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw


TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"


def _make_eight_component_sheet(path: Path) -> None:
    image = Image.new("RGBA", (160, 80), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    # The first two figures have overlapping AABBs but no touching pixels:
    # red's high weapon crosses right, green's torso remains below it.
    draw.rectangle((3, 5, 10, 35), fill=(220, 40, 40, 255))
    draw.rectangle((10, 10, 55, 12), fill=(220, 40, 40, 255))
    draw.rectangle((45, 20, 55, 38), fill=(40, 220, 40, 255))
    draw.rectangle((55, 35, 77, 37), fill=(40, 220, 40, 255))
    for index in range(2, 8):
        row, col = divmod(index, 4)
        left = col * 40 + 8
        top = row * 40 + 8
        draw.rectangle((left, top, left + 18, top + 24), fill=(30 + index * 20, 80, 220, 255))
    image.save(path)


def test_cli_recovers_anonymous_four_by_two_sheet_with_overlapping_component_aabbs(tmp_path):
    source = tmp_path / "source.png"
    output = tmp_path / "recovered.png"
    report = tmp_path / "report.json"
    _make_eight_component_sheet(source)

    result = subprocess.run(
        [
            sys.executable, str(TOOLS_DIR / "asset_connected_component_recovery.py"),
            "--source", str(source), "--output", str(output), "--grid", "4x2",
            "--background", "transparent", "--min-component-area", "10", "--report", str(report),
        ],
        capture_output=True, text=True, check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["method"] == "whole_sheet_8_connected_components"
    assert payload["component_count"] == 8
    assert [placement["target_cell"] for placement in payload["placements"]] == [
        [0, 0], [1, 0], [2, 0], [3, 0], [0, 1], [1, 1], [2, 1], [3, 1],
    ]
    first, second = payload["placements"][:2]
    assert first["source_bbox"][2] > second["source_bbox"][0]
    assert first["source_bbox"][3] > second["source_bbox"][1]
    assert Path(payload["output_path"]).exists()
    assert json.loads(report.read_text(encoding="utf-8"))["status"] == "recovered"


def test_cli_reports_stable_recoverable_error_for_wrong_component_count(tmp_path):
    source = tmp_path / "source.png"
    output = tmp_path / "recovered.png"
    report = tmp_path / "report.json"
    image = Image.new("RGBA", (80, 40), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((5, 5, 20, 30), fill=(220, 40, 40, 255))
    image.save(source)

    result = subprocess.run(
        [
            sys.executable, str(TOOLS_DIR / "asset_connected_component_recovery.py"),
            "--source", str(source), "--output", str(output), "--grid", "2x1",
            "--background", "transparent", "--report", str(report),
        ],
        capture_output=True, text=True, check=False,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "needs_fallback"
    assert payload["error_code"] == "component_count_mismatch"
    assert json.loads(report.read_text(encoding="utf-8"))["error_code"] == "component_count_mismatch"
