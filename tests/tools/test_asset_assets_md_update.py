import json
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_assets_md_update import AssetsMdUpdateError, update_assets_md  # noqa: E402


def make_entry(asset_id="player_idle", **overrides):
    entry = {
        "asset_id": asset_id,
        "tag": "v0.1.0",
        "family": "character_frame_output",
        "production_shape": "delivery_sheet",
        "runtime_role": "player",
        "source_path": ".godotmaker/asset-generation/sources/player_idle_source.png",
        "final_path": "assets/sprites/player_idle_sheet.png",
        "prompt_path": ".godotmaker/asset-generation/prompts/player_idle.txt",
        "processing_status": "ready",
        "extraction_status": "processed",
        "curation": {
            "status": "selected",
            "strategy": "transparent_grid",
            "report_path": ".godotmaker/asset-generation/curation/player_idle.json",
        },
    }
    entry.update(overrides)
    return entry


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def write_assets_md(path: Path):
    path.write_text(
        "# Assets\n\n"
        "| ID | Tag | Name | Type | Size | Generation Params | Path | Status |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
        "| 1 | v0.1.0 | player_idle | sprite | 128x128 | prompt=old.txt | assets/sprites/player_idle_sheet.png | MISSING |\n"
        "| 2 | v0.1.0 | coin | sprite | 64x64 | — | assets/sprites/coin.png | MISSING |\n"
        "| 3 | v0.2.0 | player_idle | sprite | 128x128 | — | assets/sprites/player_idle_v2.png | MISSING |\n",
        encoding="utf-8",
    )


def touch_final(path: Path, relative: str = "assets/sprites/player_idle_sheet.png"):
    final_path = path / relative
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_bytes(b"png")


def test_update_assets_md_updates_matching_row_only(tmp_path):
    assets_md = tmp_path / "ASSETS.md"
    entry_file = tmp_path / ".godotmaker" / "asset-generation" / "work" / "manifest-entries" / "player_idle.json"
    write_assets_md(assets_md)
    touch_final(tmp_path)
    write_json(entry_file, make_entry())

    result = update_assets_md(assets_md, [entry_file])

    text = assets_md.read_text(encoding="utf-8")
    assert result["ok"] is True
    assert result["updated"] == ["player_idle"]
    assert "| 1 | v0.1.0 | player_idle | sprite | 128x128 |" in text
    assert "| generated |" in text
    assert "manifest_entry=" in text
    assert "source_path=" not in text
    assert "final_path=" not in text
    assert "curation_report=" not in text
    assert "| 3 | v0.2.0 | player_idle | sprite | 128x128 | — | assets/sprites/player_idle_v2.png | MISSING |" in text


def test_update_assets_md_updates_multiple_entries(tmp_path):
    assets_md = tmp_path / "ASSETS.md"
    player_entry = tmp_path / "player_idle.json"
    coin_entry = tmp_path / "coin.json"
    write_assets_md(assets_md)
    touch_final(tmp_path)
    touch_final(tmp_path, "assets/sprites/coin.png")
    write_json(player_entry, make_entry())
    write_json(
        coin_entry,
        make_entry(
            "coin",
            family="runtime_sprite",
            production_shape="single_image",
            source_path=".godotmaker/asset-generation/sources/coin_source.png",
            final_path="assets/sprites/coin.png",
            prompt_path=".godotmaker/asset-generation/prompts/coin.txt",
            curation={"status": "not_required", "strategy": "single_image"},
        ),
    )

    result = update_assets_md(assets_md, [player_entry, coin_entry])

    assert result["updated"] == ["player_idle", "coin"]
    assert assets_md.read_text(encoding="utf-8").count("| generated |") == 2


def test_update_assets_md_rejects_missing_row(tmp_path):
    assets_md = tmp_path / "ASSETS.md"
    entry_file = tmp_path / "missing.json"
    write_assets_md(assets_md)
    touch_final(tmp_path)
    write_json(entry_file, make_entry("missing_asset"))

    with pytest.raises(AssetsMdUpdateError, match="missing rows"):
        update_assets_md(assets_md, [entry_file])

    assert "| 1 | v0.1.0 | player_idle" in assets_md.read_text(encoding="utf-8")


def test_update_assets_md_rejects_entry_without_final_path(tmp_path):
    assets_md = tmp_path / "ASSETS.md"
    entry_file = tmp_path / "player_idle.json"
    write_assets_md(assets_md)
    touch_final(tmp_path)
    entry = make_entry()
    entry.pop("final_path")
    write_json(entry_file, entry)

    with pytest.raises(AssetsMdUpdateError, match="missing final_path"):
        update_assets_md(assets_md, [entry_file])


def test_update_assets_md_rejects_missing_final_file(tmp_path):
    assets_md = tmp_path / "ASSETS.md"
    entry_file = tmp_path / "player_idle.json"
    write_assets_md(assets_md)
    write_json(entry_file, make_entry())

    with pytest.raises(AssetsMdUpdateError, match="final_path does not exist"):
        update_assets_md(assets_md, [entry_file])


def test_cli_outputs_json(tmp_path):
    assets_md = tmp_path / "ASSETS.md"
    entry_file = tmp_path / "player_idle.json"
    write_assets_md(assets_md)
    touch_final(tmp_path)
    write_json(entry_file, make_entry())

    result = subprocess.run(
        [
            sys.executable,
            str(TOOLS_DIR / "asset_assets_md_update.py"),
            "--assets-md",
            str(assets_md),
            "--entry-file",
            str(entry_file),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["updated"] == ["player_idle"]
