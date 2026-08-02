import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_action_entry_draft import (  # noqa: E402
    ActionEntryDraftError,
    build_action_entry_draft,
    build_character_bundle_entry_draft,
    build_fx_bundle_entry_draft,
    write_action_entry_draft,
    write_character_bundle_entry_draft,
    write_fx_bundle_entry_draft,
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
    "field, value, message",
    [
        ("fps", float("nan"), "metadata.fps must be a positive number"),
        ("fps", float("inf"), "metadata.fps must be a positive number"),
        ("frame_durations", [1.0, float("nan")], "metadata.frame_durations values must be positive numbers"),
        ("frame_durations", [1.0, float("inf")], "metadata.frame_durations values must be positive numbers"),
    ],
)
def test_nonfinite_animation_timing_is_rejected(tmp_path, field, value, message):
    metadata = make_metadata()
    metadata[field] = value
    produce(tmp_path, metadata)

    with pytest.raises(ActionEntryDraftError, match=message):
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


def _character_bundle_inputs(tmp_path):
    asset_id = "hero"
    root = stable_dir(asset_id)
    request = {
        "asset_type": "character-bundle",
        "asset_id": asset_id,
        "brief": "A non-pixel-art hero.",
        "provider": "native",
        "spec": {
            "required_actions": ["idle", "walk"],
            "frame_canvas_px": 256,
            "actions": [
                {
                    "name": "idle", "intent": "A calm breathing cycle.",
                    "grid": {"columns": 2, "rows": 1},
                    "frame_names": ["idle_01", "idle_02"], "fps": 8,
                    "loop": True, "frame_durations": [1, 1],
                },
                {
                    "name": "walk", "intent": "A brisk two-step walk cycle.",
                    "grid": {"columns": 2, "rows": 1},
                    "frame_names": ["walk_01", "walk_02"], "fps": 10,
                    "loop": True, "frame_durations": [1, 1],
                },
            ],
        },
    }
    request_path = tmp_path / "ASSET_REQUEST.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    metadata_paths = []
    baseline_metadata_path = (
        tmp_path
        / ".godotmaker"
        / "asset-generation"
        / "work"
        / "idle"
        / "pipeline-meta.json"
    )
    for action, frames, checked in (
        ("idle", ["idle_01", "idle_02"], False),
        ("walk", ["walk_01", "walk_02"], True),
    ):
        metadata = {
            "frame_count": len(frames),
            "final_sheet_path": f"{root}/{asset_id}_{action}_sheet.png",
            "final_frame_paths": [f"{root}/{asset_id}_{action}_{frame}.png" for frame in frames],
            "align": "feet", "shared_scale": True, "action_name": action,
            "fps": 8 if action == "idle" else 10, "loop": True,
            "frame_durations": [1.0, 1.0], "edge_touch_frames": [],
            "scale_reference": (
                {
                    "checked": True,
                    "reference_metadata_path": str(baseline_metadata_path),
                }
                if checked
                else {"checked": False}
            ),
            "cell_size": 256,
            "grid": {"cols": 2, "rows": 1},
            "frame_labels": frames,
        }
        for relative in [metadata["final_sheet_path"], *metadata["final_frame_paths"]]:
            path = tmp_path / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGBA", (4, 4), (255, 255, 255, 255)).save(path)
        metadata_path = tmp_path / ".godotmaker" / "asset-generation" / "work" / action / "pipeline-meta.json"
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        metadata_paths.append(metadata_path)

    return asset_id, root, request_path, metadata_paths


def _character_bundle_result(asset_id, root, **overrides):
    result = {
        "asset_type": "character-bundle",
        "outputs": [
            {
                "role": "runtime",
                "name": asset_id,
                "path": f"res://{root}/{asset_id}.tres",
                "godot_type": "SpriteFrames",
            }
        ],
        "sources": [
            {"path": f"res://{root}/{asset_id}_idle_sheet.png", "layout": "grid_sheet"},
            {"path": f"res://{root}/{asset_id}_walk_sheet.png", "layout": "grid_sheet"},
        ],
        "previews": [],
        "validation": {
            "passed": True,
            "levels": {"L0": True, "L1": True, "L2": True, "L3": True, "L4": True},
        },
    }
    result.update(overrides)
    return result


