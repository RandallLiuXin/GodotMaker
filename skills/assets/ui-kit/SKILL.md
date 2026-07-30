---
name: ui-kit
description: Produce a complete reusable Godot UI Theme from a binding visual reference, including provider-generated UI source sheets, processed atlases, StyleBoxTexture state resources, AtlasTexture icons, and Theme bindings.
---

# UI Kit Asset

Use this skill to make one reusable visual Theme, not a page or a Control
layout. The result supplies interface icons, panels, and button states a worker
needs to construct later screens. It does not create a composite screen, readable UI copy,
characters, logos, or gameplay geometry.
Do not use it for card frames.
Do not use it for portrait frames.

Read [references/theme-baseline.md](references/theme-baseline.md) before
planning. That is the complete common-control contract; do not ask the caller
to repeat it in their brief. Read
[references/source-sheet-scheme.json](references/source-sheet-scheme.json)
before every provider call; it is the production contract for the three source
sheets.

## Input gate

Accept the shared Asset Skill request schema at
`.godotmaker/asset-runtime/schema/asset-skill-request.schema.json` and require
`asset_type: ui-kit`. Validate the returned document with the shared result schema and checker at
`.godotmaker/asset-runtime/schema/asset-skill-result.schema.json` before
running the family binding checks.
Require one or more `references` with a readable local image path. Preserve
every `role`. A missing, unreadable, or unattached reference is a STOP, before
calling a provider or writing generated output. Pixel-art requests are not
supported and are a STOP.

Respect the declared `provider` exactly (`native`, `codex`, `gemini`, or
`openai`). Do not substitute another provider. Pass every reference as an
actual image attachment, not a prompt path: the Codex route uses
`referenced_image_paths`; the other routes use their declared attachment path.
Record provider, image model identity when exposed, coding model, reasoning,
reference roles, exact attached paths, and tool/provider call identity in the
generation trace. STOP if the declared route cannot attach the references.

This skill can be invoked directly or by an orchestrator with the same
contract. Do not read or write `ASSETS.md`, tags, stage state, generated
manifests, stable entries, or worker dispatch state.

## Produce

1. Derive a closed `theme_plan.json` from the brief and reference. It owns
   palette, contrast, outline/shadow language, shape vocabulary, texture
   treatment, `rendering_medium`, the exact `tokens` object required by
   `asset_ui_theme_recipe.py` (`text`, `text_hover`, `text_pressed`,
   `text_disabled`, `text_outline`, `text_placeholder`, `selection`, and
   `focus`), semantic component/state mapping, and all
   baseline component bindings. `rendering_medium` must positively describe
   the observed visual medium, such as hand-painted fantasy illustration,
   bold comic-book game art, or glossy mobile-game illustration; do not use
   pixel-art negations in provider prompts. The template is a deterministic
   skeleton; it is not visual art.
2. Create `source_sheet_plan.json` with:

   ```powershell
   python tools/asset_ui_source_sheet_plan.py --request ASSET_REQUEST.json --scheme .agents/skills/ui-kit/references/source-sheet-scheme.json --rendering-medium "<theme_plan rendering_medium>" --out source_sheet_plan.json
   ```

   Use each plan entry as one provider call. Attach every reference as an
   actual image input in every call. Use the plan's component names, row-major
   order, target sizes, atlas dimensions, and slot rectangles unchanged. Use
   the plan prompt unchanged. Never turn a screen mockup into a source sheet.
3. Make exactly the three provider-generated source sheets named by the plan:
   state/frame, form/navigation, and utility icons. Save each raw provider
   image, its exact prompt, attached reference roles and paths, provider/image
   model, coding model, reasoning, call id, and attempt number. A source sheet
   without this provenance is incomplete.
4. Process each provider sheet with the existing controlled tools:

   - Run `asset_image_finalize.py --background magenta --no-origin` once to
     create the transparent processing source and report.
   - Run `asset_sheet_process.py --snap-mode autoslice` without `--grid`. Pass
     the plan's ordered component names through `--names` and preserve the
     report.
   - Require the detected region count to equal the plan component count.
     Regenerate only that provider sheet when the count, separation, or edge
     checks fail.
   - Run `asset_image_finalize.py --resize <slot_width>x<slot_height>
     --no-origin` for every accepted candidate. Use the plan slot target size.
   - Write the fixed-slot atlas declaration from the plan atlas dimensions and
     slot rectangles. Point each slot at its normalized candidate.
   - Run `asset_atlas_assemble.py` once per sheet. Preserve its physical atlas
     and metadata.

   Do not pass provider source-sheet rectangles into a compiler. Do not draw,
   synthesize, recolor, or replace art with Pillow, SVG, canvas, ImageMagick,
   Godot drawing, inline scripts, or placeholders.
