"""End-to-end contract smoke for projects with no references directory."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_asset_accept_and_evaluate_contracts_need_no_scene_reference(tmp_path):
    design = tmp_path / "DESIGN.md"
    design.write_text(_read("templates/DESIGN.md"), encoding="utf-8")
    capture = tmp_path / "e2e" / "screenshots" / "scene_main.png"
    capture.parent.mkdir(parents=True)
    Image.new("RGBA", (4, 4), (20, 30, 40, 255)).save(capture)
    assert not (tmp_path / "references").exists()

    built = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "design_rules.py"),
            "build-request",
            "--design",
            "DESIGN.md",
            "--subject",
            "mixed",
            "--name",
            "scene_main",
            "--kind",
            "scene",
            "--project-root",
            ".",
            "--capture",
            "e2e/screenshots/scene_main.png",
            "--requirement",
            "Player and HUD are visible",
            "--output",
            "request.json",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert built.returncode == 0, built.stderr
    request = json.loads((tmp_path / "request.json").read_text(encoding="utf-8"))
    assert request["reference_provenance"] == []
    assert request["reference_resources"] == []
    assert request["content_requirements"] == ["Player and HUD are visible"]

    asset = _read("skills/core/gm-asset/SKILL.md")
    accept = _read("skills/core/gm-accept/SKILL.md")
    evaluate = _read("skills/core/gm-evaluate/SKILL.md")
    assert "No MISSING assets for the current tag" in asset
    assert "with their design-rule and content verdicts" in accept
    assert "--reference references/scene_" not in evaluate
    assert "applicable rules selected from `DESIGN.md`" in evaluate


def test_public_family_surface_has_no_screen_reference():
    request_schema = json.loads(
        _read("skills/assets/_shared/schema/asset-skill-request.schema.json")
    )
    result_schema = json.loads(
        _read("skills/assets/_shared/schema/asset-skill-result.schema.json")
    )
    assert "screen-reference" not in request_schema["properties"]["asset_type"]["enum"]
    assert "screen-reference" not in result_schema["properties"]["asset_type"]["enum"]
    assert not (ROOT / "skills" / "assets" / "screen-reference").exists()
