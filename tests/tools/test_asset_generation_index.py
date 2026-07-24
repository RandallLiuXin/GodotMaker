import json
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_generation_index import (  # noqa: E402
    GenerationIndexError,
    check_index,
    update_index,
)

INDEX_TOOL = TOOLS_DIR / "asset_generation_index.py"


def valid_entry(asset_id="player", tag="v0.1.0"):
    return {
        "version": 1,
        "asset_id": asset_id,
        "tag": tag,
        "production_family": "character-bundle",
        "source_layout": {
            "type": "grid_sheet",
            "path": f"res://assets/generated/character-bundle/{asset_id}/{asset_id}.png",
        },
        "godot_artifact": {
            "type": "SpriteFrames",
            "path": f"res://assets/generated/character-bundle/{asset_id}/{asset_id}.tres",
        },
        "processing_status": "ready",
    }


def index_item(asset_id="player", tag="v0.1.0"):
    return {
        "asset_id": asset_id,
        "tag": tag,
        "entry_path": f".godotmaker/asset-generation/entries/{tag}/{asset_id}.json",
    }


def write_index(path: Path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "entries": entries}), encoding="utf-8")
    return path


def write_entry_file(root: Path, entry) -> Path:
    rel = f".godotmaker/asset-generation/entries/{entry['tag']}/{entry['asset_id']}.json"
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(entry), encoding="utf-8")
    return target


def test_check_valid_index(tmp_path):
    path = write_index(tmp_path / "manifest.json", [index_item(), index_item("enemy")])
    result = check_index(path, project_root=tmp_path)
    assert result["ok"] is True
    assert result["entry_count"] == 2


@pytest.mark.parametrize(
    "entries, match",
    [
        ([{"asset_id": "player", "tag": "v0.1.0"}], "entry_path"),
        ([index_item("player"), index_item("player")], "Duplicate asset_id"),
        (
            [dict(index_item(), entry_path=".godotmaker/asset-generation/entries/v0.1.0/other.json")],
            "entry_path must be",
        ),
        ([dict(index_item(), production_family="character-bundle")], "unexpected fields"),
        ([dict(index_item(), asset_id="../evil")], "path separators"),
    ],
)
def test_invalid_index_rejected(tmp_path, entries, match):
    path = write_index(tmp_path / "manifest.json", entries)
    with pytest.raises(GenerationIndexError, match=match):
        check_index(path, project_root=tmp_path)


def test_extra_root_field_rejected(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps({"version": 1, "entries": [], "unexpected": True}), encoding="utf-8"
    )
    with pytest.raises(GenerationIndexError, match="unexpected fields: unexpected"):
        check_index(path, project_root=tmp_path)


@pytest.mark.parametrize("version", [2, True, False, 1.0, "1", None])
def test_bad_version_rejected(tmp_path, version):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"version": version, "entries": []}), encoding="utf-8")
    with pytest.raises(GenerationIndexError, match="version must be integer 1"):
        check_index(path, project_root=tmp_path)


@pytest.mark.parametrize(
    "entry_path",
    [
        ".godotmaker\\asset-generation\\entries\\v0.1.0\\player.json",  # backslashes
        ".godotmaker/asset-generation/entries/v0.1.0//player.json",     # double slash
        "./.godotmaker/asset-generation/entries/v0.1.0/player.json",    # leading ./
        ".godotmaker/asset-generation/entries/v0.1.0/./player.json",    # inner ./
    ],
)
def test_non_canonical_entry_path_rejected(tmp_path, entry_path):
    item = dict(index_item(), entry_path=entry_path)
    path = write_index(tmp_path / "manifest.json", [item])
    with pytest.raises(GenerationIndexError, match="entry_path must be"):
        check_index(path, project_root=tmp_path)


def test_legacy_manifest_demands_regeneration(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps({"version": 1, "assets": [{"asset_id": "player", "runtime_artifact": "grid_sheet"}]}),
        encoding="utf-8",
    )
    with pytest.raises(GenerationIndexError, match="Regenerate generated assets through /gm-asset"):
        check_index(path, project_root=tmp_path)


def test_legacy_field_in_item_rejected(tmp_path):
    item = index_item()
    item["runtime_artifact"] = "grid_sheet"
    path = write_index(tmp_path / "manifest.json", [item])
    with pytest.raises(GenerationIndexError, match="Regenerate"):
        check_index(path, project_root=tmp_path)


def test_check_entries_resolves_files(tmp_path):
    write_entry_file(tmp_path, valid_entry())
    path = write_index(tmp_path / ".godotmaker/asset-generation/manifest.json", [index_item()])
    result = check_index(path, project_root=tmp_path, check_entries=True)
    assert result["entry_checks"] == 1


def test_check_entries_missing_file(tmp_path):
    path = write_index(tmp_path / ".godotmaker/asset-generation/manifest.json", [index_item()])
    with pytest.raises(GenerationIndexError, match="Entry file not found"):
        check_index(path, project_root=tmp_path, check_entries=True)


