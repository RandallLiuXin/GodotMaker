"""Public contracts for standalone UI and card Asset Skills."""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = REPO_ROOT / "skills" / "assets"
sys.path.insert(0, str(REPO_ROOT / "tools"))

from asset_skill_contract_check import check_result  # noqa: E402


FAMILIES = {
    "ui-kit": {
        "terms": ("icons", "panels", "button states", "Theme", "StyleBoxTexture", "AtlasTexture"),
        "source_layouts": {"theme_recipe", "region_atlas"},
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

    assert skill_path.is_file()
    assert fixture_path.is_file()
    skill = skill_path.read_text(encoding="utf-8")
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    assert "shared Asset Skill request schema" in skill
    assert "shared result schema and checker" in skill
    assert "invoked directly or by an orchestrator" in skill
    for forbidden_context in ("ASSETS.md", "tags", "stage state", "generated\nmanifests"):
        assert forbidden_context in skill
    for term in expected["terms"]:
        assert term in skill

    assert check_result(fixture)["ok"] is True
    assert fixture["asset_type"] == family
    assert {item["godot_type"] for item in fixture["outputs"]} == {
        "Theme", "StyleBoxTexture", "AtlasTexture"
    }
    assert all(item["role"] == "runtime" for item in fixture["outputs"])
    assert {item["layout"] for item in fixture["sources"]} == expected["source_layouts"]
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
    assert "deterministic tools" in skill


def test_ui_kit_owns_a_color_keyed_three_sheet_provider_plan():
    skill_root = ASSETS_DIR / "ui-kit"
    skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    scheme = json.loads((skill_root / "references" / "source-sheet-scheme.json").read_text(encoding="utf-8"))

    assert scheme["background"] == {
        "color": "#FF00FF", "flat": True, "reserved_for_color_key": True, "forbid_in_art": True,
    }
    assert [sheet["id"] for sheet in scheme["sheets"]] == [
        "state_frames", "form_navigation", "utility_icons",
    ]
    assert "asset_ui_source_sheet_plan.py" in skill
    assert "Treat a\nfailed level as repair input" in skill
    assert "do not STOP merely because a production validation attempt failed" in skill


def test_gm_asset_dispatches_ui_and_card_kits_to_their_named_skills():
    manager = (REPO_ROOT / "skills" / "core" / "gm-asset" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    planner = (
        REPO_ROOT / "skills" / "core" / "gm-asset" / "references" / "asset-planner.md"
    ).read_text(encoding="utf-8")

    for family in FAMILIES:
        assert not (REPO_ROOT / "skills" / "core" / "gm-asset" / "references" /
                    "production-units" / f"{family}.md").exists()
        assert f"| `{family}` | First-class `{family}` Asset Skill |" in manager
        assert f"| `{family}` | First-class `{family}` Asset Skill |" in planner
        assert f"references/production-units/{family}.md" not in manager
        assert f"references/production-units/{family}.md" not in planner
        assert family in manager.split("First-class unit:")[1]
