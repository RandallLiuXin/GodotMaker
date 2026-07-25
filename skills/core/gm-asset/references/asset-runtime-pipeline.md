# Asset Runtime Pipeline Reference

Use this file for common paths, manager-to-producer handoff, and stable-entry
registration. Use production-unit docs for prompts, finalization, extraction,
processing, and curation commands.

## Fixed Paths

For each generated visual production unit, reserve:

1. Raw provider output under `.godotmaker/asset-generation/sources/`.
2. Replaced raw output under `.godotmaker/asset-generation/sources/history/`.
3. Prompt files under `.godotmaker/asset-generation/prompts/`.
4. Reports under `.godotmaker/asset-generation/reports/`.
5. Curation reports under `.godotmaker/asset-generation/curation/`.
6. Processed previews and derived files under
   `.godotmaker/asset-generation/processed/`.
7. Stable entry drafts under `.godotmaker/asset-generation/work/entries/`.
8. Registered stable entries under
   `.godotmaker/asset-generation/entries/<tag>/<asset_id>.json`.
9. The root index at `.godotmaker/asset-generation/manifest.json`.
10. Worker-consumable runtime outputs under
    `assets/generated/<production_family>/<asset_id>/`.
11. Scene references under `references/`.

Everything under `.godotmaker/asset-generation/` is generation scratch. No
registered entry may point into it — not the raw source, not the processed
preview, not the work directory. A registered path is always under the asset's
stable output directory, so a non-reference production unit finishes by writing
its finalized image there.

## Provider Docs

Use exactly one provider doc per production unit:

1. `references/providers/native.md`
2. `references/providers/codex.md`
3. `references/providers/gemini.md`
4. `references/providers/openai.md`

## Production Families

`production_family` is the stable identity of the producing unit and picks the
output directory. Allowed values:

`background-map`, `character-bundle`, `fx-bundle`, `ui-kit`, `card-kit`,
`compact-prop-pack`, `platform-strip`, `scene-prop-set`, `screen-reference`,
`tileset`.

`screen-reference` is the only reference-only family.

## Stable Output Paths

Every worker-consumable file for one asset — the runtime image, the Godot
artifact, and required support files such as region or action metadata — lives
under one identity-derived directory:

```text
assets/generated/<production_family>/<asset_id>/
```

Print and validate it with:

```bash
python tools/asset_output_path.py --family <production_family> --asset-id <asset_id>
```

Regeneration overwrites the same directory in place. A timestamped, `v2`, or
`final` drift path is rejected. Reference-only assets keep their `references/`
location and never write into this tree.

## Source Layouts

`source_layout.type` describes how pixels are organized in the generated source.
It is not a Godot artifact.

| Type | Use for |
|------|---------|
| `single` | One runtime image: background, panel, portrait, large prop |
| `grid_sheet` | Equal-cell sheet for animation frames, FX, or fixed cells |
| `region_atlas` | Irregular UI, icon, prop, strip, or tileset atlas |
| `theme_recipe` | UI theme description compiled into a `Theme` |
| `tile_atlas` | Tileset source compiled into a `TileSet` |
| `reference` | Screen and style references; `screen-reference` family only |

## Processing Status

`processing_status` maps to the L0-L4 readiness ladder:

1. `pending` — L0 only; nothing produced yet.
2. `source_ready` — L1 source generation and processing succeeded.
3. `compiled` — L2 native Godot artifact compiled, not yet L3-L4 verified.
4. `ready` — L0-L4 all passed; worker-consumable.
5. `failed` — a stage failed.

`compiled` and `ready` require a `godot_artifact` for every non-reference asset.

**Current pipeline state.** The native compilers and the L0-L4 runner are not
implemented. `/gm-asset` therefore registers `source_ready` entries and nothing
further. Do not write `compiled` or `ready`, and do not invent a `godot_artifact`
to reach them: a generated asset is not worker-consumable yet, and claiming
otherwise hands `/gm-build` an asset that was never compiled or verified.

## Stable Entry Contract

One stable entry is the single source of truth for one generated asset. It holds
stable identity plus the minimal contract a worker needs, and nothing else:

