"""End-to-end handoff over the v1 generated-asset contract.

The other tool tests exercise each side of the contract in isolation. This file
covers the seam `/gm-asset` actually walks: write a stable entry, upsert its
pointer into the root index, then have the checker consume the very same
artifacts. Every documented failure mode is asserted to fail closed, so a green
run here means the real pipeline converged on one schema instead of two.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_action_entry_draft import write_action_entry_draft  # noqa: E402
from asset_assets_md_update import AssetsMdUpdateError, update_assets_md  # noqa: E402
from asset_generation_index import (  # noqa: E402
    GenerationIndexError,
    check_index,
    update_index,
)
from asset_stable_entry import (  # noqa: E402
    StableEntryError,
    entry_relative_path,
    stable_output_dir,
    write_entry,
)

TAG = "v0.1.0"
FAMILY = "character-bundle"
ASSET_ID = "player_idle"
INDEX_RELATIVE = ".godotmaker/asset-generation/manifest.json"
ENTRY_TOOL = TOOLS_DIR / "asset_stable_entry.py"
INDEX_TOOL = TOOLS_DIR / "asset_generation_index.py"


def source_relative(asset_id=ASSET_ID, family=FAMILY):
    return f"{stable_output_dir(family, asset_id)}/{asset_id}_source.png"


def artifact_relative(asset_id=ASSET_ID, family=FAMILY):
    """The compiled SpriteFrames a grid_sheet becomes, not its source image."""
    return f"{stable_output_dir(family, asset_id)}/{asset_id}.tres"


def make_entry(asset_id=ASSET_ID, family=FAMILY, **overrides):
    """A `ready` entry with a legitimately compiled artifact.

    A `grid_sheet` compiles to `SpriteFrames`; pointing the artifact at the
    source image instead is the forbidden shortcut the schema now rejects, so
    this fixture must model real future compiler output. It exercises the
    forward-looking schema and is not what `/gm-asset` emits today — see
    ``test_stage_one_chain_registers_but_never_promotes_a_row`` for that.
    """
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
            "type": "SpriteFrames",
            "path": f"res://{artifact_relative(asset_id, family)}",
        },
        "processing_status": "ready",
    }
    entry.update(overrides)
    return entry


def touch(project_root: Path, relative: str) -> Path:
    target = project_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"png")
    return target


def produce_asset(project_root: Path, asset_id=ASSET_ID, family=FAMILY) -> None:
    touch(project_root, source_relative(asset_id, family))
    touch(project_root, artifact_relative(asset_id, family))


def register(project_root: Path, entry: dict) -> Path:
    """Run the two documented registration steps and return the entry path."""
    write_entry(entry, project_root=project_root, check_files=True)
    entry_path = project_root / entry_relative_path(entry["tag"], entry["asset_id"])
    update_index(
        project_root / INDEX_RELATIVE, [entry_path], project_root=project_root
    )
    return entry_path


def read_index(project_root: Path) -> dict:
    return json.loads((project_root / INDEX_RELATIVE).read_text(encoding="utf-8"))


def test_stage_one_chain_registers_but_never_promotes_a_row(tmp_path):
    """The real `/gm-asset` chain as it stands today, end to end.

    The action builder produces the draft and support metadata, the entry
    registers, and the gate passes — but the asset stops at `source_ready`
    because no compiler produced a `SpriteFrames` and no L0-L4 runner verified
    it. The ASSETS.md row must therefore stay `MISSING`. This is the honest
    Stage 1 outcome; a green chain here must not be mistaken for a delivered
    runtime asset.
    """
    sheet = f"{stable_output_dir(FAMILY, ASSET_ID)}/{ASSET_ID}_sheet.png"
    frames = [f"{stable_output_dir(FAMILY, ASSET_ID)}/{ASSET_ID}_f{i}.png" for i in (1, 2)]
    for relative in [sheet, *frames]:
        touch(tmp_path, relative)
    metadata_path = tmp_path / ".godotmaker/asset-generation/processed/p/pipeline-meta.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(
            {
                "frame_count": 2,
                "final_sheet_path": sheet,
                "final_frame_paths": frames,
                    "align": "feet",
                    "shared_scale": True,
                    "action_name": "idle",
                    "fps": 8,
                    "loop": True,
                    "frame_durations": [1, 1],
                    "edge_touch_frames": [],
                "scale_reference": {"checked": True},
            }
        ),
        encoding="utf-8",
    )

    draft_path = tmp_path / ".godotmaker/asset-generation/work/entries/player_idle.json"
    write_action_entry_draft(
        metadata_path,
        asset_id=ASSET_ID,
        tag=TAG,
        production_family=FAMILY,
        project_root=tmp_path,
        out=draft_path,
    )
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    assert draft["processing_status"] == "source_ready"
    assert "godot_artifact" not in draft

    entry_path = register(tmp_path, draft)
    gate = check_index(tmp_path / INDEX_RELATIVE, project_root=tmp_path, check_files=True)
    assert gate["ok"] is True and gate["entry_checks"] == 1

    assets_md = write_assets_md(tmp_path)
    with pytest.raises(AssetsMdUpdateError, match="processing_status is source_ready"):
        update_assets_md(assets_md, [entry_path])
    assert "| generated |" not in assets_md.read_text(encoding="utf-8")
    assert "MISSING" in assets_md.read_text(encoding="utf-8")


def test_written_entry_is_consumed_by_the_index_checker(tmp_path):
    produce_asset(tmp_path)
    entry_path = register(tmp_path, make_entry())

    index = read_index(tmp_path)
    assert index == {
        "version": 1,
        "entries": [
            {
                "asset_id": ASSET_ID,
                "tag": TAG,
                "entry_path": entry_relative_path(TAG, ASSET_ID),
            }
        ],
    }

    summary = check_index(
        tmp_path / INDEX_RELATIVE, project_root=tmp_path, check_entries=True
    )
    assert summary["ok"] is True
    assert summary["entry_count"] == 1
    assert summary["entry_checks"] == 1

    # The checker consumed the same file the writer produced, and that file holds
    # the full entry body while the index holds only the pointer.
    written = json.loads(entry_path.read_text(encoding="utf-8"))
    assert written["production_family"] == FAMILY
    assert written["source_layout"]["type"] == "grid_sheet"
    assert written["godot_artifact"] == {
        "type": "SpriteFrames",
        "path": f"res://{artifact_relative()}",
    }
    assert written["processing_status"] == "ready"
    assert "godot_artifact" not in index["entries"][0]


def write_assets_md(project_root: Path) -> Path:
    assets_md = project_root / "ASSETS.md"
    assets_md.write_text(
        "| ID | Tag | Name | Type | Size | Generation Params | Path | Status |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
        f"| 1 | {TAG} | {ASSET_ID} | sprite | 128x128 | — | {artifact_relative()} | MISSING |\n",
        encoding="utf-8",
    )
    return assets_md


def test_registered_entry_promotes_the_assets_md_row(tmp_path):
    produce_asset(tmp_path)
    entry_path = register(tmp_path, make_entry())
    assets_md = write_assets_md(tmp_path)

    update_assets_md(assets_md, [entry_path])

    text = assets_md.read_text(encoding="utf-8")
    assert "| generated |" in text
    assert f"manifest_entry={entry_relative_path(TAG, ASSET_ID)}" in text


def test_reregistering_the_same_asset_overwrites_one_pointer(tmp_path):
    produce_asset(tmp_path)
    register(tmp_path, make_entry())
    register(tmp_path, make_entry(processing_status="compiled"))

    index = read_index(tmp_path)
    assert len(index["entries"]) == 1
    entry = json.loads(
        (tmp_path / entry_relative_path(TAG, ASSET_ID)).read_text(encoding="utf-8")
    )
    assert entry["processing_status"] == "compiled"


def test_legacy_full_entry_manifest_is_rejected(tmp_path):
    """An old `{version, assets: [...]}` manifest can never be upserted into."""
    produce_asset(tmp_path)
    write_entry(make_entry(), project_root=tmp_path)
    index_path = tmp_path / INDEX_RELATIVE
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps(
            {
                "version": 1,
                "assets": [
                    {
                        "asset_id": ASSET_ID,
                        "tag": TAG,
                        "runtime_artifact": "grid_sheet",
                        "final_path": f"assets/sprites/{ASSET_ID}.png",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    before = index_path.read_text(encoding="utf-8")

    with pytest.raises(GenerationIndexError, match="Legacy runtime_artifact manifest"):
        update_index(
            index_path,
            [tmp_path / entry_relative_path(TAG, ASSET_ID)],
            project_root=tmp_path,
        )

    with pytest.raises(GenerationIndexError, match="Legacy runtime_artifact manifest"):
        check_index(index_path, project_root=tmp_path, check_entries=True)

    # Fail closed: the rejected legacy file is left untouched, not half-migrated.
    assert index_path.read_text(encoding="utf-8") == before


def test_legacy_entry_body_is_rejected_before_the_index_moves(tmp_path):
    produce_asset(tmp_path)
    register(tmp_path, make_entry())
    good_index = read_index(tmp_path)
    assets_md = write_assets_md(tmp_path)

    legacy_path = tmp_path / entry_relative_path(TAG, ASSET_ID)
    legacy = make_entry()
    legacy["runtime_artifact"] = "grid_sheet"
    legacy_path.write_text(json.dumps(legacy), encoding="utf-8")

    with pytest.raises(GenerationIndexError, match="Legacy runtime_artifact schema"):
        update_index(
            tmp_path / INDEX_RELATIVE, [legacy_path], project_root=tmp_path
        )
    with pytest.raises(GenerationIndexError, match="Legacy runtime_artifact schema"):
        check_index(
            tmp_path / INDEX_RELATIVE, project_root=tmp_path, check_entries=True
        )
    with pytest.raises(AssetsMdUpdateError, match="Legacy runtime_artifact schema"):
        update_assets_md(assets_md, [legacy_path])

    assert read_index(tmp_path) == good_index
    assert "| generated |" not in assets_md.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("artifact_path", "message"),
    [
        ("res://assets/sprites/player_idle.png", "must be a file under"),
        (
            f"res://{stable_output_dir(FAMILY, 'other_asset')}/player_idle.png",
            "must be a file under",
        ),
        (
            f"res://{stable_output_dir(FAMILY, ASSET_ID)}/../escape.png",
            "no empty, '.' or '..' segments",
        ),
        (
            f"res://.godotmaker/asset-generation/work/{ASSET_ID}.png",
            "must not depend on the generation work/ workspace",
        ),
    ],
    ids=["outside-generated-tree", "other-asset-dir", "parent-escape", "work-workspace"],
)
def test_out_of_bounds_artifact_path_never_registers(tmp_path, artifact_path, message):
    """A drifting artifact path is rejected on its own merits.

    The draft sits at the canonical entry path so the canonical-path guard
    cannot be what fails; the asserted message pins the rejection to the
    stable-output-directory check itself.
    """
    produce_asset(tmp_path)
    entry = make_entry(godot_artifact={"type": "SpriteFrames", "path": artifact_path})
    draft = tmp_path / entry_relative_path(TAG, ASSET_ID)
    draft.parent.mkdir(parents=True, exist_ok=True)
    draft.write_text(json.dumps(entry), encoding="utf-8")

    with pytest.raises(GenerationIndexError, match=re.escape(message)):
        update_index(tmp_path / INDEX_RELATIVE, [draft], project_root=tmp_path)

    with pytest.raises(StableEntryError, match=re.escape(message)):
        write_entry(entry, project_root=tmp_path, check_files=True)

    assert not (tmp_path / INDEX_RELATIVE).exists()


def test_missing_entry_file_fails_the_index_gate(tmp_path):
    produce_asset(tmp_path)
    entry_path = register(tmp_path, make_entry())
    entry_path.unlink()

    with pytest.raises(GenerationIndexError, match="Entry file not found"):
        check_index(
            tmp_path / INDEX_RELATIVE, project_root=tmp_path, check_entries=True
        )


@pytest.mark.parametrize(
    ("relative", "message"),
    [
        (artifact_relative(), "godot_artifact.path not found"),
        (source_relative(), "source_layout.path not found"),
    ],
    ids=["artifact", "source"],
)
def test_deleting_a_registered_handoff_file_fails_the_gate(tmp_path, relative, message):
    """The gate must prove the files it gates on, not just the schema.

    Registration succeeds while the asset is on disk; deleting it afterwards
    leaves a structurally perfect index whose pointer resolves to a dangling
    path. `--check-entries` alone still passes, which is exactly why the
    documented gate adds `--check-files`.
    """
    produce_asset(tmp_path)
    register(tmp_path, make_entry())
    index_path = tmp_path / INDEX_RELATIVE
    (tmp_path / relative).unlink()

    schema_only = check_index(index_path, project_root=tmp_path, check_entries=True)
    assert schema_only["ok"] is True, "schema-only pass is not the handoff gate"

    with pytest.raises(GenerationIndexError, match=re.escape(message)):
        check_index(index_path, project_root=tmp_path, check_files=True)


def test_check_files_alone_is_the_full_gate(tmp_path):
    """`--check-files` implies `--check-entries` so it can never be a no-op."""
    produce_asset(tmp_path)
    register(tmp_path, make_entry())

    summary = check_index(
        tmp_path / INDEX_RELATIVE, project_root=tmp_path, check_files=True
    )
    assert summary["check_entries"] is True
    assert summary["check_files"] is True
    assert summary["entry_checks"] == 1


def test_index_pointer_must_be_the_canonical_entry_path(tmp_path):
    produce_asset(tmp_path)
    register(tmp_path, make_entry())
    index_path = tmp_path / INDEX_RELATIVE
    data = read_index(tmp_path)
    data["entries"][0]["entry_path"] = ".godotmaker/asset-generation/work/player_idle.json"
    index_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(GenerationIndexError, match="entry_path must be"):
        check_index(index_path, project_root=tmp_path, check_entries=True)


def test_missing_artifact_file_fails_the_write_gate(tmp_path):
    touch(tmp_path, source_relative())

    with pytest.raises(StableEntryError, match="godot_artifact.path not found"):
        write_entry(make_entry(), project_root=tmp_path, check_files=True)

    assert not (tmp_path / entry_relative_path(TAG, ASSET_ID)).exists()


def test_documented_cli_chain_registers_and_validates(tmp_path):
    """The exact command chain `/gm-asset` Step 5 runs must work end to end."""
    produce_asset(tmp_path)
    draft = tmp_path / ".godotmaker/asset-generation/work/entries/player_idle.json"
    draft.parent.mkdir(parents=True, exist_ok=True)
    draft.write_text(json.dumps(make_entry()), encoding="utf-8")

    def run(*args):
        return subprocess.run(
            [sys.executable, *args],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            check=False,
        )

    written = run(
        str(ENTRY_TOOL), str(draft), "--project-root", ".", "--write", "--check-files"
    )
    assert written.returncode == 0, written.stdout + written.stderr
    assert json.loads(written.stdout)["path"] == entry_relative_path(TAG, ASSET_ID)

    upserted = run(
        str(INDEX_TOOL),
        "--project-root",
        ".",
        "--entry-file",
        entry_relative_path(TAG, ASSET_ID),
    )
    assert upserted.returncode == 0, upserted.stdout + upserted.stderr
    assert json.loads(upserted.stdout)["upserted"] == [ASSET_ID]

    gate = run(
        str(INDEX_TOOL), "--project-root", ".", "--check-entries", "--check-files"
    )
    assert gate.returncode == 0, gate.stdout + gate.stderr
    assert json.loads(gate.stdout)["entry_checks"] == 1

    # The same gate turns red the moment the registered artifact disappears.
    (tmp_path / artifact_relative()).unlink()
    broken = run(
        str(INDEX_TOOL), "--project-root", ".", "--check-entries", "--check-files"
    )
    assert broken.returncode == 1
    assert "godot_artifact.path not found" in json.loads(broken.stdout)["error"]


def test_cli_gate_fails_on_a_legacy_manifest(tmp_path):
    index_path = tmp_path / INDEX_RELATIVE
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps({"version": 1, "assets": [{"asset_id": ASSET_ID, "tag": TAG}]}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(INDEX_TOOL), "--project-root", ".", "--check-entries"],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        check=False,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "Regenerate generated assets through /gm-asset" in payload["error"]
