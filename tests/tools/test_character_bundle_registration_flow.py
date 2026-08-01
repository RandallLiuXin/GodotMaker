"""The `/gm-asset` seam for a first-class character-bundle, end to end.

`test_asset_action_entry_draft.py` covers the builder in isolation and
`test_asset_generation_handoff.py` covers registration from a hand-built entry.
Neither walks the path the manager actually takes for a first-class Skill:
resolved request plus one action processing report each, then the Skill's
validated result, then draft, register, gate, ASSETS.md.

Every case here is a documented outcome of that seam, so a green run means the
manager and the Skill agree on one contract instead of two.
"""
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
    write_character_bundle_entry_draft,
)
from asset_assets_md_update import AssetsMdUpdateError, update_assets_md  # noqa: E402
from asset_generation_index import check_index, update_index  # noqa: E402
from asset_stable_entry import (  # noqa: E402
    entry_relative_path,
    stable_output_dir,
    write_entry,
)

TAG = "v0.1.0"
FAMILY = "character-bundle"
ASSET_ID = "hero"
ACTIONS = ("idle", "walk")
INDEX_RELATIVE = ".godotmaker/asset-generation/manifest.json"


def stable_dir(asset_id=ASSET_ID):
    return stable_output_dir(FAMILY, asset_id)


def artifact_res(asset_id=ASSET_ID):
    return f"res://{stable_dir(asset_id)}/{asset_id}.tres"


def sheet_res(action, asset_id=ASSET_ID):
    return f"res://{stable_dir(asset_id)}/{asset_id}_{action}_sheet.png"


def write_png(project_root: Path, relative: str) -> Path:
    target = project_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (4, 4), (255, 255, 255, 255)).save(target)
    return target


def resolved_request(asset_id=ASSET_ID) -> dict:
    return {
        "asset_type": FAMILY,
        "asset_id": asset_id,
        "brief": "A hand-drawn cel-shaded hero with an idle and a walk cycle.",
        "provider": "native",
        "spec": {
            "required_actions": list(ACTIONS),
            "frame_canvas_px": 256,
            "actions": [
                {
                    "name": action,
                    "intent": f"A readable {action} cycle.",
                    "grid": {"columns": 2, "rows": 1},
                    "frame_names": [f"{action}_01", f"{action}_02"],
                    "fps": 8 if action == "idle" else 10,
                    "loop": True,
                    "frame_durations": [1, 1],
                }
                for action in ACTIONS
            ],
        },
    }


def skill_result(asset_id=ASSET_ID, **overrides) -> dict:
    result = {
        "asset_type": FAMILY,
        "outputs": [
            {
                "role": "runtime",
                "name": asset_id,
                "path": artifact_res(asset_id),
                "godot_type": "SpriteFrames",
            }
        ],
        "sources": [
            {"path": sheet_res(action, asset_id), "layout": "grid_sheet"}
            for action in ACTIONS
        ],
        "previews": [
            {
                "path": f"res://{stable_dir(asset_id)}/{asset_id}_{action}.gif",
                "label": action,
            }
            for action in ACTIONS
        ],
        "validation": {
            "passed": True,
            "levels": {"L0": True, "L1": True, "L2": True, "L3": True, "L4": True},
        },
    }
    result.update(overrides)
    return result