```json
{
  "version": 1,
  "asset_id": "<asset_id>",
  "tag": "<tag>",
  "production_family": "character-bundle",
  "source_layout": {
    "type": "grid_sheet",
    "path": "res://assets/generated/character-bundle/<asset_id>/<asset_id>_sheet.png"
  },
  "processing_status": "source_ready"
}
```

Rules:

1. `source_layout` holds exactly `type` and `path`.
2. `godot_artifact` holds exactly `type` and `path`. `type` is a Godot ClassDB
   identifier the native compiler may produce for this layout. The table is a
   closed compatibility set, not permission to use any ClassDB type:

   | `source_layout.type` | Allowed `godot_artifact.type` |
   |---|---|
   | `single` | `Texture2D` or `StyleBoxTexture` |
   | `grid_sheet` | `SpriteFrames` |
   | `region_atlas` | `AtlasTexture` or `StyleBoxTexture` |
   | `theme_recipe` | `Theme` |
   | `tile_atlas` | `TileSet` |
   | `reference` | no `godot_artifact` |

3. Both paths are `res://` paths under the asset's stable output directory. A
   path under `.godotmaker/` is rejected, so finalize into the stable directory
   before drafting the entry.
4. Only a native compiler writes `godot_artifact`. Never point it at the source
   image to make an asset look finished — a `grid_sheet` is not a `SpriteFrames`
   just because its sheet exists, and a worker that loads it gets a static image
   where an animation was promised. No compiler exists yet, so entries stay at
   `source_ready` with no `godot_artifact`.
5. A `reference` layout carries no `godot_artifact` and keeps its `references/`
   location.
6. Detailed runtime metadata (region rects, frame lists) is a support file beside
   the artifact, never an entry field.
7. No other field is allowed. Regenerate through `/gm-asset` instead of adding
   one.

## Root Index

`.godotmaker/asset-generation/manifest.json` is a pointer-only index. It stores
identity and one `entry_path` per asset and never duplicates an entry body:

```json
{
  "version": 1,
  "entries": [
    {
      "asset_id": "<asset_id>",
      "tag": "<tag>",
      "entry_path": ".godotmaker/asset-generation/entries/<tag>/<asset_id>.json"
    }
  ]
}
```

Consumers resolve `entry_path` and read the entry. Nothing reads runtime data
straight from the root index.

## Runtime Snapshot Resolution

The resolver is the deterministic reader for one registered runtime asset. It
does not by itself change the published worker-dispatch brief format; that
integration remains a follow-up for WOR-233 because this v1 entry exposes only
the four-field runtime contract, while the existing brief also requires target
size, support metadata, frame data, and cwd-relative paths.

Resolve the current-tag ASSETS.md row:

```bash
python tools/asset_runtime_resolver.py \
  --project-root . \
  --assets-md ASSETS.md \
  --tag <tag> \
  --asset-id <asset_id>
```

or provide its canonical pointer directly:

```bash
python tools/asset_runtime_resolver.py \
  --project-root . \
  --manifest-entry .godotmaker/asset-generation/entries/<tag>/<asset_id>.json
```

Both modes require the project-root ASSETS.md row to be `generated` and point to
the same entry. The resolver also verifies the canonical pointer, root-index
registration, entry identity, v1 schema, `ready` status, and source/artifact
file existence. It emits only `asset_id`, `production_family`, `source_layout`,
and `godot_artifact`, in that order. Reference-only entries are valid manifest
records but never produce a worker runtime snapshot.

## Registration Commands

Build the entry draft with the deterministic builder for the production path.
Every production path has one; do not hand-write a draft or its support metadata.
The builders are what enforce frame count, edge-touch rejection, scale reference,
curation selection, aspect validation, and stable-path containment.

Processed action output (`character-bundle`, `fx-bundle`):

```bash
python tools/asset_action_entry_draft.py \
  --metadata <processed_dir>/pipeline-meta.json \
  --asset-id <asset_id> --tag <tag> --production-family <production_family> \
  --project-root . \
  --out .godotmaker/asset-generation/work/entries/<asset_id>.json
```

