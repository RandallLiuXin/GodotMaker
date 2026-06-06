import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import asset_source_generate as source_generate  # noqa: E402


def make_spec(tmp_path: Path, **overrides):
    spec = {
        "asset_id": "coin",
        "model": "grok",
        "prompt": "a gold coin icon on a solid green background",
        "prompt_path": ".godotmaker/asset-generation/prompts/coin.txt",
        "source_path": ".godotmaker/asset-generation/sources/coin_source.png",
        "size": "1K",
        "aspect_ratio": "1:1",
        "reference_images": [],
    }
    spec.update(overrides)
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


def write_png(path: Path, size=(12, 10)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (255, 210, 40)).save(path, format="PNG")


def test_load_spec_requires_explicit_model(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec_path = make_spec(tmp_path, model="")

    with pytest.raises(source_generate.SourceGenerateError, match="model"):
        source_generate.load_spec(spec_path)


def test_generate_source_writes_prompt_source_and_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec = source_generate.load_spec(
        make_spec(
            tmp_path,
            report_path=".godotmaker/asset-generation/reports/coin_source.json",
        )
    )

    def fake_grok(spec_data, output, _model_name):
        assert spec_data["prompt"] == "a gold coin icon on a solid green background"
        write_png(output)

    monkeypatch.setattr(source_generate, "_generate_grok", fake_grok)

    result = source_generate.generate_source(spec)

    assert result["ok"] is True
    assert result["provider"] == "grok"
    assert result["asset_id"] == "coin"
    assert result["source_path"] == ".godotmaker/asset-generation/sources/coin_source.png"
    assert result["prompt_path"] == ".godotmaker/asset-generation/prompts/coin.txt"
    assert result["report_path"] == ".godotmaker/asset-generation/reports/coin_source.json"
    assert (tmp_path / result["source_path"]).exists()
    assert (tmp_path / result["prompt_path"]).read_text(encoding="utf-8") == spec["prompt"]

    report = json.loads((tmp_path / result["report_path"]).read_text(encoding="utf-8"))
    assert report["source_path"] == result["source_path"]


def test_generate_source_does_not_write_report_when_validation_fails(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    spec = source_generate.load_spec(
        make_spec(
            tmp_path,
            report_path=".godotmaker/asset-generation/reports/coin_source.json",
        )
    )

    def fake_grok(_spec_data, output, _model_name):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("not an image", encoding="utf-8")

    monkeypatch.setattr(source_generate, "_generate_grok", fake_grok)

    with pytest.raises(source_generate.SourceGenerateError, match="readable image"):
        source_generate.generate_source(spec)

    assert not (tmp_path / ".godotmaker" / "asset-generation" / "reports" / "coin_source.json").exists()


def test_generate_source_rejects_runtime_native_selectors(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec = source_generate.load_spec(make_spec(tmp_path, model="codex"))

    with pytest.raises(source_generate.SourceGenerateError, match="runtime-native"):
        source_generate.generate_source(spec)


def test_cli_outputs_json_error(tmp_path):
    spec_path = make_spec(tmp_path, model="native")

    result = subprocess.run(
        [
            sys.executable,
            str(TOOLS_DIR / "asset_source_generate.py"),
            "--spec",
            str(spec_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )

    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["ok"] is False
    assert "runtime-native" in data["error"]
