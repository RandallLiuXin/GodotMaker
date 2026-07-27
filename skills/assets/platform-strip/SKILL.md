---
name: platform-strip
description: Generate collision-aligned horizontal platform pieces as Texture2D segments or explicitly declared AtlasTexture regions.
---

# Platform Strip Asset

Use this skill for floors, bridges, platforms, rails, pipes, long hazards,
terrain chunks, and other collision-aligned horizontal pieces. Do not use it
for characters, enemies, UI, compact props, or full scenic backgrounds.

## Invocation

Accept one asset request matching the shared Asset Skill request schema in
`.godotmaker/asset-runtime/schema/asset-skill-request.schema.json`. Require
`asset_type` to be `platform-strip`. `spec` is `{ "kind": "single" | "atlas",
"segments": [{"name": "..."}] }`; it declares the complete logical segment
set. Run `standalone_validation.compile_and_validate()` before returning it.
The runner binds every segment to its stable Texture2D or AtlasTexture path,
executes the applicable compiler route, then runs real headless Godot L3/L4.
It begins from the shared result schema and checker, then proves the result.

This skill can be invoked directly or by an orchestrator with the same contract.
Do not read or write `ASSETS.md`, tags, stage state, generated manifests, or
worker dispatch state.

## Produce

1. From the brief, declare the segment list: left cap, repeat middle, right
   cap, plus any explicitly requested slope or variant. Keep a walkable top
   edge and y-position consistent across compatible cells.
2. Generate a source with a solid `#FF00FF` background and no actors, UI,
   text, or labels. Process fixed cells with an explicitly declared grid; do
   not infer segmentation from a loose collage.
3. For a selected independent segment, publish its PNG at
   `res://assets/generated/platform-strip/<asset_id>/<segment>.png` and return
   it as `Texture2D` through Godot's default import.
4. For a shared strip atlas, assemble a physical PNG from declared fixed slots
   and publish exact region metadata. Compile every logical region to its own
   `.tres` `AtlasTexture` with zero margin. Do not use automatic packing,
   trimming, heuristic region discovery, or an undeclared region.
5. Load the declared result in Godot and validate its reported resource type.
   The public runner, rather than a self-reported validation object, owns this
   L0-L4 verdict.

## Result

Return the shared generic result. Each output is either:

- a `runtime` `Texture2D` PNG for an independent segment; or
- a `runtime` `AtlasTexture` `.tres` for a declared region of one physical
  strip atlas.

For an atlas result, include the physical PNG in `sources` with
`layout: "region_atlas"`; do not expose the PNG as a substitute for its
`AtlasTexture` region. A representative atlas result is:

```json
{
  "asset_type": "platform-strip",
  "outputs": [{
    "role": "runtime",
    "name": "bridge_middle",
    "path": "res://assets/generated/platform-strip/wood_bridge/bridge_middle.tres",
    "godot_type": "AtlasTexture"
  }],
  "sources": [{
    "path": "res://assets/generated/platform-strip/wood_bridge/wood_bridge.png",
    "layout": "region_atlas"
  }],
  "previews": [],
  "validation": {
    "passed": true,
    "levels": {"L0": true, "L1": true, "L2": true, "L3": true, "L4": true}
  }
}
```

If a grid, declared segment, atlas region, or Godot type check fails, return
`outputs: []` with `validation.passed: false` and explanatory notes. The shared
result contract accepts an empty output list only for this failed state, so the
strip never implies it can be used safely.
