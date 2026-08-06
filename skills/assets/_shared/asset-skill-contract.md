# Asset Skill Contract

The single source of truth for how any first-class asset skill is invoked and
what it returns. Every asset skill under `skills/assets/<family>/` accepts an
**asset request** and returns an **asset result** that matches this contract,
regardless of who calls it.

A user may invoke an asset skill directly. `/gm-asset` invokes the same skill in
exactly the same way. The calling manager handles any project registration and
stage-state updates. There is no separate "gm mode" inside an asset skill.

## Independence

An asset skill knows nothing about the project pipeline. Neither the request nor
the result may carry, and the skill must not read:

- `/gm-asset` or any pipeline orchestration;
- tags, stage state, or `ROADMAP.md`;
- `ASSETS.md`;
- `assets/manifest.json` or `.godotmaker/asset-generation/manifest.json`;
- manifest registration, stable entries, or worker dispatch.

Registration concepts — `tag`, `stage`, `manifest_entry`, and any index or
worker-handoff data — never belong to this contract. The schemas set
`additionalProperties: false`, so leaked pipeline fields fail closed.

## Files

| File | Role |
|---|---|
| `schema/asset-skill-request.schema.json` | Canonical declarative schema for the request |
| `schema/asset-skill-result.schema.json` | Canonical declarative schema for the result |
| `samples/request/*.json` | Valid request examples |
| `samples/result/*.json` | Valid result examples |
| `tools/asset_skill_contract_check.py` | Dependency-free enforcement of the same rules (runtime L0 + CI) |

The JSON Schema files are the canonical declarative contract. The checker is a
dependency-free implementation of the identical rules so validation can run at
runtime (schema/L0) inside a game project without a `jsonschema` dependency. The
two are semantically equivalent — a document is accepted by the JSON Schema if
and only if it is accepted by the checker. A bidirectional parity test enforces
this on a shared battery of valid and invalid documents. The checker fails
closed: any malformed input — including a wrong JSON type on an enum field —
becomes a single `AssetContractError`, never an uncaught exception.

These rules go beyond plain field structure, and both enforcers encode them:

- every required string is non-empty after trimming whitespace (a whitespace-only
  value is rejected);
- an optional field is either omitted or a value of its declared type — an
  explicit `null` is a wrong-typed value and is rejected, not treated as absent;
- a runtime output `path` must be `res://` followed by a relative resource path
  of one or more non-empty segments, and no segment may be `.` or `..`. Bare
  `res://`, `res:///`, `res://.`, and `res://../outside.tres` are all rejected.

`_shared/` holds cross-skill contract material only. It has no `SKILL.md` and is
not independently triggerable.

## Request

```json
{
  "asset_type": "character-bundle",
  "asset_id": "player",
  "brief": "A small hand-painted knight with idle and run actions, side view; do not use pixel art.",
  "references": [
    { "role": "canonical", "path": "res://references/player_canonical.png" }
  ],
  "provider": "native",
  "spec": {}
}
```

| Field | Required | Type | Rule |
|---|---|---|---|
| `asset_type` | yes | string | One of the known production families (see below) |
| `asset_id` | yes | string | Stable logical id, `^[a-z0-9][a-z0-9_-]*$` |
| `brief` | yes | string | Non-empty natural-language description of the asset to produce |
| `references` | no | array | Visible reference images; each `{ role, path }` |
| `provider` | no | string | Image provider hint: `native`, `codex`, `gemini`, `openai` |
| `spec` | no | object | Family-specific structured parameters; inner shape owned by each family skill |

`references[].role` is one of `canonical`, `style`, `screen`. `references[].path`
is a non-empty string.

## Result

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
    {
      "path": "res://assets/generated/character-bundle/player/player.png",
      "layout": "grid_sheet"
    }
  ],
  "previews": [],
  "validation": { "passed": true }
}
```

The result stably contains `asset_type`, `outputs`, `sources`, `previews`, and
`validation`. All five keys are always present; `sources` and `previews` may be
empty arrays.

### outputs

When `validation.passed` is `true`, `outputs` has at least one entry. A failed
result (`validation.passed: false`) may use an empty `outputs` array to state
that no usable asset was produced. One successful invocation may return
multiple logical outputs (for example a `Theme` plus a `StyleBoxTexture`, or
several actors). The request declares every logical output before production;
`/gm-asset` atomically records the validated outputs directly in their matching
`ASSETS.md` rows.

| Field | Required | Type | Rule |
|---|---|---|---|
| `role` | yes | string | `runtime` or `reference` |
| `path` | yes | string | Non-empty; a `runtime` path must be `res://` followed by a relative resource path with no `.`/`..` segment (bare `res://`, `res:///`, `res://.`, `res://../x` are rejected) |
| `godot_type` | runtime only | string | Godot ClassDB type, `^[A-Z][A-Za-z0-9]+$` (open, not a closed enum) |
| `name` | no | string | Optional logical label to disambiguate multiple outputs |

- `runtime` outputs are worker-consumable native Godot resources. `godot_type` is
  a Godot ClassDB type name (`SpriteFrames`, `AtlasTexture`, `Theme`,
  `StyleBoxTexture`, `TileSet`, `Texture2D`, …); it is validated for shape, not
  against a closed list.
- `reference` outputs are visual references such as a screen reference. They are
  not handed to workers as runtime game assets and do not require a `godot_type`.

### sources

Raw generated or claimed source images the outputs were compiled from. Each
entry is `{ path, layout? }`. `layout` describes pixel organization and is one of
`single`, `grid_sheet`, `region_atlas`, `action_frames`, `theme_recipe`,
`tile_atlas`. `sources` may be empty only when the family contract has no raw
source to preserve; a generated screen reference records its deterministic raw
provider source.

### previews

Optional preview or inspection images, each `{ path, label? }`. Previews are for
human or later curation review, never a runtime handoff. `previews` may be empty.

### validation

`{ passed: bool, levels?, notes? }`. `levels` is an optional map of `L0`–`L5`
booleans. When `passed` is `true` and `levels` is present, every provided level
must be `true` — a passed result may not report a failed level.

## Production families

`asset_type` is one of:

`background-map`, `character-bundle`, `fx-bundle`, `ui-kit`, `card-kit`,
`compact-prop-pack`, `platform-strip`, `scene-prop-set`, `screen-reference`,
`tileset`.
