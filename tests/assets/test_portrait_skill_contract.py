"""The first-class ``portrait`` family, end to end, and its routing boundary.

A portrait is one runtime ``Texture2D`` for a UI display slot. A character
identity anchor is an optional ``canonical`` request reference -- provider
input -- and never a result output or an ``ASSETS.md`` row. Portraits are no
longer routed through ``background-map``, whose scenic-only boundary stays put.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(REPO_ROOT / "skills" / "assets" / "_shared"),
    str(REPO_ROOT / "tools"),
]

import missing_family_standalone_validation as runner  # noqa: E402
from asset_family_registry import FAMILIES  # noqa: E402
from asset_result_registration import (  # noqa: E402
    AssetResultRegistrationError,
    register_result,
    runtime_snapshot,
)
from asset_skill_contract_check import check_request, check_result  # noqa: E402
from asset_validation import ProbeReport, ProbeResult  # noqa: E402
from design_rules import ASSET_SUBJECT_CLASSES  # noqa: E402
from missing_family_standalone_validation import MissingFamilySkillError  # noqa: E402


SKILL_DIR = REPO_ROOT / "skills" / "assets" / "portrait"
FIXTURES = SKILL_DIR / "fixtures"
ASSETS_TEMPLATE = REPO_ROOT / "templates" / "ASSETS.md"
BACKGROUND_SKILL = REPO_ROOT / "skills" / "assets" / "background-map" / "SKILL.md"
SCHEMA_DIR = REPO_ROOT / "skills" / "assets" / "_shared" / "schema"
TAG = "v0.1.0"
LEVELS = ("L0", "L1", "L2", "L3", "L4")


def _fixtures() -> tuple[dict, dict]:
    return (
        json.loads((FIXTURES / "representative-request.json").read_text(encoding="utf-8")),
        json.loads((FIXTURES / "representative-result.json").read_text(encoding="utf-8")),
    )


def _adapter(family: str):
    path = REPO_ROOT / "skills" / "assets" / family / "standalone_validation.py"
    spec = importlib.util.spec_from_file_location(f"portrait_test_{family}_adapter", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _Texture2DProbe:
    def __init__(self, _path):
        pass

    def probe(self, _root, requests):
        return ProbeReport(
            "fake",
            tuple(
                ProbeResult(
                    item.res_path, "Texture2D", True, "CompressedTexture2D", True,
                    structure={"texture2d": {"width": 4, "height": 4}},
                )
                for item in requests
            ),
        )


def _deliver(root: Path, result: dict) -> Path:
    artifact = root / result["outputs"][0]["path"].removeprefix("res://")
    artifact.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (4, 4), (10, 20, 30, 255)).save(artifact)
    return artifact


def _template_assets_md(root: Path) -> Path:
    """Copy the shipped template's Asset Table header and its portrait row."""
    text = ASSETS_TEMPLATE.read_text(encoding="utf-8")
    lines = text.splitlines()
    header = next(line for line in lines if line.startswith("| # | Tag | Name |"))
    portrait = next(line for line in lines if "| player_portrait |" in line)
    separator = lines[lines.index(header) + 1]
    path = root / "ASSETS.md"
    path.write_text(
        "# Assets\n\n## Asset Table\n\n" + "\n".join((header, separator, portrait)) + "\n",
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# AC-03: request -> result -> standalone validation -> registration
# ---------------------------------------------------------------------------


def test_portrait_is_one_single_layout_texture2d_route():
    family = FAMILIES["portrait"]
    assert [variant.variant for variant in family.variants] == ["default"]
    variant = family.variants[0]
    assert variant.entry_source_layouts == ("single",)
    assert variant.artifact_types == ("Texture2D",)
    assert variant.runtime_outputs == "one"
    assert family.terminal_status == "generated"


def test_portrait_fixtures_pass_the_shared_contract_with_an_identity_anchor():
    request, result = _fixtures()
    assert check_request(request)["asset_type"] == "portrait"
    assert [item["role"] for item in request["references"]] == ["canonical"]
    assert check_result(result)["runtime_output_count"] == 1
    assert [item["role"] for item in result["outputs"]] == ["runtime"]

    jsonschema = pytest.importorskip("jsonschema")
    request_schema = json.loads((SCHEMA_DIR / "asset-skill-request.schema.json").read_text(encoding="utf-8"))
    result_schema = json.loads((SCHEMA_DIR / "asset-skill-result.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(request, request_schema)
    jsonschema.validate(result, result_schema)


def test_portrait_runs_l0_to_l4_records_and_registers_its_texture(monkeypatch, tmp_path):
    request, result = _fixtures()
    artifact = _deliver(tmp_path, result)
    monkeypatch.setattr(runner, "GodotProbe", _Texture2DProbe)

    validated = _adapter("portrait").compile_and_validate(
        request, result, project_root=tmp_path, godot_path="fake"
    )

    assert validated["validation"] == {"passed": True, "levels": {level: True for level in LEVELS}}
    record = json.loads(
        (tmp_path / ".godotmaker/asset-generation/reports/player_portrait_validation.json")
        .read_text(encoding="utf-8")
    )
    assert record["production_family"] == "portrait"
    assert record["artifact"]["path"] == result["outputs"][0]["path"]

    assets_md = _template_assets_md(tmp_path)
    request_path, result_path = tmp_path / "request.json", tmp_path / "result.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    result_path.write_text(json.dumps(validated), encoding="utf-8")
    registered = register_result(
        assets_md, result_path, tag=TAG, request_path=request_path, loader=lambda *_: None
    )
    assert registered["updated"] == ["player_portrait"]

    row = next(
        line for line in assets_md.read_text(encoding="utf-8").splitlines()
        if "| player_portrait |" in line
    )
    cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
    assert cells[5].startswith("family=portrait")
    assert cells[6:] == [
        "Texture2D",
        "res://assets/generated/portrait/player_portrait/player_portrait.png",
        "generated",
    ]
    # The identity anchor is provider input: it never becomes a row.
    assert "canonical" not in assets_md.read_text(encoding="utf-8")
    assert runtime_snapshot(assets_md, tag=TAG, asset_ids=["player_portrait"]) == [{
        "asset_id": "player_portrait",
        "godot_artifact": {
            "type": "Texture2D",
            "path": "res://assets/generated/portrait/player_portrait/player_portrait.png",
        },
    }]
    assert artifact.is_file()


def test_portrait_generates_without_an_identity_anchor(monkeypatch, tmp_path):
    request, result = _fixtures()
    request.pop("references")
    _deliver(tmp_path, result)
    monkeypatch.setattr(runner, "GodotProbe", _Texture2DProbe)

    validated = _adapter("portrait").compile_and_validate(
        request, result, project_root=tmp_path, godot_path="fake"
    )

    assert validated["validation"]["passed"] is True


def test_portrait_never_returns_its_identity_anchor_as_an_output(tmp_path):
    request, result = _fixtures()
    result["outputs"].append({
        "role": "reference",
        "name": "canonical",
        "path": "res://assets/generated/portrait/player_portrait/player_portrait_canonical.png",
    })
    with pytest.raises(MissingFamilySkillError, match="identity anchor stays a request reference"):
        _adapter("portrait").compile_and_validate(
            request, result, project_root=tmp_path, godot_path="fake"
        )


def test_portrait_registration_requires_the_bytes_its_ladder_examined(tmp_path):
    request, result = _fixtures()
    _deliver(tmp_path, result)
    assets_md = _template_assets_md(tmp_path)
    request_path, result_path = tmp_path / "request.json", tmp_path / "result.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    result_path.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(AssetResultRegistrationError, match="validation record"):
        register_result(
            assets_md, result_path, tag=TAG, request_path=request_path, loader=lambda *_: None
        )
    assert "| MISSING |" in assets_md.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("adapter", "family"),
    [("portrait", "background-map"), ("background-map", "portrait")],
)
def test_portrait_and_background_adapters_refuse_each_other(tmp_path, adapter, family):
    request, result = _fixtures()
    request, result = copy.deepcopy(request), copy.deepcopy(result)
    request["asset_type"] = result["asset_type"] = family
    with pytest.raises(MissingFamilySkillError, match="L0 standalone contract failed"):
        _adapter(adapter).compile_and_validate(
            request, result, project_root=tmp_path, godot_path="fake"
        )


def test_portrait_is_judged_as_a_character_subject():
    assert ASSET_SUBJECT_CLASSES["portrait"] == "character"


# ---------------------------------------------------------------------------
# AC-04: the template routes portraits to `portrait`; background-map unchanged
# ---------------------------------------------------------------------------


def test_template_routes_every_portrait_row_to_the_portrait_family():
    text = ASSETS_TEMPLATE.read_text(encoding="utf-8")
    table = text.split("## Asset Table", 1)[1].split("\n## ", 1)[0]
    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in table.splitlines()
        if line.startswith("| ") and "---" not in line
    ]
    portraits = [cells for cells in rows if len(cells) == 9 and cells[3] == "portrait"]
    assert portraits, "the template must show a portrait row"
    for cells in portraits:
        assert cells[5].startswith("family=portrait;")
        assert cells[6] == "Texture2D"
        assert cells[7].startswith("res://assets/generated/portrait/")
    # No row of any type sends a portrait through the scenic family.
    for cells in rows:
        if len(cells) == 9 and "family=background-map" in cells[5]:
            assert cells[3] == "background"
            assert "portrait" not in cells[2]
    assert "generated/background-map/player_portrait" not in text
    assert "Portrait rows use the `portrait` family" in text
    assert "`background-map` stays scenic\n   backgrounds only." in text


def test_background_map_keeps_its_scenic_only_boundary():
    text = BACKGROUND_SKILL.read_text(encoding="utf-8")
    assert "Do not\nuse it for actors, foreground props, UI, or collision-bearing\ngeometry." in text
    assert "Generate a source image with no gameplay actors, pickups, hazards, UI," in text
    assert "portrait" not in text.lower()


def test_background_map_rejects_a_delivery_at_the_portrait_path(tmp_path):
    request, result = _fixtures()
    request = {"asset_type": "background-map", "asset_id": "player_portrait", "brief": "A sky."}
    result["asset_type"] = "background-map"
    with pytest.raises(MissingFamilySkillError, match="background-map needs exactly its stable Texture2D"):
        _adapter("background-map").compile_and_validate(
            request, result, project_root=tmp_path, godot_path="fake"
        )


def test_planner_routes_portraits_away_from_background_map_and_character_bundle():
    planner = (REPO_ROOT / "skills/core/gm-asset/references/asset-planner.md").read_text(encoding="utf-8")
    assert "Plan a character portrait for a UI display slot as its own `portrait`\n   unit." in planner
    assert "Never route a portrait to `background-map`" in planner
    assert "| `portrait` | yes | 1, 2, 3, 4, 5, 6, 7, 9 | no | yes |" in planner
