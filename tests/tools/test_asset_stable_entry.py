import copy
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_stable_entry import (  # noqa: E402
    LAYOUT_ARTIFACT_TYPES,
    REFERENCE_LAYOUTS,
    SOURCE_LAYOUT_TYPES,
    StableEntryError,
    _assert_within_root,
    entry_relative_path,
    validate_entry,
    write_entry,
)

STABLE_ENTRY_TOOL = TOOLS_DIR / "asset_stable_entry.py"


def valid_entry(**overrides):
    entry = {
        "version": 1,
        "asset_id": "player",
        "tag": "v0.1.0",
        "production_family": "character-bundle",
        "source_layout": {
            "type": "grid_sheet",
            "path": "res://assets/generated/character-bundle/player/player.png",
        },
        "godot_artifact": {
            "type": "SpriteFrames",
            "path": "res://assets/generated/character-bundle/player/player.tres",
        },
        "processing_status": "ready",
    }
    entry.update(overrides)
    return entry


def reference_entry(**overrides):
    entry = {
        "version": 1,
        "asset_id": "title_screen",
        "tag": "v0.1.0",
        "production_family": "screen-reference",
        "source_layout": {
            "type": "reference",
            "path": "res://assets/references/title_screen.png",
        },
        "processing_status": "source_ready",
    }
    entry.update(overrides)
    return entry


def test_validate_ready_entry_ok():
    assert validate_entry(valid_entry()) == valid_entry()


def test_every_non_reference_layout_has_an_artifact_type():
    """Guard the mapping against layout drift.

    ``_validate_godot_artifact`` indexes ``LAYOUT_ARTIFACT_TYPES`` directly, so a
    new ``source_layout.type`` without an entry here would raise ``KeyError``
    instead of a contract error.
    """
    assert set(LAYOUT_ARTIFACT_TYPES) == SOURCE_LAYOUT_TYPES - REFERENCE_LAYOUTS
    assert all(
        isinstance(artifact_types, tuple) and artifact_types
        for artifact_types in LAYOUT_ARTIFACT_TYPES.values()
    )
    assert LAYOUT_ARTIFACT_TYPES == {
        "single": ("Texture2D", "StyleBoxTexture"),
        "grid_sheet": ("SpriteFrames",),
        "region_atlas": ("AtlasTexture", "StyleBoxTexture"),
        "theme_recipe": ("Theme",),
        "tile_atlas": ("TileSet",),
    }


@pytest.mark.parametrize(
    ("layout", "artifact_type"),
    [
        (layout, artifact_type)
        for layout, artifact_types in sorted(LAYOUT_ARTIFACT_TYPES.items())
        for artifact_type in artifact_types
    ],
)
def test_matching_artifact_type_is_accepted(layout, artifact_type):
    entry = valid_entry(
        source_layout={
            "type": layout,
            "path": "res://assets/generated/character-bundle/player/player.png",
        },
        godot_artifact={
            "type": artifact_type,
            "path": "res://assets/generated/character-bundle/player/player.tres",
        },
    )
    validate_entry(entry)


@pytest.mark.parametrize(
    ("layout", "artifact_type"),
    [
        # The exact shortcut the Owner ruling forbids: a static image published
        # as if it were the compiled SpriteFrames a worker was promised.
        ("grid_sheet", "Texture2D"),
        ("region_atlas", "Texture2D"),
        ("tile_atlas", "Texture2D"),
        ("theme_recipe", "Texture2D"),
        ("single", "SpriteFrames"),
        ("grid_sheet", "AtlasTexture"),
        ("region_atlas", "SpriteFrames"),
        ("single", "Resource"),
        ("grid_sheet", "StyleBoxTexture"),
        ("theme_recipe", "StyleBoxTexture"),
        ("tile_atlas", "StyleBoxTexture"),
    ],
)
def test_mismatched_artifact_type_is_rejected(layout, artifact_type):
    entry = valid_entry(
        source_layout={
            "type": layout,
            "path": "res://assets/generated/character-bundle/player/player.png",
        },
        godot_artifact={
            "type": artifact_type,
            "path": "res://assets/generated/character-bundle/player/player.tres",
        },
    )
    expected = ", ".join(LAYOUT_ARTIFACT_TYPES[layout])
    with pytest.raises(
        StableEntryError,
        match=re.escape(f"must be one of: {expected}; not {artifact_type}"),
    ):
        validate_entry(entry)