It also writes the action support metadata to
`assets/generated/<production_family>/<asset_id>/<asset_id>.json`.

Selected curation candidate (`ui-kit`, `card-kit`, `compact-prop-pack`,
`scene-prop-set`, `platform-strip`):

```bash
python tools/asset_curation_entry_draft.py \
  --report <curation_report.json> --candidate <candidate_id_or_name> \
  --asset-id <asset_id> --tag <tag> --production-family <production_family> \
  --project-root . \
  --out .godotmaker/asset-generation/work/entries/<asset_id>.json
```

One finalized image (`screen-reference`, `background-map`, and single card or
portrait frames):

```bash
python tools/asset_finalize_entry_draft.py \
  --finalize-report <finalize_report.json> \
  --asset-id <asset_id> --tag <tag> --production-family <production_family> \
  --project-root . \
  --out .godotmaker/asset-generation/work/entries/<asset_id>.json
```

Capture the report by redirecting `asset_image_finalize.py` stdout. The builder
requires that run to have succeeded with `--require-aspect` inside tolerance and
`--label <asset_id>`. It derives the layout from the family — `reference` pinned
to `references/` for `screen-reference`, `single` pinned to the stable output
directory for every other family.

Write one validated entry to its canonical path:

```bash
python tools/asset_stable_entry.py <entry_draft.json> --project-root . --write --check-files
```

Upsert its pointer into the root index:

```bash
python tools/asset_generation_index.py --project-root . \
  --entry-file .godotmaker/asset-generation/entries/<tag>/<asset_id>.json
```

Validate the whole index, every referenced entry, and every handoff file:

```bash
python tools/asset_generation_index.py --project-root . --check-entries --check-files
```

`--check-entries` alone is a schema-only pass. `--check-files` additionally proves
every registered `source_layout.path` and `godot_artifact.path` is still on disk,
so it catches an asset deleted after registration. That pair is the registration
gate; it is not a readiness gate and does not check support files or compiled
output, because neither the compilers nor the L0-L4 runner exist yet.

Producer reports list stable entry drafts. The manager writes each entry, upserts
its pointer, and runs the root-index gate before updating ASSETS.md.

Update matching ASSETS.md rows with:

```bash
python tools/asset_assets_md_update.py \
  --entry-file .godotmaker/asset-generation/entries/<tag>/<asset_id>.json
```

The updater promotes a runtime row to `generated` only for a `ready`
non-reference entry. A `screen-reference` row may become `generated` at
`source_ready` or `ready` with a finalized reference file, canonical stable
entry, and root-index pointer. It schema-validates index pointers and validates
the selected reference file. Do not create a `godot_artifact`, worker handoff,
or hand-edited ASSETS.md status for a reference. Keep all other `source_ready`
entries `MISSING`.

Register entries for new current-tag assets. Preserve prior entries unless the
same current-tag asset is being regenerated.

## Curation

Curation is a production step, not an entry field. Keep candidate selection,
strategy, and rejection detail in the curation report under
`.godotmaker/asset-generation/curation/`. See `references/asset-curation.md` for
the record shape and allowed states.

Register a stable entry only after curation selected the final artifact. An
unresolved curation leaves the asset unregistered and its ASSETS.md row
`MISSING`.

## Runtime Ready Gate

An asset is worker-consumable only when its entry is `ready`, which requires all
of:

1. The root index points at the entry and
   `asset_generation_index.py --check-entries --check-files` passes.
2. A native compiler produced the `godot_artifact` for the entry's
   `source_layout.type`, and that file exists under the stable output directory.
3. Required support files (region metadata, action metadata) exist beside the
   artifact.
4. The L0-L4 runner verified the asset.

Steps 2 and 4 are not implemented. **No generated asset can reach `ready` today**,
so `/gm-build` and worker dispatch currently receive no generated runtime assets.
Registration, stable paths, and the pointer index are what this stage delivers;
compilation and verification arrive with the compiler work.

Compiler target compatibility by source layout, for when that work lands:

