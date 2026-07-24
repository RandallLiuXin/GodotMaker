import json
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_output_path import (  # noqa: E402
    check_entry_file,
    check_paths,
    describe_output_dir,
)
from asset_stable_entry import (  # noqa: E402
    StableEntryError,
    assert_within_output_dir,
    check_output_path,
    check_support_files,
    stable_output_dir,
    stable_output_res_path,
)


def _symlink_escape_resolve(monkeypatch, real_stable, escaped):
    """Make ``Path.resolve`` treat ``real_stable`` as a symlink to ``escaped``.

    Portable stand-in for an out-of-project directory symlink so the guard's
    fail-closed behavior is covered on platforms (Windows CI) that cannot create
    symlinks without elevation.
    """
    orig_resolve = Path.resolve

    def fake_resolve(self, *args, **kwargs):
        real = orig_resolve(self, *args, **kwargs)
        if real == real_stable:
            return escaped
        try:
            tail = real.relative_to(real_stable)
        except ValueError:
            return real
        return escaped / tail

    monkeypatch.setattr(Path, "resolve", fake_resolve)

OUTPUT_TOOL = TOOLS_DIR / "asset_output_path.py"


def valid_entry(asset_id="player", family="character-bundle"):
    return {
        "version": 1,
        "asset_id": asset_id,
        "tag": "v0.1.0",
        "production_family": family,
        "source_layout": {
            "type": "grid_sheet",
            "path": f"res://assets/generated/{family}/{asset_id}/{asset_id}.png",
        },
        "godot_artifact": {
            "type": "SpriteFrames",
            "path": f"res://assets/generated/{family}/{asset_id}/{asset_id}.tres",
        },
        "processing_status": "ready",
    }


# --- Deterministic directory computation ------------------------------------

def test_stable_output_dir_is_deterministic():
    first = stable_output_dir("character-bundle", "player")
    second = stable_output_dir("character-bundle", "player")
    assert first == second == "assets/generated/character-bundle/player"
    assert stable_output_res_path("character-bundle", "player") == (
        "res://assets/generated/character-bundle/player"
    )


def test_unrelated_assets_get_disjoint_dirs():
    player = stable_output_dir("character-bundle", "player")
    enemy = stable_output_dir("character-bundle", "enemy")
    other_family = stable_output_dir("ui-kit", "player")
    assert player != enemy != other_family
    # No asset's directory is a prefix of another's, so writes to one can never
    # land inside another.
    assert not enemy.startswith(player + "/")
    assert not other_family.startswith(player + "/")


@pytest.mark.parametrize("family", ["not-a-family", "", "Character-Bundle"])
def test_illegal_family_rejected(family):
    with pytest.raises(StableEntryError, match="production_family"):
        stable_output_dir(family, "player")


@pytest.mark.parametrize("asset_id", ["..", ".", "a/b", "a\\b", "C:", "con", "trail "])
def test_illegal_asset_id_rejected(asset_id):
    with pytest.raises(StableEntryError):
        stable_output_dir("character-bundle", asset_id)


# --- Path constraint --------------------------------------------------------

def test_check_output_path_accepts_file_under_dir():
    assert check_output_path(
        "res://assets/generated/character-bundle/player/frames/idle.png",
        production_family="character-bundle",
        asset_id="player",
        label="p",
    )


@pytest.mark.parametrize(
    "path",
    [
        "res://assets/generated/character-bundle/enemy/enemy.png",   # unrelated asset
        "res://assets/generated/ui-kit/player/player.png",           # wrong family
        "res://assets/generated/character-bundle/player",            # the dir itself
        "res://assets/generated/character-bundle/player-final/x.png",  # drift dir
        "res://tmp/character-bundle/player/x.png",                   # escape
    ],
)
def test_check_output_path_rejects_off_target(path):
    with pytest.raises(StableEntryError):
        check_output_path(
            path, production_family="character-bundle", asset_id="player", label="p"
        )


