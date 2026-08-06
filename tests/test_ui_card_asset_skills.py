"""Public contracts for standalone UI and card Asset Skills."""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = REPO_ROOT / "skills" / "assets"
sys.path.insert(0, str(REPO_ROOT / "tools"))

from asset_skill_contract_check import check_result  # noqa: E402
from asset_ui_card_contract_check import check_ui_card_handoff  # noqa: E402


FAMILIES = {
    "ui-kit": {
        "terms": ("icons", "panels", "button states", "Theme", "StyleBoxTexture", "AtlasTexture"),
        "source_layouts": {"theme_recipe", "grid_sheet", "region_atlas", None},
    },
    "card-kit": {
        "terms": ("card frames", "portrait frames", "nine-slice", "Theme", "StyleBoxTexture", "AtlasTexture"),
        "source_layouts": {"theme_recipe", "region_atlas"},
    },
}


@pytest.mark.parametrize("family,expected", FAMILIES.items())
def test_each_ui_family_has_an_independent_skill_and_valid_fixture(family, expected):
    skill_path = ASSETS_DIR / family / "SKILL.md"
    fixture_path = ASSETS_DIR / family / "fixtures" / "representative-result.json"
    request_path = ASSETS_DIR / family / "fixtures" / "representative-request.json"

    assert skill_path.is_file()
    assert fixture_path.is_file()
    skill = skill_path.read_text(encoding="utf-8")
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    request = json.loads(request_path.read_text(encoding="utf-8"))

    assert "shared Asset Skill request schema" in skill
    assert "shared result schema and checker" in skill
    assert "invoked directly or by an orchestrator" in skill
    # Families may describe the manager-owned direct registration boundary, but
    # must not revive the retired per-resource handoff contract.
    for retired_handoff in ("stable entry", "producer adapter", "entry draft"):
        assert retired_handoff not in skill.lower()
    for term in expected["terms"]:
        assert term in skill

    assert check_result(fixture)["ok"] is True
    assert check_ui_card_handoff(request, fixture)["ok"] is True
    assert fixture["asset_type"] == family
    assert {item["godot_type"] for item in fixture["outputs"]} == {
        "Theme", "StyleBoxTexture", "AtlasTexture"
    }
    assert all(item["role"] == "runtime" for item in fixture["outputs"])
    assert {item.get("layout") for item in fixture["sources"]} == expected["source_layouts"]
    assert fixture["validation"]["levels"] == {
        "L0": True, "L1": True, "L2": True, "L3": True, "L4": True
    }


@pytest.mark.parametrize("family", FAMILIES)
def test_ui_family_keeps_layout_and_runtime_responsibilities_separate(family):
    skill = (ASSETS_DIR / family / "SKILL.md").read_text(encoding="utf-8")

    assert "Control" in skill
    assert "Container" in skill
    assert "not pixel-perfect" in skill
    assert "L0-L4" in skill
    assert "deterministic tools" in skill or "controlled tools" in skill


def test_ui_kit_owns_a_color_keyed_two_sheet_provider_plan():
    skill_root = ASSETS_DIR / "ui-kit"
    skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    scheme = json.loads((skill_root / "references" / "source-sheet-scheme.json").read_text(encoding="utf-8"))

    assert scheme["background"] == {
        "color": "#FF00FF", "flat": True, "reserved_for_color_key": True, "forbid_in_art": True,
    }
    assert [sheet["id"] for sheet in scheme["sheets"]] == [
        "surface_patches", "icons",
    ]
    assert [len(sheet["components"]) for sheet in scheme["sheets"]] == [8, 24]
    assert set(tuple(component["target_size"]) for component in scheme["sheets"][0]["components"]) == {(96, 96)}
    icons = {component["name"]: component for component in scheme["sheets"][1]["components"]}
    assert icons["arrow_right"]["target_size"] == [32, 32]
    assert icons["checkbox_checked"]["target_size"] == [40, 40]
    assert icons["slider_grabber"]["target_size"] == [48, 48]
    assert icons["information"]["target_size"] == [128, 128]
    assert "asset_ui_source_sheet_plan.py" in skill
    assert "asset_ui_stylebox_plan.py" in skill
    assert "Treat a\nfailed level as repair input" in skill
    assert "do not STOP merely because a production validation attempt failed" in skill
    assert "source_sheet_provenance.json" in skill
    assert "tool_call_id" in skill
    assert "retries" in skill
    assert "surface_patches_process_report.json" in skill
    assert "icons_process_report.json" in skill


def test_gm_asset_dispatches_ui_and_card_kits_to_their_named_skills():
    manager = (REPO_ROOT / "skills" / "core" / "gm-asset" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    planner = (REPO_ROOT / "skills" / "core" / "gm-asset" /
               "references" / "asset-planner.md").read_text(encoding="utf-8")

    for family in FAMILIES:
        assert not (REPO_ROOT / "skills" / "core" / "gm-asset" / "references" /
                    "production-units" / f"{family}.md").exists()
        assert f"| `{family}` | First-class `{family}` Asset Skill |" in manager
        assert f"references/production-units/{family}.md" not in manager
        assert f"references/production-units/{family}.md" not in planner
        # The brief's Production Contract must offer this family as a choice, so
        # a producer can never be handed a unit with no named Skill to invoke.
        assert family in manager.split("First-class Asset Skill: {")[1]

    # Planning derives the expected output set from the named family's native
    # contract; the manager registers the validated result directly into
    # ASSETS.md instead of handing it to a per-family production-unit document
    # or stable-entry adapter.
    assert "native contract" in planner
    assert "compact-prop-pack" in planner
    assert "asset_result_registration.py" in planner
    assert "ASSETS.md" in planner
