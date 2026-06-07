import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_curation_select import CurationSelectError, select_candidate  # noqa: E402


def write_png(path: Path, size=(12, 8)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, (255, 120, 40, 255)).save(path)


def write_report(path: Path, candidate_path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "asset_id": "ui_kit_source",
                "tag": "v0.1.0",
                "source_path": ".godotmaker/asset-generation/sources/ui_kit_source.png",
                "strategy": "transparent_grid",
                "status": "candidate_extracted",
                "candidates": [
                    {
                        "candidate_id": "ui_kit_source.action_button",
                        "name": "action_button",
                        "path": str(candidate_path),
                        "state": "candidate",
                        "bbox": [0, 0, 12, 8],
                        "final_path": None,
                    }
                ],
                "rejected": [
                    {
                        "candidate_id": "ui_kit_source.empty_04",
                        "state": "rejected",
                        "reason": "empty_cell",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_select_candidate_finalizes_asset_and_updates_report(tmp_path):
    candidate = tmp_path / ".godotmaker" / "asset-generation" / "curation" / "ui" / "button.png"
    write_png(candidate)
    report = tmp_path / ".godotmaker" / "asset-generation" / "curation" / "ui_kit_source.json"
    write_report(report, candidate)
    final_path = tmp_path / "assets" / "ui" / "action_button.png"

    result = select_candidate(
        report,
        "ui_kit_source.action_button",
        final_path,
        asset_id="action_button",
        resize="6x4",
    )

    assert result["ok"] is True
    assert final_path.exists()
    assert result["finalize"]["asset_id"] == "action_button"
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["status"] == "selected"
    assert data["selected_count"] == 1
    assert data["rejected_count"] == 1
    assert data["selected_candidate_ids"] == ["ui_kit_source.action_button"]
    assert data["candidates"][0]["state"] == "selected"
    assert data["candidates"][0]["final_path"] == str(final_path)


def test_select_candidate_resolves_relative_paths_from_project_root(tmp_path):
    candidate = Path(".godotmaker/asset-generation/curation/ui/button.png")
    write_png(tmp_path / candidate)
    report = Path(".godotmaker/asset-generation/curation/ui_kit_source.json")
    write_report(tmp_path / report, candidate)
    final_path = Path("assets/ui/action_button.png")

    result = select_candidate(
        report,
        "ui_kit_source.action_button",
        final_path,
        asset_id="action_button",
        project_root=tmp_path,
    )

    assert result["ok"] is True
    assert result["report_path"] == str(report)
    assert result["final_path"] == str(final_path)
    assert (tmp_path / final_path).exists()
    data = json.loads((tmp_path / report).read_text(encoding="utf-8"))
    assert data["status"] == "selected"
    assert data["candidates"][0]["final_path"] == str(final_path)


def test_select_candidate_rejects_missing_candidate(tmp_path):
    candidate = tmp_path / "candidate.png"
    write_png(candidate)
    report = tmp_path / "report.json"
    write_report(report, candidate)

    with pytest.raises(CurationSelectError, match="Candidate not found"):
        select_candidate(report, "missing", tmp_path / "assets" / "out.png")


def test_cli_outputs_json(tmp_path):
    candidate = tmp_path / ".godotmaker" / "asset-generation" / "curation" / "ui" / "button.png"
    write_png(candidate)
    report = tmp_path / ".godotmaker" / "asset-generation" / "curation" / "ui_kit_source.json"
    write_report(report, candidate)
    final_path = tmp_path / "assets" / "ui" / "action_button.png"

    result = subprocess.run(
        [
            sys.executable,
            str(TOOLS_DIR / "asset_curation_select.py"),
            "--report",
            str(report),
            "--candidate",
            "action_button",
            "--final-path",
            str(final_path),
            "--asset-id",
            "action_button",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["name"] == "action_button"
    assert final_path.exists()
