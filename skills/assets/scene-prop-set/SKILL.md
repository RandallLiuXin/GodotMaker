---
name: scene-prop-set
description: Generate non-pixel-art scene prop sets from one real source sheet and deliver fixed-slot AtlasTexture resources.
---

# Scene Prop Set Asset

Use this Skill for a set of standalone foreground props derived from a scene,
map, stage reference, or an explicit scene brief. It produces usable prop
resources only. It does not perform scene placement, PackedScene creation, TileMap editing,
collision, navigation, scripts, and gameplay behavior are outside this Skill.
Do not use it for pixel art, characters, UI, backgrounds, terrain, or generic
compact pickup packs.

## Contract

Accept the shared Asset Skill request schema at
`.godotmaker/asset-runtime/schema/asset-skill-request.schema.json` with
`asset_type: "scene-prop-set"`. Use the shared result schema and checker. This
Skill can be invoked directly or by an orchestrator with the same contract. Do
not read or write `ASSETS.md`, tags, stage state, or generated manifests.
Read `.godotmaker/asset-runtime/asset-skill-contract.md` before producing a
result; this family adds the source-sheet and atlas rules below.

`references` is optional. Without references, derive the visual direction and
complete object list from the written brief. With references, every path must be
a readable image, every declared role must be preserved, and the actual images
must be supplied to the pinned provider. A path mentioned only in prompt text is
not reference use. If the selected provider cannot attach a required image,
return STOP. Never silently change `native`, `codex`, `gemini`, or `openai` to
another provider. For Codex, call image generation with
`referenced_image_paths` containing every readable local reference image.

Reject pixel-art requests. Request painted, illustrated, or rendered
non-pixel-art source art. Do not use nearest-neighbor scaling or describe a
normal image as pixel art after processing.

The family-specific `spec` is the exact fixed-slot declaration passed to
`tools/asset_atlas_assemble.py --declaration` after source processing:

```json
{
  "version": 1,
  "atlas": {"width": 512, "height": 256},
  "slots": [
    {"name": "market_stall", "rect": [0, 0, 144, 128], "source": ".godotmaker/asset-generation/normalized/market-stall/market_stall.png", "pivot": [0.5, 1.0]},
    {"name": "lantern_post", "rect": [160, 0, 64, 160], "source": ".godotmaker/asset-generation/normalized/market-stall/lantern_post.png", "pivot": [0.5, 1.0]}
  ]
}
```

Slot rectangles are explicit, positive, and non-overlapping `[x, y, width,
height]` values. Their positions are never inferred or auto-packed. Autoslice
is allowed only to discover separated source candidates before assembly; it
must not invent semantic regions, merge touching props, or alter the declared
atlas slots. No automatic packing is permitted. `asset_atlas_assemble.py` writes canonical lexicographic metadata
region order; use it when compiling and reporting the resources. `source` names
the already-normalized image that will fill the declared slot. `pivot` is
optional and defaults to `[0.5, 0.5]`.

The shared physical atlas and metadata use stable paths:

```text
res://assets/generated/scene-prop-set/<asset_id>/<asset_id>.png
res://assets/generated/scene-prop-set/<asset_id>/<asset_id>.json
```

Every declared logical prop receives one independent runtime resource:

```text
res://assets/generated/scene-prop-set/<asset_id>/<logical_prop_id>.tres
```

Return one shared generic result with one `region_atlas` source and one
`runtime` `AtlasTexture` output per declared slot. Output names exactly equal
metadata region names. Internal processing reports and provenance remain
sidecar evidence, never extra keys in the generic result.

## Produce

1. Validate the request, provider, slot declaration, object names, and optional
   references before generation. A PackedScene request, unreadable required
   reference, unsupported provider attachment, contradictory request, or an
   invalid slot declaration is a real STOP. Do not ask the execution prompt to
   decide this outcome.
2. Generate one real provider source sheet for this `asset_id`, containing all
   requested props as visibly separated objects on a solid `#FF00FF`
   background. This is one image-generation attempt for the complete set,
   rather than separate per-slot provider calls. Require no text, labels, UI, actors, floor
   plane, grid lines, annotations, or watermarks. Keep the provider pixels
   unchanged at `.godotmaker/asset-generation/sources/<asset_id>_source.png`.
3. Record provenance through the pinned provider's controlled report or claim
   tool. For Codex, before the call write a one-item plan under
   `.godotmaker/asset-generation/` containing its exact project-relative
   `source_path`, **every** request reference as `{role, path}`, and
   `require_provider_trace: true` even when references is `[]`. After the one
   `image_gen` call, write its controlled generated-path report with `asset_id`,
   `generated_path`, `references`, and `provider_trace` containing provider,
   coding model, reasoning, image call identity, image-model identity, and the
   exact `referenced_image_paths` supplied to the call. Then run
   `.godotmaker/asset-runtime/tools/codex_image_claim.py --plan ... --report ...
   --project-root . --out-report .godotmaker/asset-generation/reports/<asset_id>_source.json`.
   The resulting claim must retain those fields, including empty reference lists
   for a no-reference request. Never hand-write provider provenance or set
   `require_provider_trace` false for this family. For API-backed providers, use
   `tools/asset_source_generate.py --spec` with its controlled report path.
