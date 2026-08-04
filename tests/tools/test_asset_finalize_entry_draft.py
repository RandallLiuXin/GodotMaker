import json
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_finalize_entry_draft import (  # noqa: E402
    FinalizeEntryDraftError,
    build_finalize_entry_draft,
    write_finalize_entry_draft,
)
from asset_build_record import (  # noqa: E402
    validation_record_path,
    write_validation_record,
)
from asset_stable_entry import stable_output_dir, validate_entry  # noqa: E402

DRAFT_TOOL = TOOLS_DIR / "asset_finalize_entry_draft.py"
TAG = "v0.1.0"
ASSET_ID = "scene_main"
REFERENCE = "references/scene_main.png"


def make_report(**overrides):
    report = {
        "ok": True,
        "source": ".godotmaker/asset-generation/sources/scene_main_source.png",
        "path": REFERENCE,
        "width": 1280,
        "height": 720,
        "required_aspect": "16:9",
        "aspect_delta": 0.0,
        "aspect_tolerance": 0.03,
        "label": ASSET_ID,
        "asset_id": ASSET_ID,
    }
    report.update(overrides)
    return report


def write_report(project_root: Path, report) -> Path:
    path = project_root / ".godotmaker/asset-generation/reports/scene_main.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def touch(project_root: Path, relative: str) -> None:
    target = project_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"png")


def build(project_root: Path, report_path: Path, **kwargs):
    params = {
        "asset_id": ASSET_ID,
        "tag": TAG,
        "production_family": "screen-reference",
        "project_root": project_root,
    }
    params.update(kwargs)
    return build_finalize_entry_draft(report_path, **params)


def test_draft_is_a_valid_reference_entry(tmp_path):
    touch(tmp_path, REFERENCE)
    entry = build(tmp_path, write_report(tmp_path, make_report()))

    assert entry["asset_id"] == ASSET_ID
    assert entry["tag"] == TAG
    assert entry["production_family"] == "screen-reference"
    assert entry["source_layout"] == {"type": "reference", "path": f"res://{REFERENCE}"}
    assert entry["processing_status"] == "source_ready"
    # A reference is never handed to a worker, so it carries no artifact.
    assert "godot_artifact" not in entry
    validate_entry(entry, project_root=tmp_path, check_files=True)


def test_failed_finalize_is_rejected(tmp_path):
    touch(tmp_path, REFERENCE)

    with pytest.raises(FinalizeEntryDraftError, match="must report ok: true"):
        build(tmp_path, write_report(tmp_path, make_report(ok=False)))


def test_aspect_validation_must_have_run(tmp_path):
    """The production unit requires --require-aspect before a reference is kept."""
    touch(tmp_path, REFERENCE)
    report = make_report()
    del report["required_aspect"]

    with pytest.raises(FinalizeEntryDraftError, match="no required_aspect"):
        build(tmp_path, write_report(tmp_path, report))


def test_aspect_outside_tolerance_is_rejected(tmp_path):
    touch(tmp_path, REFERENCE)
    report = make_report(aspect_delta=0.4, aspect_tolerance=0.03)

    with pytest.raises(FinalizeEntryDraftError, match="exceeds tolerance"):
        build(tmp_path, write_report(tmp_path, report))


@pytest.mark.parametrize("field", ["aspect_delta", "aspect_tolerance"])
def test_aspect_numbers_must_be_numeric(tmp_path, field):
    touch(tmp_path, REFERENCE)
    report = make_report(**{field: "0.0"})

    with pytest.raises(FinalizeEntryDraftError, match=f"{field} must be a number"):
        build(tmp_path, write_report(tmp_path, report))


def test_report_for_another_asset_is_rejected(tmp_path):
    """Cross-bind the report to this asset so one report cannot register another."""
    touch(tmp_path, REFERENCE)
    report = make_report(label="other_screen", asset_id="other_screen")

    with pytest.raises(FinalizeEntryDraftError, match="is for other_screen, not"):
        build(tmp_path, write_report(tmp_path, report))


