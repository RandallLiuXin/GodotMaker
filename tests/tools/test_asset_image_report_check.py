import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_image_report_check import ReportCheckError, check_report  # noqa: E402


def make_png(path: Path, size=(8, 6)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (20, 30, 40)).save(path, format="PNG")


def make_report(path: Path, image_path: Path, **asset_overrides):
    item = {
        "ok": True,
        "source": str(image_path),
        "path": str(image_path),
        "asset_id": "coin",
        "bytes": image_path.stat().st_size,
        "width": 8,
        "height": 6,
        "format": "PNG",
    }
    item.update(asset_overrides)
    report = {
        "ok": True,
        "provider": "native",
        "assets": [item],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report), encoding="utf-8")


def test_check_report_validates_assets(tmp_path):
    image_path = tmp_path / "assets" / "coin.png"
    report_path = tmp_path / ".godotmaker" / "asset-generation" / "group_1.json"
    make_png(image_path)
    make_report(report_path, image_path)

    result = check_report(report_path)

    assert result["provider"] == "native"
    assert result["asset_count"] == 1
    assert result["assets"][0]["width"] == 8
    assert result["assets"][0]["height"] == 6


def test_check_report_rejects_missing_asset(tmp_path):
    image_path = tmp_path / "assets" / "coin.png"
    report_path = tmp_path / ".godotmaker" / "asset-generation" / "group_1.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        json.dumps({
            "ok": True,
            "provider": "native",
            "assets": [{"ok": True, "path": str(image_path)}],
        }),
        encoding="utf-8",
    )

    with pytest.raises(ReportCheckError):
        check_report(report_path)


def test_check_report_rejects_metadata_mismatch(tmp_path):
    image_path = tmp_path / "assets" / "coin.png"
    report_path = tmp_path / ".godotmaker" / "asset-generation" / "group_1.json"
    make_png(image_path)
    make_report(report_path, image_path, width=99)

    with pytest.raises(ReportCheckError):
        check_report(report_path)


def test_cli_outputs_json(tmp_path):
    image_path = tmp_path / "assets" / "coin.png"
    report_path = tmp_path / ".godotmaker" / "asset-generation" / "group_1.json"
    make_png(image_path)
    make_report(report_path, image_path)

    result = subprocess.run(
        [
            sys.executable,
            str(TOOLS_DIR / "asset_image_report_check.py"),
            str(report_path),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["report_count"] == 1
    assert data["asset_count"] == 1
