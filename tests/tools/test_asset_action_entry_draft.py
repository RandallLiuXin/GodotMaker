import json
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_action_entry_draft import (  # noqa: E402
    ActionEntryDraftError,
    build_action_entry_draft,
    write_action_entry_draft,
)
from asset_stable_entry import stable_output_dir, validate_entry  # noqa: E402

DRAFT_TOOL = TOOLS_DIR / "asset_action_entry_draft.py"
TAG = "v0.1.0"
FAMILY = "character-bundle"
ASSET_ID = "player_idle"


def stable_dir(asset_id=ASSET_ID, family=FAMILY):
    return stable_output_dir(family, asset_id)


def make_metadata(asset_id=ASSET_ID, family=FAMILY, frame_count=2, **overrides):
    root = stable_dir(asset_id, family)
    metadata = {
        "frame_count": frame_count,
        "final_sheet_path": f"{root}/{asset_id}_sheet.png",
        "final_frame_paths": [
            f"{root}/{asset_id}_frame{index + 1}.png" for index in range(frame_count)
        ],
        "align": "feet",
        "shared_scale": True,
        "action_name": "idle",
        "fps": 8,
        "loop": False,
        "frame_durations": [1.0] * frame_count,
        "edge_touch_frames": [],
        "scale_reference": {"checked": True, "source": "idle"},
    }
    metadata.update(overrides)
    return metadata


def write_metadata(project_root: Path, metadata) -> Path:
    path = project_root / ".godotmaker/asset-generation/processed/player/pipeline-meta.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata), encoding="utf-8")
    return path


def touch(project_root: Path, relative: str) -> None:
    target = project_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"png")


def produce(project_root: Path, metadata) -> None:
    touch(project_root, metadata["final_sheet_path"])
    for frame in metadata["final_frame_paths"]:
        touch(project_root, frame)


def build(project_root: Path, metadata_path: Path, **kwargs):
    params = {
        "asset_id": ASSET_ID,
        "tag": TAG,
        "production_family": FAMILY,
        "project_root": project_root,
    }
    params.update(kwargs)
    return build_action_entry_draft(metadata_path, **params)


def test_draft_is_a_valid_v1_entry_stopping_at_source_ready(tmp_path):
    metadata = make_metadata()
    produce(tmp_path, metadata)
    built = build(tmp_path, write_metadata(tmp_path, metadata))

    entry = built["entry"]
    assert entry["asset_id"] == ASSET_ID
    assert entry["tag"] == TAG
    assert entry["production_family"] == FAMILY
    assert entry["source_layout"] == {
        "type": "grid_sheet",
        "path": f"res://{stable_dir()}/{ASSET_ID}_sheet.png",
    }
    # No native compiler and no L0-L4 runner exist, so the draft may not claim a
    # compiled artifact or a worker-consumable state.
    assert entry["processing_status"] == "source_ready"
    assert "godot_artifact" not in entry
    validate_entry(entry, project_root=tmp_path, check_files=True)


def test_support_metadata_carries_the_deterministic_action_facts(tmp_path):
    metadata = make_metadata(frame_count=3)
    produce(tmp_path, metadata)
    built = build(tmp_path, write_metadata(tmp_path, metadata))

    support = built["support"]
    assert built["support_path"] == f"{stable_dir()}/{ASSET_ID}.json"
    assert support["frame_count"] == 3
    assert len(support["frame_paths"]) == 3
    assert all(path.startswith(f"res://{stable_dir()}/") for path in support["frame_paths"])
    assert support["align"] == "feet"
    assert support["shared_scale"] is True
    assert support["action_name"] == "idle"
    assert support["fps"] == 8.0
    assert support["loop"] is False
    assert support["frame_durations"] == [1.0, 1.0, 1.0]
    assert support["edge_touch_frames"] == []
    assert support["scale_reference"] == {"checked": True, "source": "idle"}
    assert support["source_metadata_path"].startswith(".godotmaker/asset-generation/")


def test_write_emits_support_file_beside_the_sheet_and_the_draft(tmp_path):
    metadata = make_metadata()
    produce(tmp_path, metadata)
    metadata_path = write_metadata(tmp_path, metadata)
    out = tmp_path / ".godotmaker/asset-generation/work/entries/player_idle.json"

    result = write_action_entry_draft(
        metadata_path,
        asset_id=ASSET_ID,
        tag=TAG,
        production_family=FAMILY,
        project_root=tmp_path,
        out=out,
    )

    assert result["ok"] is True
    assert result["frame_count"] == 2
    support = tmp_path / f"{stable_dir()}/{ASSET_ID}.json"
    assert support.exists()
    assert json.loads(support.read_text(encoding="utf-8"))["frame_count"] == 2
    assert json.loads(out.read_text(encoding="utf-8"))["processing_status"] == "source_ready"


def test_frame_count_must_match_the_listed_frames(tmp_path):
    metadata = make_metadata(frame_count=3)
    metadata["final_frame_paths"] = metadata["final_frame_paths"][:2]
    produce(tmp_path, metadata)

    with pytest.raises(ActionEntryDraftError, match="length must match frame_count"):
        build(tmp_path, write_metadata(tmp_path, metadata))