def _write_result(tmp_path, result) -> Path:
    path = tmp_path / "ASSET_RESULT.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    return path


def _compiled_build(tmp_path, asset_id, request_path, metadata_paths) -> None:
    """Run the `compiled` draft step that promotion is required to build on."""
    write_character_bundle_entry_draft(
        metadata_paths,
        request_path=request_path,
        asset_id=asset_id,
        tag=TAG,
        project_root=tmp_path,
        out=tmp_path / ".godotmaker/asset-generation/work/entries/compiled.json",
    )


def test_character_bundle_entry_compiles_every_required_action(tmp_path):
    """Before L0-L4 the artifact exists but the entry may only be `compiled`."""
    asset_id, root, request_path, metadata_paths = _character_bundle_inputs(tmp_path)

    built = build_character_bundle_entry_draft(
        metadata_paths,
        request_path=request_path,
        asset_id=asset_id,
        tag=TAG,
        project_root=tmp_path,
    )

    artifact = tmp_path / f"{root}/{asset_id}.tres"
    assert built["entry"]["processing_status"] == "compiled"
    assert built["entry"]["godot_artifact"] == {
        "type": "SpriteFrames", "path": f"res://{root}/{asset_id}.tres"
    }
    assert artifact.is_file()
    artifact_text = artifact.read_text(encoding="utf-8")
    assert artifact_text.index('"name": &"idle"') < artifact_text.index('"name": &"walk"')
    assert [action["action_name"] for action in built["support"]["actions"]] == ["idle", "walk"]
    assert built["support"]["actions"][0]["frame_labels"] == ["idle_01", "idle_02"]
    assert built["support"]["frame_canvas_px"] == 256
    assert built["support"]["reference_outputs"] == []


def test_character_bundle_entry_reaches_ready_only_with_a_passing_result(tmp_path):
    asset_id, root, request_path, metadata_paths = _character_bundle_inputs(tmp_path)
    _compiled_build(tmp_path, asset_id, request_path, metadata_paths)
    result_path = _write_result(tmp_path, _character_bundle_result(asset_id, root))

    built = build_character_bundle_entry_draft(
        metadata_paths,
        request_path=request_path,
        asset_id=asset_id,
        tag=TAG,
        project_root=tmp_path,
        result_path=result_path,
    )

    assert built["entry"]["processing_status"] == "ready"
    assert built["support"]["reference_outputs"] == []


