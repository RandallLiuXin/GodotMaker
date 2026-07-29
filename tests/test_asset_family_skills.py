"""Public contracts for standalone flat, strip, and reference asset skills."""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = REPO_ROOT / "skills" / "assets"
sys.path.insert(0, str(REPO_ROOT / "tools"))

from asset_skill_contract_check import check_result  # noqa: E402


FAMILIES = {
    "background-map": {
        "role": "runtime",
        "godot_type": "Texture2D",
        "source_layout": "single",
        "path_prefix": "res://assets/generated/background-map/",
    },
    "platform-strip": {
        "role": "runtime",
        "godot_type": "AtlasTexture",
        "source_layout": "region_atlas",
        "path_prefix": "res://assets/generated/platform-strip/",
    },
    "screen-reference": {
        "role": "reference",
        "godot_type": None,
        "source_layout": None,
        "path_prefix": "references/",
    },
}


@pytest.mark.parametrize("family", FAMILIES)
def test_each_extracted_family_has_a_standalone_skill_and_fixture(family):
    skill = ASSETS_DIR / family / "SKILL.md"
    fixture = ASSETS_DIR / family / "fixtures" / "representative-result.json"

    assert skill.is_file()
    assert fixture.is_file()
    text = skill.read_text(encoding="utf-8")
    assert "shared Asset Skill request schema" in text
    assert "shared result schema and checker" in text
    assert "invoked directly or by an orchestrator" in text
    for forbidden_context in ("ASSETS.md", "tags", "stage state", "generated manifests"):
        assert forbidden_context in text


@pytest.mark.parametrize("family,expected", FAMILIES.items())
def test_representative_fixture_matches_the_public_family_contract(family, expected):
    fixture = ASSETS_DIR / family / "fixtures" / "representative-result.json"
    result = json.loads(fixture.read_text(encoding="utf-8"))

    assert check_result(result)["ok"] is True
    assert result["asset_type"] == family
    output = result["outputs"][0]
    assert output["role"] == expected["role"]
    assert output["path"].startswith(expected["path_prefix"])
    assert output.get("godot_type") == expected["godot_type"]

    if expected["source_layout"] is None:
        assert result["sources"] == [
            {
                "path": ".godotmaker/asset-generation/sources/main_menu_source.png",
                "layout": "single",
            }
        ]
        assert not any(item["role"] == "runtime" for item in result["outputs"])
    else:
        assert result["sources"][0]["layout"] == expected["source_layout"]


def test_background_and_platform_runtime_contracts_keep_native_type_boundaries():
    background = (ASSETS_DIR / "background-map" / "SKILL.md").read_text(encoding="utf-8")
    platform = (ASSETS_DIR / "platform-strip" / "SKILL.md").read_text(encoding="utf-8")

    assert "Texture2D" in background
    assert "Godot's normal PNG import" in background
    assert "Do not write `ASSET_RESULT.json`" in background
    assert "--report .godotmaker/asset-generation/reports" in background
    assert "Texture2D" in platform
    assert "AtlasTexture" in platform
    assert "fixed grid" in platform
    assert "fixed-slot declaration" in platform
    assert "referenced_image_paths" in platform
    assert "_source.json" in platform
    assert "_validation.json" in platform


def test_background_map_restores_real_provider_finalize_and_non_pixel_contracts():
    background = (ASSETS_DIR / "background-map" / "SKILL.md").read_text(encoding="utf-8")
    codex = (
        REPO_ROOT / "skills" / "core" / "gm-asset" / "references" / "providers" / "codex.md"
    ).read_text(encoding="utf-8")

    for required in (
        "References are optional.",
        "readable image",
        "Do not substitute another provider",
        "asset_image_finalize.py",
        "--require-aspect",
        "source_layout: single",
        "godot_artifact: Texture2D",
        "non-pixel-art",
        "Pillow, System.Drawing, ImageMagick",
        "referenced_image_paths",
        "GM_EVAL_GODOT_PATH",
    ):
        assert required in background
    assert "referenced_image_paths" in codex
    assert "putting a path in text" in codex


def test_shared_asset_contract_examples_do_not_require_pixel_art():
    shared_contract = (ASSETS_DIR / "_shared" / "asset-skill-contract.md").read_text(
        encoding="utf-8"
    )
    character_request = (
        ASSETS_DIR / "_shared" / "samples" / "request" / "character-bundle.json"
    ).read_text(encoding="utf-8")

    assert "pixel-art" not in shared_contract.lower()
    assert "pixel-art" not in character_request.lower()


def test_screen_reference_cannot_be_misrepresented_as_a_runtime_asset():
    screen = (ASSETS_DIR / "screen-reference" / "SKILL.md").read_text(encoding="utf-8")

    assert "reference-only" in screen
    assert "has no `godot_artifact`" in screen
    assert "must not enter worker runtime handoff" in screen
    assert "no `godot_type`" in screen
    assert "Do not compile it to `Texture2D`" in screen
    assert "Do not request or produce pixel art" in screen
    assert "reference_inputs" in screen
    assert "asset_image_finalize.py" in screen


def test_gm_asset_keeps_no_second_authoritative_copy_of_extracted_families():
    old_units = REPO_ROOT / "skills" / "core" / "gm-asset" / "references" / "production-units"
    for family in FAMILIES:
        assert not (old_units / f"{family}.md").exists()

    for path in (
        REPO_ROOT / "skills" / "core" / "gm-asset" / "SKILL.md",
        REPO_ROOT / "skills" / "core" / "gm-asset" / "references" / "asset-planner.md",
    ):
        text = path.read_text(encoding="utf-8")
        for family in FAMILIES:
            assert f"references/production-units/{family}.md" not in text
            assert f"First-class `{family}` Asset Skill" in text


def test_gm_asset_dispatches_extracted_families_through_named_skills():
    manager = (REPO_ROOT / "skills" / "core" / "gm-asset" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    producer = (REPO_ROOT / "agents" / "asset-producer.md").read_text(encoding="utf-8")

    for family in FAMILIES:
        assert f"| `{family}` | First-class Asset Skill: `{family}` |" in manager
        assert f"references/production-units/{family}.md" not in manager
    assert "### First-Class Result Adapter" in manager
    assert "does not register a generic result directly." in manager
    assert "invoke it with the supplied generic request" in producer
    assert "adapt its sources,\n   outputs, and validation evidence" in producer
