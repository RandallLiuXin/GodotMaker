#!/usr/bin/env python3
"""Validate asset generation group reports."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


class ReportCheckError(Exception):
    """Raised when a generation report is invalid."""


def _load_image(path: Path):
    try:
        from PIL import Image
    except ImportError as exc:
        raise ReportCheckError("Pillow is required to validate image assets") from exc

    try:
        image = Image.open(path)
        image.load()
        return image
    except Exception as exc:
        raise ReportCheckError(f"Asset is not a readable image: {path}") from exc


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReportCheckError(message)


def check_report(path: Path) -> dict[str, object]:
    """Validate one generation group report and its referenced images."""
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ReportCheckError(f"Invalid JSON report: {path}") from exc

    _require(isinstance(report, dict), f"Report must be a JSON object: {path}")
    _require(report.get("ok") is True, f"Report is not ok: {path}")
    provider = report.get("provider")
    _require(isinstance(provider, str) and bool(provider), f"Report missing provider: {path}")
    assets = report.get("assets")
    _require(isinstance(assets, list), f"Report missing assets list: {path}")

    checked = []
    for index, item in enumerate(assets):
        _require(isinstance(item, dict), f"Asset entry {index} is not an object: {path}")
        _require(item.get("ok") is True, f"Asset entry {index} is not ok: {path}")
        asset_path_raw = item.get("path")
        _require(
            isinstance(asset_path_raw, str) and bool(asset_path_raw),
            f"Asset entry {index} missing path: {path}",
        )
        asset_path = Path(asset_path_raw)
        _require(asset_path.exists(), f"Asset path not found: {asset_path}")
        _require(asset_path.is_file(), f"Asset path is not a file: {asset_path}")

        image = _load_image(asset_path)
        try:
            width, height = image.size
            fmt = image.format
        finally:
            image.close()

        if "width" in item:
            _require(item["width"] == width, f"Asset width mismatch: {asset_path}")
        if "height" in item:
            _require(item["height"] == height, f"Asset height mismatch: {asset_path}")
        if "format" in item:
            _require(str(item["format"]).upper() == str(fmt).upper(), f"Asset format mismatch: {asset_path}")

        checked.append({
            "path": str(asset_path),
            "width": width,
            "height": height,
            "format": fmt,
        })

    return {
        "path": str(path),
        "provider": provider,
        "asset_count": len(checked),
        "assets": checked,
    }


def _main() -> int:
    parser = argparse.ArgumentParser(description="Validate asset generation group reports")
    parser.add_argument("reports", nargs="+", help="Generation group JSON report path")
    args = parser.parse_args()

    try:
        reports = [check_report(Path(report)) for report in args.reports]
    except ReportCheckError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(json.dumps({
        "ok": True,
        "report_count": len(reports),
        "asset_count": sum(report["asset_count"] for report in reports),
        "reports": reports,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
