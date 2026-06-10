import json
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_action_manifest_entry import (  # noqa: E402
    ActionManifestEntryError,
    build_action_manifest_entry,
)
from asset_generation_manifest_check import check_manifest  # noqa: E402


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def source_entry():
    return {
        "asset_id": "player_idle",
        "tag": "v0.1.0",
        "family": "character_action_source",
        "production_shape": "action_sheet",
        "runtime_role": "player",
        "source_path": ".godotmaker/asset-generation/sources/player_idle_source.png",
        "final_path": None,
        "derived_from": "player_canonical",
        "canonical_reference": "player_canonical",
        "prompt_path": ".godotmaker/asset-generation/prompts/player_idle.txt",
        "processing_status": "needs_curation",
        "extraction_status": "extracted",
        "curation": {
            "status": "candidate_extracted",
            "strategy": "solid_background_grid",
            "report_path": ".godotmaker/asset-generation/processed/player_idle/curation-report.json",
            "selected_count": 4,
            "rejected_count": 0,
        },
        "qc": {"edge_touch": "ok"},
        "preview_path": None,
        "notes": "",
    }


def metadata(project_root: Path):
    return {
        "version": 1,
        "ok": True,
        "asset_id": "player_idle",
        "tag": "v0.1.0",
        "source_path": ".godotmaker/asset-generation/sources/player_idle_source.png",
        "frame_count": 4,
        "frame_labels": [
            "player_idle_01",
            "player_idle_02",
            "player_idle_03",
            "player_idle_04",
        ],
        "align": "feet",
        "shared_scale": True,
        "curation_report_path": ".godotmaker/asset-generation/processed/player_idle/curation-report.json",
        "edge_touch_frames": [],
        "frames": [],
        "frame_paths": [
            ".godotmaker/asset-generation/processed/player_idle/frames/player_idle_01.png",
            ".godotmaker/asset-generation/processed/player_idle/frames/player_idle_02.png",
            ".godotmaker/asset-generation/processed/player_idle/frames/player_idle_03.png",
            ".godotmaker/asset-generation/processed/player_idle/frames/player_idle_04.png",
        ],
        "sheet_path": ".godotmaker/asset-generation/processed/player_idle/sheet-transparent.png",
        "gif_path": str(project_root / ".godotmaker" / "asset-generation" / "processed" / "player_idle" / "animation.gif"),
        "final_frame_paths": [
            str(project_root / "assets" / "sprites" / "player_idle_01.png"),
            str(project_root / "assets" / "sprites" / "player_idle_02.png"),
            str(project_root / "assets" / "sprites" / "player_idle_03.png"),
            str(project_root / "assets" / "sprites" / "player_idle_04.png"),
        ],
        "final_sheet_path": str(project_root / "assets" / "sprites" / "player_idle_sheet.png"),
        "scale_reference": {"checked": False},
    }


def touch_manifest_files(project_root: Path):
    for raw_path in (
        ".godotmaker/asset-generation/sources/player_idle_source.png",
        ".godotmaker/asset-generation/prompts/player_idle.txt",
        ".godotmaker/asset-generation/processed/player_idle/curation-report.json",
        ".godotmaker/asset-generation/processed/player_idle/animation.gif",
        "assets/sprites/player_idle_01.png",
        "assets/sprites/player_idle_02.png",
        "assets/sprites/player_idle_03.png",
        "assets/sprites/player_idle_04.png",
        "assets/sprites/player_idle_sheet.png",
    ):
        path = project_root / raw_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")


def test_build_action_manifest_entry(tmp_path):
    source_entry_path = tmp_path / "player_idle.json"
    metadata_path = tmp_path / ".godotmaker" / "asset-generation" / "processed" / "player_idle" / "pipeline-meta.json"
    write_json(source_entry_path, source_entry())
    write_json(metadata_path, metadata(tmp_path))

    entry = build_action_manifest_entry(
        metadata_path,
        source_entry_path,
        asset_id="player_idle_delivery",
        project_root=tmp_path,
    )

    assert entry["asset_id"] == "player_idle_delivery"
    assert entry["family"] == "character_frame_output"
    assert entry["runtime_artifact"] == "grid_sheet"
    assert entry["derived_from"] == "player_idle"
    assert entry["canonical_reference"] == "player_canonical"
    assert entry["final_path"] == "assets/sprites/player_idle_sheet.png"
    action = entry["qc"]["action_processing"]
    assert action["frame_count"] == 4
    assert action["metadata_path"] == "assets/sprites/player_idle_sheet.json"
    runtime_metadata_path = tmp_path / action["metadata_path"]
    assert runtime_metadata_path.exists()
    runtime_metadata = json.loads(runtime_metadata_path.read_text(encoding="utf-8"))
    assert runtime_metadata["frame_paths"] == [
        "assets/sprites/player_idle_01.png",
        "assets/sprites/player_idle_02.png",
        "assets/sprites/player_idle_03.png",
        "assets/sprites/player_idle_04.png",
    ]
    assert runtime_metadata["source_metadata_path"] == ".godotmaker/asset-generation/processed/player_idle/pipeline-meta.json"


def test_build_action_manifest_entry_passes_manifest_check_files(tmp_path):
    source_entry_path = tmp_path / "player_idle.json"
    metadata_path = tmp_path / ".godotmaker" / "asset-generation" / "processed" / "player_idle" / "pipeline-meta.json"
    write_json(source_entry_path, source_entry())
    write_json(metadata_path, metadata(tmp_path))
    touch_manifest_files(tmp_path)
    entry = build_action_manifest_entry(
        metadata_path,
        source_entry_path,
        asset_id="player_idle_delivery",
        project_root=tmp_path,
    )
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_json(manifest, {"version": 1, "assets": [entry]})

    result = check_manifest(manifest, project_root=tmp_path, check_files=True)

    assert result["ok"] is True
    assert result["file_checks"] == 9


def test_build_action_manifest_entry_rejects_edge_touch(tmp_path):
    source_entry_path = tmp_path / "player_idle.json"
    metadata_path = tmp_path / ".godotmaker" / "asset-generation" / "processed" / "player_idle" / "pipeline-meta.json"
    bad_metadata = metadata(tmp_path)
    bad_metadata["edge_touch_frames"] = ["player_idle.idle_01"]
    write_json(source_entry_path, source_entry())
    write_json(metadata_path, bad_metadata)

    with pytest.raises(ActionManifestEntryError, match="edge_touch_frames must be empty"):
        build_action_manifest_entry(
            metadata_path,
            source_entry_path,
            asset_id="player_idle_delivery",
            project_root=tmp_path,
        )


def test_cli_writes_entry_file(tmp_path):
    source_entry_path = tmp_path / "player_idle.json"
    metadata_path = tmp_path / ".godotmaker" / "asset-generation" / "processed" / "player_idle" / "pipeline-meta.json"
    out_path = tmp_path / "player_idle_delivery.json"
    write_json(source_entry_path, source_entry())
    write_json(metadata_path, metadata(tmp_path))

    result = subprocess.run(
        [
            sys.executable,
            str(TOOLS_DIR / "asset_action_manifest_entry.py"),
            "--metadata",
            str(metadata_path),
            "--source-entry",
            str(source_entry_path),
            "--asset-id",
            "player_idle_delivery",
            "--project-root",
            str(tmp_path),
            "--out",
            str(out_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert out_path.exists()
    entry = json.loads(out_path.read_text(encoding="utf-8"))
    assert entry["asset_id"] == "player_idle_delivery"
    assert (tmp_path / "assets" / "sprites" / "player_idle_sheet.json").exists()
