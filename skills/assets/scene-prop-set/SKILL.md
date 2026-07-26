# Scene Prop Set

Produce a standalone atlas-backed set of foreground props derived from a
scene, map, or stage reference. Use it when the source reference determines
the object list and visual invariants. Do not use it for generic compact packs,
backgrounds, UI, characters, effects, terrain, or scene placement.

## Contract

Accept the shared asset request contract from
`skills/assets/_shared/asset-skill-contract.md` with
`asset_type: "scene-prop-set"`. The family-specific `spec` declares one
physical atlas and fixed logical-object slots:

```json
{
  "atlas": {
    "width": 256,
    "height": 128,
    "slots": [
      { "name": "market_stall", "rect": [0, 0, 96, 96], "source": "market_stall.png" },
      { "name": "signpost", "rect": [112, 0, 32, 64], "source": "signpost.png" }
    ]
  }
}
```

Every slot name is a logical scene-prop id. Rectangles are explicit,
positive, non-overlapping pixel rectangles in `[x, y, width, height]` form.
The Skill never auto-packs, trims, detects, or discovers a region.

The physical atlas and its metadata use these stable paths:

```text
res://assets/generated/scene-prop-set/<asset_id>/<asset_id>.png
res://assets/generated/scene-prop-set/<asset_id>/<asset_id>.json
```

Every logical scene prop receives a separate stable runtime resource:

```text
res://assets/generated/scene-prop-set/<asset_id>/<logical_prop_id>.tres
```

Return the shared asset-result object with one `runtime` output per slot,
`godot_type: "AtlasTexture"`, and one shared `region_atlas` PNG source. Output
names exactly equal the corresponding metadata region names. The result is
standalone: it contains no tags, manifests, stages, scene placement, gameplay
objects, or worker-dispatch details.

## Processing

1. Make the supplied scene or map reference visible when the selected provider
   supports it, and derive only the requested object list and visual invariants.
2. Generate or claim a transparent RGBA PNG for each declared object. Preserve
   its exact declared slot dimensions and alpha; do not retain a solid
   chroma-key background, labels, UI, or annotations.
3. Use `tools/asset_atlas_assemble.py` to build the one physical PNG and its
   adjacent metadata from explicit fixed slots. The written metadata is the
   only source for runtime regions.
4. Use `skills/assets/_shared/asset_compiler/atlas_texture.py` once per region
   to compile an independent `AtlasTexture`. Pass its `metadata_path` and the
   exact logical region name; the `.tres` filename must match that name.
5. Run shared L0-L4 validation per output. L4 must prove the loaded resource
   refers to the shared atlas, retains its exact declared region, and has a
   zero margin.
6. Return every requested logical output only when it validates. Fail closed
   if a region is absent or invalid; never return the entire atlas as one prop.

Common schema processing, compiler routing, and validation are reused only
from `skills/assets/_shared/`; no family-local copy of a schema, compiler,
validator, packing, or trimming routine is permitted.

## Prompt Requirements

State the source-reference role, requested object names, reference-derived
visual invariants, visible style language, transparent background, and that no
text, UI, labels, or annotations may be generated.

## Example Result

See `samples/result/market-scene.json`, where three scene-derived logical
objects share a physical atlas while exposing independent runtime resources.
Their fixed metadata regions are in `samples/atlas/market-scene.json`.