def test_unlabelled_report_is_rejected(tmp_path):
    touch(tmp_path, REFERENCE)
    report = make_report()
    del report["label"]
    del report["asset_id"]

    with pytest.raises(FinalizeEntryDraftError, match="no asset label"):
        build(tmp_path, write_report(tmp_path, report))


@pytest.mark.parametrize(
    ("path", "match"),
    [
        ("assets/generated/screen-reference/scene_main/scene_main.png", "must not live under"),
        (".godotmaker/asset-generation/sources/scene_main_source.png", "must be a file under references/"),
        ("assets/ui/scene_main.png", "must be a file under references/"),
        ("references/../secrets.png", "no empty, '.' or '..' segments"),
    ],
    ids=["generated-tree", "generation-scratch", "outside-references", "parent-escape"],
)
def test_reference_path_must_live_under_references(tmp_path, path, match):
    """A reference is the one layout allowed out of the generated tree.

    Without this rule a producer could register a scratch source or a real
    runtime asset as a `reference` and skip the artifact requirement entirely.
    """
    touch(tmp_path, "references/scene_main.png")
    report = make_report(path=path)

    with pytest.raises(FinalizeEntryDraftError, match=match):
        build(tmp_path, write_report(tmp_path, report))


def test_missing_reference_file_is_rejected(tmp_path):
    with pytest.raises(FinalizeEntryDraftError, match="finalized file not found"):
        build(tmp_path, write_report(tmp_path, make_report()))


def test_reference_path_is_rejected_for_a_runtime_family(tmp_path):
    """A runtime family may not register a references/ path as its asset."""
    touch(tmp_path, REFERENCE)

    with pytest.raises(FinalizeEntryDraftError, match="finalized path must be a file under"):
        build(
            tmp_path,
            write_report(tmp_path, make_report()),
            production_family="character-bundle",
        )


def test_absolute_path_outside_the_project_is_rejected(tmp_path):
    outside = tmp_path.parent / "outside_reference"
    outside.mkdir(exist_ok=True)
    report = make_report(path=str(outside / "scene.png"))

    with pytest.raises(FinalizeEntryDraftError, match="outside the project root"):
        build(tmp_path, write_report(tmp_path, report))


RUNTIME_FAMILY = "background-map"
RUNTIME_ASSET_ID = "sky"
RUNTIME_PATH = f"{stable_output_dir(RUNTIME_FAMILY, RUNTIME_ASSET_ID)}/{RUNTIME_ASSET_ID}.png"


def test_runtime_family_drafts_a_single_layout(tmp_path):
    """background-map and single card frames register through the same builder."""
    touch(tmp_path, RUNTIME_PATH)
    report = make_report(
        path=RUNTIME_PATH, label=RUNTIME_ASSET_ID, asset_id=RUNTIME_ASSET_ID
    )
    entry = build(
        tmp_path,
        write_report(tmp_path, report),
        asset_id=RUNTIME_ASSET_ID,
        production_family=RUNTIME_FAMILY,
    )

    assert entry["source_layout"] == {"type": "single", "path": f"res://{RUNTIME_PATH}"}
    assert entry["processing_status"] == "source_ready"
    assert "godot_artifact" not in entry
    validate_entry(entry, project_root=tmp_path, check_files=True)


@pytest.mark.parametrize(
    "path",
    [
        "assets/backgrounds/sky.png",
        ".godotmaker/asset-generation/sources/sky_source.png",
        "assets/generated/background-map/other_asset/sky.png",
        "references/sky.png",
    ],
    ids=["outside-generated-tree", "generation-scratch", "other-asset-dir", "references"],
)
def test_runtime_family_path_must_be_in_the_stable_directory(tmp_path, path):
    touch(tmp_path, path)
    report = make_report(path=path, label=RUNTIME_ASSET_ID, asset_id=RUNTIME_ASSET_ID)

    with pytest.raises(FinalizeEntryDraftError, match="finalized path"):
        build(
            tmp_path,
            write_report(tmp_path, report),
            asset_id=RUNTIME_ASSET_ID,
            production_family=RUNTIME_FAMILY,
        )


