# Compact Prop Pack

Produce a standalone atlas-backed set of small, independently usable props:
pickups, crates, stones, bushes, pots, debris, small signs, and lamps. Do not
use this Skill for platforms, terrain, buildings, doors, gates, large trees,
or other wide, tall, collision-bearing assets.
It produces assets only: scene placement and gameplay objects are outside this
Skill.

## Contract

Accept the shared asset request contract from
`.godotmaker/asset-runtime/asset-skill-contract.md` with
`asset_type: "compact-prop-pack"`. The family-specific `spec` is the exact
JSON declaration passed to `tools/asset_atlas_assemble.py --declaration`; no
conversion or inferred fields are allowed:

```json
{
  "version": 1,
  "atlas": {
    "width": 192,
    "height": 64
  },
  "slots": [
    { "name": "coin", "rect": [0, 0, 32, 32], "source": "sources/coin.png" },
    { "name": "crate", "rect": [48, 0, 48, 48], "source": "sources/crate.png", "pivot": [0.5, 1.0] }
  ]
}
```

Every slot name is a logical prop id. Slot rectangles are explicit, positive,
non-overlapping pixel rectangles in `[x, y, width, height]` form. Do not
choose slots by packing, trimming, crop detection, or heuristic discovery.
`source` is a project-root-relative PNG path. `pivot` is optional and defaults
to `[0.5, 0.5]` through the assembler; when supplied it must be a two-value
coordinate from 0 to 1. The `version`, `atlas`, and top-level `slots` keys are
required exactly as shown.

The physical atlas and metadata have stable paths:

```text
res://assets/generated/compact-prop-pack/<asset_id>/<asset_id>.png
res://assets/generated/compact-prop-pack/<asset_id>/<asset_id>.json
```

Each logical prop has its own stable runtime output, even though all outputs
may share the one PNG:

```text
res://assets/generated/compact-prop-pack/<asset_id>/<logical_prop_id>.tres
```

The result follows the shared result schema. It includes one `runtime` output
per declared slot with `godot_type: "AtlasTexture"`, a single `region_atlas`
source for the physical PNG, and no pipeline registration fields. Result output
names exactly match the corresponding metadata region names.

## Processing

1. Use visible style or scene references when supplied. Otherwise use the
   request brief as the visual direction.
2. Generate or claim one transparent RGBA PNG for each declared prop. Keep
   each source at its declared slot size; transparent pixels remain transparent
   and no solid chroma-key background may survive into the atlas.
3. Assemble the physical PNG and its metadata only through
   `tools/asset_atlas_assemble.py`. Its declaration contains every slot's name,
   rectangle, source, and pivot. It is the source of the exact regions.
4. For every metadata region, compile one independent `AtlasTexture` through
   `.godotmaker/asset-runtime/asset_compiler/atlas_texture.py`, passing only
   `metadata_path` and that region's `logical_asset_id` in the compiler spec.
   The artifact filename must equal the logical id.
5. Run the shared L0-L4 validation ladder for every runtime output. L4 must
   confirm the exact declared region, the shared atlas path, and zero margin.
6. Return the shared result object only after every requested logical output
   passes. A failed or absent slot fails the invocation; do not substitute a
   whole-atlas texture or silently omit an output.

Common schema validation, atlas assembly, compiler routing, and L0-L4
 validation live exclusively in `.godotmaker/asset-runtime/`. This Skill does not
copy a schema, compiler, validator, or atlas-packing implementation.

## Prompt Requirements

State the prop list, shared environment style, lighting and perspective, clear
spacing, transparent background, and that no text, labels, UI, or floor plane
may be generated. Request only compact props appropriate to this family.

## Example Result

See `samples/result/market-props.json`. It demonstrates three logical props
that share one physical atlas and receive three independent `AtlasTexture`
outputs. Their fixed metadata regions are in `samples/atlas/market-props.json`.