5. Compile every textured state/frame to an explicit `StyleBoxTexture` with
   an exact source region, border, margins, and stretch axes. Compile every
   icon to a zero-margin `AtlasTexture` using its declared atlas rectangle.
6. Compile StyleBoxTexture and AtlasTexture resources first. Use the fixed
   semantic resource names from the baseline (`button_normal`,
   `primary_hover`, `popup_menu_separator`, `icon_checkbox_checked`, and so
   on), then build the only permitted complete Theme recipe with:

   ```powershell
   python tools/asset_ui_theme_recipe.py --theme-plan theme_plan.json --asset-id <asset_id> --out theme_recipe.json
   ```

   The recipe binds compiled `AtlasTexture` resources, not their whole source
   PNG sheets, and uses exact native Godot property names per control. Then
   compile the main `Theme` at
   `res://assets/generated/ui-kit/<asset_id>/<asset_id>_theme.tres`, binding
   those external StyleBoxTexture and AtlasTexture resources to the complete
   baseline Theme matrix. Theme variations must be real bindings, not names
   without state resources.
7. Return the generic result with `source_layout` sources and independent
   `godot_artifact` runtime outputs. Keep every path under
   `res://assets/generated/ui-kit/<asset_id>/`. `sources` includes the theme
   plan/recipe, raw-source provenance, final sheets, atlas metadata, and
   processing reports through their applicable layouts; `validation` comes
   from the validator, never from self-reporting.
8. Run applicable L0-L5 before returning: L0-L4 cover closed contract,
   source/trace and
   file checks, native compilation, headless Godot load, structural binding
   checks, and a small consumer scene that displays the complete state and
   component matrix. The deterministic tools validate serialization and Godot
   loading; L6 visual review is an independent Eval layer. A failed
   state, atlas rectangle, Theme binding, consumer load, or trace is not ready.

Write the complete derived request (including every baseline `spec` declaration)
to `ui_kit_request.json` and the candidate generic result to
`ui_kit_result.json`. Run the public validator exactly once after all resources
are written:

```powershell
python tools/asset_ui_card_validate.py --request ui_kit_request.json --result ui_kit_result.json --project-root . --godot-path $env:GODOT_BIN --allow-failure
```

It overwrites `ui_kit_result.json` with validator-owned L0-L5 facts. Treat a
failed level as repair input, not a terminal verdict:

- L1 source failure: retain the failed raw image/report and regenerate only
  that plan entry with the same pinned provider and references. Add the exact
  transparency, separation, or edge diagnostic to the next provider prompt.
- L2 recipe/compiler failure: repair the derived request, Theme recipe,
  StyleBox mapping, or native compiler support, then recompile. Do not
  regenerate valid art merely to repair a Godot schema error.
- L3-L5 failure: repair paths, regions, bindings, or the consumer setup, then
  rerun validation.

Record every retry in the source-sheet provenance. STOP only for an input-gate
condition or when the pinned provider cannot satisfy its attachment contract;
do not STOP merely because a production validation attempt failed. Never
hand-write L-level values.

For all Godot validation commands, use the configured `GODOT_BIN` executable
when it is present. Do not assume that a `godot` command is on `PATH`, and do
not substitute another Godot installation. If no configured executable can run
the required validation, return a failed result rather than claiming readiness.

## Return format

Finish with exactly one generic Asset Skill result JSON object. On success it
is the validated result after the repair loop; on genuine input-gate STOP it
has the same generic keys, no outputs, and `validation.passed: false` with a
concrete note. Do not replace that object with prose, Markdown links, or a
summary: callers use it as the handoff.

The worker owns final `Control` and `Container` page layout. The returned
Theme, StyleBoxes, and AtlasTextures are the reusable visual system; a
reference establishes visual language, not pixel-perfect screen layout.
