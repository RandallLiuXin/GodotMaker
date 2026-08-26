---
name: tileset
description: Generate a fixed-profile terrain atlas and compile it into a native Godot TileSet. Use for reusable terrain libraries, never for designing a TileMap.
---

# TileSet Asset Skill

Produce one reusable square TileSet from a real source atlas. This production path supports hand-painted, illustrated, or rendered terrain art. It is standalone: direct callers use the same request and result contract as callers higher in the pipeline.

## Contract

Read and enforce `.godotmaker/asset-runtime/asset-skill-contract.md` and `schema/request.schema.json`. Read the caller input from `ASSET_REQUEST.json`. Accept only `asset_type: "tileset"`, a stable `asset_id`, a concise `brief`, optional visible art references, and the typed family `spec`. The caller never supplies output paths, compiler recipes, profile coordinates, or processing commands. Return the deterministic runtime result at:

```json
{
  "asset_type": "tileset",
  "outputs": [{"role": "runtime", "name": "<asset_id>", "path": "res://assets/generated/tileset/<asset_id>/<asset_id>.tres", "godot_type": "TileSet"}],
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

`spec.autotile_profile` is required for declarative JSON. If an interactive caller asks for a TileSet without selecting it, ask whether the request needs simple rule-based boundaries for roads, floors, or walls, or detailed natural inner and outer corners for shorelines, caves, and irregular ground. Recommend one profile from the brief, then wait for a selection of `marching_squares_15` or `blob_47`. If the caller cannot answer, STOP before provider work. Never guess, fall back, or accept another profile.

`tools/asset_tileset_profile.py` is the fixed source of truth for slot coordinates, edge signatures, and peering bits. Provider guides, final atlas validation, recipe generation, and compiler input must derive from that one implementation. Agents must not enumerate 15/47 cells or hand-write `.tres` resources.

The profile generator emits `tile_size`, `margins`, `separation`, `terrain_sets`, and `peering_bits` deterministically. Physics, navigation, and custom data may be declared in `spec.semantic_metadata`; they are applied only to named semantic roles such as `foreground_full` or `foreground_isolated`, never inferred from pixels. In `blob_47`, the no-peering-bit slot is the isolated current terrain, not a complete background tile. This Skill does not support animated TileSets, occlusion, or alternatives. Unknown or misspelled fields are rejected.

## References, Provider, And Trace

References are optional caller-provided visual inputs, never profile definitions. With references, resolve every `res://` path against the project root, verify it is readable, preserve its `canonical`, `style`, or `screen` role, and attach the actual image to the selected provider. A textual path is not an attachment. If attachment fails, STOP. Use a style reference for its material, color, linework, and visual language; do not copy its unrelated scene composition.

Honor `provider` exactly: `native`, `codex`, `gemini`, and `openai` never fall back to another provider. For Codex, call image generation with `referenced_image_paths` containing every readable local reference. Before the call, write a one-item plan with `require_provider_trace: true` and source target `.godotmaker/asset-generation/source/<asset_id>_provider.png`. After the call, write a generated-path report containing the actual image path, the Codex tool-call identity, configured coding model/reasoning, image-model identity (or `not_exposed_by_subscription_runtime`), every reference role, and the exact attached paths. Then claim it with `python .godotmaker/asset-runtime/tools/codex_image_claim.py --plan <plan.json> --report <generated-paths.json> --project-root . --out-report .godotmaker/asset-generation/reports/<asset_id>_source.json`. Missing or incomplete provider trace is a STOP; never copy a generated image directly into the project. Use `asset_source_generate.py` for Gemini/OpenAI API-backed generation.

Retain the controlled claim result, prompt, raw source, reference roles and paths, processing reports, commands or code, diagnostics, repairs, inputs, outputs, and modified files under `.godotmaker/asset-generation/`. Do not hand-write provider provenance. Diagnostic tools beyond the owned tools are allowed when needed, but the trace must explain why they were used and what recheck passed afterward.

## Deterministic Production

