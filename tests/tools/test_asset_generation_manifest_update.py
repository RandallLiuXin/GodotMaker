import json
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_generation_manifest_update import ManifestUpdateError, update_manifest  # noqa: E402


def make_entry(asset_id="player_idle", **overrides):
    entry = {
        "asset_id": asset_id,
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
    entry.update(overrides)
    return entry


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_update_manifest_creates_manifest(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    entry_file = tmp_path / "entry.json"
    write_json(entry_file, make_entry())

    result = update_manifest(manifest, [entry_file], project_root=tmp_path)

    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert result["asset_count"] == 1
    assert data["assets"][0]["asset_id"] == "player_idle"


def test_update_manifest_replaces_existing_asset_id(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_json(manifest, {"version": 1, "assets": [make_entry(notes="old")]})
    entry_file = tmp_path / "entry.json"
    write_json(entry_file, make_entry(notes="new"))

    update_manifest(manifest, [entry_file], project_root=tmp_path)

    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert len(data["assets"]) == 1
    assert data["assets"][0]["notes"] == "new"


def test_update_manifest_preserves_same_asset_id_from_different_tag(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_json(manifest, {"version": 1, "assets": [make_entry(tag="v0.1.0", notes="old")]})
    entry_file = tmp_path / "entry.json"
    write_json(entry_file, make_entry(tag="v0.2.0", notes="new"))

    update_manifest(manifest, [entry_file], project_root=tmp_path)

    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert len(data["assets"]) == 2
    assert {(item["tag"], item["notes"]) for item in data["assets"]} == {
        ("v0.1.0", "old"),
        ("v0.2.0", "new"),
    }


def test_update_manifest_allows_entries_from_one_source_sheet(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    first_entry = tmp_path / "battle_button.json"
    second_entry = tmp_path / "resource_panel.json"
    write_json(first_entry, make_entry(
        "battle_button",
        family="ui_component_sheet",
        production_shape="grid_sheet",
        runtime_role="main menu UI component",
        source_path=".godotmaker/asset-generation/sources/ui_main_kit_source.png",
        final_path="assets/ui/battle_button.png",
        prompt_path=".godotmaker/asset-generation/prompts/ui_main_kit_source.txt",
        runtime_artifact="single",
        curation={
            "status": "selected",
            "strategy": "solid_background_grid",
            "report_path": ".godotmaker/asset-generation/curation/ui_main_kit.json",
            "selected_count": 9,
            "rejected_count": 0,
        },
    ))
    write_json(second_entry, make_entry(
        "resource_panel",
        family="ui_component_sheet",
        production_shape="grid_sheet",
        runtime_role="main menu UI component",
        source_path=".godotmaker/asset-generation/sources/ui_main_kit_source.png",
        final_path="assets/ui/resource_panel.png",
        prompt_path=".godotmaker/asset-generation/prompts/ui_main_kit_source.txt",
        runtime_artifact="single",
        curation={
            "status": "selected",
            "strategy": "solid_background_grid",
            "report_path": ".godotmaker/asset-generation/curation/ui_main_kit.json",
            "selected_count": 9,
            "rejected_count": 0,
        },
    ))

    result = update_manifest(manifest, [first_entry, second_entry], project_root=tmp_path)

    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert result["asset_count"] == 2
    assert {item["asset_id"] for item in data["assets"]} == {
        "battle_button",
        "resource_panel",
    }


def test_update_manifest_rejects_duplicate_existing_entries(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_json(
        manifest,
        {
            "version": 1,
            "assets": [
                make_entry(notes="first"),
                make_entry(notes="second"),
            ],
        },
    )
    entry_file = tmp_path / "entry.json"
    write_json(entry_file, make_entry(notes="new"))

    with pytest.raises(ManifestUpdateError, match="duplicate asset_id"):
        update_manifest(manifest, [entry_file], project_root=tmp_path)


def test_update_manifest_rejects_manifest_shaped_entry_file(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    entry_file = tmp_path / "entries.json"
    write_json(
        entry_file,
        {
            "version": 1,
            "assets": [
                make_entry("player_idle"),
                make_entry(
                    "coin",
                    family="runtime_sprite",
                    production_shape="single_image",
                    runtime_role="pickup",
                    source_path=".godotmaker/asset-generation/sources/coin_source.png",
                    final_path="assets/sprites/coin.png",
                    prompt_path=".godotmaker/asset-generation/prompts/coin.txt",
                ),
            ],
        },
    )

    with pytest.raises(ManifestUpdateError, match="not a manifest"):
        update_manifest(manifest, [entry_file], project_root=tmp_path)


def test_update_manifest_rejects_malformed_existing_manifest(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_json(manifest, {"version": 1})
    entry_file = tmp_path / "entry.json"
    write_json(entry_file, make_entry())

    with pytest.raises(ManifestUpdateError, match="missing assets"):
        update_manifest(manifest, [entry_file], project_root=tmp_path)


def test_update_manifest_rejects_invalid_entry_without_writing(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    write_json(manifest, {"version": 1, "assets": [make_entry(notes="old")]})
    entry_file = tmp_path / "entry.json"
    write_json(entry_file, make_entry(family="model_reference"))

    with pytest.raises(ManifestUpdateError, match="family is not allowed"):
        update_manifest(manifest, [entry_file], project_root=tmp_path)

    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["assets"][0]["notes"] == "old"


def test_cli_outputs_json(tmp_path):
    manifest = tmp_path / ".godotmaker" / "asset-generation" / "manifest.json"
    entry_file = tmp_path / "entry.json"
    write_json(entry_file, make_entry())

    result = subprocess.run(
        [
            sys.executable,
            str(TOOLS_DIR / "asset_generation_manifest_update.py"),
            "--manifest",
            str(manifest),
            "--entry-file",
            str(entry_file),
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
    assert data["upserted"] == ["player_idle"]
