import json
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_curation_manifest_entry import (  # noqa: E402
    CurationManifestEntryError,
    build_curation_manifest_entry,
)
from asset_generation_manifest_check import check_manifest  # noqa: E402


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def source_entry():
    return {
        "asset_id": "ui_kit_source",
        "tag": "v0.1.0",
        "family": "ui_component_sheet",
        "production_shape": "grid_sheet",
        "runtime_role": "main menu UI component",
        "source_path": ".godotmaker/asset-generation/sources/ui_kit_source.png",
        "final_path": None,
        "derived_from": "ui_canonical",
        "canonical_reference": "ui_canonical",
        "prompt_path": ".godotmaker/asset-generation/prompts/ui_kit_source.txt",
        "processing_status": "needs_curation",
        "extraction_status": "extracted",
        "curation": {
            "status": "candidate_extracted",
            "strategy": "solid_background_autoslice",
            "report_path": ".godotmaker/asset-generation/curation/ui_kit_source.json",
            "selected_count": 1,
            "rejected_count": 1,
        },
        "qc": {},
        "preview_path": None,
        "notes": "",
    }


def selected_report():
    return {
        "version": 1,
        "asset_id": "ui_kit_source",
        "tag": "v0.1.0",
        "source_path": ".godotmaker/asset-generation/sources/ui_kit_source.png",
        "strategy": "solid_background_autoslice",
        "status": "selected",
        "selected_count": 1,
        "rejected_count": 1,
        "selected_candidate_ids": ["ui_kit_source.battle_button"],
        "candidates": [
            {
                "candidate_id": "ui_kit_source.battle_button",
                "name": "battle_button",
                "path": ".godotmaker/asset-generation/curation/ui_kit_source/battle_button.png",
                "state": "selected",
                "bbox": [0, 0, 128, 64],
                "crop_bbox": [8, 8, 120, 56],
                "component_count": 1,
                "selected_component_bbox": [8, 8, 120, 56],
                "selected_component_area": 6400,
                "role": "primary battle button",
                "final_path": "assets/ui/battle_button.png",
            }
        ],
        "rejected": [
            {
                "candidate_id": "ui_kit_source.empty_04",
                "state": "rejected",
                "reason": "empty_cell",
            }
        ],
    }


def touch_manifest_files(project_root: Path):
    for raw_path in (
        ".godotmaker/asset-generation/sources/ui_kit_source.png",
        ".godotmaker/asset-generation/prompts/ui_kit_source.txt",
        ".godotmaker/asset-generation/curation/ui_kit_source.json",
        "assets/ui/battle_button.png",
    ):
        path = project_root / raw_path
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")


def test_build_curation_manifest_entry(tmp_path):
    report_path = tmp_path / ".godotmaker" / "asset-generation" / "curation" / "ui_kit_source.json"
    source_entry_path = tmp_path / "ui_kit_source.json"
    write_json(report_path, selected_report())
    write_json(source_entry_path, source_entry())

    entry = build_curation_manifest_entry(
        report_path,
        source_entry_path,
        candidate="battle_button",
        asset_id="battle_button",
        project_root=tmp_path,
    )

    assert entry["asset_id"] == "battle_button"
    assert entry["family"] == "ui_component_sheet"
    assert entry["runtime_artifact"] == "single"
    assert entry["production_shape"] == "grid_sheet"
    assert entry["runtime_role"] == "primary battle button"
    assert entry["final_path"] == "assets/ui/battle_button.png"
    assert entry["derived_from"] == "ui_kit_source"
    assert entry["curation"]["selected_candidate_ids"] == ["ui_kit_source.battle_button"]
    assert entry["qc"]["curation_candidate"]["name"] == "battle_button"


def test_build_curation_manifest_entry_passes_manifest_check_files(tmp_path):
    report_path = tmp_path / ".godotmaker" / "asset-generation" / "curation" / "ui_kit_source.json"
    source_entry_path = tmp_path / "ui_kit_source.json"
    write_json(report_path, selected_report())
    write_json(source_entry_path, source_entry())
    touch_manifest_files(tmp_path)
    entry = build_curation_manifest_entry(
        report_path,
        source_entry_path,
        candidate="battle_button",
        asset_id="battle_button",
        project_root=tmp_path,
    )
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_json(manifest, {"version": 1, "assets": [entry]})

    result = check_manifest(manifest, project_root=tmp_path, check_files=True)

    assert result["ok"] is True
    assert result["file_checks"] == 4


def test_build_curation_manifest_entry_rejects_unselected_candidate(tmp_path):
    report = selected_report()
    report["candidates"][0]["state"] = "candidate"
    report_path = tmp_path / "report.json"
    source_entry_path = tmp_path / "ui_kit_source.json"
    write_json(report_path, report)
    write_json(source_entry_path, source_entry())

    with pytest.raises(CurationManifestEntryError, match="Candidate is not selected"):
        build_curation_manifest_entry(
            report_path,
            source_entry_path,
            candidate="battle_button",
            asset_id="battle_button",
            project_root=tmp_path,
        )


def test_cli_writes_entry_file(tmp_path):
    report_path = tmp_path / ".godotmaker" / "asset-generation" / "curation" / "ui_kit_source.json"
    source_entry_path = tmp_path / "ui_kit_source.json"
    out_path = tmp_path / "battle_button.json"
    write_json(report_path, selected_report())
    write_json(source_entry_path, source_entry())

    result = subprocess.run(
        [
            sys.executable,
            str(TOOLS_DIR / "asset_curation_manifest_entry.py"),
            "--report",
            str(report_path),
            "--source-entry",
            str(source_entry_path),
            "--candidate",
            "battle_button",
            "--asset-id",
            "battle_button",
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
    assert entry["asset_id"] == "battle_button"
