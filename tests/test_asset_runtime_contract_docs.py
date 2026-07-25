from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

# The only modules allowed to name the retired schema, and only to reject it.
LEGACY_REJECTION_TOOLS = {
    "asset_stable_entry.py",
    "asset_generation_index.py",
    "asset_skill_contract_check.py",
}

# Tools retired with the v1 switch. No active caller may name them again.
RETIRED_TOOLS = (
    "asset_generation_manifest_update.py",
    "asset_generation_manifest_check.py",
    "asset_action_manifest_entry.py",
    "asset_curation_manifest_entry.py",
)


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def _collect(roots) -> list[Path]:
    """Collect every file under `roots`, failing loudly on an empty scan."""
    found: list[Path] = []
    for root, patterns in roots:
        directory = REPO_ROOT / root
        assert directory.is_dir(), f"scan root disappeared: {root}"
        before = len(found)
        for pattern in patterns:
            found.extend(directory.glob(pattern))
        assert len(found) > before, f"scan root matched nothing: {root}"
    return found


def _active_contract_files() -> list[Path]:
    """Every active skill, reference, agent, template, and tool file."""
    return _collect(
        (
            ("skills", ("**/*.md", "**/*.json")),
            ("agents", ("**/*.md",)),
            ("templates", ("**/*.md",)),
            ("tools", ("**/*.py",)),
        )
    )


def _all_shipped_files() -> list[Path]:
    """Everything an active caller could live in, including docs and runtimes."""
    return _active_contract_files() + _collect(
        (
            ("docs", ("**/*.md",)),
            ("agent-runtimes", ("**/*.md", "**/*.json")),
            ("hooks", ("**/*.py",)),
            ("config", ("**/*.json", "**/*.yaml", "**/*.default")),
            ("migrations", ("**/*.py",)),
        )
    )


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
    assert "leave affected stable entry drafts unwritten" in producer


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

    assert "## Production Families" in runtime
    assert "## Source Layouts" in runtime
    assert "## Processing Status" in runtime
    assert "## Curation" in runtime


def test_production_unit_sheet_process_examples_pass_grid():
    units = [
        "ui-kit",
        "card-kit",
        "compact-prop-pack",
        "fx-bundle",
        "scene-prop-set",
        "platform-strip",
    ]
    for unit in units:
        doc = _read(f"skills/core/gm-asset/references/production-units/{unit}.md")
        for block in doc.split("```"):
            if "python tools/asset_sheet_process.py" not in block:
                continue
            assert "--grid" in block, (
                f"{unit}.md asset_sheet_process example is missing --grid"
            )


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
    assert "--source-layout region_atlas" in ui
    assert "tools/asset_curation_entry_draft.py" in fx
    assert "tools/asset_action_entry_draft.py" in fx
    assert "--snap-mode grid" in platform
    assert "--background magenta" in platform
    assert "--source-layout region_atlas" in platform
    assert "tools/asset_action_process.py" in character
    assert "tools/asset_action_entry_draft.py" in character
    assert "source_layout.type: grid_sheet" in character


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


def test_runtime_pipeline_documents_stable_entry_contract():
    runtime = _read("skills/core/gm-asset/references/asset-runtime-pipeline.md")

    assert "## Stable Entry Contract" in runtime
    assert "## Root Index" in runtime
    assert "## Runtime Ready Gate" in runtime
    assert "`production_family`" in runtime
    assert "`source_layout`" in runtime
    assert "`godot_artifact`" in runtime
    assert "`processing_status`" in runtime
    assert "`region_atlas`" in runtime
    assert "`grid_sheet`" in runtime
    assert ".godotmaker/asset-generation/entries/<tag>/<asset_id>.json" in runtime
    assert "assets/generated/<production_family>/<asset_id>/" in runtime
    assert "\"rect\": [0, 0, 256, 96]" in runtime

    # The root index is pointer-only: identity plus one entry_path, never a body.
    assert '"entry_path"' in runtime
    assert "never duplicates an entry body" in runtime


