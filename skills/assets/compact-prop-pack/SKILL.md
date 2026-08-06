---
name: compact-prop-pack
description: Produce a reusable compact-prop atlas from one provider source sheet, with independently loadable AtlasTexture resources for every declared prop.
---

# Compact Prop Pack

Produce a standalone atlas-backed pack of small reusable props: pickups,
crates, stones, bushes, pots, debris, small signs, lamps, and environmental
dressing. Use one provider source sheet for the whole requested pack; do not
make one provider image request per prop. Do not use this Skill for platforms,
terrain, buildings, doors, gates, large trees, or other wide, tall,
collision-bearing assets. It produces assets only, never scene placement or
gameplay objects.

This Skill can be invoked directly or by an orchestrator. It never reads or
writes `ASSETS.md`, tags, stage state, or generated manifests.

## Contract

Accept the shared Asset Skill request schema and shared result schema and checker from
`.godotmaker/asset-runtime/asset-skill-contract.md` with
`asset_type: "compact-prop-pack"`. The `spec` is the exact fixed-slot
declaration consumed by `tools/asset_atlas_assemble.py --declaration`:

```json
{
  "version": 1,
  "atlas": { "width": 192, "height": 64 },
  "slots": [
    { "name": "coin", "rect": [0, 0, 32, 32], "source": "assets/generated/compact-prop-pack/market/normalized/coin.png" },
    { "name": "crate", "rect": [48, 0, 48, 48], "source": "assets/generated/compact-prop-pack/market/normalized/crate.png", "pivot": [0.5, 1.0] }
  ]
}
```

Slot names are logical prop ids. Rectangles are explicit, positive,
non-overlapping `[x, y, width, height]` values. `source` is the final,
normalized project-relative PNG for that slot; it must have exactly the
rectangle's width and height. The assembler does not resize, perform packing,
trim, or infer semantics. It only copies these finalized files into declared
slots.

Use these stable paths:

```text
res://assets/generated/compact-prop-pack/<bundle_id>/<bundle_id>.png
res://assets/generated/compact-prop-pack/<bundle_id>/<bundle_id>.json
res://assets/generated/compact-prop-pack/<bundle_id>/<logical_prop_id>.tres
```

Return one `runtime` `AtlasTexture` output per declared slot, one
`region_atlas` source for the physical PNG, and no registration fields. The
request's fixed slots are the complete logical output declaration; the manager
records every validated prop directly in its own `ASSETS.md` row.

Pixel-art production is not supported by this family. Do not use pixel-art
prompts, nearest-neighbor resampling, or a pixelated filter to disguise
ordinary illustration.

## Provider and Reference Preconditions

Honor the request's provider exactly. Never silently switch among `native`,
`codex`, `gemini`, or `openai`.

- With no `references`, generate the one source sheet from the brief and
  declared item list.
- With references, validate every path is readable before generation, preserve
  its `canonical`, `style`, or `screen` role in the trace, and pass each real
  image as provider image input. Passing a path only in text is not attachment.
- For `codex`, call the image provider with the actual reference files through
  `referenced_image_paths`; omit that parameter only when there are no
  references. For `gemini` and `openai`, use the reference-input path of
  `tools/asset_source_generate.py`. If the pinned provider cannot accept a
  required reference image, STOP before output rather than changing provider.
- For `native`, use its declared native generation path. If that path cannot
  receive the required reference attachment, STOP before output.

