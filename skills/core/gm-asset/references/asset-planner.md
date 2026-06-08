# Asset Planning Reference

This file describes how `/gm-asset` plans the current tag's asset work before
generation. Use `asset-runtime-pipeline.md` for provider commands, runtime
claim protocol, finalization, and batch execution. Use
`asset-prompt-contracts.md` for visual source prompt shapes.

## Scope

Use this file for:

1. Reading current-tag asset requirements.
2. Deriving missing visual assets from project documents and scene references.
3. Choosing asset roles, anchors, derivatives, and provider paths.
4. Building generation batches and ASSETS.md updates.
5. Writing `.godotmaker/asset-generation/manifest.json` entries.

Do not use this file to write PLAN.md, GDD.md, STRUCTURE.md, SCENES.md, or
STYLE.md.

## Inputs

Read these before planning:

1. `ASSETS.md`: current tag rows and existing asset statuses.
2. `PLAN.md`: current playable-unit tasks and declared asset needs.
3. `STYLE.md`: visual prompt anchor, suffix, rules, and avoid list.
4. `STRUCTURE.md`: architecture and asset hints.
5. `SCENES.md`: scene element lists and gameplay screen descriptions.
6. `references/scene_*.png`: visual targets generated from scene descriptions.
7. `references/asset-family-contract.md`: asset family and production shape
   definitions.
8. `references/asset-curation.md`: extraction, canonical selection, and
   rejected candidate records.

If a scene reference is missing, use the SCENES.md text and STYLE.md instead.

## Planning Workflow

### 1. Determine current tag scope

Read the current tag from `PLAN.md`'s `**Tag:**` header. If the header is
missing, stop and report the missing tag. Only plan rows whose `Tag` matches
the current tag. Prior-tag rows are not modified by `/gm-asset`.

### 2. Analyze visible game content

For each current-tag scene:

1. Check whether `references/scene_{name}.png` exists.
2. If image content must be analyzed, dispatch the analyst subagent. Do not read
   image binaries in the main agent.
3. Use the analyst summary to identify visible objects, scale, composition,
   foreground/background layers, UI elements, and repeated visual motifs.
4. Cross-check SCENES.md for elements that are required but not visible in the
   analyst summary.
5. Cross-check PLAN.md and STRUCTURE.md for assets required by gameplay logic.

The final list is the union of scene-visible assets and gameplay-required
assets.

### 3. Choose production strategy

Choose one production strategy before choosing the manifest family:

1. `component_sheet`: UI pieces, icons, small props, pickups, badges, compact
   chests, and other similarly sized objects.
2. `action_sheet`: one body action or one FX loop for a character, enemy, NPC,
   summon, animated prop, projectile, impact, slash, aura, dust, or pickup FX.
3. `map_or_stage_reference`: layered-map or side-scroll visual planning
   artifact plus the asset list derived from it.
4. `single_image`: background, panel, card frame, large prop, canonical
   character, texture, or runtime sprite that does not need splitting.

Use the strategy to choose prompt shape, layout guide use, processing tool,
curation record, and runtime outputs.

### 3.1 Classify asset families

Classify each planned asset into one family from
`references/asset-family-contract.md`:

1. `screen_reference`
2. `style_reference`
3. `character_canonical`
4. `character_action_source`
5. `character_frame_output`
6. `projectile_fx_source`
7. `impact_fx_source`
8. `compact_prop_pack`
9. `ui_component_sheet`
10. `icon_pack`
11. `panel_source`
12. `background`
13. `runtime_sprite`
14. `texture`
15. `audio`

Choose one production shape for each visual asset:

1. `single_image`
2. `grid_sheet`
3. `action_sheet`
4. `frame_sequence`
5. `delivery_sheet`
6. `reference_only`
7. `curation_required`

Record the family and production shape before writing the prompt.

### 3.2 Strategy rules

Use `component_sheet` for compact assets that share one style and fit one
regular grid or autoslice sheet:

1. UI buttons, tabs, counters, badges, HUD pieces, card slots, small frames.
2. Resource icons, skill icons, rank icons, item icons.
3. Compact props, pickups, crates, stones, bushes, pots, debris, small signs.