4. Use the raw source sheet directly with the owned deterministic processor:

   ```powershell
   python tools/asset_sheet_process.py --source .godotmaker/asset-generation/sources/<asset_id>_source.png --out-dir .godotmaker/asset-generation/candidates/<asset_id> --names <declared-slot-names-in-reading-order> --asset-id <asset_id> --background magenta --snap-mode autoslice --report .godotmaker/asset-generation/reports/<asset_id>_autoslice.json
   ```

   Do not pass `--grid` to autoslice. The supplied names count must exactly
   equal the detected disconnected regions. `needs_regeneration`, touching
   props, split props, opaque magenta, an absent requested object, or an
   unreadable source is diagnostic evidence: repair the source layout, prompt,
   or processing parameters and re-run. Do not silently discard, merge, or
   publish partial candidates.
5. Run `tools/asset_curation_select.py` for every selected candidate, first
   writing its selected copy under
   `.godotmaker/asset-generation/selected/<asset_id>/<logical_prop_id>.png`.
   Preserve the shared autoslice/curation report, selected state, and source
   lineage. A selection failure is a repair diagnostic, not permission to
   substitute a different prop.
6. Run `tools/asset_image_finalize.py` separately for every selected prop with
   its declared slot size. For a slot named `<logical_prop_id>`, use the
   selected copy as `--source`, the declaration's `source` as `--out`,
   `--resize <slot-width>x<slot-height>`, `--background magenta`,
   `--label <logical_prop_id>`, `--no-origin`, and write
   `.godotmaker/asset-generation/reports/<asset_id>_<logical_prop_id>_finalize.json`.
   preserve aspect ratio and center the prop with transparent padding. Never
   resize the whole sheet before autoslice and never stretch a tall or wide prop
   to fill a slot.
7. Assemble only the normalized per-prop PNGs through
   `tools/asset_atlas_assemble.py`. It writes the stable atlas PNG and metadata
   at the paths above. The metadata is the only runtime authority for named
   regions and pivots.
8. Compile every metadata region with
   `.godotmaker/asset-runtime/asset_compiler/atlas_texture.py`, using the
   stable atlas, metadata path, and that exact logical region name. The output
   `.tres` filename must equal its logical prop id.
9. Run the controlled validation command below for applicable L0-L4. It owns
   the family `standalone_validation.py` binding, writes the returned generic
   result back to `<asset_id>-result.json`, and writes the identical evidence
   to the required validation report. It must use exactly `GM_EVAL_GODOT_PATH`
   or `GODOT_BIN` when configured:

   ```powershell
   $godotPath = if ($env:GM_EVAL_GODOT_PATH) { $env:GM_EVAL_GODOT_PATH } else { $env:GODOT_BIN }
   & $godotPath --headless --path . --import
   python tools/asset_scene_prop_set_validate.py --request ASSET_REQUEST.json --result .godotmaker/asset-generation/<asset_id>-result.json --report .godotmaker/asset-generation/reports/<asset_id>_validation.json --project-root . --godot-path $godotPath
   ```

   The visible import records the pinned engine in the trace; L3 then independently loads every
   AtlasTexture through the same pinned Godot binary. L0 binds the
   request/result, L1 verifies atlas and metadata delivery, L2 compiles, L3
   loads through headless Godot, and L4 verifies every AtlasTexture's shared
   atlas path, exact region, and zero margin. Read diagnostics, repair source,
   parameters, metadata, or artifacts, then repeat from the affected step.
   Return ready only after all applicable layers pass; the first check failure
   is never the final result unless it is a real STOP condition.

The project-owned deterministic tools above are the preferred processing path.
Diagnostic repair may also use Pillow, System.Drawing, ImageMagick, SVG,
canvas, Godot drawing, or a temporary script when necessary. Trace the reason,
command or code, inputs, outputs, modified files, diagnostics, and repair
result. Never fabricate provider calls, reference attachments, or validation
evidence. Repeated ad-hoc repairs are a follow-up improvement signal, not a
reason to stop this production run.

## Result And Handoff

Return exactly one shared generic result JSON object and no prose. A failed
result has `outputs: []`, `validation.passed: false`, and explanatory notes; it
must not expose partial runtime output.

For `/gm-asset`, persist the successful generic result at
`.godotmaker/asset-generation/<asset_id>-result.json`. The producer adapter
validates it, then runs `tools/asset_scene_prop_set_entry_draft.py` with the
first declared slot as the deterministic v1 primary artifact. The entry keeps
the shared `source_layout: region_atlas`, one real `godot_artifact:
AtlasTexture`, and `processing_status: ready`; the stable metadata and all
other independent AtlasTexture files remain the authoritative set inventory.
The Skill itself does not register entries or update stage documents.

See `samples/result/market-scene.json` and
`samples/atlas/market-scene.json` for the stable multi-output shape.
