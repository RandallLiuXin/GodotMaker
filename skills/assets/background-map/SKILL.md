---
name: background-map
description: Generate and validate a fixed-viewport background, map base, or parallax plate as a ready-to-load Texture2D.
---

# Background Map Asset

Use this skill for a runtime background, map base, parallax plate, fixed battle
background, title illustration, or other fixed-viewport scenic asset. Do not
use it for scene references, actors, foreground props, UI, or collision-bearing
geometry.

## Invocation

Accept one asset request matching the shared Asset Skill request schema in
`skills/assets/_shared/schema/asset-skill-request.schema.json`. Require
`asset_type` to be `background-map`. Validate the returned document against the
shared result schema and checker before returning it.

This skill can be invoked directly or by an orchestrator; its request and
result are identical in both cases. Do not read or write `ASSETS.md`, tags,
stage state, generated manifests, or dispatch state.

## Produce

1. Use the brief and visible style or screen references to establish the scene
   role, viewpoint, target aspect, orientation, layer responsibility, and
   style language.
2. Generate a source image with no gameplay actors, pickups, hazards, UI,
   labels, or text.
3. Finalize the accepted image at the stable path
   `res://assets/generated/background-map/<asset_id>/<asset_id>.png` after
   checking the requested aspect and dimensions.
4. Verify that Godot can import and load that PNG as `Texture2D`.

Godot's normal PNG import is the native resource path for this family; do not
create a redundant `.tres` merely to wrap the image.

## Result

Return the shared generic result with one `runtime` output:

```json
{
  "asset_type": "background-map",
  "outputs": [{
    "role": "runtime",
    "name": "<asset_id>",
    "path": "res://assets/generated/background-map/<asset_id>/<asset_id>.png",
    "godot_type": "Texture2D"
  }],
  "sources": [{
    "path": "res://assets/generated/background-map/<asset_id>/<asset_id>.png",
    "layout": "single"
  }],
  "previews": [],
  "validation": {
    "passed": true,
    "levels": {"L0": true, "L1": true, "L2": true, "L3": true, "L4": true}
  }
}
```

Use the requested stable asset id in every path. A failed aspect, import, or
load check must return `validation.passed: false` with an explanatory note;
never claim a failed background is ready.
