"""Explicitly opted-in live Wan smoke tests; normal CI never calls the network."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from PIL import Image

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import asset_source_generate as source_generate  # noqa: E402


pytestmark = pytest.mark.skipif(
    os.environ.get("WAN_LIVE_SMOKE") != "1",
    reason="set WAN_LIVE_SMOKE=1 with regional DashScope credentials to run live Wan smoke tests",
)


def _spec(tmp_path: Path, *, references: list[dict[str, str]] | None = None) -> dict:
    return {
        "asset_id": "wan-smoke",
        "model": os.environ.get("WAN_LIVE_SMOKE_MODEL", "wan:wan2.7-image"),
        "prompt": "A single small blue ceramic vase on a plain cream background, no text, centered product illustration.",
        "prompt_path": str(tmp_path / "prompt.txt"),
        "source_path": str(tmp_path / "source.png"),
        "report_path": str(tmp_path / "report.json"),
        "size": "1K",
        "aspect_ratio": "1:1",
        "seed": 20260820,
        "reference_inputs": references or [],
    }


def _assert_live_result(spec: dict) -> None:
    spec_path = Path(spec["source_path"]).with_name("spec.json")
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    result = source_generate.generate_source(source_generate.load_spec(spec_path))
    assert Path(result["source_path"]).is_file()
    assert result["format"] == "PNG"
    assert result["provider_payload"]["request_id"]
    assert result["provider_payload"]["usage"]
    assert Path(result["report_path"]).is_file()


@pytest.mark.parametrize("attempt", [1, 2])
def test_wan_live_text_to_image(tmp_path, attempt):
    _assert_live_result(_spec(tmp_path))


@pytest.mark.parametrize("attempt", [1, 2])
def test_wan_live_style_reference_edit(tmp_path, attempt):
    reference = tmp_path / "style-reference.png"
    Image.new("RGB", (240, 240), (34, 87, 154)).save(reference, format="PNG")
    _assert_live_result(_spec(tmp_path, references=[{"role": "style", "path": str(reference)}]))
