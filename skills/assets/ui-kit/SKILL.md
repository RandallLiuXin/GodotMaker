---
name: ui-kit
description: Produce a complete reusable flat-first Godot UI Theme from a binding visual reference, with two provider-generated source sheets, fixed square nine-slice patches, stable AtlasTexture icons, and native Theme bindings.
---

# UI Kit Asset

Produce one reusable visual system, not a page layout. The result gives a
worker a complete Godot `Theme`, named `StyleBoxTexture` resources, and named
`AtlasTexture` icons. Its reusable art covers button states, panels, tabs, and
semantic icons. It does not create a composite screen, readable UI copy,
characters, logos, gameplay geometry, or final `Control`/`Container` layout.
Do not use it for card frames.
Do not use it for portrait frames.

Read [references/theme-baseline.md](references/theme-baseline.md) and
[references/source-sheet-scheme.json](references/source-sheet-scheme.json)
before planning. They own the baseline controls, stable runtime names, two
provider sheets, fixed patch geometry, and source-to-runtime reuse mappings.
The caller's brief supplies visual direction; do not make it repeat this
contract.

## Input gate

Accept the shared Asset Skill request schema at
`.godotmaker/asset-runtime/schema/asset-skill-request.schema.json`; require
`asset_type: ui-kit`, a pinned `provider` (`native`, `codex`, `gemini`, or
`openai`), and at least one readable image in `references`. Preserve every
reference `role`. Missing or unreadable references and pixel-art requests are
input-gate STOP conditions.

Validate the returned document with the shared result schema and checker at
`.godotmaker/asset-runtime/schema/asset-skill-result.schema.json` before family
binding checks.

Attach every reference as real image input to both provider calls. The Codex
route uses `referenced_image_paths`; other routes use their declared attachment
mechanism. Never reduce a reference to prompt text or silently switch provider.
Record provider, image model when exposed, coding model, reasoning, roles,
absolute attached paths, call identity, prompt, and attempt in provenance.
STOP before generation if the pinned route cannot attach every reference.

This skill can be invoked directly or by an orchestrator with the same
contract. Do not read or write `ASSETS.md`, tags, stage state, generated
manifests, stable entries, or worker dispatch state.

## Produce

1. Inspect the reference and write `theme_plan.json` before image generation.
   It contains:

   - a positive `rendering_medium` such as `bold comic-book game art`,
     `hand-painted fantasy illustration`, or `glossy mobile-game illustration`;
   - exactly the color tokens required by `asset_ui_theme_recipe.py`:
     `text`, `text_muted`, `text_outline`, `surface`, `surface_raised`, `input`,
     `primary`, `secondary`, `danger`, `success`, `border`, `focus`,
     `selection`, and `shadow`;
   - exactly the geometry tokens `corner_radius_small`,
     `corner_radius_medium`, `corner_radius_large`, `border_width`,
     `content_margin`, `shadow_size`, `shadow_offset`, and `font_size`;
   - concise observations for palette, contrast, shape, outline, shadow, and
     material language, plus the reference roles and paths used to derive them.

   Use positive medium language. Do not put pixel-art negations into image
   prompts. The Theme plan is a deterministic visual-system specification, not
   generated art.

2. Generate the deterministic source plan:

   ```powershell
   python tools/asset_ui_source_sheet_plan.py --request ASSET_REQUEST.json --scheme .agents/skills/ui-kit/references/source-sheet-scheme.json --rendering-medium "<theme_plan rendering_medium>" --out source_sheet_plan.json
   ```

   Use the plan prompts unchanged. Make exactly two provider calls, attaching
   every reference to each call:

   - `surface_patches_source.png`: eight 96x96 square runtime patches for button
     normal/hover/pressed/disabled, base/raised panel, and selected/unselected
     tab treatment. Decoration stays inside the declared border band; the
     declared safe center remains continuous and undecorated.
   - `icons_source.png`: 24 unique semantic icons. The plan normalizes Theme
     arrows to 32x32, checks and toggles to 40x40, slider grabbers to 48x48,
     and reusable action/status icons to 128x128. Its mappings expand to all
     stable runtime icon names.

   Both images use only solid `#FF00FF` as background, with separated artwork
   that never touches canvas edges. Save each raw provider image and full
   provenance. Do not accept a screen mockup as either sheet.

   Write `source_sheet_provenance.json` as an array with exactly one final
   record per sheet, in plan order. Each record contains `sheet_id`, final
   `attempt`, exact `prompt`, `provider`, `image_model`, `coding_model`,
   `reasoning`, `tool_call_id`, `attached_references`, and `raw_source_path`.
   Every attached reference entry preserves its request `role` and readable
   request-relative `path`. Keep earlier failed generation attempts under a
   `retries` array on that sheet's final record; never replace or conceal them.