def produce_actions(project_root: Path, asset_id=ASSET_ID) -> list[Path]:
    """Write the stable action output and one processing report per action."""
    root = stable_dir(asset_id)
    baseline_meta = (
        project_root / ".godotmaker/asset-generation/work" / ACTIONS[0] / "pipeline-meta.json"
    )
    metadata_paths: list[Path] = []
    for index, action in enumerate(ACTIONS):
        frames = [f"{action}_01", f"{action}_02"]
        metadata = {
            "frame_count": 2,
            "final_sheet_path": f"{root}/{asset_id}_{action}_sheet.png",
            "final_frame_paths": [
                f"{root}/{asset_id}_{action}_{frame}.png" for frame in frames
            ],
            "align": "feet",
            "shared_scale": True,
            "action_name": action,
            "fps": 8 if action == "idle" else 10,
            "loop": True,
            "frame_durations": [1.0, 1.0],
            "edge_touch_frames": [],
            "scale_reference": (
                {"checked": False}
                if index == 0
                else {"checked": True, "reference_metadata_path": str(baseline_meta)}
            ),
            "cell_size": 256,
            "grid": {"cols": 2, "rows": 1},
            "frame_labels": frames,
        }
        for relative in [metadata["final_sheet_path"], *metadata["final_frame_paths"]]:
            write_png(project_root, relative)
        path = (
            project_root
            / ".godotmaker/asset-generation/work"
            / action
            / "pipeline-meta.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(metadata), encoding="utf-8")
        metadata_paths.append(path)
    return metadata_paths


def write_json(project_root: Path, relative: str, payload: dict) -> Path:
    path = project_root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def draft(project_root: Path, metadata_paths, *, result=None, asset_id=ASSET_ID) -> Path:
    """Run the manager's adapter step and return the written draft path."""
    request_path = write_json(
        project_root,
        f".godotmaker/asset-generation/plans/{asset_id}_resolved_request.json",
        resolved_request(asset_id),
    )
    result_path = (
        None
        if result is None
        else write_json(
            project_root, f".godotmaker/asset-generation/{asset_id}-result.json", result
        )
    )
    out = project_root / f".godotmaker/asset-generation/work/entries/{asset_id}.json"
    write_character_bundle_entry_draft(
        metadata_paths,
        request_path=request_path,
        asset_id=asset_id,
        tag=TAG,
        project_root=project_root,
        out=out,
        result_path=result_path,
    )
    return out


def register(project_root: Path, draft_path: Path) -> Path:
    """Run gm-asset Step 5: write the entry, then upsert its pointer."""
    entry = json.loads(draft_path.read_text(encoding="utf-8"))
    write_entry(entry, project_root=project_root, check_files=True)
    entry_path = project_root / entry_relative_path(entry["tag"], entry["asset_id"])
    update_index(
        project_root / INDEX_RELATIVE, [entry_path], project_root=project_root
    )
    return entry_path


def write_assets_md(project_root: Path, asset_id=ASSET_ID) -> Path:
    assets_md = project_root / "ASSETS.md"
    assets_md.write_text(
        "| ID | Tag | Name | Type | Size | Generation Params | Path | Status |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
        f"| 1 | {TAG} | {asset_id} | sprite | 256x256 | — | "
        f"{stable_dir(asset_id)}/{asset_id}.tres | MISSING |\n",
        encoding="utf-8",
    )
    return assets_md


def read_index(project_root: Path) -> dict:
    return json.loads((project_root / INDEX_RELATIVE).read_text(encoding="utf-8"))


def test_a_passing_bundle_registers_one_spriteframes_and_promotes_its_row(tmp_path):
    """The representative success path, from Skill result to ASSETS.md."""
    metadata_paths = produce_actions(tmp_path)
    draft_path = draft(tmp_path, metadata_paths, result=skill_result())
    entry_path = register(tmp_path, draft_path)
    assets_md = write_assets_md(tmp_path)

    gate = check_index(tmp_path / INDEX_RELATIVE, project_root=tmp_path, check_files=True)
    assert gate["ok"] is True and gate["entry_checks"] == 1

    update_assets_md(assets_md, [entry_path])

    entry = json.loads(entry_path.read_text(encoding="utf-8"))
    assert entry["processing_status"] == "ready"
    assert entry["production_family"] == FAMILY
    assert entry["source_layout"] == {"type": "grid_sheet", "path": sheet_res("idle")}
    assert entry["godot_artifact"] == {"type": "SpriteFrames", "path": artifact_res()}
    assert (tmp_path / stable_dir() / f"{ASSET_ID}.tres").is_file()

    text = assets_md.read_text(encoding="utf-8")
    assert "| generated |" in text
    assert f"manifest_entry={entry_relative_path(TAG, ASSET_ID)}" in text


def test_the_manager_index_holds_a_pointer_and_never_a_copy_of_the_entry(tmp_path):
    """A duplicated entry body in the index would become a second truth."""
    metadata_paths = produce_actions(tmp_path)
    register(tmp_path, draft(tmp_path, metadata_paths, result=skill_result()))

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


def test_a_generated_canonical_is_registered_as_provenance_not_a_second_asset(tmp_path):
    """One call, several logical outputs, still exactly one runtime entry."""
    metadata_paths = produce_actions(tmp_path)
    canonical = f"res://{stable_dir()}/{ASSET_ID}_canonical.png"
    write_png(tmp_path, canonical[len("res://"):])
    result = skill_result()
    result["outputs"].append(
        {"role": "reference", "name": "canonical", "path": canonical}
    )

    entry_path = register(tmp_path, draft(tmp_path, metadata_paths, result=result))

    support = json.loads(
        (tmp_path / stable_dir() / f"{ASSET_ID}.json").read_text(encoding="utf-8")
    )
    assert support["reference_outputs"] == [canonical]

    # The canonical is recorded beside the artifact, never as its own entry.
    assert read_index(tmp_path)["entries"] == [
        {
            "asset_id": ASSET_ID,
            "tag": TAG,
            "entry_path": entry_relative_path(TAG, ASSET_ID),
        }
    ]
    entry = json.loads(entry_path.read_text(encoding="utf-8"))
    assert entry["godot_artifact"]["path"] == artifact_res()
    assert canonical not in json.dumps(entry)


def test_a_failed_skill_result_never_produces_a_draft_to_register(tmp_path):
    metadata_paths = produce_actions(tmp_path)
    failed = skill_result(
        outputs=[],
        validation={
            "passed": False,
            "levels": {"L0": True, "L1": False},
            "notes": "no complete action set could be produced",
        },
    )

    with pytest.raises(ActionEntryDraftError, match="validation.passed to be true"):
        draft(tmp_path, metadata_paths, result=failed)

    assert not (tmp_path / ".godotmaker/asset-generation/work/entries").exists()
    assert not (tmp_path / INDEX_RELATIVE).exists()


def test_a_missing_action_report_never_produces_a_draft_to_register(tmp_path):
    """A bundle is all-or-nothing: a dropped action must not register partially."""
    metadata_paths = produce_actions(tmp_path)

    with pytest.raises(ActionEntryDraftError, match="one report per required action"):
        draft(tmp_path, metadata_paths[:1], result=skill_result())

    assert not (tmp_path / ".godotmaker/asset-generation/work/entries").exists()
    assert not (tmp_path / INDEX_RELATIVE).exists()


@pytest.mark.parametrize("failed_level", ["L3", "L4"])
def test_an_l3_or_l4_failure_leaves_the_row_missing(tmp_path, failed_level):
    """The artifact compiles, so the entry may register — but not as `ready`.

    This is the case the old builder got wrong: it wrote `ready` straight from
    the compiler, so a bundle that never loaded in Godot would still have been
    handed to a worker.
    """
    metadata_paths = produce_actions(tmp_path)
    result = skill_result()
    result["validation"]["passed"] = False
    result["validation"]["levels"][failed_level] = False

    with pytest.raises(ActionEntryDraftError, match="validation.passed to be true"):
        draft(tmp_path, metadata_paths, result=result)

    # Without the passing result the same inputs still register, but only as
    # `compiled`, and ASSETS.md refuses to call that generated.
    entry_path = register(tmp_path, draft(tmp_path, metadata_paths))
    assets_md = write_assets_md(tmp_path)
    assert json.loads(entry_path.read_text(encoding="utf-8"))["processing_status"] == "compiled"

    gate = check_index(tmp_path / INDEX_RELATIVE, project_root=tmp_path, check_files=True)
    assert gate["ok"] is True

    with pytest.raises(AssetsMdUpdateError, match="processing_status is compiled"):
        update_assets_md(assets_md, [entry_path])
    assert "| generated |" not in assets_md.read_text(encoding="utf-8")
    assert "MISSING" in assets_md.read_text(encoding="utf-8")


def test_the_documented_command_chain_runs_end_to_end(tmp_path):
    """The exact commands the Skill and Step 5 publish, as a user would run them."""
    metadata_paths = produce_actions(tmp_path)
    request_path = write_json(
        tmp_path,
        f".godotmaker/asset-generation/plans/{ASSET_ID}_resolved_request.json",
        resolved_request(),
    )
    result_path = write_json(
        tmp_path, f".godotmaker/asset-generation/{ASSET_ID}-result.json", skill_result()
    )
    draft_relative = f".godotmaker/asset-generation/work/entries/{ASSET_ID}.json"
    entry_relative = entry_relative_path(TAG, ASSET_ID)
    write_assets_md(tmp_path)

    def run(tool, *args):
        return subprocess.run(
            [sys.executable, str(TOOLS_DIR / tool), *args],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            check=False,
        )

    compiled = run(
        "asset_action_entry_draft.py",
        *[arg for path in metadata_paths for arg in ("--metadata", str(path))],
        "--request", str(request_path),
        "--asset-id", ASSET_ID, "--tag", TAG,
        "--production-family", FAMILY,
        "--project-root", ".", "--out", draft_relative,
    )
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    assert json.loads(compiled.stdout)["processing_status"] == "compiled"

    promoted = run(
        "asset_action_entry_draft.py",
        *[arg for path in metadata_paths for arg in ("--metadata", str(path))],
        "--request", str(request_path),
        "--result", str(result_path),
        "--asset-id", ASSET_ID, "--tag", TAG,
        "--production-family", FAMILY,
        "--project-root", ".", "--out", draft_relative,
    )
    assert promoted.returncode == 0, promoted.stdout + promoted.stderr
    assert json.loads(promoted.stdout)["processing_status"] == "ready"

    written = run(
        "asset_stable_entry.py", draft_relative, "--project-root", ".", "--write", "--check-files"
    )
    assert written.returncode == 0, written.stdout + written.stderr

    upserted = run(
        "asset_generation_index.py", "--project-root", ".", "--entry-file", entry_relative
    )
    assert upserted.returncode == 0, upserted.stdout + upserted.stderr
    assert json.loads(upserted.stdout)["upserted"] == [ASSET_ID]

    gate = run(
        "asset_generation_index.py", "--project-root", ".", "--check-entries", "--check-files"
    )
    assert gate.returncode == 0, gate.stdout + gate.stderr

    promoted_row = run("asset_assets_md_update.py", "--entry-file", entry_relative)
    assert promoted_row.returncode == 0, promoted_row.stdout + promoted_row.stderr
    assert "| generated |" in (tmp_path / "ASSETS.md").read_text(encoding="utf-8")


def test_regeneration_overwrites_the_same_paths_and_leaves_others_alone(tmp_path):
    """Stable paths come from identity, so a rerun may only touch its own asset."""
    other_id = "villain"
    other_artifact = tmp_path / stable_dir(other_id) / f"{other_id}.tres"
    other_artifact.parent.mkdir(parents=True, exist_ok=True)
    other_artifact.write_text("unrelated", encoding="utf-8")

    metadata_paths = produce_actions(tmp_path)
    entry_path = register(tmp_path, draft(tmp_path, metadata_paths, result=skill_result()))
    first = (tmp_path / stable_dir() / f"{ASSET_ID}.tres").read_text(encoding="utf-8")

    # A second production run over the same identity: same inputs, same outputs.
    metadata_paths = produce_actions(tmp_path)
    repeat_entry_path = register(
        tmp_path, draft(tmp_path, metadata_paths, result=skill_result())
    )

    assert repeat_entry_path == entry_path
    assert (tmp_path / stable_dir() / f"{ASSET_ID}.tres").read_text(encoding="utf-8") == first
    assert len(read_index(tmp_path)["entries"]) == 1
    assert len(list((tmp_path / stable_dir()).glob("*.tres"))) == 1
    assert other_artifact.read_text(encoding="utf-8") == "unrelated"

    gate = check_index(tmp_path / INDEX_RELATIVE, project_root=tmp_path, check_files=True)
    assert gate["ok"] is True and gate["entry_checks"] == 1