def make_runtime_result(**overrides):
    """The background-map Skill result for the image the report finalized."""
    res_path = f"res://{RUNTIME_PATH}"
    result = {
        "asset_type": RUNTIME_FAMILY,
        "outputs": [
            {
                "role": "runtime",
                "name": RUNTIME_ASSET_ID,
                "path": res_path,
                "godot_type": "Texture2D",
            }
        ],
        "sources": [{"path": res_path, "layout": "single"}],
        "previews": [],
        "validation": {
            "passed": True,
            "levels": {level: True for level in ("L0", "L1", "L2", "L3", "L4")},
        },
    }
    result.update(overrides)
    return result


def write_runtime_result(project_root: Path, result) -> Path:
    path = project_root / ".godotmaker/asset-generation/sky-result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result), encoding="utf-8")
    return path


def record_validation(project_root: Path, *, path: str = RUNTIME_PATH, **overrides):
    """Leave the record the family's validation runner writes when L0-L4 pass."""
    params = {
        "production_family": RUNTIME_FAMILY,
        "asset_id": RUNTIME_ASSET_ID,
        "artifact_path": f"res://{path}",
    }
    params.update(overrides)
    return write_validation_record(project_root, **params)


def build_runtime(project_root: Path, result, *, report=None):
    report = report if report is not None else make_report(
        path=RUNTIME_PATH, label=RUNTIME_ASSET_ID, asset_id=RUNTIME_ASSET_ID
    )
    return build(
        project_root,
        write_report(project_root, report),
        asset_id=RUNTIME_ASSET_ID,
        production_family=RUNTIME_FAMILY,
        result_path=write_runtime_result(project_root, result),
    )


def test_a_validated_background_map_becomes_a_ready_texture2d_entry(tmp_path):
    """The PNG is the Texture2D Godot imports; no .tres wraps it."""
    touch(tmp_path, RUNTIME_PATH)
    record_validation(tmp_path)

    entry = build_runtime(tmp_path, make_runtime_result())

    assert entry["source_layout"] == {"type": "single", "path": f"res://{RUNTIME_PATH}"}
    assert entry["godot_artifact"] == {
        "type": "Texture2D",
        "path": f"res://{RUNTIME_PATH}",
    }
    assert entry["processing_status"] == "ready"
    validate_entry(entry, project_root=tmp_path, check_files=True)


def test_a_failed_ladder_never_reaches_ready(tmp_path):
    touch(tmp_path, RUNTIME_PATH)
    result = make_runtime_result()
    result["validation"] = {
        "passed": False,
        "levels": {"L0": True, "L1": True, "L2": True, "L3": False, "L4": False},
    }

    with pytest.raises(FinalizeEntryDraftError, match="not passing: L3, L4"):
        build_runtime(tmp_path, result)


def test_a_result_without_levels_never_reaches_ready(tmp_path):
    """`passed: true` alone is a claim; the levels are the evidence."""
    touch(tmp_path, RUNTIME_PATH)
    result = make_runtime_result()
    del result["validation"]["levels"]

    with pytest.raises(FinalizeEntryDraftError, match="no explicit validation levels"):
        build_runtime(tmp_path, result)


def test_a_self_declared_failure_never_reaches_ready(tmp_path):
    """An all-true ladder plus `passed: false` is still a refused delivery."""
    touch(tmp_path, RUNTIME_PATH)
    result = make_runtime_result()
    result["validation"]["passed"] = False
    result["validation"]["notes"] = "the horizon line drifts under the viewport"

    with pytest.raises(FinalizeEntryDraftError, match="validation.passed is not true"):
        build_runtime(tmp_path, result)


def test_a_result_about_another_image_cannot_register_this_one(tmp_path):
    touch(tmp_path, RUNTIME_PATH)
    result = make_runtime_result()
    result["outputs"][0]["path"] = "res://assets/generated/background-map/dusk/dusk.png"

    with pytest.raises(FinalizeEntryDraftError, match="must be the finalized stable"):
        build_runtime(tmp_path, result)