def test_reference_entry_needs_no_artifact():
    validate_entry(reference_entry())


@pytest.mark.parametrize("status", ["pending", "source_ready", "failed"])
def test_reference_entry_accepts_only_its_process_and_failure_statuses(status):
    validate_entry(reference_entry(processing_status=status))


@pytest.mark.parametrize("status", ["compiled", "ready"])
def test_reference_entry_rejects_runtime_ladder_statuses(status):
    with pytest.raises(StableEntryError, match=rf"not {status}"):
        validate_entry(reference_entry(processing_status=status))


def test_reference_entry_rejects_artifact():
    entry = reference_entry(
        godot_artifact={"type": "Texture2D", "path": "res://x.tres"}
    )
    with pytest.raises(StableEntryError, match="reference"):
        validate_entry(entry)


def test_artifact_required_for_ready_non_reference():
    entry = valid_entry()
    del entry["godot_artifact"]
    with pytest.raises(StableEntryError, match="godot_artifact is required"):
        validate_entry(entry)


def test_artifact_optional_before_ready():
    entry = valid_entry(processing_status="source_ready")
    del entry["godot_artifact"]
    validate_entry(entry)


@pytest.mark.parametrize(
    "mutate, match",
    [
        (lambda e: e.update(version=2), "version"),
        (lambda e: e.pop("asset_id"), "asset_id"),
        (lambda e: e.update(asset_id="../evil"), "path separators"),
        (lambda e: e.update(tag="a/b"), "path separators"),
        (lambda e: e.update(production_family="not-a-family"), "production_family"),
        (lambda e: e.update(processing_status="weird"), "processing_status"),
        (lambda e: e["source_layout"].update(type="bogus"), "source_layout.type"),
        (lambda e: e["source_layout"].update(path="assets/x.png"), "res://"),
        (lambda e: e["godot_artifact"].update(type="123bad"), "ClassDB"),
        (lambda e: e["godot_artifact"].update(path="/abs/x.tres"), "res://"),
    ],
)
def test_invalid_entries_rejected(mutate, match):
    entry = valid_entry()
    mutate(entry)
    with pytest.raises(StableEntryError, match=match):
        validate_entry(entry)


@pytest.mark.parametrize(
    "field",
    ["runtime_artifact", "production_shape", "extraction_status", "family", "final_path"],
)
def test_legacy_fields_demand_regeneration(field):
    entry = valid_entry()
    entry[field] = "grid_sheet"
    with pytest.raises(StableEntryError, match="Regenerate this asset through /gm-asset"):
        validate_entry(entry)


def test_legacy_field_nested_in_source_layout():
    entry = valid_entry()
    entry["source_layout"]["runtime_artifact"] = "grid_sheet"
    with pytest.raises(StableEntryError, match="Regenerate"):
        validate_entry(entry)


@pytest.mark.parametrize("field", ["tag", "asset_id"])
@pytest.mark.parametrize(
    "bad",
    [".", "..", "C:", "a:b", "a/b", "a\\b", "con", "CON", "nul.png", "lpt1", "aux",
     "a<b", "a>b", 'a"b', "a|b", "a?b", "a*b", "trail ", " lead", "trail."],
)
def test_identity_must_be_safe_path_segment(field, bad):
    entry = valid_entry(**{field: bad})
    with pytest.raises(StableEntryError):
        validate_entry(entry)


def test_write_entry_rejects_unsafe_tag(tmp_path):
    entry = valid_entry(tag=".")
    with pytest.raises(StableEntryError, match="must not be"):
        write_entry(entry, project_root=tmp_path)
    # Nothing was written outside the (never-created) canonical location.
    assert not (tmp_path / ".godotmaker/asset-generation/entries/player.json").exists()


@pytest.mark.parametrize("field", ["asset_id", "tag"])
def test_stable_identifiers_reject_generation_param_delimiters(field):
    entry = valid_entry()
    entry[field] = "unsafe;identifier"

    with pytest.raises(StableEntryError, match="reserved characters"):
        validate_entry(entry)


@pytest.mark.parametrize("version", [True, False, 1.0, "1", None, 2])
def test_version_must_be_strict_integer(version):
    entry = valid_entry(version=version)
    with pytest.raises(StableEntryError, match="version"):
        validate_entry(entry)


