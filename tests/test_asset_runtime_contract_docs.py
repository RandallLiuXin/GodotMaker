from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def test_provider_contracts_are_separate_from_generic_asset_docs():
    runtime = _read("skills/core/gm-asset/references/asset-runtime-pipeline.md")
    skill = _read("skills/core/gm-asset/SKILL.md")
    codex = _read("skills/core/gm-asset/references/providers/codex.md")
    native = _read("skills/core/gm-asset/references/providers/native.md")
    gemini = _read("skills/core/gm-asset/references/providers/gemini.md")
    codex_runtime = _read("agent-runtimes/codex/references/runtime-mapping.md")
    claude_runtime = _read("agent-runtimes/claude-code/references/runtime-mapping.md")

    assert "references/providers/codex.md" in runtime
    assert "references/providers/native.md" in skill
    assert "references/providers/gemini.md" in skill
    assert "generated_path" in codex
    assert "--out-report" in codex
    assert "exactly one new image file" in codex
    assert "tools/codex_image_claim.py --plan" in codex
    assert "active coding-agent runtime's native image-generation path" in native
    assert "tools/asset_source_generate.py --spec" in gemini
    assert "generated-path claim protocol" in codex_runtime
    assert "generated-path claim protocol" in claude_runtime
    assert "--out-report" in codex_runtime
    assert "--out-report" in claude_runtime

    forbidden = [
        "ImageGenerationEnd.saved_path",
        "tools/codex_image_claim.py --plan",
        "codex exec --json",
        "generated_images",
        "Sort-Object LastWriteTime",
        "Select-Object -First 1",
    ]
    for token in forbidden:
        assert token not in runtime
        assert token not in skill

    assert "ImageGenerationEnd.saved_path" not in codex
    assert "\"saved_path\"" not in codex
    assert "saved_path claim protocol" not in codex_runtime
    assert "saved_path claim protocol" not in claude_runtime
    assert "Retry transient tool or provider failures at most 2 times." in codex
    assert "Do not create placeholder or procedural images" in codex
    assert '"ok": false' in codex


def test_gm_asset_manager_dispatches_asset_producer_units():
    skill = _read("skills/core/gm-asset/SKILL.md")
    producer = _read("agents/asset-producer.md")

    assert "Dispatch `asset-producer`" in skill
    assert "asset_producer_model from .godotmaker/config.yaml, default: sonnet" in skill
    assert "Do not generate raw visual art in the manager context." in skill
    assert "Dispatch one subagent per production unit." in skill
    assert "## Asset Producer Report:" in producer
    assert "Write only the output paths listed in the brief." in producer
    assert "Use visible scene references and canonical asset references" in producer
    assert "Use only provider outputs or user-provided assets as raw visual sources." in producer
    assert "Do not create procedural, placeholder, or fallback images" in producer
    assert "leave affected manifest entries unwritten" in producer


def test_production_unit_docs_are_first_entry_points():
    skill = _read("skills/core/gm-asset/SKILL.md")
    planner = _read("skills/core/gm-asset/references/asset-planner.md")
    runtime = _read("skills/core/gm-asset/references/asset-runtime-pipeline.md")

    units = [
        "screen-reference",
        "character-bundle",
        "fx-bundle",
        "ui-kit",
        "card-kit",
        "compact-prop-pack",
        "background-map",
        "platform-strip",
        "scene-prop-set",
    ]
    for unit in units:
        path = f"skills/core/gm-asset/references/production-units/{unit}.md"
        assert (REPO_ROOT / path).exists(), f"missing production unit: {unit}"
        assert f"references/production-units/{unit}.md" in skill
        assert f"`{unit}`" in planner

    assert "## Production Shapes" in runtime
    assert "## Processing Status" in runtime
    assert "## Extraction Status" in runtime
    assert "## Curation Field" in runtime


def test_ui_and_prop_units_default_to_autoslice():
    ui = _read("skills/core/gm-asset/references/production-units/ui-kit.md")
    card = _read("skills/core/gm-asset/references/production-units/card-kit.md")
    props = _read("skills/core/gm-asset/references/production-units/compact-prop-pack.md")
    curation = _read("skills/core/gm-asset/references/asset-curation.md")

    assert "--snap-mode autoslice" in ui
    assert "--snap-mode autoslice" in card
    assert "--snap-mode autoslice" in props
    assert "--snap-mode grid" in ui
    assert "--snap-mode grid" in card
    assert "--snap-mode grid" in props
    assert "Use the assigned production-unit doc for extraction" in curation


def test_card_kit_is_separate_from_generic_ui_components():
    planner = _read("skills/core/gm-asset/references/asset-planner.md")
    ui = _read("skills/core/gm-asset/references/production-units/ui-kit.md")
    card = _read("skills/core/gm-asset/references/production-units/card-kit.md")

    assert "| `card-kit` | `references/production-units/card-kit.md` |" in planner
    assert "| `card_frame_source` | `card-kit` |" in planner
    assert "| `portrait_frame_source` | `card-kit` |" in planner
    assert "Do not use this unit for card frames" in ui
    assert "no card frame or portrait-frame layout" in ui
    assert "card-game-specific visual assets" in card
    assert "empty portrait windows and card art windows" in card