def test_asset_stage_runs_stable_entry_gate_before_assets_update():
    skill = _read("skills/core/gm-asset/SKILL.md")
    producer = _read("agents/asset-producer.md")
    runtime = _read("skills/core/gm-asset/references/asset-runtime-pipeline.md")

    assert "python tools/asset_stable_entry.py <entry_draft.json> --project-root . --write --check-files" in skill
    assert "python tools/asset_assets_md_update.py" in skill
    assert "Update the matching ASSETS.md rows only after the root-index gate passes" in skill

    # The documented gate must be the file-checking one. `--check-entries` alone
    # is schema-only and would pass on an asset deleted after registration.
    for doc in (skill, runtime):
        assert (
            "python tools/asset_generation_index.py --project-root . --check-entries --check-files"
            in doc
        )
        assert "--check-entries\n```" not in doc
    assert "Validate stable entry content and referenced files." in producer
    assert "Do not switch providers." in producer
    assert "Configured Provider:" in producer
    assert "Used Provider:" in producer
    assert "runs the root-index gate before updating ASSETS.md" in runtime


def test_build_and_fixgap_handoff_runtime_assets_to_workers():
    build = _read("skills/core/gm-build/SKILL.md")
    fixgap = _read("skills/core/gm-fixgap/SKILL.md")
    worker_dispatch = _read("skills/core/_shared/worker-dispatch.md")
    worker = _read("agents/worker.md")

    for doc in (build, fixgap):
        assert "`ASSETS.md` and `.godotmaker/asset-generation/manifest.json`" in doc
        assert "Asset Runtime Snapshot" in doc

    assert "### Asset Runtime Snapshot" in worker_dispatch
    assert "Use `ready` stable entries only" in worker_dispatch
    assert "`grid_sheet` or `region_atlas`" in worker_dispatch
    assert "Do not use `.godotmaker/asset-generation/sources/`" in worker_dispatch
    # Generated-asset runtime handoff reads the generated manifest, never the
    # analyst's user-provided-asset classification manifest.
    assert ".godotmaker/asset-generation/manifest.json" in worker_dispatch
    assert ".godotmaker/asset-generation/manifest.json" in worker
    assert "## Runtime Asset Rules" in worker
    assert "For `grid_sheet`, read the listed action metadata JSON" in worker
    assert "For `region_atlas`, read the listed atlas metadata JSON" in worker
    assert "wire animation playback from metadata" in worker_dispatch
    assert "frame_count > 1" in worker_dispatch
    assert "temporary animated FX" in worker_dispatch
    assert "do not use the sheet as a static" in worker
    assert "do not use only the first frame" in worker
    assert "effect lifecycle" in worker


def test_reviewer_checks_runtime_asset_usage_and_evaluate_uses_scene_contract():
    reviewer_dispatch = _read("skills/core/_shared/reviewer-dispatch.md")
    reviewer = _read("agents/reviewer.md")
    evaluate = _read("skills/core/gm-evaluate/SKILL.md")
    animation_skill = _read("skills/reviewer/animation/SKILL.md")
    animation_checklist = _read("skills/reviewer/animation/checklist.md")

    assert "### Asset Runtime Snapshot" in reviewer_dispatch
    assert "frame_count" in reviewer_dispatch
    assert "expected runtime animation behavior" in reviewer_dispatch
    assert "temporary-FX teardown requirement" in reviewer_dispatch
    assert "**Review runtime asset usage.**" in reviewer
    assert "### Asset Usage Review" in reviewer
    assert "No generation source or curation candidate is used at runtime" in reviewer
    assert "Missing expected animation is itself a review issue" in reviewer
    assert "Multi-frame grid sheets are animated" in reviewer
    assert "Temporary animated FX clear after playback" in reviewer
    assert "omitted" in animation_skill
    assert "expected animation is a finding" in animation_skill
    assert "Expected multi-frame animation missing" in animation_checklist
    assert "Static sheet or first-frame collapse" in animation_checklist
    assert "Temporary animated FX lifecycle" in animation_checklist
    assert "`visual-qa` skill in Question mode" in evaluate
    assert "Do not compare screenshots against" in evaluate
    assert "--question \"Does this screenshot satisfy the scene contract?" in evaluate
    assert "`assets/manifest.json` — runtime asset handoff manifest" not in evaluate
    assert "**Runtime asset preflight.**" not in evaluate
    assert '"reference": "references/scene_<name>.png"' not in evaluate