1. `single`: `Texture2D`, no support file; or `StyleBoxTexture`.
2. `grid_sheet`: `SpriteFrames`, with action metadata beside the artifact.
3. `region_atlas`: `AtlasTexture` or `StyleBoxTexture`, with atlas metadata beside the artifact.
4. `theme_recipe`: `Theme`. `tile_atlas`: `TileSet`.
5. `reference`: no artifact; complete a reference-type ASSETS row only.

Support files are named after the asset and live beside the artifact:

```text
assets/generated/<production_family>/<asset_id>/<asset_id>.json
```

That fixed name is the only support-metadata path a consumer needs, which is why
the entry does not carry it. Keep detailed runtime metadata there, never in the
entry and never in ASSETS.md.

Atlas metadata shape (`assets/generated/ui-kit/main_atlas/main_atlas.json`):

```json
{
  "version": 1,
  "atlas_path": "res://assets/generated/ui-kit/main_atlas/main_atlas.png",
  "regions": [
    {
      "name": "battle_button",
      "rect": [0, 0, 256, 96],
      "pivot": [0.5, 0.5],
      "nine_slice": null
    }
  ]
}
```

Build that physical atlas and its metadata only from an explicit fixed-slot
declaration. The assembler does not pack, trim, or discover regions:

```json
{
  "version": 1,
  "atlas": {"width": 512, "height": 256},
  "slots": [
    {
      "name": "battle_button",
      "rect": [0, 0, 256, 96],
      "source": "battle_button.png",
      "pivot": [0.5, 0.5]
    }
  ]
}
```

```bash
python tools/asset_atlas_assemble.py \
  --declaration <fixed_slots.json> \
  --atlas-out assets/generated/ui-kit/main_atlas/main_atlas.png \
  --metadata-out assets/generated/ui-kit/main_atlas/main_atlas.json \
  --family ui-kit \
  --asset-id main_atlas \
  --project-root .
```

Every source must be a PNG with exactly the declared slot size. Out-of-bounds,
overlapping, missing, or malformed slots fail before either output is written.
Source paths are project-root relative, as are all other asset-tool inputs.
Both outputs must be under the declared asset's stable directory and are
committed together; a write failure restores any prior output pair. The emitted
regions are ordered by name for stable metadata, with `nine_slice: null` because
nine-slice behavior is outside this tool.

Action metadata shape (`assets/generated/character-bundle/player/player.json`):

```json
{
  "version": 1,
  "sheet_path": "res://assets/generated/character-bundle/player/player_sheet.png",
  "frame_count": 4,
  "frame_paths": [
    "res://assets/generated/character-bundle/player/player_idle_01.png"
  ],
  "align": "feet",
  "shared_scale": true,
  "edge_touch_frames": []
}
```

## Production Unit Plan Shape

Use this shape for manager-to-producer handoff:

```json
{
  "unit_id": "<unit_id>",
  "unit_doc": "references/production-units/<unit>.md",
  "provider_doc": "references/providers/<provider>.md",
  "provider": "<asset_image_model>",
  "dependencies": [],
  "items": [
    {
      "asset_id": "<asset_id>",
      "production_family": "<production_family>",
      "source_layout_type": "<single|grid_sheet|region_atlas|theme_recipe|tile_atlas|reference>",
      "target_size": "<WIDTHxHEIGHT or null>",
      "target_aspect": "<WIDTH:HEIGHT or null>",
      "prompt_path": ".godotmaker/asset-generation/prompts/<asset_id>.txt",
      "raw_source_path": ".godotmaker/asset-generation/sources/<asset_id>_source.png",
      "output_dir": "assets/generated/<production_family>/<asset_id>/",
      "entry_draft_path": ".godotmaker/asset-generation/work/entries/<asset_id>.json"
    }
  ],
  "report_path": ".godotmaker/asset-generation/reports/<unit_id>.json"
}
```

## Report Shape

Each production unit writes one report:

```json
{
  "ok": true,
  "unit_id": "<unit_id>",
  "provider": "<asset_image_model>",
  "status": "done",
  "sequential_fallback_reason": null,
  "sources": [],
  "outputs": [],
  "prompts": [],
  "entry_drafts": [],
  "curation_reports": [],
  "failures": []
}
```
