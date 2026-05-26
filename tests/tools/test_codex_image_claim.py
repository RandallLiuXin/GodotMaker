import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
from PIL import Image

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from codex_image_claim import CodexImageClaimError, claim_codex_image  # noqa: E402


def make_png(path: Path, size=(12, 8)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, (20, 30, 40, 255)).save(path, format="PNG")


def test_claim_codex_image_copies_explicit_saved_path(tmp_path):
    source = tmp_path / ".codex" / "generated_images" / "thread-1" / "ig_1.png"
    output = tmp_path / ".godotmaker" / "asset-generation" / "codex" / "A01_source.png"
    make_png(source)

    result = claim_codex_image(str(source), output, asset_id="A01")

    assert result["ok"] is True
    assert result["asset_id"] == "A01"
    assert result["source"] == str(source)
    assert result["path"] == str(output)
    assert result["width"] == 12
    assert result["height"] == 8
    assert output.read_bytes() == source.read_bytes()


def test_claim_codex_image_accepts_file_url(tmp_path):
    source = tmp_path / "generated" / "ig_1.png"
    output = tmp_path / "claimed" / "A01_source.png"
    make_png(source)

    result = claim_codex_image(source.as_uri(), output)

    assert result["ok"] is True
    assert result["source"] == str(source)
    assert output.exists()


def test_claim_codex_image_accepts_localhost_file_url(tmp_path):
    source = tmp_path / "generated" / "ig_1.png"
    output = tmp_path / "claimed" / "A01_source.png"
    make_png(source)
    file_url = source.as_uri().replace("file:///", "file://localhost/")

    result = claim_codex_image(file_url, output)

    assert result["ok"] is True
    assert result["source"] == str(source)
    assert output.exists()


def test_claim_codex_image_uses_explicit_source_not_newest_file(tmp_path):
    source = tmp_path / ".codex" / "generated_images" / "thread-1" / "ig_1.png"
    newer = source.with_name("ig_2.png")
    output = tmp_path / ".godotmaker" / "asset-generation" / "codex" / "A01_source.png"
    make_png(source, size=(12, 8))
    time.sleep(0.01)
    make_png(newer, size=(4, 4))

    result = claim_codex_image(str(source), output, asset_id="A01")

    assert result["ok"] is True
    assert result["width"] == 12
    assert result["height"] == 8
    assert output.read_bytes() == source.read_bytes()
    assert output.read_bytes() != newer.read_bytes()


def test_claim_codex_image_rejects_missing_source(tmp_path):
    missing = tmp_path / "missing.png"
    output = tmp_path / "claimed.png"

    with pytest.raises(CodexImageClaimError):
        claim_codex_image(str(missing), output)


def test_cli_outputs_json_error_for_missing_source(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(TOOLS_DIR / "codex_image_claim.py"),
            "--source",
            str(tmp_path / "missing.png"),
            "--out",
            str(tmp_path / "out.png"),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["ok"] is False
    assert "Source image not found" in data["error"]


def test_cli_outputs_json_error_for_output_path_os_error(tmp_path):
    source = tmp_path / "generated" / "ig_1.png"
    output_parent_as_file = tmp_path / "claimed"
    output = output_parent_as_file / "A01_source.png"
    make_png(source)
    output_parent_as_file.write_text("not a directory", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(TOOLS_DIR / "codex_image_claim.py"),
            "--source",
            str(source),
            "--out",
            str(output),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["ok"] is False
    assert data["error"]
