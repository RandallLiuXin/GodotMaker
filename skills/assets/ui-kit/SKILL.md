---
name: ui-kit
description: Produce a complete reusable non-pixel-art Godot UI Theme from a binding visual reference, including provider-generated UI source sheets, processed atlases, StyleBoxTexture state resources, AtlasTexture icons, and Theme bindings.
---

# UI Kit Asset

Use this skill to make one reusable visual Theme, not a page or a Control
layout. The result supplies interface icons, panels, and button states a worker
needs to construct later screens. It does not create a composite screen, readable UI copy,
characters, logos, or gameplay geometry.

Read [references/theme-baseline.md](references/theme-baseline.md) before
planning. That is the complete common-control contract; do not ask the caller
to repeat it in their brief.

## Input gate

Accept the shared Asset Skill request schema and require `asset_type: ui-kit`.
Validate the returned document with the shared result schema and checker before
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
   treatment, semantic component/state mapping, and all baseline component
   bindings. The template is a deterministic skeleton; it is not visual art.
2. Make at least three provider-generated non-text UI source sheets: state and
   frame treatments, form/navigation treatments, and a utility-icon sheet.
   They must share the same binding reference in the actual provider call. Do
   not generate a screen mockup in place of reusable UI source art.
3. Use only the existing controlled tools to process actual provider or user
   images: `asset_image_finalize.py`, `asset_sheet_process.py`,
   `asset_curation_select.py`, and `asset_atlas_assemble.py`. Use autoslice
   for separated source pieces, preserve the reports, and use fixed slots for
   every final atlas rectangle. Do not draw, synthesize, recolor, or replace
   art with Pillow, SVG, canvas, ImageMagick, Godot drawing, inline scripts, or
   placeholders.
4. Compile every textured state/frame to an explicit `StyleBoxTexture` with
   an exact source region, border, margins, and stretch axes. Compile every
   icon to a zero-margin `AtlasTexture` using its declared atlas rectangle.
5. Compile StyleBoxTexture and AtlasTexture resources first. Then compile the
   main `Theme` at
   `res://assets/generated/ui-kit/<asset_id>/<asset_id>_theme.tres`, binding
   those external StyleBoxTexture and AtlasTexture resources to the complete
   baseline Theme matrix. Theme variations must be real bindings, not names
   without state resources.
6. Return the generic result with `source_layout` sources and independent
   `godot_artifact` runtime outputs. Keep every path under
   `res://assets/generated/ui-kit/<asset_id>/`. `sources` includes the theme
   plan/recipe, raw-source provenance, final sheets, atlas metadata, and
   processing reports through their applicable layouts; `validation` comes
   from the validator, never from self-reporting.
7. Run applicable L0-L5 before returning: L0-L4 cover closed contract,
   source/trace and
   file checks, native compilation, headless Godot load, structural binding
   checks, and a small consumer scene that displays the complete state and
   component matrix. The deterministic tools validate serialization and Godot
   loading; L6 visual review is an independent Eval layer. A failed
   state, atlas rectangle, Theme binding, consumer load, or trace is not ready.

The worker owns final `Control` and `Container` page layout. The returned
Theme, StyleBoxes, and AtlasTextures are the reusable visual system; a
reference establishes visual language, not pixel-perfect screen layout.