def test_character_bundle_registers_a_generated_canonical_as_a_reference(tmp_path):
    """One call may deliver several logical outputs; only one is runtime."""
    asset_id, root, request_path, metadata_paths = _character_bundle_inputs(tmp_path)
    _compiled_build(tmp_path, asset_id, request_path, metadata_paths)
    canonical = f"res://{root}/{asset_id}_canonical.png"
    result = _character_bundle_result(asset_id, root)
    result["outputs"].append({"role": "reference", "name": "canonical", "path": canonical})
    result_path = _write_result(tmp_path, result)

    built = build_character_bundle_entry_draft(
        metadata_paths,
        request_path=request_path,
        asset_id=asset_id,
        tag=TAG,
        project_root=tmp_path,
        result_path=result_path,
    )

    assert built["entry"]["processing_status"] == "ready"
    assert built["entry"]["godot_artifact"]["path"] == f"res://{root}/{asset_id}.tres"
    assert built["support"]["reference_outputs"] == [canonical]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        pytest.param(
            lambda result, asset_id, root: result["validation"].update(
                passed=False, levels={"L0": True, "L1": True, "L2": True, "L3": False, "L4": False}
            ),
            "validation.passed to be true",
            id="skill-failure",
        ),
        pytest.param(
            lambda result, asset_id, root: result["validation"]["levels"].update(L3=False),
            "these levels failed: L3",
            id="l3-failure",
        ),
        pytest.param(
            lambda result, asset_id, root: result["validation"]["levels"].pop("L4"),
            "passing validation levels: L4",
            id="l4-missing",
        ),
        pytest.param(
            lambda result, asset_id, root: result["outputs"].append(
                {
                    "role": "runtime",
                    "name": "canonical",
                    "path": f"res://{root}/{asset_id}_canonical.png",
                    "godot_type": "Texture2D",
                }
            ),
            "exactly one SpriteFrames runtime output",
            id="second-runtime-artifact",
        ),
        pytest.param(
            lambda result, asset_id, root: result["outputs"].append(
                {
                    "role": "reference",
                    "name": "canonical",
                    "path": f"res://{root}/{asset_id}_canonical.png",
                    "godot_type": "Texture2D",
                }
            ),
            "must not declare a godot_type",
            id="reference-masquerading-as-runtime",
        ),
        pytest.param(
            lambda result, asset_id, root: result["outputs"].append(
                {
                    "role": "reference",
                    "name": "canonical",
                    "path": "res://assets/generated/character-bundle/other/other_canonical.png",
                }
            ),
            "must be a file under",
            id="reference-outside-the-stable-directory",
        ),
        pytest.param(
            lambda result, asset_id, root: result["outputs"][0].update(
                path=f"res://{root}/{asset_id}_idle.tres"
            ),
            "must be the compiled SpriteFrames stable path",
            id="unrelated-runtime-path",
        ),
        pytest.param(
            lambda result, asset_id, root: result["sources"].reverse(),
            "stable per-action sheets in action order",
            id="sources-out-of-action-order",
        ),
    ],
)
def test_character_bundle_result_must_prove_the_entry_it_promotes(
    tmp_path, mutate, message
):
    asset_id, root, request_path, metadata_paths = _character_bundle_inputs(tmp_path)
    _compiled_build(tmp_path, asset_id, request_path, metadata_paths)
    result = _character_bundle_result(asset_id, root)
    mutate(result, asset_id, root)
    result_path = _write_result(tmp_path, result)

    with pytest.raises(ActionEntryDraftError, match=message):
        build_character_bundle_entry_draft(
            metadata_paths,
            request_path=request_path,
            asset_id=asset_id,
            tag=TAG,
            project_root=tmp_path,
            result_path=result_path,
        )


def _repaint_action_frames(tmp_path, root, asset_id, action="idle"):
    """Replace the stable frames in place, exactly as a regeneration would."""
    for frame in (f"{action}_01", f"{action}_02"):
        path = tmp_path / f"{root}/{asset_id}_{action}_{frame}.png"
        Image.new("RGBA", (4, 4), (7, 9, 11, 255)).save(path)


def test_a_passing_result_cannot_promote_a_later_unvalidated_build(tmp_path):
    """The regression the stale-result review found.

    Stable paths are derived from `asset_id`, so a regeneration overwrites the
    exact paths the old result names. Without a content binding the old result
    would still match by path, and the bundle that replaced the validated one —
    which no L0-L4 run has ever seen — would register as worker-consumable.
    """
    asset_id, root, request_path, metadata_paths = _character_bundle_inputs(tmp_path)
    _compiled_build(tmp_path, asset_id, request_path, metadata_paths)
    result_path = _write_result(tmp_path, _character_bundle_result(asset_id, root))

    _repaint_action_frames(tmp_path, root, asset_id)

    with pytest.raises(ActionEntryDraftError, match="changed since the compiled build"):
        build_character_bundle_entry_draft(
            metadata_paths,
            request_path=request_path,
            asset_id=asset_id,
            tag=TAG,
            project_root=tmp_path,
            result_path=result_path,
        )


