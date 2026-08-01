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
    "scene-prop-set": {
        "role": "runtime",
        "godot_type": "AtlasTexture",
        "source_layout": "region_atlas",
        "path_prefix": "res://assets/generated/scene-prop-set/",
    },
    "screen-reference": {
        "role": "reference",
        "godot_type": None,
        "source_layout": None,
        "path_prefix": "references/",
    },
    "compact-prop-pack": {
        "role": "runtime",
        "godot_type": "AtlasTexture",
        "source_layout": "region_atlas",
        "path_prefix": "res://assets/generated/compact-prop-pack/",
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
    assert ".godotmaker/asset-runtime/tools/codex_image_claim.py --plan" in platform
    assert "never hand-write provenance JSON" in platform
    assert "Split the raw provider sheet before any crop, resize, or padding" in platform
    assert "Never normalize the whole sheet as one image" in platform
    assert "one `sources` entry with `layout: \"single\"` for every processed segment" in platform


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


def test_scene_prop_set_uses_one_real_source_sheet_and_trace_first_repair():
    skill = (ASSETS_DIR / "scene-prop-set" / "SKILL.md").read_text(encoding="utf-8")

    for required in (
        "`references` is optional",
        "referenced_image_paths",
        "Do not pass `--grid` to autoslice",
        "one image-generation attempt for the complete set",
        "asset_sheet_process.py",
        "asset_curation_select.py",
        "asset_image_finalize.py",
        "asset_atlas_assemble.py",
        "preserve aspect ratio",
        "Pillow, System.Drawing, ImageMagick",
        "needs_regeneration",
        "Reject pixel-art requests",
        "asset_scene_prop_set_entry_draft.py",
        "standalone_validation.py",
        "configured `godot_path`",
    ):
        assert required in skill
    assert "GM_EVAL_GODOT_PATH" not in skill
    assert "one provider image per slot" not in skill


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
    """Every planned family, not just the flat ones, lost its duplicate doc.

    `character-bundle` and `fx-bundle` were the last two to keep a
    production-unit document. While one survived under a directory a runtime
    agent reads, a producer could still treat it as the family's execution
    contract and drift from the real Skill.
    """
    old_units = REPO_ROOT / "skills" / "core" / "gm-asset" / "references" / "production-units"
    assert not old_units.exists()

    planned = sorted({*FAMILIES, "character-bundle", "fx-bundle", "ui-kit", "card-kit"})
    for path in (
        REPO_ROOT / "skills" / "core" / "gm-asset" / "SKILL.md",
        REPO_ROOT / "skills" / "core" / "gm-asset" / "references" / "asset-planner.md",
    ):
        text = path.read_text(encoding="utf-8")
        for family in planned:
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
    assert "asset_scene_prop_set_entry_draft.py" in manager
    assert "one provider source sheet" in producer


def test_gm_asset_adapts_a_first_class_result_without_inventing_a_second_entry():
    """The manager's role in a first-class call is adapter, never author.

    A Skill call may deliver several logical outputs. Only one of them is the
    runtime asset; the rest are provenance. Without this rule the manager could
    draft a second entry for a generated canonical, and a worker resolving the
    row would find two competing artifacts for one asset.
    """
    manager = (REPO_ROOT / "skills" / "core" / "gm-asset" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    producer = (REPO_ROOT / "agents" / "asset-producer.md").read_text(encoding="utf-8")
    flat = " ".join(manager.split())

    assert "One Skill call may return several logical outputs." in flat
    assert "Exactly one runtime output per logical asset becomes a stable entry" in flat
    assert "Never draft a second entry or a `godot_artifact` for a reference." in flat

    # character-bundle hands back the resolved request, one report per action,
    # and the validated result — that triple is what the builder binds together.
    assert "archived resolved request" in flat
    assert "one action processing report per required action" in flat
    assert "registers exactly one worker-consumable `SpriteFrames` entry" in flat
    assert "reaches `ready` only from a result whose L0-L4 levels all passed" in flat
    assert "a user-supplied canonical is not republished at all" in flat
    assert "archived resolved request" in " ".join(producer.split())

    # No family may fall back to a production-unit document any more.
    assert "production-unit document to read" in flat
    assert "no fallback contract for a family" in flat


def test_character_bundle_restores_canonical_actions_and_first_class_routing():
    skill = (ASSETS_DIR / "character-bundle" / "SKILL.md").read_text(encoding="utf-8")
    animation_planning = (ASSETS_DIR / "_shared" / "animation-planning.md").read_text(
        encoding="utf-8"
    )
    manager = (REPO_ROOT / "skills" / "core" / "gm-asset" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    planner = (
        REPO_ROOT / "skills" / "core" / "gm-asset" / "references" / "asset-planner.md"
    ).read_text(encoding="utf-8")
    fixture = (ASSETS_DIR / "character-bundle" / "fixtures" / "valid-request.json").read_text(
        encoding="utf-8"
    )

    for required in (
        "External references are optional.",
        "referenced_image_paths",
        "asset_image_finalize.py",
        "asset_action_process.py",
        "--recover-edge-touch",
        'status: "needs_regeneration"',
        "--scale-reference-metadata",
        "Pixel-art production is unsupported",
        "SpriteFrames",
        "GIF",
        "animation-planning.md",
        "temporal cadence",
        "identity_anchor_origin",
    ):
        assert required in skill
    assert "Plan temporal cadence before choosing a frame count." in animation_planning
    assert "Do not mechanically map one named pose beat to one frame" in animation_planning
    assert "temporal cadence" in animation_planning
    assert "pixel knight" not in fixture.lower()
    assert '"intent"' in fixture
    assert '"grid"' not in fixture
    assert "First-class `character-bundle` Asset Skill" in manager
    assert "First-class `character-bundle` Asset Skill" in planner
    character_row = next(line for line in planner.splitlines() if line.startswith("| `character-bundle` |"))
    assert "Portraits, detached" in character_row
