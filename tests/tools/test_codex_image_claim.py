import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
from PIL import Image

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from codex_image_claim import CodexImageClaimError, claim_codex_image, claim_codex_image_batch  # noqa: E402


def make_png(path: Path, size=(12, 8)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, (20, 30, 40, 255)).save(path, format="PNG")


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


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


def test_batch_claim_uses_planned_source_paths(tmp_path):
    source_a = tmp_path / ".codex" / "generated_images" / "thread-a" / "ig_a.png"
    source_b = tmp_path / ".codex" / "generated_images" / "thread-b" / "ig_b.png"
    make_png(source_a, size=(24, 16))
    make_png(source_b, size=(32, 20))
    plan = tmp_path / "plan.json"
    report = tmp_path / "saved-paths.json"
    write_json(
        plan,
        {
            "items": [
                {"asset_id": "A01", "source_path": ".godotmaker/asset-generation/sources/A01_source.png"},
                {"asset_id": "A02", "source_path": ".godotmaker/asset-generation/sources/A02_source.png"},
            ]
        },
    )
    write_json(
        report,
        {
            "ok": True,
            "assets": [
                {"asset_id": "A01", "saved_path": str(source_a)},
                {"asset_id": "A02", "saved_path": str(source_b)},
            ],
        },
    )

    result = claim_codex_image_batch(plan, report, project_root=tmp_path)

    assert result["ok"] is True
    assert len(result["assets"]) == 2
    assert (tmp_path / ".godotmaker/asset-generation/sources/A01_source.png").read_bytes() == source_a.read_bytes()
    assert (tmp_path / ".godotmaker/asset-generation/sources/A02_source.png").read_bytes() == source_b.read_bytes()


def test_batch_claim_supports_scene_reference_plan_shape(tmp_path):
    anchor_source = tmp_path / "anchor.png"
    parallel_source = tmp_path / "parallel.png"
    make_png(anchor_source)
    make_png(parallel_source)
    plan = tmp_path / "scene-plan.json"
    report = tmp_path / "scene-saved-paths.json"
    write_json(
        plan,
        {
            "anchor_item": {
                "asset_id": "scene_main",
                "source_path": ".godotmaker/asset-generation/sources/scene_main_source.png",
            },
            "parallel_items": [
                {
                    "asset_id": "scene_shop",
                    "source_path": ".godotmaker/asset-generation/sources/scene_shop_source.png",
                }
            ],
        },
    )
    write_json(
        report,
        {
            "assets": [
                {"asset_id": "scene_main", "saved_path": str(anchor_source)},
                {"asset_id": "scene_shop", "saved_path": str(parallel_source)},
            ]
        },
    )

    result = claim_codex_image_batch(plan, report, project_root=tmp_path)

    assert result["ok"] is True
    assert (tmp_path / ".godotmaker/asset-generation/sources/scene_main_source.png").exists()
    assert (tmp_path / ".godotmaker/asset-generation/sources/scene_shop_source.png").exists()


def test_batch_claim_rejects_missing_saved_path(tmp_path):
    plan = tmp_path / "plan.json"
    report = tmp_path / "saved-paths.json"
    write_json(plan, {"items": [{"asset_id": "A01", "source_path": ".godotmaker/sources/A01.png"}]})
    write_json(report, {"assets": [{"asset_id": "A01"}]})

    with pytest.raises(CodexImageClaimError, match="saved_path"):
        claim_codex_image_batch(plan, report, project_root=tmp_path)


def test_batch_claim_rejects_source_path_outside_project(tmp_path):
    source = tmp_path / "ig.png"
    make_png(source)
    plan = tmp_path / "plan.json"
    report = tmp_path / "saved-paths.json"
    write_json(plan, {"items": [{"asset_id": "A01", "source_path": "../outside.png"}]})
    write_json(report, {"assets": [{"asset_id": "A01", "saved_path": str(source)}]})

    with pytest.raises(CodexImageClaimError, match="within the project"):
        claim_codex_image_batch(plan, report, project_root=tmp_path)


def test_batch_claim_rejects_unknown_reported_asset(tmp_path):
    source = tmp_path / "ig.png"
    make_png(source)
    plan = tmp_path / "plan.json"
    report = tmp_path / "saved-paths.json"
    write_json(plan, {"items": [{"asset_id": "A01", "source_path": ".godotmaker/sources/A01.png"}]})
    write_json(
        report,
        {
            "assets": [
                {"asset_id": "A01", "saved_path": str(source)},
                {"asset_id": "A99", "saved_path": str(source)},
            ]
        },
    )

    with pytest.raises(CodexImageClaimError, match="unknown asset_id"):
        claim_codex_image_batch(plan, report, project_root=tmp_path)


def test_batch_claim_rejects_missing_reported_asset(tmp_path):
    source = tmp_path / "ig.png"
    make_png(source)
    plan = tmp_path / "plan.json"
    report = tmp_path / "saved-paths.json"
    write_json(
        plan,
        {
            "items": [
                {"asset_id": "A01", "source_path": ".godotmaker/sources/A01.png"},
                {"asset_id": "A02", "source_path": ".godotmaker/sources/A02.png"},
            ]
        },
    )
    write_json(report, {"assets": [{"asset_id": "A01", "saved_path": str(source)}]})

    with pytest.raises(CodexImageClaimError, match="missing asset_id"):
        claim_codex_image_batch(plan, report, project_root=tmp_path)


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


def test_batch_claim_cli_outputs_json_error(tmp_path):
    plan = tmp_path / "plan.json"
    report = tmp_path / "saved-paths.json"
    write_json(plan, {"items": [{"asset_id": "A01", "source_path": ".godotmaker/sources/A01.png"}]})
    write_json(report, {"ok": False, "error": "provider failed"})

    result = subprocess.run(
        [
            sys.executable,
            str(TOOLS_DIR / "codex_image_claim.py"),
            "--plan",
            str(plan),
            "--report",
            str(report),
            "--project-root",
            str(tmp_path),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["ok"] is False
    assert "provider failed" in data["error"]


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
