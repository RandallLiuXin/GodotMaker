"""Regression gates for neutral Asset Skill handoff contracts."""
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hooks.metrics.outcome import OUTPUT_CATEGORIES, VALIDATION_LEVELS  # noqa: E402


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_asset_producer_outcome_template_matches_runtime_schema():
    producer = _read("agents/asset-producer.md")
    for category in OUTPUT_CATEGORIES:
        assert f'"{category}"' in producer
    for level in VALIDATION_LEVELS:
        assert f'"{level}"' in producer


def test_hook_docs_document_the_runtime_validation_levels():
    for relative in ("docs/hooks.md", "docs/zh/hooks.md"):
        text = _read(relative)
        assert "L0" in text and "L5" in text


def test_asset_no_work_resume_path_appends_the_asset_stage_event():
    skill = _read("skills/core/gm-asset/SKILL.md")
    completion = skill[skill.index("After ASSETS.md has no current-tag"):]
    assert "python tools/append_stage_event.py asset" in completion


def test_reference_outputs_never_become_worker_runtime_inputs():
    registration = _read("skills/core/gm-asset/references/asset-result-registration.md")
    worker_dispatch = _read("skills/core/_shared/worker-dispatch.md")
    assert "`reference` outputs are already-validated" in registration
    assert "Only runtime outputs are registered" in registration
    assert "optional provider-input images" in worker_dispatch


def test_codex_provider_claims_raw_image_before_final_validation():
    provider = _read("skills/core/gm-asset/references/providers/codex.md")

    assert "The provider step owns generation and source handoff" in provider
    assert "Do not reject the raw provider image" in provider
    assert "claim it so the production unit can finalize and validate it" in provider
def test_residual_asset_families_use_canonical_generation_workspace_handoffs():
    manager = _read("skills/core/gm-asset/SKILL.md")
    producer = _read("agents/asset-producer.md")
    families = {
        name: _read(f"skills/assets/{name}/SKILL.md")
        for name in ("fx-bundle", "tileset", "scene-prop-set", "ui-kit")
    }

    assert "immutable canonical request owned by the manager" in manager
    assert "before dispatch" in manager
    assert "manager-owned canonical request" in producer
    assert "never create,\n    derive, replace, or modify that file" in producer

    canonical_request = ".godotmaker/asset-generation/<asset_id>-request.json"
    canonical_result = ".godotmaker/asset-generation/<asset_id>-result.json"
    for skill in families.values():
        assert canonical_request in skill
        assert canonical_result in skill
        assert "ASSET_REQUEST.json" not in skill
        assert "ASSET_RESULT.json" not in skill

    ui_kit = families["ui-kit"]
    for root_intermediate in (
        "--out source_sheet_plan.json",
        "--out stylebox_plan.json",
        "--out theme_recipe.json",
    ):
        assert root_intermediate not in ui_kit
    assert ".godotmaker/asset-generation/work/<asset_id>/" in ui_kit
    assert ".godotmaker/asset-generation/reports/<asset_id>_source_sheet_provenance.json" in ui_kit


def test_ui_kit_request_is_closed_by_manager_before_producer_dispatch():
    manager = _read("skills/core/gm-asset/SKILL.md")
    planner = _read("skills/core/gm-asset/references/asset-planner.md")
    producer = _read("agents/asset-producer.md")
    ui_kit = _read("skills/assets/ui-kit/SKILL.md")

    assert "complete the **UI-kit pre-dispatch planning** procedure" in manager
    assert "only then writes the canonical request" in manager
    assert "The manager must not read reference image binaries" in planner
    assert "Dispatch `visual-qa` in\n   Question mode" in planner
    assert "Copy\n   `stylebox_plan.styleboxes` exactly into `spec.styleboxes`" in planner
    assert "Never write it earlier and\n   patch it after dispatch" in planner
    assert "byte-identical copies" in planner

    assert "Never regenerate or modify them" in producer
    assert "verify the supplied pre-dispatch plans agree with the immutable\n   request" in producer
    assert "The caller owns pre-dispatch planning" in ui_kit
    assert "do not\n   regenerate or modify it after dispatch" in ui_kit
    assert "it must not repair the immutable\n     request or caller-owned plans" in ui_kit

    permissions = _read("hooks/check_file_permissions.py")
    assert "_is_manager_owned_asset_planning_path" in permissions
    for filename in (
        "planning-request.json",
        "theme_plan.json",
        "source_sheet_plan.json",
        "stylebox_plan.json",
        "theme_recipe.json",
    ):
        assert f'"{filename}"' in permissions


def test_screen_reference_skill_is_retired():
    assert not (ROOT / "skills/assets/screen-reference").exists()