@pytest.mark.parametrize(
    "tamper",
    [
        pytest.param(
            lambda tmp_path, root, asset_id, request_path, metadata_paths: (
                _repaint_action_frames(tmp_path, root, asset_id, "walk")
            ),
            id="frames-regenerated",
        ),
        pytest.param(
            lambda tmp_path, root, asset_id, request_path, metadata_paths: (
                (tmp_path / f"{root}/{asset_id}.tres").write_text(
                    "[gd_resource type=\"SpriteFrames\"]\n", encoding="utf-8"
                )
            ),
            id="artifact-replaced",
        ),
        pytest.param(
            lambda tmp_path, root, asset_id, request_path, metadata_paths: (
                request_path.write_text(
                    request_path.read_text(encoding="utf-8").replace(
                        "A calm breathing cycle.", "A calm breathing loop."
                    ),
                    encoding="utf-8",
                )
            ),
            id="resolved-request-edited",
        ),
        pytest.param(
            lambda tmp_path, root, asset_id, request_path, metadata_paths: (
                metadata_paths[0].write_text(
                    metadata_paths[0].read_text(encoding="utf-8").replace(
                        '"shared_scale": true', '"shared_scale":  true'
                    ),
                    encoding="utf-8",
                )
            ),
            id="action-report-edited",
        ),
    ],
)
def test_promotion_rejects_any_input_changed_since_validation(tmp_path, tamper):
    asset_id, root, request_path, metadata_paths = _character_bundle_inputs(tmp_path)
    _compiled_build(tmp_path, asset_id, request_path, metadata_paths)
    result_path = _write_result(tmp_path, _character_bundle_result(asset_id, root))

    tamper(tmp_path, root, asset_id, request_path, metadata_paths)

    with pytest.raises(ActionEntryDraftError, match="changed since the compiled build"):
        build_character_bundle_entry_draft(
            metadata_paths,
            request_path=request_path,
            asset_id=asset_id,
            tag=TAG,
            project_root=tmp_path,
            result_path=result_path,
        )


def test_promotion_refuses_without_a_compiled_build_to_stand_on(tmp_path):
    asset_id, root, request_path, metadata_paths = _character_bundle_inputs(tmp_path)
    result_path = _write_result(tmp_path, _character_bundle_result(asset_id, root))

    with pytest.raises(ActionEntryDraftError, match="no compiled build to promote"):
        build_character_bundle_entry_draft(
            metadata_paths,
            request_path=request_path,
            asset_id=asset_id,
            tag=TAG,
            project_root=tmp_path,
            result_path=result_path,
        )
    assert not (tmp_path / f"{root}/{asset_id}.tres").exists()


def test_promotion_registers_the_validated_artifact_without_rebuilding_it(tmp_path):
    """L0-L4 recompiles from the same frames, so the bytes must not move."""
    asset_id, root, request_path, metadata_paths = _character_bundle_inputs(tmp_path)
    _compiled_build(tmp_path, asset_id, request_path, metadata_paths)
    artifact = tmp_path / f"{root}/{asset_id}.tres"
    validated = artifact.read_bytes()
    result_path = _write_result(tmp_path, _character_bundle_result(asset_id, root))

    built = build_character_bundle_entry_draft(
        metadata_paths,
        request_path=request_path,
        asset_id=asset_id,
        tag=TAG,
        project_root=tmp_path,
        result_path=result_path,
    )

    assert built["entry"]["processing_status"] == "ready"
    assert artifact.read_bytes() == validated
    assert built["support"]["build"]["artifact"] == hashlib.sha256(validated).hexdigest()


def test_character_bundle_needs_one_action_report_per_required_action(tmp_path):
    asset_id, _, request_path, metadata_paths = _character_bundle_inputs(tmp_path)

    with pytest.raises(ActionEntryDraftError, match="one report per required action"):
        build_character_bundle_entry_draft(
            metadata_paths[:1],
            request_path=request_path,
            asset_id=asset_id,
            tag=TAG,
            project_root=tmp_path,
        )


