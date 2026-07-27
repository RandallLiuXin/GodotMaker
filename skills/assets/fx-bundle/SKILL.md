---
name: fx-bundle
description: Produce a standalone static Texture2D effect or one explicitly timed animated SpriteFrames effect.
---

# FX Bundle

Use this skill for a projectile, impact, explosion, pickup, muzzle flash, slash
arc, aura loop, dust, or another detached foreground effect. A request produces
either one static `Texture2D` effect or one independently animated
`SpriteFrames` effect.

Read `.godotmaker/asset-runtime/asset-skill-contract.md` before accepting a request. First
validate the shared request/result shape with
`tools/asset_skill_contract_check.py`, then validate this family contract with
`tools/asset_animated_bundle_contract_check.py --kind request`. For final
runtime handoff, call the same checker with `--request <request.json> --result
<result.json>`; this is required to bind `spec.mode` to the output type and
source layout. Final handoff accepts only `validation.passed: true` with
explicit passing `L0` through `L4` evidence. The family checker is the callable
enforcement for the `spec` rules below; the shared checker alone intentionally
validates only cross-family shape.

## Standalone boundary

Accept only an asset request. Do not read or require `/gm-asset`, tags, stage
state, `ASSETS.md`, generated manifests, stable entries, worker dispatch, or
any other registration state. Return the shared asset result directly; a caller
may register it separately.

## Request contract

The request has `asset_type: "fx-bundle"` and `spec.mode` equal to either
`static` or `animated`.

- `static` has one transparent foreground image and no animation contract. It
  returns a `Texture2D` at the image path.
- `animated` has `required_actions` containing exactly one name and exactly one
  action with the same name. The action has non-empty ordered `frame_names`,
  positive `fps`, an explicit boolean `loop`, and one positive relative duration
  per frame. Its action name is both required and the sole `SpriteFrames`
  animation name.

Reject mixed static/animated requests, an animated effect with zero or multiple
actions, missing frames, duplicate frame names, non-positive FPS or durations,
or a duration count that differs from the frame count. Never infer timing or
hard-code loop state.

## Produce

1. State the effect identity, gameplay role, direction, scale, and either one
   image or the exact requested animation frame count. Keep the foreground effect
   separate on a solid `#FF00FF` source background and include no text or UI.
2. For an animated effect, process the source with
   `tools/asset_action_process.py` using `kind: fx`, the explicit action name,
   grid, frame names, FPS, loop flag, and frame durations. Use center alignment
   for floating effects, projectiles, and detached FX.
3. Pass the processed frame paths and this public request to
   `build_spriteframes_spec()` from
   `tools/asset_animated_bundle_contract_check.py`. Compile that one action
   through the shared `grid_sheet` to `SpriteFrames` route. Its compiler input
   has `required_actions` plus the action `name`, `fps`, `loop`, `frame_paths`,
   and `frame_durations`. Validate L0-L4, including headless Godot load and L4
   frame order, texture bindings, FPS, loop, and durations. Use
   `standalone_validation.compile_and_validate()` to perform that work; it
   derives stable processed frame paths using `<asset_id>_<action>_<frame>.png`
   and overwrites any supplied validation assertion.
4. For a static effect, process/select exactly one transparent foreground PNG
   and publish it through the shared `single` to `Texture2D` route. Validate
   its L0-L4 texture evidence.

Do not use a source sheet as the runtime effect. Do not generate a
`PackedScene`, particle node, shader, sound, light, or lifecycle script. Those
are consumer responsibilities; this skill supplies only a texture or
SpriteFrames resource.

## Results

An animated result has one `SpriteFrames` runtime output:

```json
{
  "asset_type": "fx-bundle",
  "outputs": [{ "role": "runtime", "name": "impact", "path": "res://assets/generated/fx-bundle/impact/impact.tres", "godot_type": "SpriteFrames" }],
  "sources": [{ "path": "res://assets/generated/fx-bundle/impact/impact_sheet.png", "layout": "grid_sheet" }],
  "previews": [],
  "validation": { "passed": true, "levels": { "L0": true, "L1": true, "L2": true, "L3": true, "L4": true } }
}
```

A static result has one `Texture2D` runtime output whose path is the selected
single image and whose source layout is `single`. Set `validation.passed` only
from the standalone runner after the applicable L0-L4 checks pass.