def test_a_result_sourced_from_another_image_cannot_register_this_one(tmp_path):
    """The runtime output alone never says which file carried the layout."""
    touch(tmp_path, RUNTIME_PATH)
    result = make_runtime_result()
    result["sources"] = [
        {"path": "res://assets/generated/background-map/dusk/dusk.png", "layout": "single"}
    ]

    with pytest.raises(FinalizeEntryDraftError, match="single source must be"):
        build_runtime(tmp_path, result)


def test_a_result_for_another_family_is_rejected(tmp_path):
    touch(tmp_path, RUNTIME_PATH)

    with pytest.raises(FinalizeEntryDraftError, match="must be a background-map result"):
        build_runtime(tmp_path, make_runtime_result(asset_type="fx-bundle"))


def test_a_second_runtime_output_is_rejected(tmp_path):
    # One scenic image is one texture; a second would reach the worker as a
    # rival background for the same asset.
    touch(tmp_path, RUNTIME_PATH)
    result = make_runtime_result()
    result["outputs"].append(
        {
            "role": "runtime",
            "path": f"res://{stable_output_dir(RUNTIME_FAMILY, RUNTIME_ASSET_ID)}/extra.png",
            "godot_type": "Texture2D",
        }
    )

    with pytest.raises(FinalizeEntryDraftError, match="exactly one runtime output"):
        build_runtime(tmp_path, result)


def test_a_result_declaring_a_wrong_artifact_type_is_rejected(tmp_path):
    touch(tmp_path, RUNTIME_PATH)
    result = make_runtime_result()
    result["outputs"][0]["godot_type"] = "SpriteFrames"

    with pytest.raises(FinalizeEntryDraftError, match="must be the finalized stable"):
        build_runtime(tmp_path, result)


def test_a_drifted_finalized_name_never_reaches_ready(tmp_path):
    """The stable PNG is `<asset_id>.png`; a `_v2` sibling is drift, not an asset."""
    drifted = f"{stable_output_dir(RUNTIME_FAMILY, RUNTIME_ASSET_ID)}/{RUNTIME_ASSET_ID}_v2.png"
    touch(tmp_path, drifted)
    report = make_report(
        path=drifted, label=RUNTIME_ASSET_ID, asset_id=RUNTIME_ASSET_ID
    )

    with pytest.raises(FinalizeEntryDraftError, match="must finalize into its stable"):
        build_runtime(tmp_path, make_runtime_result(), report=report)


def test_a_missing_finalized_image_never_reaches_ready(tmp_path):
    with pytest.raises(FinalizeEntryDraftError, match="finalized file not found"):
        build_runtime(tmp_path, make_runtime_result())


def test_regenerating_the_same_stable_png_after_validation_is_refused(tmp_path):
    """The regression this guard exists for.

    The stable path is derived from `asset_id`, so a retry's finalize run
    overwrites the exact PNG the passing result names. Every path still matches
    and the non-writing Texture2D route happily re-binds the new file, so only
    the recorded bytes tell the validated build from whatever landed after it.
    """
    touch(tmp_path, RUNTIME_PATH)
    record_validation(tmp_path)
    (tmp_path / RUNTIME_PATH).write_bytes(b"regenerated png")

    with pytest.raises(FinalizeEntryDraftError, match="changed since it passed L0-L4"):
        build_runtime(tmp_path, make_runtime_result())


def test_an_unvalidated_background_map_cannot_register(tmp_path):
    """No record means no ladder ran on these bytes in this project."""
    touch(tmp_path, RUNTIME_PATH)

    with pytest.raises(FinalizeEntryDraftError, match="no validation record"):
        build_runtime(tmp_path, make_runtime_result())


def test_a_record_from_another_asset_cannot_register_this_one(tmp_path):
    touch(tmp_path, RUNTIME_PATH)
    record_validation(tmp_path)
    record = json.loads(
        validation_record_path(tmp_path, RUNTIME_ASSET_ID).read_text(encoding="utf-8")
    )
    record["asset_id"] = "dusk"
    validation_record_path(tmp_path, RUNTIME_ASSET_ID).write_text(
        json.dumps(record), encoding="utf-8"
    )

    with pytest.raises(FinalizeEntryDraftError, match="is not a v1 background-map"):
        build_runtime(tmp_path, make_runtime_result())


