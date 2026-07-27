---
name: character-bundle
description: Produce one standalone character or skin SpriteFrames resource from a canonical reference and explicitly timed action frames.
---

# Character Bundle

Use this skill for a player character, enemy, NPC, summon, boss, or other
recurring creature identity. It produces one `SpriteFrames` resource for one
actor or skin, containing every required named body action.

Read `.godotmaker/asset-runtime/asset-skill-contract.md` before accepting a request. First
validate the shared request/result shape with
`tools/asset_skill_contract_check.py`, then validate this family contract with
`tools/asset_animated_bundle_contract_check.py --kind request`. For final
runtime handoff, call the same checker with `--request <request.json> --result
<result.json>`; a result-only check cannot prove it belongs to this request.
Final handoff accepts only `validation.passed: true` with explicit passing
`L0` through `L4` evidence.
The family checker is the callable enforcement for the `spec` rules below; the
shared checker alone intentionally validates only cross-family shape.

## Standalone boundary

Accept only an asset request. Do not read or require `/gm-asset`, tags, stage
state, `ASSETS.md`, generated manifests, stable entries, worker dispatch, or
any other registration state. Return the shared asset result directly; a caller
may register it separately.

## Request and action contract

The request has `asset_type: "character-bundle"`. Its `spec` must contain:

- `required_actions`: a non-empty, duplicate-free ordered list of action names.
- `actions`: one object for each required action, with exactly the same names.
- Each action has `name`, `frame_names`, `fps`, `loop`, and
  `frame_durations`. `fps` and every relative duration are positive; durations
  have exactly one value per frame; `loop` is an explicit boolean.

The ordered `frame_names` define frame order. Never infer timing, reverse an
action, or default `loop` to `true`. Reject a request when an action is missing,
duplicated, unexpected, has no frames, or has timing that does not match its
frames.

`references` may include a `canonical` reference. When it exists, make it
visible before producing derivative actions and preserve the identity, costume,
palette, body scale, and feet/bottom anchor. Otherwise create and return a
canonical reference source before deriving actions. Detached projectiles,
slashes, muzzle flashes, dust, auras, pickups, and impacts are FX and belong to
the `fx-bundle` skill.

## Produce

1. Create or finalize one readable full-body canonical identity source with a
   stable silhouette and no text or UI.
2. Generate one body-action source per required action. Use the same character
   identity and an exact requested grid; do not mix detached FX into the body
   sheet.
3. Process every action with `tools/asset_action_process.py` using `kind: body`.
   Supply the action name, exact grid and frame names, explicit FPS, explicit
   loop flag, and one relative duration per frame. Use a stable family/asset
   output directory for all normalized PNG frames.
4. Pass the processed frame paths and this public request to
   `build_spriteframes_spec()` from
   `tools/asset_animated_bundle_contract_check.py`. Compile the resulting
   complete action set once through the shared `grid_sheet` to `SpriteFrames`
   route. The compiler input contains `required_actions` and action objects with
   `name`, `fps`, `loop`, `frame_paths`, and `frame_durations`.
   Do not publish a per-action SpriteFrames resource or a source sheet as the
   runtime result.
5. Run `standalone_validation.compile_and_validate()` for L0-L4 validation.
   It derives each processed frame path as
   `res://assets/generated/character-bundle/<asset_id>/<asset_id>_<action>_<frame>.png`,
   compiles with a fresh registry, and overwrites rather than trusting result
   validation. L3 must load the compiled resource with headless
   Godot; L4 must confirm the action names, order, frame bindings, FPS, loop
   values, and relative durations.

## Result

Return a shared result with at least one runtime output:

```json
{
  "asset_type": "character-bundle",
  "outputs": [
    {
      "role": "runtime",
      "name": "player",
      "path": "res://assets/generated/character-bundle/player/player.tres",
      "godot_type": "SpriteFrames"
    }
  ],
  "sources": [
    { "path": "res://assets/generated/character-bundle/player/player_idle_sheet.png", "layout": "grid_sheet" }
  ],
  "previews": [],
  "validation": { "passed": true, "levels": { "L0": true, "L1": true, "L2": true, "L3": true, "L4": true } }
}
```

Set `validation.passed` only from the runner result after all required actions
and L0-L4 checks pass.
When any action is incomplete, do not return a runtime `SpriteFrames` result.