def test_gdd_templates_do_not_add_weak_dynamic_visual_checks():
    decomposer = _read("agents/decomposer.md")
    plan = _read("templates/PLAN.md")
    scenes = _read("templates/SCENES.md")

    assert "Do not reduce animation work" not in decomposer
    assert "expected disappearance or clear condition" not in decomposer
    assert "frame sequence / dynamic evidence" not in plan
    assert "Multi-frame actor and FX assets play as animation" not in plan
    assert "animation/lifecycle" not in scenes
    assert "multi-frame actors/FX" not in scenes
    assert "dynamic-mode test" not in scenes


def test_generated_and_analyst_manifests_have_distinct_responsibilities():
    """The two manifests must never be confused.

    `.godotmaker/asset-generation/manifest.json` is the pointer index into the
    generated-asset stable entries. It is the only runtime source read by
    gm-build / gm-fixgap / worker dispatch.

    `assets/manifest.json` holds the analyst's classification of user-provided
    assets and keeps that responsibility unchanged.
    """
    build = _read("skills/core/gm-build/SKILL.md")
    fixgap = _read("skills/core/gm-fixgap/SKILL.md")
    worker_dispatch = _read("skills/core/_shared/worker-dispatch.md")
    worker = _read("agents/worker.md")

    # Runtime handoff docs point at the generated manifest, not the analyst one.
    runtime_docs = {
        "gm-build/SKILL.md": build,
        "gm-fixgap/SKILL.md": fixgap,
        "worker-dispatch.md": worker_dispatch,
        "worker.md": worker,
    }
    for name, doc in runtime_docs.items():
        assert (
            ".godotmaker/asset-generation/manifest.json" in doc
        ), f"{name} must read generated runtime data from the generated manifest"

    # Regression guard: runtime handoff docs must not name the analyst's
    # user-asset manifest (`assets/manifest.json`) as a runtime source.
    for name, doc in runtime_docs.items():
        assert "assets/manifest.json" not in doc, (
            f"{name} must not name the analyst manifest as a runtime source"
        )

    # The analyst manifest keeps its distinct user-asset classification role.
    analyst = _read("agents/analyst.md")
    analyst_dispatch = _read("skills/core/_shared/analyst-dispatch.md")
    assert "assets/manifest.json" in analyst
    assert "user-provided" in analyst_dispatch or "user-provided" in analyst
    assert "assets/manifest.json" in analyst_dispatch


def test_no_active_surface_requires_the_retired_runtime_artifact_contract():
    """Gate 1: one schema owns the generated-asset manifest, not two.

    `runtime_artifact` may survive only inside a legacy-rejection module, never
    as a field an active skill, reference, agent, template, or tool asks a
    producer to write.
    """
    offenders = []
    for path in _active_contract_files():
        text = path.read_text(encoding="utf-8")
        if "runtime_artifact" not in text:
            continue
        if path.suffix == ".py" and path.name in LEGACY_REJECTION_TOOLS:
            continue
        offenders.append(str(path.relative_to(REPO_ROOT)).replace("\\", "/"))

    assert not offenders, (
        "these active files still name the retired runtime_artifact contract: "
        + ", ".join(sorted(offenders))
    )


def test_retired_manifest_tools_have_no_active_callers():
    """The old full-entry manifest tools are gone, including every reference."""
    for name in RETIRED_TOOLS:
        assert not (REPO_ROOT / "tools" / name).exists(), f"{name} was not removed"

    offenders = []
    for path in _all_shipped_files():
        text = path.read_text(encoding="utf-8")
        if any(name in text for name in RETIRED_TOOLS):
            offenders.append(str(path.relative_to(REPO_ROOT)).replace("\\", "/"))

    assert not offenders, (
        "these active files still call a retired manifest tool: "
        + ", ".join(sorted(offenders))
    )