def test_foreground_production_units_do_not_finalize_source_images():
    fx = _read("skills/core/gm-asset/references/production-units/fx-bundle.md")
    ui = _read("skills/core/gm-asset/references/production-units/ui-kit.md")
    props = _read("skills/core/gm-asset/references/production-units/compact-prop-pack.md")
    scene_props = _read("skills/core/gm-asset/references/production-units/scene-prop-set.md")
    platform = _read("skills/core/gm-asset/references/production-units/platform-strip.md")
    character = _read("skills/core/gm-asset/references/production-units/character-bundle.md")

    foreground_docs = [fx, ui, props, scene_props]
    for doc in foreground_docs:
        assert "--background magenta" in doc
        assert "--snap-mode autoslice" in doc
        assert "Do not use a source" in doc
        assert "asset_image_finalize.py" not in doc

    assert "tools/asset_curation_select.py" in fx
    assert "tools/asset_curation_select.py" in ui
    assert "tools/asset_curation_select.py" in props
    assert "tools/asset_curation_select.py" in scene_props
    assert "runtime_artifact: region_atlas" in ui
    assert "qc.atlas_metadata.metadata_path" in ui
    assert "runtime_artifact: single" in fx
    assert "runtime_artifact: grid_sheet" in fx
    assert "--snap-mode grid" in platform
    assert "--background magenta" in platform
    assert "runtime_artifact: region_atlas" in platform
    assert "tools/asset_action_process.py" in character
    assert "runtime_artifact: grid_sheet" in character


def test_character_canonical_uses_magenta_finalize():
    character = _read("skills/core/gm-asset/references/production-units/character-bundle.md")

    assert "tools/asset_image_finalize.py" in character
    assert "--background magenta" in character


def test_single_image_units_keep_finalize_path():
    screen = _read("skills/core/gm-asset/references/production-units/screen-reference.md")
    background = _read("skills/core/gm-asset/references/production-units/background-map.md")

    assert "tools/asset_image_finalize.py" in screen
    assert "--require-aspect" in screen
    assert "tools/asset_image_finalize.py" in background
    assert "--require-aspect" in background


def test_asset_planner_routes_foreground_sprites_to_extraction_units():
    planner = _read("skills/core/gm-asset/references/asset-planner.md")

    assert "| `runtime_sprite` | `compact-prop-pack` |" in planner
    assert "foreground gameplay sprite with effect behavior" in planner
    assert "uncut single-image foreground sprites" in planner


def test_runtime_pipeline_documents_runtime_ready_gate():
    runtime = _read("skills/core/gm-asset/references/asset-runtime-pipeline.md")

    assert "## Runtime Artifact Types" in runtime
    assert "## Runtime Ready Gate" in runtime
    assert "`projectile_fx_source`" in runtime
    assert "`ui_component_sheet`" in runtime
    assert "`card_component_sheet`" in runtime
    assert "`card_frame_source`" in runtime
    assert "`portrait_frame_source`" in runtime
    assert "`runtime_sprite`" in runtime
    assert "`region_atlas`" in runtime
    assert "`grid_sheet`" in runtime
    assert "qc.atlas_metadata.metadata_path" in runtime
    assert "\"rect\": [0, 0, 256, 96]" in runtime


def test_asset_stage_runs_manifest_gate_before_assets_update():
    skill = _read("skills/core/gm-asset/SKILL.md")
    producer = _read("agents/asset-producer.md")
    runtime = _read("skills/core/gm-asset/references/asset-runtime-pipeline.md")

    assert "Confirm every ready manifest entry contains `runtime_artifact`." in skill
    assert "python tools/asset_generation_manifest_update.py --entry-file <entry.json>" in skill
    assert "python tools/asset_generation_manifest_check.py --check-files" in skill
    assert "Update the matching ASSETS.md rows only after manifest validation passes" in skill
    assert "runtime_artifact" in skill
    assert "Validate manifest entry content and referenced files." in producer
    assert "Do not switch providers." in producer
    assert "Configured Provider:" in producer
    assert "Used Provider:" in producer
    assert "manager upserts entries and" in runtime


def test_build_and_fixgap_handoff_runtime_assets_to_workers():
    build = _read("skills/core/gm-build/SKILL.md")
    fixgap = _read("skills/core/gm-fixgap/SKILL.md")
    worker_dispatch = _read("skills/core/_shared/worker-dispatch.md")
    worker = _read("agents/worker.md")

    for doc in (build, fixgap):
        assert "`ASSETS.md` and `assets/manifest.json`" in doc
        assert "Asset Runtime Snapshot" in doc

    assert "### Asset Runtime Snapshot" in worker_dispatch
    assert "Use final runtime assets only." in worker_dispatch
    assert "`grid_sheet` or `region_atlas`" in worker_dispatch
    assert "Do not use `.godotmaker/asset-generation/sources/`" in worker_dispatch
    assert "## Runtime Asset Rules" in worker
    assert "For `grid_sheet`, read the listed action metadata JSON" in worker
    assert "For `region_atlas`, read the listed atlas metadata JSON" in worker


def test_reviewer_checks_runtime_asset_usage_and_evaluate_uses_scene_contract():
    reviewer_dispatch = _read("skills/core/_shared/reviewer-dispatch.md")
    reviewer = _read("agents/reviewer.md")
    evaluate = _read("skills/core/gm-evaluate/SKILL.md")

    assert "### Asset Runtime Snapshot" in reviewer_dispatch
    assert "**Review runtime asset usage.**" in reviewer
    assert "### Asset Usage Review" in reviewer
    assert "No generation source or curation candidate is used at runtime" in reviewer
    assert "`visual-qa` skill in Question mode" in evaluate
    assert "Do not compare screenshots against" in evaluate
    assert "--question \"Does this screenshot satisfy the scene contract?" in evaluate
    assert "`assets/manifest.json` — runtime asset handoff manifest" not in evaluate
    assert "**Runtime asset preflight.**" not in evaluate
    assert '"reference": "references/scene_<name>.png"' not in evaluate