@pytest.mark.parametrize(
    "frame_count",
    [0, -1, "4", 2.0, True],
    ids=["zero", "negative", "string", "float", "bool"],
)
def test_frame_count_must_be_a_positive_integer(tmp_path, frame_count):
    """`True` and `2.0` both compare equal to a valid count; reject by type."""
    metadata = make_metadata(frame_count=1)
    metadata["frame_count"] = frame_count
    produce(tmp_path, metadata)

    with pytest.raises(ActionEntryDraftError, match="frame_count must be a positive integer"):
        build(tmp_path, write_metadata(tmp_path, metadata))


def test_edge_touching_frames_are_rejected(tmp_path):
    """An edge-touching frame clipped the character; it must be regenerated."""
    metadata = make_metadata(edge_touch_frames=["frame1"])
    produce(tmp_path, metadata)

    with pytest.raises(ActionEntryDraftError, match="edge_touch_frames must be empty"):
        build(tmp_path, write_metadata(tmp_path, metadata))


@pytest.mark.parametrize(
    "scale_reference",
    [None, {}, {"checked": "yes"}, "checked"],
    ids=["missing", "empty", "wrong-type", "not-an-object"],
)
def test_scale_reference_must_be_recorded(tmp_path, scale_reference):
    metadata = make_metadata(scale_reference=scale_reference)
    produce(tmp_path, metadata)

    with pytest.raises(ActionEntryDraftError, match="scale_reference.checked must be boolean"):
        build(tmp_path, write_metadata(tmp_path, metadata))


def test_shared_scale_must_be_boolean(tmp_path):
    metadata = make_metadata(shared_scale="true")
    produce(tmp_path, metadata)

    with pytest.raises(ActionEntryDraftError, match="shared_scale must be boolean"):
        build(tmp_path, write_metadata(tmp_path, metadata))


@pytest.mark.parametrize(
    "sheet_path",
    [
        "assets/sprites/player_idle_sheet.png",
        ".godotmaker/asset-generation/work/player_idle_sheet.png",
        "assets/generated/character-bundle/other_asset/player_idle_sheet.png",
    ],
    ids=["outside-generated-tree", "work-workspace", "other-asset-dir"],
)
def test_runtime_paths_must_stay_in_the_stable_directory(tmp_path, sheet_path):
    metadata = make_metadata(final_sheet_path=sheet_path)
    produce(tmp_path, metadata)

    with pytest.raises(ActionEntryDraftError):
        build(tmp_path, write_metadata(tmp_path, metadata))


def test_frame_paths_must_stay_in_the_stable_directory(tmp_path):
    metadata = make_metadata()
    metadata["final_frame_paths"][1] = "assets/sprites/stray_frame.png"
    produce(tmp_path, metadata)

    with pytest.raises(ActionEntryDraftError, match=r"final_frame_paths\[1\]"):
        build(tmp_path, write_metadata(tmp_path, metadata))


def test_reference_family_has_no_action_output(tmp_path):
    metadata = make_metadata()
    produce(tmp_path, metadata)

    with pytest.raises(ActionEntryDraftError, match="reference-only"):
        build(
            tmp_path,
            write_metadata(tmp_path, metadata),
            production_family="screen-reference",
        )


def test_unknown_production_family_is_rejected(tmp_path):
    metadata = make_metadata()
    produce(tmp_path, metadata)

    with pytest.raises(ActionEntryDraftError, match="production_family is not allowed"):
        build(tmp_path, write_metadata(tmp_path, metadata), production_family="sprites")


def test_absolute_paths_outside_the_project_are_rejected(tmp_path):
    outside = tmp_path.parent / "outside_action"
    outside.mkdir(exist_ok=True)
    metadata = make_metadata(final_sheet_path=str(outside / "sheet.png"))

    with pytest.raises(ActionEntryDraftError, match="outside the project root"):
        build(tmp_path, write_metadata(tmp_path, metadata))


def test_cli_writes_draft_and_support(tmp_path):
    metadata = make_metadata()
    produce(tmp_path, metadata)
    metadata_path = write_metadata(tmp_path, metadata)
    out = tmp_path / ".godotmaker/asset-generation/work/entries/player_idle.json"

    result = subprocess.run(
        [
            sys.executable,
            str(DRAFT_TOOL),
            "--metadata",
            str(metadata_path),
            "--asset-id",
            ASSET_ID,
            "--tag",
            TAG,
            "--production-family",
            FAMILY,
            "--project-root",
            str(tmp_path),
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["support"] == f"{stable_dir()}/{ASSET_ID}.json"
    assert out.exists()


def test_cli_reports_a_rejection_as_json(tmp_path):
    metadata = make_metadata(edge_touch_frames=["frame1"])
    produce(tmp_path, metadata)
    metadata_path = write_metadata(tmp_path, metadata)
    out = tmp_path / "draft.json"

    result = subprocess.run(
        [
            sys.executable,
            str(DRAFT_TOOL),
            "--metadata",
            str(metadata_path),
            "--asset-id",
            ASSET_ID,
            "--tag",
            TAG,
            "--production-family",
            FAMILY,
            "--project-root",
            str(tmp_path),
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "edge_touch_frames must be empty" in json.loads(result.stdout)["error"]
    assert not out.exists()
