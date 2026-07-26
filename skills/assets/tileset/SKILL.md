---
name: tileset
description: Generate a tile atlas and compile its explicit recipe into a native Godot TileSet resource. Use for reusable terrain, wall, floor, obstacle, and animated tile libraries; not for designing a TileMap layout.
---

# TileSet Asset Skill

Produce one reusable TileSet from a processable atlas image and a fully declared
TileSet recipe. This skill is standalone: a direct user request and any caller
use the same request and result contract.

## Contract

Read and enforce the common request and result contract in
`.godotmaker/asset-runtime/asset-skill-contract.md`. Accept only a request whose
`asset_type` is `tileset`; require a stable `asset_id`, a concise `brief`, and
an explicit `spec`. Return the common result object with:

```json
{
  "asset_type": "tileset",
  "outputs": [{
    "role": "runtime",
    "path": "res://assets/generated/tileset/<asset_id>/<asset_id>.tres",
    "godot_type": "TileSet"
  }],
  "sources": [{
    "path": "res://assets/generated/tileset/<asset_id>/<asset_id>_atlas.png",
    "layout": "tile_atlas"
  }],
  "previews": [],
  "validation": {"passed": true, "levels": {"L0": true, "L1": true, "L2": true, "L3": true, "L4": true}}
}
```

The shared contract permits multiple logical outputs, but this v1 TileSet skill
supports exactly one runtime output: the `TileSet` above. It rejects any extra
runtime output at L0 rather than marking an uncompiled or unvalidated resource
as ready. Reference outputs remain allowed by the shared contract and do not
enter runtime L2-L4 validation.

Do not read or require tags, stage state, `ASSETS.md`, either generated
manifest, or any `/gm-asset` mode. Do not register outputs or decide worker
dispatch. Those are caller responsibilities outside this skill.

## Tile Atlas Source Contract

Generate or claim a single atlas PNG under
`assets/generated/tileset/<asset_id>/`. The atlas must be deliberately laid out
for the recipe, not merely visually tile-like:

- Declare the atlas cell size, margins, separation, and every usable cell.
- Use a square orthogonal atlas as the mature v1 path. Other Godot tile shapes
  require an explicit supported recipe and are not inferred from pixels.
- Keep tiles aligned to their declared grid. Leave unused grid cells absent from
  `sources[].tiles`; never discover tiles by transparency, connected regions,
  color, or filenames.
- Include a fixed visual reference when style continuity matters. References
  guide source generation but never replace the declared tile semantics.
- Prompt for coherent edge treatment, readable walkable and blocking surfaces,
  consistent lighting, and no labels or UI text. The prompt must name the tile
  size, grid coverage, intended terrain variants, and any animated cells.

The image does not declare collision, navigation, terrain connectivity, or map
layout. It only provides pixels for the explicit recipe below.

## Explicit Recipe

Put all runtime semantics in `request.spec`, using the exact field shapes
accepted by `.godotmaker/asset-runtime/asset_compiler/tileset.py`. The minimum
recipe is:

```json
{
  "godot_path": "/path/to/godot",
  "tile_shape": "square",
  "tile_size": [16, 16],
  "sources": [{
    "id": 0,
    "texture": "res://assets/generated/tileset/grassland/grassland_atlas.png",
    "region_size": [16, 16],
    "margins": [0, 0],
    "separation": [0, 0],
    "tiles": [{"coords": [0, 0]}]
  }]
}
```

`tile_shape` is one of `square`, `isometric`, `half_offset_square`, or
`hexagon`; v1 verification is deepest for `square`. Each source has a unique
non-negative `id`, a `res://` texture path, and an explicit `tiles` list. Each
tile supplies `coords` and may declare `texture_origin`, `z_index`,
`y_sort_origin`, `probability`, `terrain_set`, `terrain`, `peering_bits`,
`custom_data`, collision polygons, navigation polygons, occlusion polygons,
alternatives, and animation.

At TileSet scope, explicitly declare any `physics_layers`,
`navigation_layers`, `occlusion_layers`, `custom_data_layers`, and
`terrain_sets`. Terrain peering bits, polygons, custom data, alternatives, and
animation timing are recipe data. Never infer them from the atlas image.

TileSet v1 custom data is deliberately limited to Godot's scalar Variant
types: `NIL` (type `0`, value `null`), `bool` (`1`), `int` (`2`), `float`
(`3`, finite JSON number), and `String` (`4`). Each `custom_data[].value` must
match the declared layer type exactly; arrays, objects, resources, vectors, and
all other Variant types are outside v1 and must be rejected before Godot runs.
Only one custom-data value and one terrain peering bit may be declared per
layer/bit on a tile or alternative. Polygon layers and terrain references must
refer to declared layer and terrain indexes.

An animation declares `mode` (`default`, `random_start_times`, or `max`),
positive `frames_count`, positive `columns`, non-negative `separation`,
positive `speed`, and optional continuous `frame_durations`. Each alternative
has a positive integer `id`.

See `fixtures/orthogonal-square-recipe.json` for the representative orthogonal
square fixture, including one terrain tile, one collision polygon, and an
explicit alternative.

## Processing and Validation

1. Validate the request with the shared contract checker and reject an
   `asset_type` other than `tileset`.
2. Produce or claim the atlas at its stable path and verify the file exists
   (L1). Do not create versioned, timestamped, or work-directory outputs.
3. Construct the recipe solely from supplied declarations. Reject incomplete,
   ambiguous, out-of-contract, or implicit semantic input.
4. Register `asset_compiler.tileset.register_into()` on a per-run
   `CompilerRegistry`, then compile the `tile_atlas` to `TileSet` route. The
   shared registry owns staging and atomic commit; this skill does not write a
   hand-authored `.tres` (L2).
5. Run `standalone_validation.compile_and_validate()` for the standalone path.
   Its L0 runs the shared request/result checker only; it does not construct or
   read a stable entry. Its L1 verifies every declared atlas source. For every
   call it creates a fresh `CompilerRegistry`, registers
   `asset_compiler.tileset.register_into()`, and compiles the declared
   `tile_atlas` to `TileSet` route (L2). It then uses `GodotProbe` to load the
   returned runtime path as `TileSet` (L3), creates a fresh
   `StructureValidatorRegistry`, and registers
   `asset_validation.tileset.register_into()` to compare the loaded source,
   tile, alternative, animation, layer, terrain, polygon, and custom-data
   structure against the declared recipe (L4).
6. The standalone runner maps those five outcomes to
   `result.validation.levels` and returns a shared-contract result. It reports
   a failed validation result for L1-L4 failures; an invalid L0 request/result
   pair is rejected before there is a valid result to return. Do not claim
   runtime readiness from source-image quality.

## Delivery

Report the stable atlas and `.tres` paths, the declared TileSet shape and tile
size, the number of sources and tiles, and the L0-L4 validation outcome. State
any intentionally omitted semantics (for example, no terrain set or navigation
layer) rather than making assumptions. A TileSet is a reusable tile library;
creating or painting a `TileMap` is outside this skill.