Archive the raw provider sheet at
`.godotmaker/asset-generation/sources/<bundle_id>_source.png` and write its
source report at
`.godotmaker/asset-generation/reports/<bundle_id>_source.json`. The report
records `raw_source`, `reference_inputs`, and `provider_trace`. Each reference
record has `role`, `path`, `sha256`, and `attached: true`; `provider_trace`
records the actual coding provider/model/reasoning, `image_provider`, visible
`image_model_identity` (or `not_exposed_by_subscription_runtime` when that is
the runtime's truthful limit), provider tool-call id, and its real
image-attachment field (for Codex, `referenced_image_paths`). Use these exact
keys: `coding_provider`, `coding_model`, `reasoning`, `image_provider`,
`image_model_identity`, `tool_call_id`, and `referenced_image_paths`. The call
id must be the id emitted by the actual image-generation tool, not an invented
label; each attached path must be the same real image passed to that call.
With no references, retain an empty `reference_inputs` array. Include the
actual prompt, payload claim, readable-file checks, and attachment provenance.
Never fabricate any of those records.

## Production Loop

1. Before any provider call, validate the request, declared slots, source
   paths, and reference inputs. Each logical prop name must satisfy the shared
   cross-platform safe-identifier rule (one non-reserved path segment; no
   separator, device name, control character, or trailing dot). STOP only for
   a missing or unreadable required input, an unsupported or contradictory
   request, a provider/reference attachment that is objectively unavailable,
   or an unrecoverable environment or permission error.
2. Make one real provider image request for a separated source sheet containing
   the whole ordered prop list. Specify shared style, lighting, perspective,
   plentiful gaps between objects, a solid `#FF00FF` background, and no text,
   labels, UI, floor plane, borders, or grid. Archive the raw provider PNG.
3. Process that sheet with `asset_sheet_process.py --snap-mode autoslice`,
   `--background magenta`, `--padding 2`, and `--min-component-area 100`; never
   pass `--grid` to autoslice. The shared cleanup removes strict-key holes,
   then iteratively mattes a spill edge only when it matches a neighbouring
   foreground/background composite; it does not delete purple or blue-purple
   pixels merely for touching transparency.
   Write the cleaned transparent sheet using
   `--processed-out`, candidates, AABB report, and report JSON. Supply `--names`
   in source-sheet reading order. A count mismatch returns `needs_regeneration`
   with no candidate or processed-sheet output: inspect spacing, names, or
   source output and regenerate or repair instead of treating it as a final
   failure.
4. Curate the named candidates with `tools/asset_curation_select.py`. Preserve
   the selection and rejection reasons. For every selected prop, call
   `tools/asset_image_finalize.py --resize <slot_width>x<slot_height> --no-origin`
   into its declared `normalized/` source. The matte has already made the
   candidates transparent, so do not re-key the tight candidate crop here. This
   preserves aspect ratio, centers art, and adds transparent padding without writing a shared
   `assets/origin/<name>.png`; do not resize the whole source sheet before
   slicing.
5. Assemble only the finalized sources with `asset_atlas_assemble.py`. Its
   stable atlas and metadata must contain the exact declared regions. Compile
   every region independently through
   `.godotmaker/asset-runtime/asset_compiler/atlas_texture.py` with only
   `metadata_path` and `logical_asset_id` as compiler spec.
6. Run `standalone_validation.compile_and_validate()` for L0-L4. It verifies
   the exact declaration/result binding, decodable transparent RGBA atlas,
   per-slot visible content and transparent padding, no opaque magenta, native
   compilation, headless Godot loading, shared atlas path, exact regions, and
   zero margins. Read any diagnostic, repair the source, processing parameters,
   metadata, or artifact, then re-run the applicable checks. Mark ready only
   when every L0-L4 check passes.

Use the existing deterministic tools first. You may use a temporary image
tool, drawing command, SVG/canvas, script, or Godot drawing to diagnose or
repair a run when needed. Record its reason, command or code, inputs, outputs,
modified files, diagnostics, and post-repair results in the trace. Tool names
are not a STOP condition; invented provider calls, reference attachments, or
validation evidence are.

## Result registration

The standalone result remains free of tag and registration state. After L0-L4
passes, return the complete named AtlasTexture result. The fixed request slots
are its output contract; `/gm-asset` validates the result and atomically records
every prop in its matching `ASSETS.md` row.

## Evidence and Result

Keep the raw source, transparent processed sheet, candidate/AABB report,
curation report, every finalized PNG/report, declaration, atlas, metadata,
compiled `.tres` files, source/provider report, command trace, and L0-L4
diagnostics. Before returning, serialize the exact shared result to
`.godotmaker/asset-generation/work/<bundle_id>/result.json` and validate it
with `tools/asset_skill_contract_check.py --kind result`. Return that checked
JSON byte-for-byte: `outputs` must be the complete array of one named
`AtlasTexture` per logical prop, never a prose count or summary. A real STOP
has no fake output or ready entry and states the actual blocking condition.

See `samples/result/market-props.json` for the shared atlas/result shape.