@pytest.mark.parametrize(
    "res_path",
    [
        "res://C:/Windows/system.ini",   # drive letter
        "res://c:/x.png",
        "res:///tmp/x.png",              # absolute (empty first segment)
        "res:////server/share/x.png",    # UNC-style double slash
        "res://a//b.png",                # empty middle segment
        "res://a/./b.png",               # '.' segment
        "res://a/../b.png",              # '..' segment
        "res://..",                      # bare parent
        "res://a\\b.png",                # backslash
    ],
)
def test_source_layout_path_rejects_escapes(res_path):
    entry = valid_entry()
    entry["source_layout"]["path"] = res_path
    with pytest.raises(StableEntryError):
        validate_entry(entry)


def test_godot_artifact_path_rejects_escapes():
    entry = valid_entry()
    entry["godot_artifact"]["path"] = "res://C:/Windows/system.ini"
    with pytest.raises(StableEntryError, match="drive letter"):
        validate_entry(entry)


@pytest.mark.parametrize(
    "path",
    [
        "res://assets/generated/ui-kit/player/player.png",           # wrong family
        "res://assets/generated/character-bundle/enemy/player.png",  # unrelated asset dir
        "res://assets/generated/character-bundle/player.png",        # missing asset dir
        "res://assets/character-bundle/player/player.png",           # not under generated
        "res://assets/generated/character-bundle/player-v2/x.png",   # v2 drift dir
        "res://assets/generated/character-bundle/player_20240101/x.png",  # timestamp drift
    ],
)
def test_source_layout_path_must_be_under_stable_dir(path):
    entry = valid_entry()
    entry["source_layout"]["path"] = path
    with pytest.raises(StableEntryError, match="must be a file under"):
        validate_entry(entry)


def test_godot_artifact_path_must_be_under_stable_dir():
    entry = valid_entry()
    entry["godot_artifact"]["path"] = "res://assets/generated/character-bundle/enemy/enemy.tres"
    with pytest.raises(StableEntryError, match="must be a file under"):
        validate_entry(entry)


@pytest.mark.parametrize(
    "path",
    [
        "res://.godotmaker/asset-generation/work/character-bundle/player/player.png",
        "res://.godotmaker/asset-generation/work",
    ],
)
def test_work_dir_dependency_rejected(path):
    entry = valid_entry()
    entry["source_layout"]["path"] = path
    with pytest.raises(StableEntryError, match="work/ workspace"):
        validate_entry(entry)


def test_nested_support_path_under_stable_dir_ok():
    # A deeper file (e.g. a support frame) under the asset directory is allowed.
    entry = valid_entry()
    entry["source_layout"]["path"] = (
        "res://assets/generated/character-bundle/player/frames/idle.png"
    )
    validate_entry(entry)


def test_reference_layout_exempt_from_generated_tree():
    # A reference is not a runtime handoff asset; it keeps its own location and
    # is only held to res-path cleanliness.
    validate_entry(reference_entry())
    outside_tree = reference_entry(
        source_layout={"type": "reference", "path": "res://docs/refs/title.png"}
    )
    validate_entry(outside_tree)


def test_reference_layout_requires_reference_family():
    # A runtime family must not use a reference layout to escape the stable-dir
    # constraint with an arbitrary path.
    entry = valid_entry(
        source_layout={"type": "reference", "path": "res://docs/anything.png"},
    )
    del entry["godot_artifact"]
    with pytest.raises(StableEntryError, match="reference source_layout is only allowed"):
        validate_entry(entry)


def test_reference_family_requires_reference_layout():
    entry = reference_entry(
        source_layout={
            "type": "single",
            "path": "res://assets/generated/screen-reference/title_screen/title_screen.png",
        },
    )
    with pytest.raises(StableEntryError, match="must use a reference source_layout"):
        validate_entry(entry)


def test_containment_runs_without_check_files(tmp_path):
    # A symlinked assets tree pointing outside the root must be rejected even
    # when only a project_root is supplied (the index registration path), not
    # just under check_files=True.
    outside = tmp_path.parent / "outside_containment"
    outside.mkdir(exist_ok=True)
    root = tmp_path / "proj"
    root.mkdir()
    try:
        (root / "assets").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted on this platform")
    with pytest.raises(StableEntryError, match="outside the project root"):
        validate_entry(valid_entry(), project_root=root)