def test_character_bundle_cli_rejects_a_result_outside_bundle_mode(tmp_path):
    asset_id, root, _, metadata_paths = _character_bundle_inputs(tmp_path)
    result_path = _write_result(tmp_path, _character_bundle_result(asset_id, root))
    out = tmp_path / ".godotmaker/asset-generation/work/entries/hero.json"

    completed = subprocess.run(
        [
            sys.executable, str(DRAFT_TOOL),
            "--metadata", str(metadata_paths[0]),
            "--result", str(result_path),
            "--asset-id", asset_id,
            "--tag", TAG,
            "--production-family", FAMILY,
            "--project-root", str(tmp_path),
            "--out", str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 1
    assert "bundle mode with --request" in json.loads(completed.stdout)["error"]
    assert not out.exists()


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        pytest.param(
            lambda metadata: metadata.update(frame_labels=["idle_02", "idle_01"]),
            "frame_labels must match",
            id="frame-label-order",
        ),
        pytest.param(
            lambda metadata: metadata.update(
                final_frame_paths=list(reversed(metadata["final_frame_paths"]))
            ),
            "frame paths must match the stable action paths",
            id="frame-path-order",
        ),
        pytest.param(
            lambda metadata: metadata.update(
                final_frame_paths=[
                    path.replace("hero_idle_idle", "hero_walk_idle")
                    for path in metadata["final_frame_paths"]
                ]
            ),
            "frame paths must match the stable action paths",
            id="wrong-action-frame-path",
        ),
        pytest.param(
            lambda metadata: metadata.update(
                final_sheet_path=metadata["final_sheet_path"].replace(
                    "hero_idle_sheet", "hero_walk_sheet"
                )
            ),
            "sheet path must match the stable action path",
            id="wrong-action-sheet-path",
        ),
        pytest.param(
            lambda metadata: metadata.update(fps=99),
            "fps must match",
            id="fps",
        ),
        pytest.param(
            lambda metadata: metadata.update(loop=False),
            "loop must match",
            id="loop",
        ),
        pytest.param(
            lambda metadata: metadata.update(frame_durations=[9, 7]),
            "frame_durations must match",
            id="frame-durations",
        ),
        pytest.param(
            lambda metadata: metadata.update(grid={"cols": 1, "rows": 2}),
            "grid must match",
            id="grid",
        ),
    ],
)
def test_character_bundle_entry_binds_processed_action_to_resolved_request(
    tmp_path, mutate, message
):
    asset_id, _, request_path, metadata_paths = _character_bundle_inputs(tmp_path)
    metadata = json.loads(metadata_paths[0].read_text(encoding="utf-8"))
    mutate(metadata)
    metadata_paths[0].write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ActionEntryDraftError, match=message):
        build_character_bundle_entry_draft(
            metadata_paths,
            request_path=request_path,
            asset_id=asset_id,
            tag=TAG,
            project_root=tmp_path,
        )


def test_character_bundle_entry_requires_the_canonical_action_scale_reference(tmp_path):
    asset_id, _, request_path, metadata_paths = _character_bundle_inputs(tmp_path)
    metadata = json.loads(metadata_paths[1].read_text(encoding="utf-8"))
    metadata["scale_reference"]["reference_metadata_path"] = str(
        tmp_path / "unrelated.json"
    )
    metadata_paths[1].write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ActionEntryDraftError, match="canonical action scale reference"):
        build_character_bundle_entry_draft(
            metadata_paths,
            request_path=request_path,
            asset_id=asset_id,
            tag=TAG,
            project_root=tmp_path,
        )


def test_character_bundle_entry_requires_an_unchecked_scale_root(tmp_path):
    asset_id, _, request_path, metadata_paths = _character_bundle_inputs(tmp_path)
    metadata = json.loads(metadata_paths[0].read_text(encoding="utf-8"))
    metadata["scale_reference"] = {
        "checked": True,
        "reference_metadata_path": str(tmp_path / "unrelated.json"),
    }
    metadata_paths[0].write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ActionEntryDraftError, match="unchecked scale reference root"):
        build_character_bundle_entry_draft(
            metadata_paths,
            request_path=request_path,
            asset_id=asset_id,
            tag=TAG,
            project_root=tmp_path,
        )


