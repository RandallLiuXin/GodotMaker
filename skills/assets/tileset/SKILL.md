---
name: tileset
description: Generate a fixed-profile terrain atlas and compile it into a native Godot TileSet. Use for reusable terrain libraries, never for designing a TileMap.
---

# TileSet Asset Skill

Produce one reusable square TileSet from a real source atlas. This production path supports hand-painted, illustrated, or rendered terrain art; pixel art is not supported. It is standalone: direct callers use the same request and result contract as callers higher in the pipeline.

## Contract

Read and enforce `.godotmaker/asset-runtime/asset-skill-contract.md`. Accept only `asset_type: "tileset"`, a stable `asset_id`, a concise `brief`, and an explicit `spec`. Return one runtime result at:

```json
{
  "asset_type": "tileset",
  "outputs": [{"role": "runtime", "path": "res://assets/generated/tileset/<asset_id>/<asset_id>.tres", "godot_type": "TileSet"}],
  "sources": [{"path": "res://assets/generated/tileset/<asset_id>/<asset_id>_atlas.png", "layout": "tile_atlas"}],
  "previews": [],
  "validation": {"passed": true, "levels": {"L0": true, "L1": true, "L2": true, "L3": true, "L4": true}}
}
```

Do not read or require tags, stage state, `ASSETS.md`, either generated
manifest, or any `/gm-asset` mode. Do not register outputs or decide worker dispatch. Those are caller responsibilities outside this skill.

## Fixed Terrain Profiles

Production supports exactly these versioned profiles:

| Profile | Atlas grid | Required painted slots | Godot terrain mode | Use when |
| --- | --- | --- | --- | --- |
| `marching_squares_15` | 4x4 | 15; `(0,0)` remains transparent | Match Corners (`1`) | Rule-based roads, floors, walls, and simple boundaries |
| `blob_47` | 8x6 | 47; `(7,5)` remains transparent | Match Corners and Sides (`0`) | Natural ground, caves, shorelines, and detailed inner/outer corners |

`spec.autotile_profile` is required. If an interactive caller omits it, ask whether the request needs simple rule-based boundaries or natural detailed corners, make a recommendation from the brief, and wait for the selection. If the caller cannot answer, STOP before provider work. Never guess, fall back, or accept another profile.

`tools/asset_tileset_profile.py` is the fixed source of truth for slot coordinates and peering bits. Provider guides, final atlas validation, recipe generation, and compiler input must derive from that one implementation. Agents must not enumerate 15/47 cells or hand-write `.tres` resources.

The profile generator emits `tile_size`, `margins`, `separation`, `terrain_sets`, and `peering_bits` deterministically. Physics, navigation, occlusion, custom data, alternatives, and animation are request-specific. Do not infer collision polygons, navigation polygons, occlusion polygons, terrain names, or animation from pixels. Never infer them from the atlas image. The compiler supports `NIL`, bool, int, float, and String custom data; all other Variant types are outside v1. Alternatives retain their relative
weight, and Unknown or misspelled
fields are rejected.

## References, Provider, And Trace

References are optional. With references, resolve every `res://` path against the project root, verify it is readable, preserve its `canonical`, `style`, or `screen` role, and attach the actual image to the selected provider. A textual path is not an attachment. If attachment fails, STOP.

Honor `provider` exactly: `native`, `codex`, `gemini`, and `openai` never fall back to another provider. For Codex, call image generation with `referenced_image_paths` containing every readable local reference. Use `asset_source_generate.py` for Gemini/OpenAI API-backed generation; Codex and native use their provider documents and controlled claim path.

Retain provider/model/reasoning, prompt, raw source, reference roles and paths, actual attachments, provider payload or tool trace, processing reports, commands or code, diagnostics, repairs, inputs, outputs, and modified files under `.godotmaker/asset-generation/`. Do not hand-write provider provenance. Diagnostic tools beyond the owned tools are allowed when needed, but the trace must explain why they were used and what recheck passed afterward.

## Deterministic Production

1. Create the exact profile manifest and provider-facing labeled guide with `asset_tileset_profile.py`; do not make a generic numbered grid. The guide is not art and is not a runtime output:

   ```powershell
   python tools/asset_tileset_profile.py --profile <marching_squares_15|blob_47> `
     --manifest-out .godotmaker/asset-generation/work/<asset_id>_profile.json `
     --guide-out .godotmaker/asset-generation/work/<asset_id>_profile_guide.png
   ```
2. Generate or claim one real provider source sheet. It must fill every required profile slot, preserve the reserved transparent slot, and contain no labels, UI, actors, or text. Preserve the provider image unchanged as raw source.
3. Use `asset_sheet_process.py --snap-mode grid --preserve-cell-bounds` to split the source sheet. Use `asset_image_finalize.py` for transparent-background, AABB, alignment, or scale repair when diagnostics require it. Reassemble the fixed atlas with `asset_atlas_assemble.py`.
4. Validate the final atlas and generate the full low-level recipe and native resource with one command:

   ```powershell
   python tools/asset_tileset_profile.py `
     --profile <marching_squares_15|blob_47> `
     --atlas assets/generated/tileset/<asset_id>/<asset_id>_atlas.png `
     --texture res://assets/generated/tileset/<asset_id>/<asset_id>_atlas.png `
     --tile-size <width>x<height> `
     --godot-path <godot-executable> `
     --terrain-name <terrain-name> `
     --recipe-out .godotmaker/asset-generation/work/<asset_id>_tileset_recipe.json `
     --report .godotmaker/asset-generation/reports/<asset_id>_profile.json `
     --project-root . `
     --asset-id <asset_id> `
     --artifact res://assets/generated/tileset/<asset_id>/<asset_id>.tres
   ```

   The command rejects a wrong atlas size, empty required slot, or non-empty reserved slot before it emits a recipe. It then calls the existing native TileSet compiler. Replacing atlas art means rerunning this command, not asking an agent to rebuild metadata.
5. Apply only explicit request-specific semantic overrides to the generated recipe. The base recipe declares one square source, zero margins and separation, profile terrain set/terrain `0`, and all fixed peering bits.
6. Run `standalone_validation.compile_and_validate()`. It uses `asset_compiler.tileset.register_into()` and `asset_validation.tileset.register_into()` on fresh registries. Its L0 checks the public contract; L1 checks the atlas; L2 compiles; L3 loads the returned TileSet in headless Godot; and L4 compares the loaded source, tile, terrain, polygon, custom-data, alternative, and animation structure to the generated recipe.

An L1-L4 diagnostic is a repair loop, not a final result. Read the failure, repair source art, processing parameters, metadata, or resource, and re-run the applicable checks. Do not use a fixed retry count. Only missing/damaged required input, unavailable declared provider/reference attachment, contradictory request, unsupported profile, or unrecoverable environment failure is a STOP.

## Delivery

Return only the generic result JSON. `validation.passed` can be true only after all applicable L0-L4 checks passed. Report the selected profile, stable atlas and `.tres` paths, tile size, and intentionally omitted semantics in retained trace evidence. A TileSet is a reusable tile library; creating or painting a `TileMap` is outside this skill.