def test_check_entries_identity_mismatch(tmp_path):
    entry = valid_entry()
    # Write the entry file at the player path but with a mismatched asset_id inside.
    rel = ".godotmaker/asset-generation/entries/v0.1.0/player.json"
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    mismatched = dict(entry, asset_id="enemy")
    target.write_text(json.dumps(mismatched), encoding="utf-8")
    path = write_index(tmp_path / ".godotmaker/asset-generation/manifest.json", [index_item()])
    with pytest.raises(GenerationIndexError, match="does not match index item"):
        check_index(path, project_root=tmp_path, check_entries=True)


def test_update_index_writes_pointers_only(tmp_path):
    entry_file = write_entry_file(tmp_path, valid_entry())
    index_path = tmp_path / ".godotmaker/asset-generation/manifest.json"
    result = update_index(index_path, [entry_file], project_root=tmp_path)
    assert result["ok"] is True
    assert result["upserted"] == ["player"]

    data = json.loads(index_path.read_text(encoding="utf-8"))
    assert data == {"version": 1, "entries": [index_item()]}
    # The pointer body carries no source_layout / godot_artifact duplication.
    assert set(data["entries"][0].keys()) == {"asset_id", "tag", "entry_path"}


def test_update_index_upsert_overwrites(tmp_path):
    entry_file = write_entry_file(tmp_path, valid_entry())
    index_path = tmp_path / ".godotmaker/asset-generation/manifest.json"
    update_index(index_path, [entry_file], project_root=tmp_path)
    update_index(index_path, [entry_file], project_root=tmp_path)
    data = json.loads(index_path.read_text(encoding="utf-8"))
    assert len(data["entries"]) == 1


def test_update_index_rejects_corrupt_existing(tmp_path):
    # A pre-existing index carrying a root-level extra field must not be silently
    # "repaired" on upsert.
    index_path = tmp_path / ".godotmaker/asset-generation/manifest.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps({"version": 1, "entries": [], "unexpected": True}), encoding="utf-8"
    )
    entry_file = write_entry_file(tmp_path, valid_entry())
    with pytest.raises(GenerationIndexError, match="unexpected fields"):
        update_index(index_path, [entry_file], project_root=tmp_path)


def test_update_index_rejects_non_canonical_entry_path(tmp_path):
    # Content is valid but the file is not at entries/<tag>/<asset_id>.json, so the
    # pointer would dangle; the run must fail closed instead of writing it.
    loose = tmp_path / "input.json"
    loose.write_text(json.dumps(valid_entry()), encoding="utf-8")
    index_path = tmp_path / ".godotmaker/asset-generation/manifest.json"
    with pytest.raises(GenerationIndexError, match="canonical entry path"):
        update_index(index_path, [loose], project_root=tmp_path)
    assert not index_path.exists()


def test_update_index_rejects_legacy_existing(tmp_path):
    index_path = tmp_path / ".godotmaker/asset-generation/manifest.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps({"version": 1, "assets": []}), encoding="utf-8")
    entry_file = write_entry_file(tmp_path, valid_entry())
    with pytest.raises(GenerationIndexError, match="Regenerate"):
        update_index(index_path, [entry_file], project_root=tmp_path)


def test_update_index_rejects_legacy_entry(tmp_path):
    entry = valid_entry()
    entry["runtime_artifact"] = "grid_sheet"
    rel = ".godotmaker/asset-generation/entries/v0.1.0/player.json"
    entry_file = tmp_path / rel
    entry_file.parent.mkdir(parents=True, exist_ok=True)
    entry_file.write_text(json.dumps(entry), encoding="utf-8")
    index_path = tmp_path / ".godotmaker/asset-generation/manifest.json"
    with pytest.raises(GenerationIndexError, match="Regenerate"):
        update_index(index_path, [entry_file], project_root=tmp_path)


def _run_cli(*args):
    return subprocess.run(
        [sys.executable, str(INDEX_TOOL), *args],
        capture_output=True,
        text=True,
    )


def test_cli_update_and_check(tmp_path):
    entry_file = write_entry_file(tmp_path, valid_entry())
    index_path = tmp_path / ".godotmaker/asset-generation/manifest.json"

    updated = _run_cli(
        str(index_path),
        "--project-root",
        str(tmp_path),
        "--entry-file",
        str(entry_file),
    )
    assert updated.returncode == 0
    assert json.loads(updated.stdout)["upserted"] == ["player"]

    checked = _run_cli(str(index_path), "--project-root", str(tmp_path), "--check-entries")
    assert checked.returncode == 0
    assert json.loads(checked.stdout)["entry_checks"] == 1


def test_cli_rejects_legacy(tmp_path):
    index_path = tmp_path / "manifest.json"
    index_path.write_text(json.dumps({"version": 1, "assets": []}), encoding="utf-8")
    result = _run_cli(str(index_path), "--project-root", str(tmp_path))
    assert result.returncode == 1
    assert "Regenerate" in json.loads(result.stdout)["error"]
