import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_curation_entry_draft import (  # noqa: E402
    CurationEntryDraftError,
    build_curation_entry_draft,
    build_fx_static_entry_draft,
    write_curation_entry_draft,
    write_fx_static_entry_draft,
)
from asset_stable_entry import stable_output_dir, validate_entry  # noqa: E402

DRAFT_TOOL = TOOLS_DIR / "asset_curation_entry_draft.py"
TAG = "v0.1.0"
FAMILY = "ui-kit"
ASSET_ID = "action_button"


def stable_dir(asset_id=ASSET_ID, family=FAMILY):
    return stable_output_dir(family, asset_id)


def final_relative(asset_id=ASSET_ID, family=FAMILY):
    return f"{stable_dir(asset_id, family)}/{asset_id}.png"


def make_report(**overrides):
    report = {
        "version": 1,
        "asset_id": "ui_kit_source",
        "tag": TAG,
        "strategy": "transparent_autoslice",
        "status": "selected",
        "selected_count": 1,
        "rejected_count": 2,
        "candidates": [
            {
                "candidate_id": "ui_kit.action_button",
                "name": "action_button",
                "state": "selected",
                "final_path": final_relative(),
            },
            {
                "candidate_id": "ui_kit.empty_04",
                "name": "empty_04",
                "state": "rejected",
            },
        ],
    }
    report.update(overrides)
    return report


def write_report(project_root: Path, report) -> Path:
    path = project_root / ".godotmaker/asset-generation/curation/ui_kit_source.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def touch(project_root: Path, relative: str) -> None:
    target = project_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"png")


def build(project_root: Path, report_path: Path, **kwargs):
    params = {
        "candidate": "action_button",
        "asset_id": ASSET_ID,
        "tag": TAG,
        "production_family": FAMILY,
        "project_root": project_root,
    }
    params.update(kwargs)
    return build_curation_entry_draft(report_path, **params)


def test_draft_is_a_valid_v1_entry_stopping_at_source_ready(tmp_path):
    touch(tmp_path, final_relative())
    entry = build(tmp_path, write_report(tmp_path, make_report()))

    assert entry["asset_id"] == ASSET_ID
    assert entry["production_family"] == FAMILY
    assert entry["source_layout"] == {
        "type": "single",
        "path": f"res://{final_relative()}",
    }
    # No native compiler and no L0-L4 runner exist yet.
    assert entry["processing_status"] == "source_ready"
    assert "godot_artifact" not in entry
    validate_entry(entry, project_root=tmp_path, check_files=True)


def test_candidate_matches_by_id_or_name(tmp_path):
    touch(tmp_path, final_relative())
    report_path = write_report(tmp_path, make_report())

    by_name = build(tmp_path, report_path, candidate="action_button")
    by_id = build(tmp_path, report_path, candidate="ui_kit.action_button")
    assert by_name == by_id


def test_unselected_candidate_is_rejected(tmp_path):
    touch(tmp_path, final_relative())

    with pytest.raises(CurationEntryDraftError, match="Candidate is not selected"):
        build(tmp_path, write_report(tmp_path, make_report()), candidate="empty_04")


def test_missing_candidate_is_rejected(tmp_path):
    with pytest.raises(CurationEntryDraftError, match="Candidate not found"):
        build(tmp_path, write_report(tmp_path, make_report()), candidate="nope")


def test_ambiguous_candidate_is_rejected(tmp_path):
    """Two candidates answering to one selector must not silently pick one."""
    report = make_report()
    report["candidates"].append(
        {
            "candidate_id": "ui_kit.duplicate",
            "name": "action_button",
            "state": "selected",
            "final_path": final_relative(),
        }
    )

    with pytest.raises(CurationEntryDraftError, match="ambiguous"):
        build(tmp_path, write_report(tmp_path, report))


@pytest.mark.parametrize("selected_count", [0, -1, "1", None, True])
def test_selected_count_must_be_a_positive_integer(tmp_path, selected_count):
    touch(tmp_path, final_relative())
    report = make_report(selected_count=selected_count)

    with pytest.raises(CurationEntryDraftError, match="selected_count must be an integer"):
        build(tmp_path, write_report(tmp_path, report))


@pytest.mark.parametrize("rejected_count", [-1, "0", None, False])
def test_rejected_count_must_be_a_non_negative_integer(tmp_path, rejected_count):
    touch(tmp_path, final_relative())
    report = make_report(rejected_count=rejected_count)

    with pytest.raises(CurationEntryDraftError, match="rejected_count must be an integer"):
        build(tmp_path, write_report(tmp_path, report))


def test_strategy_must_be_recorded(tmp_path):
    touch(tmp_path, final_relative())
    report = make_report()
    report.pop("strategy")

    with pytest.raises(CurationEntryDraftError, match="report.strategy"):
        build(tmp_path, write_report(tmp_path, report))


@pytest.mark.parametrize(
    "final_path",
    [
        "assets/ui/action_button.png",
        ".godotmaker/asset-generation/curation/ui_kit_source/action_button.png",
        "assets/generated/ui-kit/other_asset/action_button.png",
    ],
    ids=["outside-generated-tree", "curation-scratch", "other-asset-dir"],
)
def test_final_path_must_stay_in_the_stable_directory(tmp_path, final_path):
    report = make_report()
    report["candidates"][0]["final_path"] = final_path
    touch(tmp_path, final_path)

    with pytest.raises(CurationEntryDraftError, match="candidate.final_path"):
        build(tmp_path, write_report(tmp_path, report))