1. Create the exact built-in profile manifest and labeled processing guide with `asset_tileset_profile.py`; do not make a generic numbered grid. The guide is not caller input, provider reference, art, or a runtime output:

   ```powershell
   python tools/asset_tileset_profile.py --profile <marching_squares_15|blob_47> `
     --manifest-out .godotmaker/asset-generation/work/<asset_id>_profile.json `
     --guide-out .godotmaker/asset-generation/work/<asset_id>_profile_guide.png
   ```
2. Generate and claim one real provider material source. Use the request brief and attached caller art references; request the two named materials without a tile grid, labels, topology diagram, UI, actors, or text. Preserve the controlled claimed source unchanged.
3. Use `asset_image_finalize.py` for transparent-background, AABB, alignment, or scale repair when diagnostics require it. Recompose the fixed profile from the retained provider image's two material regions; code owns every transition mask and reserved transparent slot:

   ```powershell
   python tools/asset_tileset_profile.py --request ASSET_REQUEST.json `
     --tile-size <width>x<height> `
     --material-source .godotmaker/asset-generation/source/<asset_id>_provider.png `
     --composed-atlas-out assets/generated/tileset/<asset_id>/<asset_id>_atlas.png `
     --composition-report .godotmaker/asset-generation/reports/<asset_id>_material_composite.json
   ```

   Retain the composition report and re-run the normal profile command with `--enforce-seams`. Never hand-write or overlay isolated diagnostic regions; a visually flat patch is not a valid seam repair.
4. Validate the final atlas and generate the full low-level recipe and native resource from the public request with one command:

   ```powershell
   python tools/asset_tileset_profile.py `
     --request ASSET_REQUEST.json `
     --atlas assets/generated/tileset/<asset_id>/<asset_id>_atlas.png `
     --texture res://assets/generated/tileset/<asset_id>/<asset_id>_atlas.png `
     --godot-path <godot-executable> `
     --recipe-out .godotmaker/asset-generation/work/<asset_id>_tileset_recipe.json `
     --report .godotmaker/asset-generation/reports/<asset_id>_profile.json `
     --enforce-seams `
     --project-root . `
     --asset-id <asset_id> `
     --artifact res://assets/generated/tileset/<asset_id>/<asset_id>.tres
   ```

   The command rejects a wrong atlas size, empty required slot, non-empty reserved slot, or a terrain-corner material mismatch before it emits a recipe. Its retained seam diagnostics name every bad tile and corner. It then calls the existing native TileSet compiler. Replacing atlas art means rerunning this command, not asking an agent to rebuild metadata.
5. `--request` maps only explicit `semantic_metadata` role overrides into the generated recipe. The base recipe declares one square source, zero margins and separation, profile terrain set/terrain `0`, and all fixed peering bits. Never hand-write a `.tres` or expose recipe fields to the caller.
6. Run `standalone_validation.compile_and_validate()` with the generated recipe. It uses `asset_compiler.tileset.register_into()` and `asset_validation.tileset.register_into()` on fresh registries. Its L0 checks the public request contract; L1 checks the atlas; L2 compiles; L3 loads the returned TileSet in headless Godot; and L4 compares the loaded source, tile, terrain, polygon, and custom-data structure to the generated recipe.

When `GM_EVAL_GODOT_PATH` is present, use that exact executable as `--godot-path`; do not search the disk for another Godot installation. In standalone published workspaces, `asset_tileset_profile.py --artifact` loads `.godotmaker/asset-runtime` directly; do not bypass it with a hand-written compiler bridge.

An L1-L4 diagnostic is a repair loop, not a final result. Read the failure, repair source art, processing parameters, metadata, or resource, and re-run the applicable checks. Do not use a fixed retry count. Only missing/damaged required input, unavailable declared provider/reference attachment, contradictory request, unsupported profile, or unrecoverable environment failure is a STOP.

## Delivery

Return only the generic result JSON. `validation.passed` can be true only after all applicable L0-L4 checks passed. Report the selected profile, stable atlas and `.tres` paths, tile size, and intentionally omitted semantics in retained trace evidence. A TileSet is a reusable tile library; creating or painting a `TileMap` is outside this skill.