def _fx_bundle_inputs(tmp_path):
    asset_id = "arc_blast"
    root = stable_dir(asset_id, "fx-bundle")
    request = {
        "asset_type": "fx-bundle",
        "asset_id": asset_id,
        "brief": "A centered three-frame arc blast.",
        "provider": "codex",
        "spec": {
            "mode": "animated",
            "required_actions": ["blast"],
            "actions": [{
                "name": "blast",
                "grid": {"columns": 3, "rows": 1},
                "frame_names": ["blast_01", "blast_02", "blast_03"],
                "fps": 12,
                "loop": False,
                "frame_durations": [1, 2, 1],
            }],
        },
    }
    request_path = tmp_path / "ASSET_REQUEST.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    metadata = {
        "frame_count": 3,
        "final_sheet_path": f"{root}/{asset_id}_sheet.png",
        "final_frame_paths": [
            f"{root}/{asset_id}_blast_{frame}.png"
            for frame in request["spec"]["actions"][0]["frame_names"]
        ],
        "align": "center",
        "shared_scale": True,
        "action_name": "blast",
        "fps": 12,
        "loop": False,
        "frame_durations": [1, 2, 1],
        "edge_touch_frames": [],
        "scale_reference": {"checked": False},
        "cell_size": 256,
        "grid": {"cols": 3, "rows": 1},
        "frame_labels": ["blast_01", "blast_02", "blast_03"],
    }
    for relative in [metadata["final_sheet_path"], *metadata["final_frame_paths"]]:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (8, 8), (255, 255, 255, 128)).save(path)
    metadata_path = tmp_path / ".godotmaker/asset-generation/work/blast/pipeline-meta.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    return asset_id, root, request_path, metadata_path


def test_fx_bundle_entry_compiles_exactly_one_explicit_action(tmp_path):
    asset_id, root, request_path, metadata_path = _fx_bundle_inputs(tmp_path)

    built = build_fx_bundle_entry_draft(
        metadata_path,
        request_path=request_path,
        asset_id=asset_id,
        tag=TAG,
        project_root=tmp_path,
    )

    assert built["entry"]["processing_status"] == "compiled"
    assert built["entry"]["godot_artifact"] == {
        "type": "SpriteFrames", "path": f"res://{root}/{asset_id}.tres"
    }
    assert (tmp_path / root / f"{asset_id}.tres").is_file()
    assert built["support"]["action"]["frame_labels"] == [
        "blast_01", "blast_02", "blast_03"
    ]
    assert built["support"]["action"]["frame_paths"] == [
        f"res://{root}/{asset_id}_blast_blast_01.png",
        f"res://{root}/{asset_id}_blast_blast_02.png",
        f"res://{root}/{asset_id}_blast_blast_03.png",
    ]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("align", "feet", "metadata.align must be center"),
        ("grid", {"cols": 1, "rows": 3}, "grid must match"),
        ("frame_labels", ["blast_02", "blast_01", "blast_03"], "frame_labels must match"),
    ],
)
def test_fx_bundle_entry_rejects_animation_metadata_that_bypasses_the_request(
    tmp_path, field, value, message
):
    asset_id, _, request_path, metadata_path = _fx_bundle_inputs(tmp_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata[field] = value
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ActionEntryDraftError, match=message):
        build_fx_bundle_entry_draft(
            metadata_path,
            request_path=request_path,
            asset_id=asset_id,
            tag=TAG,
            project_root=tmp_path,
        )


def test_fx_bundle_cli_writes_the_compiled_entry(tmp_path):
    asset_id, root, request_path, metadata_path = _fx_bundle_inputs(tmp_path)
    out = tmp_path / ".godotmaker/asset-generation/work/entries/arc_blast.json"

    result = write_fx_bundle_entry_draft(
        metadata_path,
        request_path=request_path,
        asset_id=asset_id,
        tag=TAG,
        project_root=tmp_path,
        out=out,
    )

    assert result["ok"] is True
    assert result["support"] == f"{root}/{asset_id}.json"
    assert json.loads(out.read_text(encoding="utf-8"))["processing_status"] == "compiled"