Do not put these in `component_sheet`:

1. Walkable platforms, floors, bridges, walls, ladders, doors, gates, exits.
2. Large trees, buildings, terrain chunks, long hazards, roads, rails, pipes.
3. Any object whose collision or placement depends on exact wide/tall shape.

Use `action_sheet` for one coherent action or effect loop:

1. One body action per source: idle, walk, run, attack, shoot, cast, hurt,
   death, summon, charge.
2. One detached FX loop per source: projectile, impact, slash, aura, dust,
   pickup, muzzle flash, explosion.
3. Body actions use `kind: body`; detached effects use `kind: fx`.

Use `map_or_stage_reference` for visual planning assets:

1. Layered map: foundation or background, dressed reference, object list,
   compact prop packs or separate prop sources.
2. Side-scroll stage: scenery or parallax reference, stage reference, platform,
   object, hazard, pickup, and door asset list.

Use `single_image` for sources that should stay one file:

1. Character canonical, enemy canonical, UI style reference.
2. Large panel, card frame, dialogue frame, shop slot.
3. Background, parallax plate, texture, large prop, runtime sprite.

### 4. Choose anchors and derivatives

Identify which assets establish the style for later assets.

1. Anchor assets are generated first and reviewed before derivatives.
2. Derivative assets use anchors as image references when the provider supports
   image input.
3. Keep one canonical anchor per character, UI family, environment family, or
   enemy/item family.
4. If multiple references disagree, choose one canonical version and note it in
   the asset row.

Common anchor patterns:

1. One hero character anchors all character variants.
2. One UI kit anchors all HUD and menu elements.
3. One environment image anchors vegetation, terrain, props, and background
   details.
4. One weapon/item family image anchors item variants.

### 4.0 Layout guides

Use `tools/asset_layout_guide.py` before image generation when a source must
fit a fixed grid, exact slot count, or safe padding.

Recommended use:

1. `component_sheet` with 2x2, 3x3, or 4x4 grid.
2. `action_sheet` with fixed multi-row frames.
3. Prop packs where each cell has a named output.
4. UI component sheets where spacing must stay consistent.

Write guides under `.godotmaker/asset-generation/guides/`. Make the guide
visible to the selected image-generation runtime before generating the source.
Use it as a layout reference only.

### 4.1 Plan character and enemy bundles

For every important player character, enemy family, NPC, summon, or recurring
creature:

1. Reserve one `character_canonical` entry.
2. Reserve one `character_action_source` entry for each required action.
3. Use `idle` before other body actions.
4. Use the accepted canonical reference for action prompts when the provider
   supports image references.
5. Use one action source per action family.
6. Use `character_frame_output` entries for processed runtime frames or
   delivery grid sheets derived from action sources.
7. Put projectiles, impacts, slash arcs, muzzle flashes, dust, and pickup
   effects in `projectile_fx_source` or `impact_fx_source` entries.
8. Do not use one raw mixed-action atlas as the source for an important
   character.
9. Do not use raw single-row body sheets for characters, enemies, NPCs,
   summons, or animated props.
10. If the engine needs one atlas, assemble it in a separate pass after
   per-action curation.

Default action planning:

1. `idle`: `2x2`, 4 frames, body-only, anchor `bottom` or `feet`.
2. `run` or side-view `walk`: `2x2` or `2x3`, body-only, anchor `feet`.
3. `attack`: `2x2` or `2x3`, body-only for controllable characters.
4. `shoot` or `cast`: `2x2` or `2x3`, body-only plus separate projectile or
   impact sources.
5. `hurt`: `2x2`, body-only.
6. `death` or transformation: `2x3`, `2x4`, or `3x3`.
7. Four-direction top-down locomotion: `4x4` canonical directional sheet.

### 4.5 Plan source, final, and handoff metadata

For every planned generated visual asset, reserve:

1. `source_path` under `.godotmaker/asset-generation/sources/`.
2. `prompt_path` under `.godotmaker/asset-generation/prompts/`.
3. `final_path` under `assets/` or `references/`.
4. Diagnostic `report_path` under `.godotmaker/asset-generation/reports/`.
5. Manifest entry under `.godotmaker/asset-generation/manifest.json`.
6. Curation report under `.godotmaker/asset-generation/curation/` when the
   source requires extraction or selection.

