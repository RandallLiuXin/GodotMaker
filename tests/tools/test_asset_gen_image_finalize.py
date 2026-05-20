"""Integration tests for asset_gen.py image finalization."""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tools",
))

import asset_gen


def _args(**overrides):
    base = {
        "model": "grok",
        "size": "1K",
        "aspect_ratio": "1:1",
        "image": None,
        "prompt": "a gold coin icon",
        "output": "assets/img/coin.png",
        "resize": None,
        "label": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _read_stdout_json(capsys):
    return json.loads(capsys.readouterr().out)


def _write_png(path: Path, size=(12, 10)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (255, 210, 40)).save(path, format="PNG")


def test_image_command_finalizes_output_and_records_budget(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    budget_path = tmp_path / "assets" / "budget.json"
    budget_path.parent.mkdir()
    budget_path.write_text(
        json.dumps({"budget_cents": 100, "log": []}),
        encoding="utf-8",
    )

    def fake_grok(args, output, cost, _model_name):
        _write_png(output)
        asset_gen.finish_image_output(args, output, cost, "xai")

    monkeypatch.setattr(asset_gen, "_generate_grok", fake_grok)

    asset_gen.cmd_image(_args(resize="4x3", label="coin"))

    out = _read_stdout_json(capsys)
    assert out["ok"] is True
    assert out["provider"] == "xai"
    assert out["asset_id"] == "coin"
    assert Path(out["path"]) == Path("assets/img/coin.png")
    assert Path(out["source"]) == Path("assets/img/coin.png")
    assert out["width"] == 4
    assert out["height"] == 3
    assert out["resize"] == "4x3"

    with Image.open(tmp_path / "assets" / "img" / "coin.png") as image:
        assert image.size == (4, 3)

    budget = json.loads(budget_path.read_text(encoding="utf-8"))
    assert budget["log"] == [{"xai": 2}]


def test_image_command_does_not_record_budget_when_finalize_fails(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    budget_path = tmp_path / "assets" / "budget.json"
    budget_path.parent.mkdir()
    budget_path.write_text(
        json.dumps({"budget_cents": 100, "log": []}),
        encoding="utf-8",
    )

    def fake_grok(args, output, cost, _model_name):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("not an image", encoding="utf-8")
        asset_gen.finish_image_output(args, output, cost, "xai")

    monkeypatch.setattr(asset_gen, "_generate_grok", fake_grok)

    with pytest.raises(SystemExit):
        asset_gen.cmd_image(_args())

    out = _read_stdout_json(capsys)
    assert out["ok"] is False
    assert "readable image" in out["error"]

    budget = json.loads(budget_path.read_text(encoding="utf-8"))
    assert budget["log"] == []
