import json
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_generation_manifest_check import ManifestCheckError, check_manifest  # noqa: E402


def write_manifest(path: Path, asset_overrides=None):
    asset = {
        "asset_id": "player_idle",
        "tag": "v0.1.0",
        "family": "character_action_source",
        "production_shape": "action_sheet",
        "runtime_role": "player",
        "source_path": ".godotmaker/asset-generation/sources/player_idle_source.png",
        "final_path": "assets/sprites/player_idle.png",
        "derived_from": "player_canonical",
        "canonical_reference": "player_canonical",
        "prompt_path": ".godotmaker/asset-generation/prompts/player_idle.txt",
        "processing_status": "ready",
        "extraction_status": "processed",
        "curation": {
            "status": "selected",
            "strategy": "transparent_grid",
            "report_path": ".godotmaker/asset-generation/curation/player_idle.json",
            "selected_count": 4,
            "rejected_count": 0,
        },
        "qc": {"alpha": "ok"},
        "preview_path": None,
        "notes": "",
    }
    if asset_overrides:
        asset.update(asset_overrides)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": 1, "assets": [asset]}),
        encoding="utf-8",
    )


def touch(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")


def test_check_manifest_accepts_valid_schema(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(manifest)

    result = check_manifest(manifest, project_root=tmp_path)

    assert result["ok"] is True
    assert result["asset_count"] == 1
    assert result["check_files"] is False


def test_check_manifest_rejects_unknown_family(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(manifest, {"family": "model_reference"})

    with pytest.raises(ManifestCheckError, match="family is not allowed"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_rejects_unknown_extraction_status(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(manifest, {"extraction_status": "garbage"})

    with pytest.raises(ManifestCheckError, match="extraction_status is not allowed"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_rejects_unknown_curation_status(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(manifest, {"curation": {"status": "garbage", "strategy": "transparent_grid"}})

    with pytest.raises(ManifestCheckError, match="curation.status is not allowed"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_allows_needs_curation_status(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(
        manifest,
        {
            "processing_status": "needs_curation",
            "extraction_status": "extracted",
            "final_path": None,
            "curation": {
                "status": "needs_curation",
                "strategy": "transparent_grid",
                "report_path": ".godotmaker/asset-generation/curation/player_idle.json",
                "selected_count": 3,
                "rejected_count": 1,
            },
        },
    )

    result = check_manifest(manifest, project_root=tmp_path)

    assert result["asset_count"] == 1


def test_check_manifest_rejects_ready_asset_with_unselected_curation(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(
        manifest,
        {
            "curation": {
                "status": "candidate_extracted",
                "strategy": "transparent_grid",
                "report_path": ".godotmaker/asset-generation/curation/player_idle.json",
                "selected_count": 0,
                "rejected_count": 0,
            },
        },
    )

    with pytest.raises(ManifestCheckError, match="must be selected or not_required"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_rejects_selected_curation_without_selected_count(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(
        manifest,
        {
            "curation": {
                "status": "selected",
                "strategy": "transparent_grid",
                "report_path": ".godotmaker/asset-generation/curation/player_idle.json",
                "selected_count": 0,
                "rejected_count": 0,
            },
        },
    )

    with pytest.raises(ManifestCheckError, match="selected_count must be positive"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_requires_curation_for_source_sheets(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(manifest, {"curation": None})

    with pytest.raises(ManifestCheckError, match="missing curation"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_allows_deferred_source_sheet_without_curation(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(
        manifest,
        {
            "source_path": None,
            "final_path": None,
            "prompt_path": None,
            "processing_status": "deferred",
            "extraction_status": "not_required",
            "curation": None,
        },
    )

    result = check_manifest(manifest, project_root=tmp_path)

    assert result["asset_count"] == 1


def test_check_manifest_rejects_duplicate_asset_id_within_same_tag(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(manifest)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["assets"].append(dict(data["assets"][0]))
    manifest.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ManifestCheckError, match="Duplicate asset_id for tag"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_allows_shared_source_sheet_and_prompt(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(manifest)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    duplicate = dict(data["assets"][0])
    duplicate["asset_id"] = "player_run"
    duplicate["final_path"] = "assets/sprites/player_run.png"
    data["assets"].append(duplicate)
    manifest.write_text(json.dumps(data), encoding="utf-8")

    result = check_manifest(manifest, project_root=tmp_path)

    assert result["asset_count"] == 2


def test_check_manifest_rejects_duplicate_final_paths(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(manifest)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    duplicate = dict(data["assets"][0])
    duplicate["asset_id"] = "enemy_idle"
    data["assets"].append(duplicate)
    manifest.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ManifestCheckError, match="Duplicate final_path path"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_rejects_missing_ready_final_path(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(manifest, {"final_path": None})

    with pytest.raises(ManifestCheckError, match="missing final_path"):
        check_manifest(manifest, project_root=tmp_path)


def test_check_manifest_allows_needs_curation_without_final_path(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(
        manifest,
        {
            "final_path": None,
            "processing_status": "needs_curation",
            "extraction_status": "pending",
        },
    )

    result = check_manifest(manifest, project_root=tmp_path)

    assert result["asset_count"] == 1


def test_check_manifest_checks_files_when_requested(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(manifest)
    touch(tmp_path / ".godotmaker" / "asset-generation" / "sources" / "player_idle_source.png")
    touch(tmp_path / ".godotmaker" / "asset-generation" / "prompts" / "player_idle.txt")
    touch(tmp_path / ".godotmaker" / "asset-generation" / "curation" / "player_idle.json")
    touch(tmp_path / "assets" / "sprites" / "player_idle.png")

    result = check_manifest(manifest, project_root=tmp_path, check_files=True)

    assert result["file_checks"] == 4


def test_check_manifest_reports_missing_file(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(manifest)

    with pytest.raises(ManifestCheckError, match="Source path not found"):
        check_manifest(manifest, project_root=tmp_path, check_files=True)


def test_cli_outputs_json(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_manifest(manifest)

    result = subprocess.run(
        [
            sys.executable,
            str(TOOLS_DIR / "asset_generation_manifest_check.py"),
            str(manifest),
            "--project-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["asset_count"] == 1