def test_reference_family_is_not_curated(tmp_path):
    touch(tmp_path, final_relative())

    with pytest.raises(CurationEntryDraftError, match="reference-only"):
        build(
            tmp_path,
            write_report(tmp_path, make_report()),
            production_family="screen-reference",
        )


@pytest.mark.parametrize("source_layout", ["reference", "sprite", ""])
def test_reference_and_unknown_layouts_are_rejected(tmp_path, source_layout):
    touch(tmp_path, final_relative())

    with pytest.raises(CurationEntryDraftError, match="source_layout is not allowed"):
        build(
            tmp_path,
            write_report(tmp_path, make_report()),
            source_layout=source_layout,
        )


def test_region_atlas_layout_is_allowed(tmp_path):
    touch(tmp_path, final_relative())
    entry = build(
        tmp_path, write_report(tmp_path, make_report()), source_layout="region_atlas"
    )
    assert entry["source_layout"]["type"] == "region_atlas"


def test_cli_writes_draft(tmp_path):
    touch(tmp_path, final_relative())
    report_path = write_report(tmp_path, make_report())
    out = tmp_path / ".godotmaker/asset-generation/work/entries/action_button.json"

    result = subprocess.run(
        [
            sys.executable,
            str(DRAFT_TOOL),
            "--report",
            str(report_path),
            "--candidate",
            "action_button",
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
    assert json.loads(result.stdout)["ok"] is True
    assert json.loads(out.read_text(encoding="utf-8"))["processing_status"] == "source_ready"


def test_cli_reports_a_rejection_as_json(tmp_path):
    touch(tmp_path, final_relative())
    report_path = write_report(tmp_path, make_report())
    out = tmp_path / "draft.json"

    result = subprocess.run(
        [
            sys.executable,
            str(DRAFT_TOOL),
            "--report",
            str(report_path),
            "--candidate",
            "empty_04",
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
    assert "Candidate is not selected" in json.loads(result.stdout)["error"]
    assert not out.exists()


def test_write_emits_the_draft_file(tmp_path):
    touch(tmp_path, final_relative())
    report_path = write_report(tmp_path, make_report())
    out = tmp_path / ".godotmaker/asset-generation/work/entries/action_button.json"

    result = write_curation_entry_draft(
        report_path,
        candidate="action_button",
        asset_id=ASSET_ID,
        tag=TAG,
        production_family=FAMILY,
        project_root=tmp_path,
        source_layout="single",
        out=out,
    )

    assert result["ok"] is True
    assert out.exists()


def _fx_static_inputs(tmp_path):
    asset_id = "lantern_spark"
    family = "fx-bundle"
    relative = final_relative(asset_id, family)
    image = tmp_path / relative
    image.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (16, 16), (255, 192, 0, 160)).save(image)
    report = make_report()
    report["candidates"][0].update(
        candidate_id="fx.lantern_spark",
        name="lantern_spark",
        final_path=relative,
    )
    report_path = write_report(tmp_path, report)
    request = {
        "asset_type": "fx-bundle",
        "asset_id": asset_id,
        "brief": "A static lantern spark.",
        "provider": "codex",
        "spec": {"mode": "static"},
    }
    request_path = tmp_path / "ASSET_REQUEST.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    return asset_id, relative, report_path, request_path


def test_fx_static_entry_binds_selected_png_to_texture2d(tmp_path):
    asset_id, relative, report_path, request_path = _fx_static_inputs(tmp_path)

    entry = build_fx_static_entry_draft(
        report_path,
        candidate="lantern_spark",
        request_path=request_path,
        asset_id=asset_id,
        tag=TAG,
        project_root=tmp_path,
    )

    assert entry["processing_status"] == "compiled"
    assert entry["source_layout"] == {"type": "single", "path": f"res://{relative}"}
    assert entry["godot_artifact"] == {"type": "Texture2D", "path": f"res://{relative}"}


def test_fx_static_entry_requires_the_static_request_mode(tmp_path):
    asset_id, _, report_path, request_path = _fx_static_inputs(tmp_path)
    request = json.loads(request_path.read_text(encoding="utf-8"))
    request["spec"] = {
        "mode": "animated",
        "required_actions": ["spark"],
        "actions": [{
            "name": "spark",
            "grid": {"columns": 1, "rows": 1},
            "frame_names": ["spark_01"],
            "fps": 1,
            "loop": False,
            "frame_durations": [1],
        }],
    }
    request_path.write_text(json.dumps(request), encoding="utf-8")

    with pytest.raises(CurationEntryDraftError, match="static fx-bundle"):
        build_fx_static_entry_draft(
            report_path,
            candidate="lantern_spark",
            request_path=request_path,
            asset_id=asset_id,
            tag=TAG,
            project_root=tmp_path,
        )


def test_fx_static_entry_writer_emits_compiled_draft(tmp_path):
    asset_id, relative, report_path, request_path = _fx_static_inputs(tmp_path)
    out = tmp_path / ".godotmaker/asset-generation/work/entries/lantern_spark.json"

    result = write_fx_static_entry_draft(
        report_path,
        candidate="lantern_spark",
        request_path=request_path,
        asset_id=asset_id,
        tag=TAG,
        project_root=tmp_path,
        out=out,
    )

    assert result["ok"] is True
    assert result["path"] == f"res://{relative}"
    assert json.loads(out.read_text(encoding="utf-8"))["processing_status"] == "compiled"
