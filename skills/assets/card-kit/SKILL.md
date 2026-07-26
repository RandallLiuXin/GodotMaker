---
name: card-kit
description: Produce standalone native resources for card frames, portrait windows, card controls, and scalable card UI borders.
---

# Card Kit Asset

Use this skill for card-game-specific UI: card frames, portrait frames, rarity
frames, card slots, deck slots, resource badges, card-state overlays, card
panels, and card buttons. Do not use it for generic HUD controls, character
portraits, a finished card illustration unless explicitly requested, a full
composite screen, readable text, or scene layout.

## Invocation

Accept one asset request matching the shared Asset Skill request schema in
`skills/assets/_shared/schema/asset-skill-request.schema.json`. Require
`asset_type` to be `card-kit`. Validate the returned document against the
shared result schema and checker before returning it.

This skill can be invoked directly or by an orchestrator with the same
contract. Do not read or write `ASSETS.md`, tags, stage state, generated
manifests, stable entries, or worker dispatch state.

## Produce

1. Use the brief plus visible card or UI references to set the frame geometry,
   rarity language, panel treatment, badge/icon language, and state treatment.
   The LLM fills this visual recipe; deterministic tools do not invent a card
   design.
2. Keep card-art and portrait windows empty unless the request explicitly asks
   for finished portrait art. A frame must remain a reusable frame rather than
   a flattened example card.
3. When card controls need shared colors, typography, constants, or state
   binding, write a closed `theme_recipe` and compile a standalone `Theme`
   with a declared type variation at
   `res://assets/generated/card-kit/<asset_id>/<asset_id>_theme.tres`.
4. Compile every card frame, portrait frame, scalable slot, panel, or button
   state from an explicit `StyleBoxTexture` recipe. Declare its PNG region,
   four borders, expand margins, and stretch axes, then use nine-slice scaling
   to preserve corners and frame geometry.
5. Assemble badges, resource icons, and fixed overlays into declared atlas
   slots where appropriate. Compile each named region into a distinct
   zero-margin `AtlasTexture`; no automatic packing, trimming, or inferred
   region is allowed.
6. Declare all requested card states (`normal`, `hover`, `pressed`,
   `disabled`, `selected`, or `locked`) as named resources. Never infer a
   missing state from another frame.
7. Run shared L0-L4 validation for every output. The deterministic tools enforce
   legal serialization, complete declared resource types, Godot loading, and
   type-specific structure checks.

The worker owns `Control` and `Container` layout and card placement. A
reference shows visual direction only and is not pixel-perfect.
Workers bind the returned Theme and use the separate StyleBoxTexture and
AtlasTexture outputs for the card controls they construct.

## Result

Return the shared generic result. A successful result exposes each native
resource independently: an optional card `Theme`, one `StyleBoxTexture` for
each scalable frame or state, and one `AtlasTexture` for each declared icon or
overlay region. `sources` records each `theme_recipe`, `single`, or
`region_atlas` input used by the resources. See
`fixtures/representative-result.json` for a valid standalone result.

If a requested frame/state is absent, a portrait window is incorrectly filled,
a nine-slice declaration is invalid, an atlas region is missing, or any L0-L4
check fails, return `outputs: []` with `validation.passed: false` and notes.
Do not expose a card PNG as a replacement for its native runtime resource.