def test_check_files_rejects_path_outside_root(tmp_path):
    # A clean, constraint-conforming res:// path can never escape, but the
    # post-resolve guard holds even if a symlink or ``project_root`` trick
    # pointed the stable directory elsewhere.
    outside = tmp_path.parent / "outside"
    outside.mkdir()
    root = tmp_path / "proj"
    root.mkdir()
    # Symlink the whole assets tree inside the root to a sibling outside it.
    link = root / "assets"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted on this platform")
    entry = valid_entry(
        source_layout={
            "type": "single",
            "path": "res://assets/generated/character-bundle/player/player.png",
        },
    )
    del entry["godot_artifact"]
    entry["processing_status"] = "source_ready"
    with pytest.raises(StableEntryError, match="outside the project root"):
        validate_entry(entry, project_root=root, check_files=True)


def test_assert_within_root_rejects_outside(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    _assert_within_root(root, root / "assets" / "x.png", "source_layout.path")
    with pytest.raises(StableEntryError, match="outside the project root"):
        _assert_within_root(root, tmp_path / "outside" / "x.png", "source_layout.path")


def test_godot_artifact_rejects_extra_keys():
    entry = valid_entry()
    entry["godot_artifact"]["receipt"] = {"hash": "abc"}
    with pytest.raises(StableEntryError, match="godot_artifact must only hold type and path"):
        validate_entry(entry)


def test_source_layout_rejects_extra_keys():
    entry = valid_entry()
    entry["source_layout"]["grid"] = [4, 4]
    with pytest.raises(StableEntryError, match="source_layout must only hold type and path"):
        validate_entry(entry)


def test_check_files_requires_present_paths(tmp_path):
    entry = valid_entry()
    with pytest.raises(StableEntryError, match="source_layout.path not found"):
        validate_entry(entry, project_root=tmp_path, check_files=True)

    src = tmp_path / "assets/generated/character-bundle/player/player.png"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"png")
    with pytest.raises(StableEntryError, match="godot_artifact.path not found"):
        validate_entry(entry, project_root=tmp_path, check_files=True)

    (tmp_path / "assets/generated/character-bundle/player/player.tres").write_text("res")
    validate_entry(entry, project_root=tmp_path, check_files=True)


def test_entry_relative_path():
    assert (
        entry_relative_path("v0.1.0", "player")
        == ".godotmaker/asset-generation/entries/v0.1.0/player.json"
    )


def test_write_entry_serializes_to_canonical_path(tmp_path):
    result = write_entry(valid_entry(), project_root=tmp_path)
    assert result["ok"] is True
    assert result["path"] == ".godotmaker/asset-generation/entries/v0.1.0/player.json"
    written = json.loads((tmp_path / result["path"]).read_text(encoding="utf-8"))
    assert written == valid_entry()


def test_validate_allows_internal_extra_fields():
    entry = valid_entry(compiler_receipt={"hash": "abc", "compiler": "sprite_frames"})
    validate_entry(entry)


def test_validate_does_not_mutate_input():
    entry = valid_entry()
    snapshot = copy.deepcopy(entry)
    validate_entry(entry)
    assert entry == snapshot


def _run_cli(*args):
    return subprocess.run(
        [sys.executable, str(STABLE_ENTRY_TOOL), *args],
        capture_output=True,
        text=True,
    )


def test_cli_validate_and_write(tmp_path):
    entry_file = tmp_path / "entry.json"
    entry_file.write_text(json.dumps(valid_entry()), encoding="utf-8")

    ok = _run_cli(str(entry_file))
    assert ok.returncode == 0
    assert json.loads(ok.stdout)["ok"] is True

    written = _run_cli(str(entry_file), "--project-root", str(tmp_path), "--write")
    assert written.returncode == 0
    payload = json.loads(written.stdout)
    assert (tmp_path / payload["path"]).exists()


def test_cli_rejects_legacy(tmp_path):
    entry = valid_entry()
    entry["runtime_artifact"] = "grid_sheet"
    entry_file = tmp_path / "legacy.json"
    entry_file.write_text(json.dumps(entry), encoding="utf-8")

    result = _run_cli(str(entry_file))
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "Regenerate" in payload["error"]