Use these status rules:

1. `screen_reference` and `style_reference`: `processing_status` can be
   `ready` when the reference is accepted.
2. `character_canonical`: `processing_status` can be `ready` when it is usable
   as a derivative reference.
3. `character_action_source`, `projectile_fx_source`, `impact_fx_source`,
   `compact_prop_pack`, `ui_component_sheet`, and `icon_pack`: use
   `needs_curation` until final runtime assets are processed or selected.
4. `character_frame_output`: use `processed` or `ready` only after processed
   frames or delivery grid sheets exist at their final project paths.
5. `background`, `runtime_sprite`, and `texture`: use `ready` only after the
   final project path exists and matches the ASSETS.md row.
6. `panel_source`: use `needs_curation` when the panel still needs slicing,
   sizing, or state variants.
7. `grid_sheet`, `action_sheet`, `frame_sequence`, `delivery_sheet`, and
   `curation_required`: include a `curation` object in the manifest entry when
   source processing or selection was required.

### 4.6 Plan curation records

For every source that requires curation:

1. Choose the extraction strategy from `asset-curation.md`.
2. Reserve a curation report path:
   `.godotmaker/asset-generation/curation/<asset_id>.json`.
3. Reserve candidate output paths under
   `.godotmaker/asset-generation/curation/<asset_id>/`.
4. Record selected final runtime paths under `assets/`.
5. Record rejected candidates in the curation report.
6. Use canonical references for derivative assets.

### 5. Select provider path

Read `.godotmaker/config.yaml` and use `asset_image_model` as the default image
path.

1. `native`: use the active runtime-native image-generation path documented in
   `asset-runtime-pipeline.md`.
2. `codex`: use the Codex image generation path documented in
   `asset-runtime-pipeline.md`.
3. `gemini:<model>`, `openai:<model>`, `grok:<model>`: use
   `tools/asset_source_generate.py --spec <spec.json>` as documented in
   `asset-runtime-pipeline.md`.

Provider choice by asset role:

1. Use precise providers for scene references, character canonicals, action
   sources, UI sources, and backgrounds with exact layout.
2. Use simpler providers for textures, simple props, compact prop packs, and simple
   scenic backgrounds when exact prompt adherence is not critical.
3. Use image references for derivatives when style consistency matters.
4. Treat missing API keys or unavailable runtime-native generation as hard
   failures.

### 6. Build generation batches

Plan batches that can run without conflicting outputs.

1. Put anchors before derivatives.
2. Put character canonicals before their action sources.
3. Put action sources before `character_frame_output` entries.
4. Group independent assets into parallel-ready batches, at most 3 concurrent
   generation groups.
5. Keep all outputs for one asset under known source and final target paths.
6. Plan every generated source path under
   `.godotmaker/asset-generation/sources/`.
7. Plan every diagnostic report under
   `.godotmaker/asset-generation/reports/`.
8. For generated project assets, plan final paths under `assets/` or
   `references/` only through the approved tools in `/gm-asset` SKILL.md.
9. Write prompt text to the planned `prompt_path` before generation.
10. Include `family`, `production_shape`, `source_path`, `final_path`, and
   `prompt_path` in each batch item.

If isolated generation groups may be unavailable, include a sequential fallback
note for the executor to report in the generation summary.

Scene reference planning uses the same batch rules:

1. If one scene establishes the visual style, plan it as `anchor_item`.
2. Put the remaining scene references in `parallel_items`.
3. If no anchor scene is needed, put all missing scene references in
   `parallel_items`.
4. Plan fixed scene paths:
   - source path: `.godotmaker/asset-generation/sources/scene_{name}_source.png`
   - final path: `references/scene_{name}.png`
   - report path: `.godotmaker/asset-generation/reports/scene_refs_<group_id>.json`
   - family: `screen_reference`
   - production shape: `reference_only`
5. Plan one flat finalize JSON diagnostic entry per scene reference.

### 7. Prepare ASSETS.md updates

For each generated or user-provided asset row, preserve the existing ASSETS.md
table schema and include:

1. `Tag`: current tag.
2. `Status`: `generated`, `provided`, `deferred`, or `N/A`.
3. `File Path`: final project path.
4. `Generation Params`: family, production shape, provider, prompt path,
   source path, canonical reference, derivative source, and processing status.
   Include curation report and selected candidate when curation was required.
5. `Size`: intended in-game display or world size when the table has a size
   column.

Audio rows remain `deferred` unless the user provides files.

Update `ASSETS.md` Visual Asset Contract for each current-tag visual asset:

1. `Scene / Mechanic`: every scene and mechanic that must show the asset.
2. `Visible Object`: the object or UI element name used in SCENES.md.
3. `Asset Row / Path`: `asset_name / assets/...` for a concrete ASSETS.md
   row and final path, or `procedural`, `UI text`, or
   `not required this tag` with a deferral reason.
4. `Runtime Size`: the intended display size in pixels, viewport percentage,
   or world units.
5. `Visual Role`: player, enemy, projectile, pickup, prop, background, HUD,
   overlay, VFX, or other concrete role.
6. `Readability Requirement`: the screenshot or frame-sequence condition that
   makes the asset acceptable in play.
7. `Source`: `canonical`, `derived from <asset>`, `source sheet`,
   `scene reference`, `needs curation`, `user-provided`, or `procedural/UI`.

For small sprites, write the minimum readable display size and the contrast or
silhouette requirement. For derivative assets, name the anchor asset.

## Asset Type Rules

### Background

Use for title screens, sky panoramas, arena backgrounds, parallax layers, and
large scenic images. Specify viewport behavior and intended display size.

### Texture

Use for repeated terrain, floors, walls, UI materials, and tileable surfaces.
Specify tile size in world units.

### Runtime sprite

Use for characters, enemies, items, props, pickups, icons, and VFX images.
Specify intended in-game pixel size.

### Character canonical

Use one canonical reference per important character, enemy family, or NPC
family. Generate a neutral readable pose with a clean silhouette.

### Character action source

Use one source per action. Keep body actions separate from projectiles, impact
effects, and UI effects. Process action sources into `character_frame_output`
entries before binding them to gameplay-visible ASSETS.md rows.

### Compact prop pack

Use for compact similarly sized props. Plan rows, columns, expected items, and
names before generation. Mark as `needs_curation` until final prop files exist.

Use separate sources for wide, tall, collision-bearing, or placement-critical
objects.

### UI component sheet

Use for related interface elements. Prefer one coherent kit source when style
consistency matters. Mark extraction or curation needs in ASSETS.md notes.

### Map or stage reference

Use for visual planning assets.

Layered map planning output:

1. Foundation or background source.
2. Dressed reference source.
3. Object list with asset ids, roles, approximate placement, and production
   strategy.
4. Compact prop packs or separate prop/panel/background sources.

Side-scroll stage planning output:

1. Scenery or parallax source list.
2. Stage reference source.
3. Platform, terrain, hazard, pickup, door, gate, and checkpoint asset list.
4. Compact prop packs, wide strips, or separate single-image sources.

## Common Mistakes

### Tiny generated images in-game

Do not plan a highly detailed generated sprite for a tiny display size. Use a
larger display size, a kit source, or a bold/simple prompt.

### Texture used as a unique background

Do not stretch a small tileable texture over a large scenic area. Plan a real
background instead.

### Procedural shapes as generated art

Simple geometric UI elements can be drawn in code. Use generated art for
characters, backgrounds, terrain, objects, icons, and visually important UI.

### Missing asset assignment

Every generated asset must be represented in ASSETS.md with a current-tag row.
Do not rely on hidden memory or untracked notes for asset ownership.

## Planning Output

When planning is complete, identify:

1. Current-tag ASSETS.md rows that need updates.
2. Assets to generate, claim, provide, defer, or mark N/A.
3. Planned source paths and final project paths.
4. Provider path and generation batch membership.
5. Scene reference anchor item and parallel items, when applicable.
6. Source sheets or UI kits that will need curation.
7. Manifest entries to write under `.godotmaker/asset-generation/manifest.json`.
