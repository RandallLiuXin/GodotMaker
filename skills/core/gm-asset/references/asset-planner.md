# Asset Planning Reference

This file describes how `/gm-asset` plans the current tag's asset work before
generation. Use `asset-gen.md` for provider commands, runtime claim protocol,
finalization, and asset-type generation recipes.

## Scope

Use this file for:

1. Reading current-tag asset requirements.
2. Deriving missing visual assets from project documents and scene references.
3. Choosing asset roles, anchors, derivatives, and provider paths.
4. Building generation batches and ASSETS.md updates.

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

### 3. Classify assets

Classify each planned asset into one role:

1. `scene_reference`: full-scene target image.
2. `background`: large scenic image, parallax layer, title screen, or arena.
3. `texture`: tileable or repeated material.
4. `sprite`: standalone 2D object, character, item, icon, or VFX frame.
5. `ui_kit`: related UI panels, buttons, icons, and HUD elements.
6. `item_kit`: several small objects generated as one source image.
7. `model_reference`: 2D image intended for GLB conversion.
8. `animated_sprite`: reference, poses, video, frames, and extracted animation.
9. `audio`: user-provided only.

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

### 5. Select provider path

Read `.godotmaker/config.yaml` and use `asset_image_model` as the default image
path.

1. `native`: use the active runtime-native image-generation path documented in
   `asset-gen.md`.
2. `codex`: use the Codex image generation path documented in `asset-gen.md`.
3. `gemini:<model>`, `openai:<model>`, `grok:<model>`: use
   `tools/asset_gen.py image --model <selector>` as documented in
   `asset-gen.md`.

Provider choice by asset role:

1. Use precise providers for scene references, character designs, 3D model
   references, animation references, and backgrounds with exact layout.
2. Use simpler providers for textures, simple props, item kits, and simple
   scenic backgrounds when exact prompt adherence is not critical.
3. Use image references for derivatives when style consistency matters.
4. Treat missing API keys or unavailable runtime-native generation as hard
   failures.

### 6. Build generation batches

Plan batches that can run without conflicting outputs.

1. Put anchors before derivatives.
2. Group independent assets into parallel-ready batches, at most 3 concurrent
   generation groups.
3. Keep all outputs for one asset under known source and final target paths.
4. Plan every generated source path under
   `.godotmaker/asset-generation/sources/`.
5. Plan every generation report under
   `.godotmaker/asset-generation/reports/`.
6. For generated project assets, plan final paths under `assets/` or
   `references/` only through the approved tools in `/gm-asset` SKILL.md.

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
5. Plan one flat finalize JSON report entry per scene reference.

### 7. Prepare ASSETS.md updates

For each generated or user-provided asset row, preserve the existing ASSETS.md
table schema and include:

1. `Tag`: current tag.
2. `Status`: `generated`, `provided`, `deferred`, or `N/A`.
3. `File Path`: final project path.
4. `Generation Params`: provider, prompt source, anchor relationship,
   derivative source, or curation status.
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
7. `Source`: `anchor`, `derivative of <asset>`, `scene reference`,
   `user-provided`, or `procedural/UI`.

For small sprites, write the minimum readable display size and the contrast or
silhouette requirement. For derivative assets, name the anchor asset.

## Asset Type Rules

### Background

Use for title screens, sky panoramas, arena backgrounds, parallax layers, and
large scenic images. Specify viewport behavior and intended display size.

### Texture

Use for repeated terrain, floors, walls, UI materials, and tileable surfaces.
Specify tile size in world units.

### Sprite

Use for characters, enemies, items, props, pickups, icons, and VFX images.
Specify intended in-game pixel size.

### UI kit

Use for related interface elements. Prefer one coherent kit source when style
consistency matters. Mark extraction or curation needs in ASSETS.md notes.

### Item kit

Use for multiple related small items. Plan the kit source image and the
individual final item paths.

### Model reference

Use for GLB conversion. Specify the final GLB path and the reference image path.
Use a clean presentation image with a solid background.

### Animated sprite

Plan one reference image per character or animated object. Then plan actions:

1. Root actions from the reference.
2. Optional chained actions from a previous action's last extracted frame.
3. Frame output directories.
4. Loop or one-shot playback type.
5. Background removal needs.

Keep animation chains short to limit visual drift.

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
