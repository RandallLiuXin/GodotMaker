---
name: ui-kit
description: Produce a standalone UI skin with native Theme, StyleBoxTexture, and AtlasTexture resources for reusable controls.
---

# UI Kit Asset

Use this skill for a reusable UI skin: interface icons, panels, tabs, badges,
progress bars, and button states. It produces visual resources, not a scene or
layout. Do not use it for card frames, portrait frames, character art, a full
composite screen, readable text, or gameplay geometry.

## Invocation

Accept one asset request matching the shared Asset Skill request schema in
`skills/assets/_shared/schema/asset-skill-request.schema.json`. Require
`asset_type` to be `ui-kit`. Validate the returned document against the shared result schema and checker before returning it.

This skill can be invoked directly or by an orchestrator with the same
contract. Do not read or write `ASSETS.md`, tags, stage state, generated
manifests, stable entries, or worker dispatch state.

## Produce

1. Use the brief plus visible style or screen references to choose a coherent
   skin. The LLM supplies the visual recipe: palette, hierarchy, icon language,
   panel treatment, button-state treatment, and the requested reusable pieces.
2. Write one closed `theme_recipe` JSON document and compile it to the main
   `Theme` at
   `res://assets/generated/ui-kit/<asset_id>/<asset_id>_theme.tres`. Declare at
   least one type variation and all requested Theme colors, constants, fonts,
   icons, and StyleBox bindings through the legal recipe schema.
3. For every textured panel, scalable border, or button-state frame, declare an
   explicit `StyleBoxTexture` recipe: source PNG, texture region, four borders,
   expand margins, and horizontal/vertical stretch axes. Compile each recipe
   to its own `.tres`; use nine-slice borders instead of stretching a whole
   panel image.
4. For icon sheets or fixed button-state sheets, assemble a physical atlas from
   declared slots and metadata. Compile each named runtime region to an
   independent zero-margin `AtlasTexture`; do not use packing, trimming,
   inferred regions, or a PNG atlas as a substitute for a region resource.
5. Cover every requested button state explicitly (`normal`, `hover`, `pressed`,
   `disabled`, and `focus` when requested). Missing requested states are a
   failed result, not a visual fallback.
6. Run the shared L0-L4 ladder for every runtime output. The deterministic tools
   own legal serialization, resource-type completeness, Godot loading, and
   structure checks; they do not claim to generate a good visual design by
   themselves.

The worker owns `Control` and `Container` layout. Reference images establish
visual direction only; they are not pixel-perfect layout oracles. A worker
binds the returned Theme and applies the supplied StyleBoxTexture or
AtlasTexture resources where its concrete controls need them.

## Result

Return the shared generic result. A successful invocation returns independent
native outputs rather than one opaque bundle:

- one runtime `Theme` for the skin and its type variations;
- one runtime `StyleBoxTexture` for each declared scalable panel or state
  frame; and
- one runtime `AtlasTexture` for each declared icon or sheet region.

The result may include only the requested resource kinds, but every listed
runtime output must have a successful L0-L4 result. `sources` records the
`theme_recipe` JSON and each `region_atlas` or `single` PNG used by those
resources. A representative result is in `fixtures/representative-result.json`.

If recipe validation, a requested button state, a nine-slice declaration, an
atlas region, or a Godot type check fails, return `outputs: []` with
`validation.passed: false` and explanatory notes. Never report a partly loaded
skin as ready.
