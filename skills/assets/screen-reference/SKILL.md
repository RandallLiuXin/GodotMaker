---
name: screen-reference
description: Generate and validate a full-screen visual reference for scene direction and evaluation, without producing a runtime asset.
---

# Screen Reference Asset

Use this skill for full-screen scene references and visual evaluation targets.
It is reference-only: it does not create a runtime Godot resource, has no
`godot_artifact`, and must not enter worker runtime handoff.

## Invocation

Accept one asset request matching the shared Asset Skill request schema in
`skills/assets/_shared/schema/asset-skill-request.schema.json`. Require
`asset_type` to be `screen-reference`. Validate the returned document against
the shared result schema and checker before returning it.

This skill can be invoked directly or by an orchestrator with the same contract.
Do not read or write `ASSETS.md`, tags, stage state, generated manifests, or
worker dispatch state.

## Produce

1. Use the brief and visible references to describe the game genre, scene
   purpose, camera or viewpoint, gameplay-visible objects, approximate layout,
   requested HUD or UI elements, style language, target aspect, and orientation.
2. Generate one source image per requested scene. Do not add labels, callouts,
   debug overlays, or unrequested objects.
3. Finalize the accepted image at `references/<asset_id>.png` after checking
   the requested aspect and dimensions.
4. Preserve it as a visual reference only. Do not compile it to `Texture2D`,
   `AtlasTexture`, or any other native runtime resource.

## Result

Return the shared generic result with one `reference` output, no `godot_type`,
and no runtime outputs:

```json
{
  "asset_type": "screen-reference",
  "outputs": [{
    "role": "reference",
    "name": "<asset_id>",
    "path": "references/<asset_id>.png"
  }],
  "sources": [],
  "previews": [],
  "validation": {
    "passed": true,
    "levels": {"L0": true, "L1": true}
  }
}
```

If generation or aspect validation fails, report `validation.passed: false`
with notes. Never present a screen reference as a worker-consumable asset.
