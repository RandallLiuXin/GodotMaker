---
name: card-kit
description: Produce reusable card art sources and native Godot card UI resources.
---

# Card Kit Asset

Use this Skill for reusable non-pixel-art, card-game-specific UI: card frames, portrait frames,
rarity frames, card/deck slots, resource badges, state overlays, card panels,
and card buttons. It produces art sources and native Godot resources, not card
rules, deck logic, a `Control` or `Container` layout, a `PackedScene`, readable text, or a full
composite screen. A request for pixel art is unsupported and must STOP.

## Invocation and Boundaries

Accept one request matching the shared Asset Skill request schema in
`.godotmaker/asset-runtime/schema/asset-skill-request.schema.json` with
`asset_type: "card-kit"`. First run
`python tools/asset_ui_card_contract_check.py <request.json> --kind request`.
The family contract owns the Theme recipe/variation, requested frame/state
pairs, and named atlas regions. The request decides which card resources are
needed; do not add a default front/back, portrait, rarity, or state bundle.
This card-game-specific UI Skill can be invoked directly or by an orchestrator
through `gm-asset`, but it never registers stable entries, edits `ASSETS.md`, tags, or
stage state, or writes generated
manifests. The producer adapter owns that later registration handoff.

`references` is optional. When it is non-empty, each path is binding input:

1. Verify that it is a readable image before generation.
2. Preserve its `canonical`, `style`, or `screen` role in the prompt and trace.
3. Attach its real image bytes through the declared provider path.
4. STOP if that provider cannot attach every required reference.

A prompt-only filename, silent omission, or provider substitution is not
reference use. Use only the requested provider (`native`, `codex`, `gemini`,
or `openai`). For Codex, call `image_gen` with the real
`referenced_image_paths` when any are present. Record provider, model identity
when exposed, coding model, reasoning, attachment paths/roles, and provider
call identity. For `openai` and `gemini`, use `tools/asset_source_generate.py`
with `reference_inputs`; it records hashes and attachment provenance.

## Production Loop

### 1. Plan and generate the visual source

Turn the brief into one concrete source plan: frame geometry/orientation,
empty portrait or card-art safe zones unless finished art is requested, rarity
language, state treatment, and only the requested component list. A reusable
card frame is not a flattened example card. Keep card-art and portrait windows empty
unless the request declares finished art. Keep generated images free of readable
text, numbers, watermarks, and unrelated composite screens.

Write the prompt and source plan under `.godotmaker/asset-generation/`, then
generate real provider art into its declared raw-source path. Preserve the raw
image and provider report; never replace failed generation with procedural or
placeholder art.

### 2. Process and curate

Prefer the repository's deterministic tools, selecting only those the source
needs:

- `asset_image_finalize.py` for a single card or portrait frame, including
  transparency, alpha bounds, aspect checks, and finalization report;
- `asset_sheet_process.py` for component sheets, with `autoslice` for separated
  pieces and `grid` only for intentional equal cells;
- `asset_curation_select.py` to choose final components with a curation record;
- `asset_atlas_assemble.py` to build a transparent atlas and region metadata.

Temporary scripts or other image tools are allowed when diagnosis needs them.
The trace must state the reason, command or code, inputs, outputs, changed
files, diagnostic, and repair result. Never claim a provider call, attachment,
or verification that did not happen.

### 3. Compile native resources

Keep final sources under `assets/generated/card-kit/<asset_id>/`. Compile one
`StyleBoxTexture` for every declared frame/state
pair using an explicit source/region, borders, expand margins, and stretch
axes, plus explicit content margins. This preserves card corners through
nine-slice scaling. Compile those
StyleBoxes first, then build the optional Theme at `<asset_id>_theme.tres` when
the request declares one. A Theme recipe may bind a generated
`StyleBoxTexture` when the caller requests that composition. Compile every
named fixed component into a distinct `AtlasTexture`. Front/back images,
portrait frames, rarity badges, and overlays are separate only when the request
declares them; never infer a missing requested resource from another region.

### 4. Diagnose, repair, and recheck

Run `standalone_validation.compile_and_validate()` after a candidate set exists.
L0 binds the family request/result, L1 checks final sources and metadata, L2
compiles a fresh registry, L3 loads the artifacts in headless Godot, and L4
checks type-specific resource structure. These are production diagnostics, not
a one-shot failure gate: inspect the failed diagnostic, repair the source,
processing parameters, metadata, recipe, or Godot resource, and re-run the
affected checks followed by the final full check.

Only STOP for a missing/corrupt required input, unsupported pixel-art request,
contradictory request, unavailable declared provider or required reference
attachment, or unrecoverable environment/permission failure. A final result is
ready only after every applicable L0-L4 check passes.

## Result and Handoff

Return the shared generic result with independently usable native runtime
resources (`Theme`, `StyleBoxTexture`, and `AtlasTexture`), its `theme_recipe`,
`single`, or `region_atlas` sources, previews when produced, and final L0-L4
evidence. Check it with the shared result schema and checker plus this family
contract. Before responding, persist that exact generic result JSON at
`.godotmaker/asset-generation/<asset_id>-result.json`, then return the same
JSON directly in the final response. The runner, not a self-reported boolean,
records validation.

The output is reusable card UI, not pixel-perfect `Control` or `Container`
composition. Consumers choose their own layout and may apply only the declared
Theme, StyleBoxTexture, or AtlasTexture resources.

For `gm-asset`, the producer adapter translates a successful generic result
into stable `source_layout + godot_artifact` entries and performs the normal
ready handoff. Private Eval independently assesses consumer use, visual quality,
reference consistency, and whether an improvised repair should become a shared
tool improvement.