def test_no_doc_fakes_a_compiled_artifact_or_ready_state():
    """No native compiler and no L0-L4 runner exist, so nothing may claim them.

    Pointing `godot_artifact` at a source image would make a `grid_sheet` look
    like a compiled `SpriteFrames`, and a worker binding it would get a static
    image where an animation was promised. Guard the whole authoring surface, not
    just the file that happened to say it first.
    """
    offenders = []
    for path in _active_contract_files():
        text = path.read_text(encoding="utf-8")
        if path.suffix != ".md":
            continue
        for line in text.splitlines():
            lowered = line.lower()
            if "godot_artifact" not in lowered:
                continue
            # A doc may name the field, describe the compiler that will fill it,
            # or state that it stays absent — it may not instruct anyone to point
            # it at an image today.
            if "point `godot_artifact` at the finalized image" in lowered or (
                "texture2d" in lowered and "point `godot_artifact`" in lowered
            ):
                offenders.append(
                    f"{str(path.relative_to(REPO_ROOT))}: {line.strip()}"
                )

    assert not offenders, (
        "these docs tell a producer to fake a compiled artifact: "
        + "; ".join(sorted(offenders))
    )


def test_production_units_stop_at_source_ready():
    """Every production path must draft `source_ready`, never `ready`."""
    unit_dir = REPO_ROOT / "skills/core/gm-asset/references/production-units"
    units = sorted(unit_dir.glob("*.md"))
    assert units, "production-unit docs disappeared"

    for path in units:
        text = path.read_text(encoding="utf-8")
        name = path.name
        assert '"processing_status": "ready"' not in text, f"{name} drafts a ready entry"
        assert "processing_status: ready" not in text, f"{name} drafts a ready entry"


def test_entry_drafts_come_from_deterministic_builders():
    """Producers must not hand-write drafts or support metadata.

    The retired manifest builders carried mechanical checks — frame count,
    edge-touch, scale reference, curation selection. Those live in the v1 draft
    builders now; the skill must route through them rather than asking an agent
    to honour the rules in prose.
    """
    skill = _read("skills/core/gm-asset/SKILL.md")
    runtime = _read("skills/core/gm-asset/references/asset-runtime-pipeline.md")

    for doc in (skill, runtime):
        assert "tools/asset_action_entry_draft.py" in doc
        assert "tools/asset_curation_entry_draft.py" in doc
    assert "Reject a hand-written draft" in skill
    assert "Do not hand-write a draft or its support metadata" in runtime


def test_gm_asset_registers_through_the_stable_entry_tools_only():
    skill = _read("skills/core/gm-asset/SKILL.md")
    runtime = _read("skills/core/gm-asset/references/asset-runtime-pipeline.md")

    for doc in (skill, runtime):
        assert "tools/asset_stable_entry.py" in doc
        assert "tools/asset_generation_index.py" in doc
    assert ".godotmaker/asset-generation/entries/<tag>/<asset_id>.json" in skill
    # No hand-edit escape hatch around the gates.
    assert "Do not hand-edit" in skill


def test_region_atlas_single_region_contract():
    worker = _read("agents/worker.md")
    worker_dispatch = _read("skills/core/_shared/worker-dispatch.md")
    reviewer_dispatch = _read("skills/core/_shared/reviewer-dispatch.md")
    reviewer = _read("agents/reviewer.md")
    evaluate = _read("skills/core/gm-evaluate/SKILL.md")

    # Worker resolves the region by name from metadata, not the whole atlas image.
    assert "matching region by name from it" in worker
    assert "Use the region named in the brief when given" in worker
    assert "must reference its named region via `AtlasTexture`" in worker
    assert "Do not use a whole `region_atlas` or `grid_sheet` image as one visible sprite" in worker

    # Dispatch passes only the metadata path; region names come from metadata,
    # and the target region is named only when the match is not obvious.
    assert "bind each single-element node to its named region via AtlasTexture/region" in worker_dispatch
    assert "Region atlases are single regions." in worker_dispatch
    assert "the region and its rect from that metadata by name" in worker_dispatch
    assert "the element-to-region match is not obvious" in worker_dispatch
    assert "region names/count" not in worker_dispatch
    assert "the element-to-region match is not obvious" in reviewer_dispatch

    # Reviewer flags whole-atlas misuse as an issue.
    assert "Region atlases bind single named regions instead of the whole atlas image" in reviewer
    assert "Whole-atlas misuse is" in reviewer

    # Evaluate covers whole-image-as-atlas/sub-image misuse via the VQA question.
    assert "**Atlas misuse check.**" in evaluate
    assert "the whole atlas or sheet." in evaluate
    assert "is a `critical_issue`" in evaluate
