import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_layout_guide import LayoutGuideError, create_layout_guide  # noqa: E402


def test_create_layout_guide_writes_expected_canvas(tmp_path):
    out = tmp_path / ".godotmaker" / "asset-generation" / "guides" / "ui_3x3.png"

    result = create_layout_guide(
        out,
        rows=3,
        cols=3,
        cell_width=64,
        cell_height=48,
        labels=["a", "b", "c", "d", "e", "f", "g", "h", "i"],
    )

    assert result["ok"] is True
    assert result["canvas_width"] == 192
    assert result["canvas_height"] == 144
    assert out.exists()
    with Image.open(out) as image:
        assert image.size == (192, 144)


def test_create_layout_guide_rejects_bad_dimensions(tmp_path):
    with pytest.raises(LayoutGuideError, match="--rows"):
        create_layout_guide(tmp_path / "guide.png", rows=0, cols=3)


def test_cli_writes_layout_guide(tmp_path):
    out = tmp_path / "guide.png"
    result = subprocess.run(
        [
            sys.executable,
            str(TOOLS_DIR / "asset_layout_guide.py"),
            "--out",
            str(out),
            "--rows",
            "2",
            "--cols",
            "2",
            "--cell-width",
            "32",
            "--cell-height",
            "32",
            "--labels",
            "idle,run,attack,hurt",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["labels"] == ["idle", "run", "attack", "hurt"]
    with Image.open(out) as image:
        assert image.size == (64, 64)