def test_assert_within_output_dir_accepts_in_tree_target(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    resolved = assert_within_output_dir(
        root,
        root / "assets/generated/ui-kit/coin/coin.png",
        production_family="ui-kit",
        asset_id="coin",
    )
    assert resolved == (root / "assets/generated/ui-kit/coin/coin.png").resolve()


def test_assert_within_output_dir_rejects_symlinked_stable_dir(tmp_path, monkeypatch):
    # If the stable directory itself is a symlink pointing out of the project,
    # both it and the target resolve outside; the guard must still fail closed.
    root = tmp_path / "proj"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    real_stable = Path.resolve(root) / "assets/generated/ui-kit/coin"
    escaped = Path.resolve(outside) / "coin"
    _symlink_escape_resolve(monkeypatch, real_stable, escaped)
    with pytest.raises(StableEntryError, match="outside the project root"):
        assert_within_output_dir(
            root,
            root / "assets/generated/ui-kit/coin/coin.png",
            production_family="ui-kit",
            asset_id="coin",
        )


def test_check_output_path_rejects_work_dependency():
    with pytest.raises(StableEntryError, match="work/ workspace"):
        check_output_path(
            "res://.godotmaker/asset-generation/work/character-bundle/player/tmp.png",
            production_family="character-bundle",
            asset_id="player",
            label="p",
        )


@pytest.mark.parametrize(
    "path",
    [
        "res://C:/Windows/system.ini",   # Windows drive letter
        "res://assets\\generated\\character-bundle\\player\\x.png",  # backslashes
        "res:////server/share/x.png",    # UNC double slash
        "assets/generated/character-bundle/player/x.png",           # missing res://
    ],
)
def test_check_output_path_rejects_windows_and_res_escapes(path):
    with pytest.raises(StableEntryError):
        check_output_path(
            path, production_family="character-bundle", asset_id="player", label="p"
        )


# --- Support files ----------------------------------------------------------

def test_support_files_all_constrained():
    ok = check_support_files(
        [
            "res://assets/generated/character-bundle/player/palette.gpl",
            "res://assets/generated/character-bundle/player/meta/hitbox.json",
        ],
        production_family="character-bundle",
        asset_id="player",
    )
    assert len(ok) == 2


def test_support_files_reject_one_off_target():
    with pytest.raises(StableEntryError, match="support_files\\[1\\]"):
        check_support_files(
            [
                "res://assets/generated/character-bundle/player/palette.gpl",
                "res://assets/generated/character-bundle/enemy/palette.gpl",
            ],
            production_family="character-bundle",
            asset_id="player",
        )


def test_support_files_reject_non_list():
    with pytest.raises(StableEntryError, match="must be a list"):
        check_support_files(
            "res://assets/generated/character-bundle/player/x.png",
            production_family="character-bundle",
            asset_id="player",
        )


# --- describe / check_paths helpers -----------------------------------------

def test_describe_output_dir_shape():
    result = describe_output_dir("tileset", "grass")
    assert result == {
        "ok": True,
        "production_family": "tileset",
        "asset_id": "grass",
        "dir": "assets/generated/tileset/grass",
        "res_dir": "res://assets/generated/tileset/grass",
    }


def test_check_paths_validates_all():
    result = check_paths(
        "character-bundle",
        "player",
        paths=["res://assets/generated/character-bundle/player/player.png"],
        support_files=["res://assets/generated/character-bundle/player/palette.gpl"],
    )
    assert result["ok"] is True
    assert result["checked_paths"] == [
        "res://assets/generated/character-bundle/player/player.png"
    ]


# --- Entry-file validation --------------------------------------------------

def test_check_entry_file_ok(tmp_path):
    entry_file = tmp_path / "entry.json"
    entry_file.write_text(json.dumps(valid_entry()), encoding="utf-8")
    result = check_entry_file(
        entry_file,
        project_root=tmp_path,
        support_files=["res://assets/generated/character-bundle/player/palette.gpl"],
    )
    assert result["ok"] is True
    assert result["dir"] == "assets/generated/character-bundle/player"


def test_check_entry_file_rejects_drifted_entry(tmp_path):
    entry = valid_entry()
    entry["godot_artifact"]["path"] = (
        "res://assets/generated/character-bundle/player_v2/player.tres"
    )
    entry_file = tmp_path / "entry.json"
    entry_file.write_text(json.dumps(entry), encoding="utf-8")
    with pytest.raises(StableEntryError, match="must be a file under"):
        check_entry_file(entry_file, project_root=tmp_path, support_files=[])


# --- CLI --------------------------------------------------------------------

def _run_cli(*args):
    return subprocess.run(
        [sys.executable, str(OUTPUT_TOOL), *args],
        capture_output=True,
        text=True,
    )


def test_cli_computes_dir():
    result = _run_cli("--family", "character-bundle", "--asset-id", "player")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["dir"] == "assets/generated/character-bundle/player"
    assert payload["res_dir"] == "res://assets/generated/character-bundle/player"


def test_cli_validates_path():
    ok = _run_cli(
        "--family", "character-bundle", "--asset-id", "player",
        "--path", "res://assets/generated/character-bundle/player/player.png",
    )
    assert ok.returncode == 0
    assert json.loads(ok.stdout)["ok"] is True

    bad = _run_cli(
        "--family", "character-bundle", "--asset-id", "player",
        "--path", "res://assets/generated/character-bundle/enemy/player.png",
    )
    assert bad.returncode == 1
    assert json.loads(bad.stdout)["ok"] is False


def test_cli_rejects_work_dependency():
    result = _run_cli(
        "--family", "character-bundle", "--asset-id", "player",
        "--path", "res://.godotmaker/asset-generation/work/x.png",
    )
    assert result.returncode == 1
    assert "work/ workspace" in json.loads(result.stdout)["error"]


def test_cli_validates_entry(tmp_path):
    entry_file = tmp_path / "entry.json"
    entry_file.write_text(json.dumps(valid_entry()), encoding="utf-8")
    result = _run_cli("--entry", str(entry_file), "--project-root", str(tmp_path))
    assert result.returncode == 0
    assert json.loads(result.stdout)["dir"] == "assets/generated/character-bundle/player"


def test_cli_entry_rejects_conflicting_identity_flags(tmp_path):
    entry_file = tmp_path / "entry.json"
    entry_file.write_text(json.dumps(valid_entry()), encoding="utf-8")
    result = _run_cli(
        "--entry", str(entry_file), "--family", "character-bundle"
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["ok"] is False


def test_cli_requires_identity_without_entry():
    result = _run_cli("--path", "res://assets/generated/character-bundle/player/x.png")
    assert result.returncode == 1
    assert "required" in json.loads(result.stdout)["error"]
