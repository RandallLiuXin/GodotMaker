import re
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


# The nine production units `/gm-asset` can plan. `tileset` ships as a
# first-class Skill but has no manager routing yet.
MANAGER_FAMILIES = (
    "screen-reference",
    "character-bundle",
    "fx-bundle",
    "ui-kit",
    "card-kit",
    "compact-prop-pack",
    "background-map",
    "platform-strip",
    "scene-prop-set",
)


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def _flat(text: str) -> str:
    """Collapse wrapped prose so a contract sentence matches across line breaks."""
    return " ".join(text.split())


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
    assert ".godotmaker/asset-runtime/tools/codex_image_claim.py --plan" in codex
    assert "active coding-agent runtime's native image-generation path" in native
    assert "tools/asset_source_generate.py --spec" in gemini
    assert "generated-path claim protocol" in codex_runtime
    assert "generated-path claim protocol" in claude_runtime
    assert "--out-report" in codex_runtime
    assert "--out-report" in claude_runtime

    forbidden = [
        "ImageGenerationEnd.saved_path",
        ".godotmaker/asset-runtime/tools/codex_image_claim.py --plan",
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


def test_first_class_asset_skills_are_the_only_entry_points():
    """No production unit keeps a second authoritative execution document.

    The `production-units/` tree is gone, not merely unreferenced: while a file
    sits under a directory a runtime agent can read, a producer can still land on
    it as a fallback contract and diverge from the family's real Skill.
    """
    skill = _read("skills/core/gm-asset/SKILL.md")
    planner = _read("skills/core/gm-asset/references/asset-planner.md")
    runtime = _read("skills/core/gm-asset/references/asset-runtime-pipeline.md")

    unit_dir = REPO_ROOT / "skills/core/gm-asset/references/production-units"
    assert not unit_dir.exists(), "the retired production-unit tree came back"

    compact = _read("skills/assets/compact-prop-pack/SKILL.md")
    assert "one provider source sheet" in compact
    for family in MANAGER_FAMILIES:
        assert (REPO_ROOT / f"skills/assets/{family}/SKILL.md").is_file()
        assert f"First-class `{family}` Asset Skill" in skill
        assert f"| `{family}` | First-class `{family}` Asset Skill |" in planner
        for doc in (skill, planner, runtime):
            assert f"references/production-units/{family}.md" not in doc

    assert "## Production Families" in runtime
    assert "## Source Layouts" in runtime
    assert "## Processing Status" in runtime
    assert "## Curation" in runtime


def test_autoslice_contracts_never_pair_with_an_explicit_grid():
    """Autoslice discovers regions; a grid would bucket them back together."""
    forbids_grid = re.compile(r"(?:[Dd]o not (?:supply|pass)|never pass) `--grid` to autoslice")
    for family in ("fx-bundle", "scene-prop-set", "compact-prop-pack"):
        doc = _read(f"skills/assets/{family}/SKILL.md")
        assert "--snap-mode autoslice" in doc
        assert forbids_grid.search(_flat(doc)), (
            f"{family}/SKILL.md does not forbid --grid with autoslice"
        )
        # Fenced blocks alternate with prose, so only the odd chunks are code.
        # Prose legitimately names `--grid` while forbidding it.
        for block in doc.split("```")[1::2]:
            if "tools/asset_sheet_process.py" not in block:
                continue
            if "--snap-mode autoslice" not in block:
                continue
            assert "--grid" not in block, (
                f"{family}/SKILL.md autoslice example still passes --grid"
            )


def test_prop_units_default_to_autoslice_while_ui_and_card_use_native_resources():
    props = _read("skills/assets/compact-prop-pack/SKILL.md")
    curation = _read("skills/core/gm-asset/references/asset-curation.md")
    ui = _read("skills/assets/ui-kit/SKILL.md")
    card = _read("skills/assets/card-kit/SKILL.md")

    assert "--snap-mode autoslice" in props
    assert "--processed-out" in props
    assert "asset_image_finalize.py --resize" in props
    assert "asset_atlas_assemble.py" in props
    assert "StyleBoxTexture" in ui
    assert "AtlasTexture" in ui
    assert "StyleBoxTexture" in card
    assert "AtlasTexture" in card
    assert "Use the assigned first-class Asset Skill for extraction" in curation


def test_card_kit_is_separate_from_generic_ui_components():
    planner = _read("skills/core/gm-asset/references/asset-planner.md")
    ui = _read("skills/assets/ui-kit/SKILL.md")
    card = _read("skills/assets/card-kit/SKILL.md")

    assert "| `card-kit` | First-class `card-kit` Asset Skill |" in planner
    assert "| `card_frame_source` | `card-kit` |" in planner
    assert "| `portrait_frame_source` | `card-kit` |" in planner
    assert "Do not use it for card frames" in ui
    assert "portrait frames" in ui
    assert "card-game-specific UI" in card
    assert "Keep card-art and portrait windows empty" in card


def test_foreground_families_extract_before_they_publish_a_final_asset():
    """A foreground family must cut its source, never publish the sheet itself."""
    fx = _read("skills/assets/fx-bundle/SKILL.md")
    props = _read("skills/assets/compact-prop-pack/SKILL.md")
    scene_props = _read("skills/assets/scene-prop-set/SKILL.md")
    character = _read("skills/assets/character-bundle/SKILL.md")

    # FX keeps the magenta source contract, the autoslice-then-curate static
    # route, and the explicit-grid animated route as two separate paths.
    assert "#FF00FF" in fx
    assert "--snap-mode autoslice" in fx
    assert "Animation never uses autoslice" in _flat(fx)
    assert "do not let autoslice split one effect into unrelated runtime assets" in _flat(fx)

    assert "tools/asset_curation_select.py" in fx
    assert "tools/asset_curation_select.py" in props
    assert "tools/asset_curation_select.py" in scene_props
    assert "asset_image_finalize.py" in scene_props
    assert "one image-generation attempt for the complete set" in scene_props
    assert "Do not pass `--grid` to autoslice" in scene_props
    assert "asset_image_finalize.py" in props
    assert "asset_compact_prop_pack_entry_draft.py" in props
    assert "tools/asset_curation_entry_draft.py" in fx
    assert "tools/asset_action_entry_draft.py" in fx
    assert "tools/asset_action_process.py" in character
    assert "tools/asset_action_entry_draft.py" in character
    assert "source_layout: grid_sheet" in character


def test_character_canonical_uses_magenta_finalize():
    character = _read("skills/assets/character-bundle/SKILL.md")

    assert "tools/asset_image_finalize.py" in character
    assert "--background magenta" in character


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
    """Normal handoff: the resolver output travels from manager to worker.

    The manager's only job is to run `asset_runtime_resolver.py` per asset and
    paste the result; the worker's only job is to load the artifact it names.
    """
    build = _read("skills/core/gm-build/SKILL.md")
    fixgap = _read("skills/core/gm-fixgap/SKILL.md")
    worker_dispatch = _read("skills/core/_shared/worker-dispatch.md")
    worker = _read("agents/worker.md")

    for doc in (build, fixgap):
        assert "`ASSETS.md` and `.godotmaker/asset-generation/manifest.json`" in doc
        assert "Asset Runtime Snapshot" in doc
        assert "tools/asset_runtime_resolver.py" in doc
        assert "pasted verbatim" in _flat(doc)

    assert "### Asset Runtime Snapshot" in worker_dispatch
    assert "tools/asset_runtime_resolver.py --project-root . --assets-md ASSETS.md" in worker_dispatch
    assert "The resolver output IS this section." in worker_dispatch
    assert "Do not use `.godotmaker/asset-generation/sources/`" in worker_dispatch
    # Generated-asset runtime handoff reads the generated manifest, never the
    # analyst's user-provided-asset classification manifest.
    assert ".godotmaker/asset-generation/manifest.json" in worker_dispatch
    assert ".godotmaker/asset-generation/manifest.json" in worker
    assert "## Runtime Asset Rules" in worker
    assert "tools/asset_runtime_resolver.py" in worker

    # The worker binds the compiled resource; animation and FX lifecycle stay
    # runtime behavior, they just come out of `SpriteFrames` now.
    assert "bind it as that type" in worker
    assert "wire animation playback from that resource" in worker_dispatch
    assert "`SpriteFrames` artifact" in worker_dispatch
    assert "temporary animated FX" in worker_dispatch
    assert "`AnimatedSprite2D.sprite_frames`" in worker
    assert "do not reduce a multi-frame actor or FX to one static frame" in _flat(worker)
    assert "effect lifecycle" in worker


def test_manager_never_copies_stable_entry_fields_into_a_brief():
    """A hand-copied field is how a rebuild instruction gets back into a brief.

    The v1 snapshot is exactly asset_id / production_family / source_layout /
    godot_artifact. The moment a manager re-adds frame counts, region rects, or
    support-metadata paths, the worker has everything it needs to reconstruct
    the resource — and will, instead of loading the compiled one.
    """
    worker_dispatch = _flat(_read("skills/core/_shared/worker-dispatch.md"))
    runtime = _flat(_read("skills/core/gm-asset/references/asset-runtime-pipeline.md"))

    prohibition = (
        "do not enrich the snapshot with target size, frame_count, fps, loop, "
        "frame paths, region names, region rects, or support metadata paths"
    )
    assert "Do not copy fields out of a stable entry, the root index, or an ASSETS.md row by hand" in worker_dispatch
    assert prohibition in worker_dispatch
    assert "**The resolver owns the snapshot.**" in worker_dispatch
    assert "never widen the four-field contract" in worker_dispatch
    assert "they do not copy entry fields by hand" in runtime

    # The retired enrichment instructions must not come back. Scan with the
    # prohibition itself removed — it necessarily names the fields it forbids.
    remainder = worker_dispatch.replace(prohibition, "")
    for token in (
        "Support metadata is always",
        "atlas metadata path",
        "action metadata path",
        "frame_paths",
        "frame_count",
    ):
        assert token not in remainder, (
            f"worker-dispatch.md re-introduced hand-copied snapshot data: {token}"
        )


def test_worker_binds_the_compiled_artifact_instead_of_rebuilding_it():
    """`source_layout` is provenance. Rebuilding from it discards L0-L4.

    Every compiled type is named explicitly: a rule that only forbids rebuilding
    `SpriteFrames` still lets a worker hand-assemble a `Theme` or re-slice an
    atlas.
    """
    worker = _read("agents/worker.md")
    worker_dispatch = _read("skills/core/_shared/worker-dispatch.md")

    assert "**Bind the artifact, do not rebuild it.**" in worker
    assert "**Bind the artifact, do not rebuild it.**" in worker_dispatch
    for doc in (worker, worker_dispatch):
        flat = _flat(doc)
        for artifact_type in (
            "SpriteFrames",
            "AtlasTexture",
            "StyleBoxTexture",
            "Theme",
            "TileSet",
        ):
            assert f"`{artifact_type}`" in flat, (
                f"{artifact_type} has no stated binding contract"
            )
        assert "from `source_layout`" in flat or "out of `source_layout.path`" in flat

    assert "it is not an input to your code" in _flat(worker)
    assert "re-slice, re-grid, or re-region" in worker
    # The compiled AtlasTexture already is one region — nothing to look up.
    assert "already exactly one region" in worker
    assert "`TileMapLayer.tile_set`" in worker


def test_a_missing_artifact_fails_closed_instead_of_reaching_a_worker():
    """No artifact means no visual dispatch — not an invented path.

    The resolver already refuses; these docs are what stops a manager from
    routing around the refusal and a worker from silently substituting art.
    """
    worker_dispatch = _flat(_read("skills/core/_shared/worker-dispatch.md"))
    worker = _read("agents/worker.md")
    build = _flat(_read("skills/core/gm-build/SKILL.md"))
    fixgap = _flat(_read("skills/core/gm-fixgap/SKILL.md"))

    assert "The resolver fails closed" in worker_dispatch
    assert "a missing source or artifact file" in worker_dispatch
    assert "do not dispatch a visual task against an invented path" in worker_dispatch
    assert "must go back through `/gm-asset` first" in worker_dispatch
    for doc in (build, fixgap):
        assert "report its `error` instead of dispatching the task against an invented path" in doc

    assert "report `PARTIAL` or `FAILED` with the missing path. Do not invent one." in _flat(worker)


def test_reference_only_assets_never_become_worker_runtime_assets():
    reference_docs = {
        "worker-dispatch.md": _flat(_read("skills/core/_shared/worker-dispatch.md")),
        "asset-runtime-pipeline.md": _flat(
            _read("skills/core/gm-asset/references/asset-runtime-pipeline.md")
        ),
    }

    assert "a reference-only asset never becomes a runtime asset" in reference_docs["worker-dispatch.md"]
    assert "a reference-only asset all exit non-zero" in reference_docs["worker-dispatch.md"]
    assert (
        "Reference-only entries are valid manifest records but never produce a worker runtime snapshot."
        in reference_docs["asset-runtime-pipeline.md"]
    )
    # ASSETS.md `reference` rows stay out of the visual contract too.
    assert (
        "or ASSETS.md rows whose type is `reference` as runtime assets"
        in reference_docs["worker-dispatch.md"]
    )


def test_no_deliverables_restriction_cancels_the_integration_repair_exception():
    """The autonomy grant is worthless if a nearby MUST NOT overrides it.

    File ownership and runtime asset repair live in the same prompt, so stating
    the exception once is not enough — an agent that reads only the generic
    "MUST NOT modify files outside Deliverables" stops and reports instead of
    repairing. Every place that states the restriction must carry the carve-out,
    which is a structural property no single text-presence assertion catches.
    """
    restriction = re.compile(r"modify (?:files|a file) (?:outside|not in) [^\n]*", re.IGNORECASE)
    sources = {
        "agents/worker.md": _read("agents/worker.md"),
        "skills/core/_shared/worker-dispatch.md": _read(
            "skills/core/_shared/worker-dispatch.md"
        ),
    }

    uncarved = []
    for name, text in sources.items():
        statements = [
            (index, line)
            for index, line in enumerate(text.splitlines(), start=1)
            if restriction.search(line)
        ]
        assert statements, f"{name} lost its file-ownership restriction entirely"
        for index, line in statements:
            if "exception" not in line.lower():
                uncarved.append(f"{name}:{index}: {line.strip()}")

    assert not uncarved, (
        "these Deliverables restrictions cancel the runtime asset integration "
        "repair exception: " + "; ".join(uncarved)
    )


def test_integration_repair_exception_is_explicit_narrow_and_wins():
    """The exception must beat the general rule, and stop right after it."""
    worker = _read("agents/worker.md")
    flat_worker = _flat(worker)
    flat_dispatch = _flat(_read("skills/core/_shared/worker-dispatch.md"))

    assert "### Exception: runtime asset integration repair" in worker
    # Precedence is stated, not left to the reader to infer from ordering.
    assert "One exception overrides the rule above, and nothing else does." in flat_worker
    assert "this exception is the narrower rule and it wins" in flat_worker
    assert "That exception overrides this line for those files only" in flat_dispatch
    # A brief must not be able to re-close the door the agent definition opened.
    assert (
        "Never write a `Scope Boundaries` or `Prohibited Actions` line that cancels this"
        in flat_dispatch
    )

    # Narrow: exactly the artifact plus the scene/script that binds it.
    assert "the `.tres` / `.res` artifact you were told to bind" in flat_worker
    assert "the project-local scene or script that binds it" in flat_worker

    # And bounded — an unbounded exception is just a repeal of file ownership.
    for excluded in (
        "images, or any art you would have to produce yourself",
        "`.godotmaker/asset-generation/` entries, the root index, or `sources/`",
        "unrelated files, refactors, or improvements",
    ):
        assert excluded in flat_worker, f"the exception lost a boundary: {excluded}"
    for protected in ("PLAN.md", "STRUCTURE.md", "SCENES.md", "GAP.md", "ASSETS.md", "e2e/"):
        assert protected in flat_worker.split("It never covers:", 1)[1].split("List every file", 1)[0], (
            f"{protected} dropped out of the exception's exclusion list"
        )

    # The only obligation stays a report line.
    assert "List every file you touched under this exception in your report's Notes." in flat_worker
    assert "no repair record, no revalidation pass, no new skill" in flat_worker


def test_worker_repairs_integration_without_absorbing_art_production():
    """Two boundaries in one place, because they fail in opposite directions.

    Too tight and a worker stalls on a project-integration problem it could fix;
    too loose and it starts drawing replacement art, which silently moves image
    production out of `/gm-asset` and out of L0-L4.
    """
    worker = _read("agents/worker.md")
    worker_dispatch = _read("skills/core/_shared/worker-dispatch.md")
    flat_worker = _flat(worker)
    flat_dispatch = _flat(worker_dispatch)

    # Autonomy: the worker owns project-local Godot resources, scenes, scripts.
    assert "**Integration repair is yours.**" in worker
    assert "edit or replace a project-local Godot resource, scene, or script" in flat_worker
    assert "including a generated `.tres`" in flat_worker
    assert "**Workers keep integration autonomy.**" in worker_dispatch
    assert (
        "may edit or replace a project-local Godot resource, scene, or script"
        in flat_dispatch
    )

    # No repair bureaucracy: no record, no revalidation pass, no worker-authored skill.
    assert "No repair record, revalidation pass, or new skill is required of you." in flat_worker
    assert "Do not demand a repair record, a revalidation pass, or a worker-authored skill" in flat_dispatch

    # But art production stays with /gm-asset on both sides of the handoff.
    assert "**Art production is never yours.**" in worker
    assert "do not run an asset-generation skill or tool to fill a gap" in flat_worker
    assert "That responsibility stays with `/gm-asset`." in flat_worker
    assert "What stays off-limits is producing the art itself." in flat_dispatch
    assert (
        "never ask a worker to generate, draw, or synthesize art as part of runtime integration"
        in flat_dispatch
    )


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


def test_only_a_passing_l0_l4_result_reaches_a_ready_entry():
    """`ready` is the worker-consumable state, so nothing may shortcut into it.

    The two animated-bundle families compile before they can be validated, so
    their builder drafts `compiled` and the same builder promotes it once the
    L0-L4 evidence comes back. A family that already holds a passing result when
    it drafts writes `ready` outright. No doc may offer a third route.
    """
    runtime = _read("skills/core/gm-asset/references/asset-runtime-pipeline.md")
    character = _read("skills/assets/character-bundle/SKILL.md")
    fx = _read("skills/assets/fx-bundle/SKILL.md")

    assert "Nothing else may write `ready`." in runtime
    assert "drafts `compiled` and promotes the same" in _flat(runtime)
    for doc in (character, fx):
        assert "processing_status: compiled" in doc
        assert "L0-L4" in doc
    assert "--result <result.json>" in character
    assert "Do not hand-edit `processing_status`." in character


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
        # Reference-only production needs a builder too, or Step 5's
        # "no hand-written drafts" rule would leave screen-reference with no
        # executable registration path at all.
        assert "tools/asset_finalize_entry_draft.py" in doc
    assert "reject a hand-written draft" in skill
    assert "do not hand-write a draft or its support metadata" in runtime


def test_every_planned_family_routes_through_a_draft_builder():
    """No planned family may be left without an executable registration path.

    Step 5 rejects a hand-written draft, so a family the manager can plan but
    whose registration reference names no builder would have no legal way to
    register at all. With the production-unit tree gone, the pipeline reference
    is where that mapping lives.
    """
    runtime = _read("skills/core/gm-asset/references/asset-runtime-pipeline.md")
    section = _flat(runtime.split("## Registration Commands", 1)[1].split("\n## ", 1)[0])
    assert section, "the registration command reference disappeared"

    for builder in (
        "asset_action_entry_draft.py",
        "asset_curation_entry_draft.py",
        "asset_finalize_entry_draft.py",
        "asset_compact_prop_pack_entry_draft.py",
        "asset_scene_prop_set_entry_draft.py",
    ):
        assert builder in section, f"{builder} lost its documented registration path"

    missing = [family for family in MANAGER_FAMILIES if f"`{family}`" not in section]
    assert not missing, (
        "these planned families have no deterministic draft builder: "
        + ", ".join(missing)
    )


def test_gm_asset_registers_through_the_stable_entry_tools_only():
    skill = _read("skills/core/gm-asset/SKILL.md")
    runtime = _read("skills/core/gm-asset/references/asset-runtime-pipeline.md")

    for doc in (skill, runtime):
        assert "tools/asset_stable_entry.py" in doc
        assert "tools/asset_generation_index.py" in doc
    assert ".godotmaker/asset-generation/entries/<tag>/<asset_id>.json" in skill
    # No hand-edit escape hatch around the gates.
    assert "Do not hand-edit" in skill


def test_runtime_resolver_is_documented_as_a_registered_assets_reader():
    runtime = _read("skills/core/gm-asset/references/asset-runtime-pipeline.md")
    tools = _read("docs/wiki/05-tools/asset-tools.md")
    tools_zh = _read("docs/zh/wiki/05-tools/asset-tools.md")
    guide = _read("docs/wiki/07-contributing/codebase-guide.md")
    guide_zh = _read("docs/zh/wiki/07-contributing/codebase-guide.md")

    assert "## Runtime Snapshot Resolution" in runtime
    assert "tools/asset_runtime_resolver.py" in runtime
    assert "root-index" in runtime
    assert "registration" in runtime
    assert "Both modes require" in runtime
    for doc in (tools, tools_zh, guide, guide_zh):
        assert "asset_runtime_resolver.py" in doc


def test_region_atlas_single_region_contract():
    """Whole-atlas misuse stays a finding after the artifact handoff change.

    The worker no longer looks a region up by name — its `AtlasTexture` already
    is the region (see the artifact-binding test). What must survive is the
    review side: substituting the physical atlas for a single element is still
    caught.
    """
    worker = _read("agents/worker.md")
    reviewer_dispatch = _read("skills/core/_shared/reviewer-dispatch.md")
    reviewer = _read("agents/reviewer.md")
    evaluate = _read("skills/core/gm-evaluate/SKILL.md")

    # The worker binds the compiled region and never falls back to the sheet.
    assert "never substitute the physical atlas image behind" in _flat(worker)
    assert "the element-to-region match is not obvious" in reviewer_dispatch

    # Reviewer flags whole-atlas misuse as an issue.
    assert "Region atlases bind single named regions instead of the whole atlas image" in reviewer
    assert "Whole-atlas misuse is" in reviewer

    # Evaluate covers whole-image-as-atlas/sub-image misuse via the VQA question.
    assert "**Atlas misuse check.**" in evaluate
    assert "the whole atlas or sheet." in evaluate
    assert "is a `critical_issue`" in evaluate