def test_a_record_for_another_artifact_cannot_register_this_one(tmp_path):
    touch(tmp_path, RUNTIME_PATH)
    other = f"{stable_output_dir(RUNTIME_FAMILY, RUNTIME_ASSET_ID)}/{RUNTIME_ASSET_ID}_alt.png"
    touch(tmp_path, other)
    record_validation(tmp_path, path=other)

    with pytest.raises(FinalizeEntryDraftError, match="describes another artifact"):
        build_runtime(tmp_path, make_runtime_result())


def test_a_reference_family_cannot_be_promoted_with_a_result(tmp_path):
    """`--result` compiles a native artifact; a reference never has one."""
    touch(tmp_path, REFERENCE)
    result = make_runtime_result(asset_type="screen-reference")

    with pytest.raises(FinalizeEntryDraftError, match="only supported for background-map"):
        build(
            tmp_path,
            write_report(tmp_path, make_report()),
            result_path=write_runtime_result(tmp_path, result),
        )


def test_a_rejected_promotion_leaves_no_draft_behind(tmp_path):
    """A partial registration is worse than none: nothing may be written."""
    touch(tmp_path, RUNTIME_PATH)
    result = make_runtime_result()
    result["validation"]["levels"]["L4"] = False
    result["validation"]["passed"] = False
    out = tmp_path / ".godotmaker/asset-generation/work/entries/sky.json"

    with pytest.raises(FinalizeEntryDraftError):
        write_finalize_entry_draft(
            write_report(
                tmp_path,
                make_report(
                    path=RUNTIME_PATH, label=RUNTIME_ASSET_ID, asset_id=RUNTIME_ASSET_ID
                ),
            ),
            asset_id=RUNTIME_ASSET_ID,
            tag=TAG,
            production_family=RUNTIME_FAMILY,
            project_root=tmp_path,
            out=out,
            result_path=write_runtime_result(tmp_path, result),
        )

    assert not out.exists()


def test_unknown_production_family_is_rejected(tmp_path):
    touch(tmp_path, REFERENCE)

    with pytest.raises(FinalizeEntryDraftError, match="production_family is not allowed"):
        build(
            tmp_path,
            write_report(tmp_path, make_report()),
            production_family="backgrounds",
        )


def test_write_emits_the_draft_file(tmp_path):
    touch(tmp_path, REFERENCE)
    report_path = write_report(tmp_path, make_report())
    out = tmp_path / ".godotmaker/asset-generation/work/entries/scene_main.json"

    result = write_finalize_entry_draft(
        report_path,
        asset_id=ASSET_ID,
        tag=TAG,
        production_family="screen-reference",
        project_root=tmp_path,
        out=out,
    )

    assert result["ok"] is True
    assert json.loads(out.read_text(encoding="utf-8"))["processing_status"] == "source_ready"


def test_cli_writes_draft(tmp_path):
    touch(tmp_path, REFERENCE)
    report_path = write_report(tmp_path, make_report())
    out = tmp_path / ".godotmaker/asset-generation/work/entries/scene_main.json"

    result = subprocess.run(
        [
            sys.executable,
            str(DRAFT_TOOL),
            "--finalize-report",
            str(report_path),
            "--asset-id",
            ASSET_ID,
            "--tag",
            TAG,
            "--production-family",
            "screen-reference",
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
    assert payload["source_layout"] == "reference"
    assert payload["path"] == f"res://{REFERENCE}"
    assert out.exists()


def test_cli_reports_a_rejection_as_json(tmp_path):
    touch(tmp_path, REFERENCE)
    report = make_report()
    del report["required_aspect"]
    report_path = write_report(tmp_path, report)
    out = tmp_path / "draft.json"

    result = subprocess.run(
        [
            sys.executable,
            str(DRAFT_TOOL),
            "--finalize-report",
            str(report_path),
            "--asset-id",
            ASSET_ID,
            "--tag",
            TAG,
            "--production-family",
            "screen-reference",
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
    assert "no required_aspect" in json.loads(result.stdout)["error"]
    assert not out.exists()