3. Process each real provider image only with controlled tools already owned by
   the project:

   - `asset_image_finalize.py --background magenta --no-origin` creates the
     transparent processing source and report.
   - `asset_sheet_process.py --snap-mode autoslice` receives the plan's ordered
     source component names. Do not pass `--grid`.
   - The detected region count must equal the plan count. On count, separation,
     edge, or transparency failure, preserve evidence and regenerate only that
     provider sheet with the same provider and attachments.
   - Normalize each accepted component with `asset_image_finalize.py --resize`
     to its fixed plan size.
   - Assemble each plan atlas with `asset_atlas_assemble.py`, preserving the
     final physical atlas, metadata, and processing reports.

   Do not programmatically draw, replace, or repair art with Pillow, SVG,
   canvas, ImageMagick, Godot drawing, inline scripts, placeholders, or a new
   pixel tool. Do not pass raw provider rectangles directly to a compiler.

4. Compile the flat-first runtime resources. Generate `stylebox_plan.json`:

   ```powershell
   python tools/asset_ui_stylebox_plan.py --source-sheet-plan source_sheet_plan.json --theme-plan theme_plan.json --asset-id <asset_id> --out stylebox_plan.json
   ```

   The fixed profiles, not freehand agent guesses, own borders, content
   margins, safe centers, stretch modes, and preview sizes. The plan expands
   eight source patches into 23 stable `StyleBoxTexture` outputs. Base,
   Primary, Secondary, and Danger button families reuse the same state patches
   through deterministic `modulate_color`; popup and tooltip reuse panel
   patches. Copy `stylebox_plan.styleboxes` unchanged into
   `ui_kit_request.json.spec.styleboxes` and compile every entry.

   Compile 31 stable runtime `AtlasTexture` outputs from the icon metadata.
   Multiple names may intentionally share one of the 24 source rectangles.
   Bind only Godot-defined semantic icon slots in `Theme`; keep other utility
   icons as independently reusable named runtime resources.

5. Generate and compile the complete Theme recipe:

   ```powershell
   python tools/asset_ui_theme_recipe.py --theme-plan theme_plan.json --asset-id <asset_id> --out theme_recipe.json
   ```

   The recipe uses native `StyleBoxFlat`/`StyleBoxEmpty` resources for input,
   text, progress, slider, scrollbar, option-button, focus, separator, and
   undrawn control backgrounds. It uses the compiled texture resources only
   for button, panel, tab, popup-panel, and tooltip surfaces. Compile the final
   Theme to
   `res://assets/generated/ui-kit/<asset_id>/<asset_id>_theme.tres`.

6. Return the generic result with separate `source_layout` sources and
   `godot_artifact` runtime outputs, all under
   `res://assets/generated/ui-kit/<asset_id>/`. Sources include theme/source
   plans, recipe, raw provenance, physical atlases, atlas metadata, and
   processing reports. Declare each raw provider sheet as `grid_sheet`, each
   physical final atlas as `region_atlas`, and plans/provenance/reports without
   an invented layout. Use stable report names
   `surface_patches_finalize_report.json`, `icons_finalize_report.json`,
   `surface_patches_process_report.json`, and `icons_process_report.json`.
   Runtime outputs include the Theme, 23
   `StyleBoxTexture` resources, and 31 `AtlasTexture` resources.

7. Write the complete derived request to `ui_kit_request.json` and candidate
   result to `ui_kit_result.json`. Run the public validator after resources
   exist:

   ```powershell
   python tools/asset_ui_card_validate.py --request ui_kit_request.json --result ui_kit_result.json --project-root . --godot-path $env:GODOT_BIN --allow-failure
   ```

   It owns L0-L5 facts. L0-L4 check the closed contract, sources and trace,
   native compilation, Godot load, and structural bindings. L5 instantiates
   common controls at compact and expanded sizes. L6 is a separate private
   visual Eval.

Treat a
failed level as repair input:

   - L1: preserve evidence and regenerate only the invalid source sheet.
   - L2: repair derived requests, mappings, recipes, or compiler support; do
     not regenerate valid art for a Godot schema error.
   - L3-L5: repair paths, regions, bindings, or consumer setup and rerun.

Record retries. STOP only for an input-gate failure or a pinned provider that
cannot attach references. Never hand-write L-level values; do not STOP merely because a production validation attempt failed.

Use the configured `GODOT_BIN`; do not substitute another Godot installation.
If required validation cannot run, return a failed result rather than claiming
readiness.

## Return format

Finish with exactly one generic Asset Skill result JSON object. A successful
result is validator-owned. A genuine input-gate STOP has the same generic keys,
no outputs, and `validation.passed: false` with a concrete note. Do not replace
the object with prose or Markdown.

The worker owns final page layout. The returned Theme, StyleBoxes, and
AtlasTextures are reusable visual-system resources; a reference establishes
visual language, not pixel-perfect screen layout.
