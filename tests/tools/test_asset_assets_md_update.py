import json
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_assets_md_update import AssetsMdUpdateError, update_assets_md  # noqa: E402
from asset_stable_entry import entry_relative_path, stable_output_dir  # noqa: E402

TAG = "v0.1.0"


def artifact_relative(asset_id: str, family: str = "character-bundle") -> str:
    return f"{stable_output_dir(family, asset_id)}/{asset_id}.png"


def source_relative(asset_id: str, family: str = "character-bundle") -> str:
    return f"{stable_output_dir(family, asset_id)}/{asset_id}_source.png"


def make_entry(asset_id="player_idle", family="character-bundle", **overrides):
    entry = {
        "version": 1,
        "asset_id": asset_id,
        "tag": TAG,
        "production_family": family,
        "source_layout": {
            "type": "grid_sheet",
            "path": f"res://{source_relative(asset_id, family)}",
        },
        "godot_artifact": {
            "type": "Texture2D",
            "path": f"res://{artifact_relative(asset_id, family)}",
        },
        "processing_status": "ready",
    }
    entry.update(overrides)
    return entry


def write_entry(project_root: Path, entry: dict) -> Path:
    path = project_root / entry_relative_path(entry["tag"], entry["asset_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entry), encoding="utf-8")
    return path


def touch(project_root: Path, relative: str) -> None:
    target = project_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"png")


def touch_asset_files(project_root: Path, asset_id: str, family: str = "character-bundle") -> None:
    touch(project_root, source_relative(asset_id, family))
    touch(project_root, artifact_relative(asset_id, family))


def write_assets_md(path: Path):
    path.write_text(
        "# Assets\n\n"
        "| ID | Tag | Name | Type | Size | Generation Params | Path | Status |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
        f"| 1 | {TAG} | player_idle | sprite | 128x128 | prompt=old.txt | "
        f"{artifact_relative('player_idle')} | MISSING |\n"
        f"| 2 | {TAG} | coin | sprite | 64x64 | — | "
        f"{artifact_relative('coin', 'compact-prop-pack')} | MISSING |\n"
        "| 3 | v0.2.0 | player_idle | sprite | 128x128 | — | assets/sprites/player_idle_v2.png | MISSING |\n",
        encoding="utf-8",
    )


def test_update_assets_md_updates_matching_row_only(tmp_path):
    assets_md = tmp_path / "ASSETS.md"
    write_assets_md(assets_md)
    touch_asset_files(tmp_path, "player_idle")
    entry_file = write_entry(tmp_path, make_entry())

    result = update_assets_md(assets_md, [entry_file])

    text = assets_md.read_text(encoding="utf-8")
    assert result["ok"] is True
    assert result["updated"] == ["player_idle"]
    assert f"| 1 | {TAG} | player_idle | sprite | 128x128 |" in text
    assert "| generated |" in text
    assert f"manifest_entry={entry_relative_path(TAG, 'player_idle')}" in text
    assert "source_layout=" not in text
    assert "godot_artifact=" not in text
    assert "curation_report=" not in text
    assert "| 3 | v0.2.0 | player_idle | sprite | 128x128 | — | assets/sprites/player_idle_v2.png | MISSING |" in text


def test_update_assets_md_updates_multiple_entries(tmp_path):
    assets_md = tmp_path / "ASSETS.md"
    write_assets_md(assets_md)
    touch_asset_files(tmp_path, "player_idle")
    touch_asset_files(tmp_path, "coin", "compact-prop-pack")
    player_entry = write_entry(tmp_path, make_entry())
    coin_entry = write_entry(
        tmp_path,
        make_entry(
            "coin",
            family="compact-prop-pack",
            source_layout={
                "type": "single",
                "path": f"res://{source_relative('coin', 'compact-prop-pack')}",
            },
            godot_artifact={
                "type": "Texture2D",
                "path": f"res://{artifact_relative('coin', 'compact-prop-pack')}",
            },
        ),
    )

    result = update_assets_md(assets_md, [player_entry, coin_entry])

    assert result["updated"] == ["player_idle", "coin"]
    assert assets_md.read_text(encoding="utf-8").count("| generated |") == 2


def test_update_assets_md_rejects_missing_row(tmp_path):
    assets_md = tmp_path / "ASSETS.md"
    write_assets_md(assets_md)
    touch_asset_files(tmp_path, "missing_asset")
    entry_file = write_entry(tmp_path, make_entry("missing_asset"))

    with pytest.raises(AssetsMdUpdateError, match="missing rows"):
        update_assets_md(assets_md, [entry_file])

    assert f"| 1 | {TAG} | player_idle" in assets_md.read_text(encoding="utf-8")


def test_update_assets_md_rejects_legacy_entry(tmp_path):
    """A row can never be promoted from an old runtime_artifact entry."""
    assets_md = tmp_path / "ASSETS.md"
    write_assets_md(assets_md)
    touch_asset_files(tmp_path, "player_idle")
    entry = make_entry()
    entry["runtime_artifact"] = "grid_sheet"
    entry_file = write_entry(tmp_path, entry)

    with pytest.raises(AssetsMdUpdateError, match="Legacy runtime_artifact schema"):
        update_assets_md(assets_md, [entry_file])

    assert "| generated |" not in assets_md.read_text(encoding="utf-8")


def test_update_assets_md_rejects_missing_artifact_file(tmp_path):
    assets_md = tmp_path / "ASSETS.md"
    write_assets_md(assets_md)
    touch(tmp_path, source_relative("player_idle"))
    entry_file = write_entry(tmp_path, make_entry())

    with pytest.raises(AssetsMdUpdateError, match="godot_artifact.path not found"):
        update_assets_md(assets_md, [entry_file])


def test_update_assets_md_rejects_non_canonical_entry_path(tmp_path):
    assets_md = tmp_path / "ASSETS.md"
    write_assets_md(assets_md)
    touch_asset_files(tmp_path, "player_idle")
    stray = tmp_path / ".godotmaker" / "asset-generation" / "work" / "player_idle.json"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_text(json.dumps(make_entry()), encoding="utf-8")

    with pytest.raises(AssetsMdUpdateError, match="canonical entry path"):
        update_assets_md(assets_md, [stray])


def test_cli_outputs_json(tmp_path):
    assets_md = tmp_path / "ASSETS.md"
    write_assets_md(assets_md)
    touch_asset_files(tmp_path, "player_idle")
    entry_file = write_entry(tmp_path, make_entry())

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
